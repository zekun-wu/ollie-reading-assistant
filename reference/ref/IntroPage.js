import React from 'react';
import './IntroPage.css';

const IntroPage = ({ onContinue, onBack }) => {
  const assistantName = 'Ollie';
  const [step, setStep] = React.useState('askName'); // askName -> final
  const [childName, setChildName] = React.useState('');
  const [currentText, setCurrentText] = React.useState(`Hi! My name is ${assistantName}. I'm your reading friend today. Could you tell me what is your name?`);
  const [currentLang, setCurrentLang] = React.useState('en-US');

  const [audioUrl, setAudioUrl] = React.useState(null);
  const [audioDone, setAudioDone] = React.useState(false);
  const [typedText, setTypedText] = React.useState('');
  const [typingDone, setTypingDone] = React.useState(false);
  // Sync mode ensures we don't start typing until we commit to audio fallback
  const [syncMode, setSyncMode] = React.useState('pending'); // 'pending' | 'audio' | 'typing'
  // Warm-up animation to buy time for TTS
  const [showWarmup, setShowWarmup] = React.useState(true);
  const [dots, setDots] = React.useState('');
  const audioRef = React.useRef(null);

  React.useEffect(() => {
    // Only run independent typing when we've decided to not use audio
    if (syncMode !== 'typing') return;
    let idx = 0;
    const speedMs = 22;
    const t = setInterval(() => {
      idx += 1;
      setTypedText(currentText.slice(0, idx));
      if (idx >= currentText.length) {
        clearInterval(t);
        setTypingDone(true);
      }
    }, speedMs);
    return () => clearInterval(t);
  }, [currentText, syncMode]);

  // Pending animation: cycle dots while waiting for TTS decision
  React.useEffect(() => {
    if (syncMode !== 'pending') { setDots(''); return; }
    let i = 0;
    const timer = setInterval(() => {
      i = (i + 1) % 4;
      setDots('.'.repeat(i));
    }, 350);
    return () => clearInterval(timer);
  }, [syncMode]);

  React.useEffect(() => {
    const speak = async () => {
      try {
        const fd = new FormData();
        fd.append('text', currentText);
        fd.append('language', currentLang);
        const voiceMap = { 'en-US': 'en-US-AnaNeural', 'de-DE': 'de-DE-KatjaNeural' };
        fd.append('voice', voiceMap[currentLang] || 'en-US-AnaNeural');
        const resp = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
        if (resp.ok) {
          const data = await resp.json();
          setAudioUrl(`http://localhost:8001${data.audio_url}`);
          setSyncMode('audio');
        } else {
          setSyncMode('typing');
        }
      } catch {
        setSyncMode('typing');
      }
    };
    // Reset state for new utterance; defer text until we know mode
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

  return (
    <div className="intro-page">
      <div className="intro-upload-top">
        <button className="intro-upload-btn" onClick={onBack}>← Back</button>
      </div>
      <div className="intro-card">
        <div className="assistant-stage">
          <img src="http://localhost:8001/assistant/hi.png" alt="assistant says hi" className="intro-assistant chat-bob" />
          <div className="chat-bubble">
            <span className="typed-text">
              { (showWarmup || syncMode === 'pending') ? dots : typedText }
            </span>
            {syncMode === 'typing' && !typingDone && !(showWarmup || syncMode === 'pending') && <span className="cursor">|</span>}
            {allowNameInput && (
              <div className="intro-form">
                <input
                  className="intro-input"
                  type="text"
                  value={childName}
                  onChange={(e) => setChildName(e.target.value)}
                  placeholder="Type your name here"
                />
                <button
                  className="intro-confirm"
                  disabled={!childName.trim()}
                  onClick={() => {
                    const name = childName.trim();
                    const nextText = `Nice to meet you, ${name}! I'm so excited to be your picture-buddy today. Let's start our reading adventure!`;
                    setStep('final');
                    setCurrentText(nextText);
                  }}
                >
                  That's my name
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="intro-actions">
          {!canStart && (
            <button className="intro-skip" onClick={() => onContinue('Guest')}>Skip</button>
          )}
          {canStart && (
            <button className="intro-continue" onClick={() => onContinue(childName.trim())}>Start Reading</button>
          )}
        </div>
      </div>
      {syncMode === 'audio' && audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          autoPlay
          onTimeUpdate={() => {
            try {
              const el = audioRef.current;
              if (!el || !el.duration || el.duration <= 0) return;
              const frac = Math.max(0, Math.min(1, el.currentTime / el.duration));
              const chars = Math.floor(frac * currentText.length);
              setTypedText(currentText.slice(0, chars));
              if (chars >= currentText.length) setTypingDone(true);
            } catch {}
          }}
          onEnded={() => {
            setTypedText(currentText);
            setTypingDone(true);
            setAudioDone(true);
          }}
        />
      )}
    </div>
  );
};

export default IntroPage;


