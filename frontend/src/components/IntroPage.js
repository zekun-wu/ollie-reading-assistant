import React, { useState, useEffect, useRef } from 'react';
import './IntroPage.css';

const IntroPage = ({ onContinue, onBack, config, language = 'de' }) => {
  const assistantName = 'Ollie';
  
  // German translations for all steps
  const t = {
    askName: `Hi! Mein Name ist ${assistantName}. Ich bin heute dein Lese-Freund. Könntest du mir sagen, was dein Name ist?`,
    askAge: (name) => `Nett dich kennenzulernen, ${name}! Wie alt bist du?`,
    ack: "Ich freue mich heute dein Bilder-Freund zu sein.",
    help1: "Ich helfe dir heute auf verschiedenen Wegen, während du liest.",
    help2: "Manchmal suche ich einen kleinen Teil des Bildes aus und erzähle dir etwas spaßiges darüber.",
    help3: "Und manchmal erkenne ich, was du dir anschaust und teile etwas mit, womit du es in einem anderen Licht siehst.",
    final: "Lass uns unser Lese-Abenteuer starten!",
    inputName: "Bitte gib deinen Namen ein!",
    inputAge: "Bitte gib dein Alter ein!",
    namePlaceholder: "Gib hier deinen Namen ein",
    agePlaceholder: "Gib hier dein Alter ein",
    nameButton: "Das ist mein Name",
    ageButton: "Das ist mein Alter",
    skipButton: "Einführung überspringen",
    startButton: "Lesen starten",
    speaking: "Ollie spricht"
  };
  
  const ttsLang = 'de-DE';
  
  const [step, setStep] = useState('askName'); // askName -> askAge -> ack -> help1 -> help2 -> help3 -> final
  const [childName, setChildName] = useState('');
  const [childAge, setChildAge] = useState('');
  const [currentText, setCurrentText] = useState(t.askName);
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
    const timer = setTimeout(() => {
      setTypingDone(true);
    }, delay);
    return () => clearTimeout(timer);
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
        
        
        
        // Use Azure TTS for intro voice
        const response = await fetch(`${(process.env.REACT_APP_API_URL || '')}/api/manual-assistance/tts/waiting`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: `text=${encodeURIComponent(currentText)}&image_name=intro&activity=intro&language=de`
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
  }, [currentText, currentLang]);

  const progressDone = () => (syncMode === 'audio' ? audioDone : (syncMode === 'typing' ? typingDone : false));
  const canStart = step === 'final' ? progressDone() : false;
  const allowNameInput = step === 'askName' && progressDone();
  const allowAgeInput = step === 'askAge' && progressDone();

  // Keyboard shortcuts: Enter to continue (final), or submit name during askName
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Enter') {
        if (canStart) {
          e.preventDefault();
          onContinue((childName || 'Guest').trim(), (childAge || '').trim(), config);
        } else if (step === 'askName' && allowNameInput && childName.trim()) {
          e.preventDefault();
          const name = childName.trim();
          setAudioDone(false);
          setTypingDone(false);
          setSyncMode('pending');
          setStep('askAge');
          setCurrentText(t.askAge(name));
        } else if (step === 'askAge' && allowAgeInput && childAge.trim()) {
          e.preventDefault();
          setAudioDone(false);
          setTypingDone(false);
          setSyncMode('pending');
          setStep('ack');
          setCurrentText(t.ack);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [canStart, step, allowNameInput, allowAgeInput, childName, childAge, config, onContinue, t]);

  // Auto-advance through new intro steps once each voice/text finishes
  useEffect(() => {
    if (!progressDone()) return;
    if (step === 'ack') {
      // 1) Overview with hi.png
      setAudioDone(false); setTypingDone(false); setSyncMode('pending');
      setStep('help1');
      setCurrentText(t.help1);
    } else if (step === 'help1') {
      // 2) Teach a part with teach.png
      setAudioDone(false); setTypingDone(false); setSyncMode('pending');
      setStep('help2');
      setCurrentText(t.help2);
    } else if (step === 'help2') {
      // 3) Eye-aware help with super_read.png
      setAudioDone(false); setTypingDone(false); setSyncMode('pending');
      setStep('help3');
      setCurrentText(t.help3);
    } else if (step === 'help3') {
      // Final CTA
      setAudioDone(false); setTypingDone(false); setSyncMode('pending');
      setStep('final');
      setCurrentText(t.final);
    }
  }, [audioDone, typingDone, step, t]);

  return (
    <div className="intro-page">
      <div className="intro-upload-top">
        <button className="intro-upload-btn" onClick={onBack}>← Zurück</button>
        {!canStart && (
          <button className="intro-upload-btn" onClick={() => onContinue('Guest', '', config)}>
            {t.skipButton}
          </button>
        )}
      </div>
      
      <div className="intro-card">
        <div className="assistant-stage">
          <img 
            src={(function(){
              if (step === 'help2') return `${(process.env.REACT_APP_API_URL || '')}/animated_assistant/teach.png`;
              if (step === 'help3') return `${(process.env.REACT_APP_API_URL || '')}/animated_assistant/super_read.png`;
              return `${(process.env.REACT_APP_API_URL || '')}/animated_assistant/hi.png`;
            })()} 
            alt="Ollie the assistant says hi" 
            className="intro-assistant chat-bob" 
          />
          
          <div className="chat-bubble">
            {/* Always show fixed message for non-input steps, including initial step */}
            {!(allowNameInput || allowAgeInput) && (
              <span className="typed-text" style={{ whiteSpace: 'pre-wrap' }}>
                {t.speaking}
              </span>
            )}
            
            {allowNameInput && (
              <div className="intro-form">
                <div style={{ marginBottom: '10px', fontWeight: '500' }}>
                  {t.inputName}
                </div>
                <input
                  className="intro-input"
                  type="text"
                  value={childName}
                  onChange={(e) => setChildName(e.target.value)}
                  placeholder={t.namePlaceholder}
                  autoFocus
                />
                <button
                  className="intro-confirm"
                  disabled={!childName.trim()}
                  onClick={() => {
                    const name = childName.trim();
                    setAudioDone(false);
                    setTypingDone(false);
                    setSyncMode('pending');
                    setStep('askAge');
                    setCurrentText(t.askAge(name));
                  }}
                >
                  {t.nameButton}
                </button>
              </div>
            )}
            
            {allowAgeInput && (
              <div className="intro-form">
                <div style={{ marginBottom: '10px', fontWeight: '500' }}>
                  {t.inputAge}
                </div>
                <input
                  className="intro-input"
                  type="text"
                  value={childAge}
                  onChange={(e) => setChildAge(e.target.value)}
                  placeholder={t.agePlaceholder}
                  autoFocus
                />
                <button
                  className="intro-confirm"
                  disabled={!childAge.trim()}
                  onClick={() => {
                    setAudioDone(false);
                    setTypingDone(false);
                    setSyncMode('pending');
                    setStep('ack');
                    setCurrentText(t.ack);
                  }}
                >
                  {t.ageButton}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="intro-actions">
          {canStart && (
            <button className="intro-continue" onClick={() => onContinue((childName || 'Guest').trim(), (childAge || '').trim(), config)}>
              {t.startButton}
            </button>
          )}
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

export default IntroPage;
