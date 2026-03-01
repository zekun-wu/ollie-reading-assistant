import React, { useState, useEffect, useRef } from 'react';
import './GroupIntroPage.css';

const GroupIntroPage = ({ groupType, childName, onContinue, language = 'de' }) => {
  const assistantName = 'Ollie';
  
  // Group-specific content (German only) - manual and eye_tracking only
  const groupContent = {
    manual: {
      image: 'teach.png',
      text: `Hi ${childName}! Für die nächsten Bilder suche ich mir kleine Teile der Seite aus und erzähle dir etwas spaßiges darüber. Lass mir dir helfen, neue Sachen zu entdecken!`
    },
    eye_tracking: {
      image: 'super_read.png',
      text: `Hi ${childName}! Für die nächsten Bilder erkenne ich, was du dir anschaust und teile Informationen mit, die dir helfen, es in einem neuen Licht zu sehen. Lass dich von deiner Neugierigkeit leiten!`
    }
  };

  const content = groupContent[groupType] || groupContent.manual;
  const [currentText, setCurrentText] = useState(content.text);
  const ttsLang = 'de-DE';
  const [currentLang, setCurrentLang] = useState(ttsLang);

  const [audioUrl, setAudioUrl] = useState(null);
  const [audioDone, setAudioDone] = useState(false);
  const [typedText, setTypedText] = useState('');
  const [typingDone, setTypingDone] = useState(false);
  const [syncMode, setSyncMode] = useState('pending'); // 'pending' | 'audio' | 'typing'
  const [showWarmup, setShowWarmup] = useState(true);
  const [dots, setDots] = useState('');
  const audioRef = useRef(null);

  useEffect(() => {
    // Only run independent typing when we've decided to not use audio
    // Simplified: just mark as done after delay for fallback (no text display)
    if (syncMode !== 'typing') return;
    const delay = currentText.length * 22; // Approximate delay based on text length
    const t = setTimeout(() => {
      setTypingDone(true);
    }, delay);
    return () => clearTimeout(t);
  }, [currentText, syncMode]);

  // Pending animation: cycle dots while waiting for TTS decision
  useEffect(() => {
    if (syncMode !== 'pending') { setDots(''); return; }
    let i = 0;
    const timer = setInterval(() => {
      i = (i + 1) % 4;
      setDots('.'.repeat(i));
    }, 350);
    return () => clearInterval(timer);
  }, [syncMode]);

  useEffect(() => {
    const speak = async () => {
      try {
        // Stop any currently playing audio first
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current.currentTime = 0;
        }
        
        // Use Azure TTS for group intro voice
        const response = await fetch(`${(process.env.REACT_APP_API_URL || '')}/api/manual-assistance/tts/waiting`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: `text=${encodeURIComponent(currentText)}&image_name=group_intro_${groupType}&activity=intro&language=de`
        });
        
        if (response.ok) {
          const result = await response.json();
          if (result.success && result.audio_url) {
            setAudioUrl(`${(process.env.REACT_APP_API_URL || '')}${result.audio_url}`);
            setSyncMode('audio');
          } else {
            setSyncMode('typing');
          }
        } else {
          setSyncMode('typing');
        }
      } catch (error) {
        setSyncMode('typing');
      }
    };
    
    // Reset state for new utterance
    setTypedText('');
    setTypingDone(false);
    setAudioDone(false);
    setAudioUrl(null);
    setSyncMode('pending');
    setShowWarmup(true);
    
    // End warmup after ~1.2s
    const warm = setTimeout(() => setShowWarmup(false), 1200);
    speak();
    return () => clearTimeout(warm);
  }, [currentText, currentLang, groupType]);

  const progressDone = () => (syncMode === 'audio' ? audioDone : (syncMode === 'typing' ? typingDone : false));

  // Auto-continue when audio/typing finishes
  useEffect(() => {
    if (progressDone()) {
      onContinue();
    }
  }, [audioDone, typingDone, onContinue]);

  return (
    <div className="intro-page">
      <div className="intro-card">
        <div className="assistant-stage">
          <img 
            src={`${(process.env.REACT_APP_API_URL || '')}/animated_assistant/${content.image}`}
            alt="Ollie the assistant"
            className="intro-assistant chat-bob"
          />
          
          <div className="chat-bubble">
            <span className="typed-text" style={{ whiteSpace: 'pre-wrap' }}>
              Ollie spricht
            </span>
          </div>
        </div>
      </div>
      
      {/* Audio playback for TTS */}
      {syncMode === 'audio' && audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          autoPlay
          onTimeUpdate={() => {
            // Simplified: no text syncing needed since we show fixed message
            // Just track completion
            try {
              const el = audioRef.current;
              if (!el || !el.duration || el.duration <= 0) return;
              const frac = Math.max(0, Math.min(1, el.currentTime / el.duration));
              if (frac >= 1) setTypingDone(true);
            } catch {}
          }}
          onEnded={() => {
            // Only set completion flags, no need to update typedText
            setTypingDone(true);
            setAudioDone(true);
          }}
        />
      )}
    </div>
  );
};

export default GroupIntroPage;
