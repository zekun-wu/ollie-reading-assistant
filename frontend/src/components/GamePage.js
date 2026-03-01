import React, { useState, useEffect, useRef, useCallback } from 'react';
import './IntroPage.css'; // Reuse IntroPage styles

/**
 * GamePage - Interactive game session after each image reading
 * Shows assistant with game image, plays audio prompts, offers Continue/End options
 */
const GamePage = ({ 
  imageNumber = 1,  // 1-9, determines which game_X.png to show
  onEnd,            // Called when user ends the game session
  onBack,           // Called to go back (optional)
  language = 'de'
}) => {
  // Phase: 'intro' (playing open+intro), 'buttons' (showing choices), 'continue' (playing praise+next), 'ending' (playing close)
  const [phase, setPhase] = useState('intro');
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(null);
  const audioQueueRef = useRef([]);
  const [continueCount, setContinueCount] = useState(0);

  // German text for game session
  const t = {
    speaking: 'Ollie spricht',
    continueBtn: 'Weiter',
    endBtn: 'Ende'
  };

  // Get random audio file from a category
  const getRandomAudio = useCallback((category) => {
    const prefixes = {
      open: '1',
      intro: '2',
      next: '3',
      praise: '5',
      close: '6'
    };
    const prefix = prefixes[category];
    const randomNum = Math.floor(Math.random() * 5) + 1; // 1-5
    return `${process.env.REACT_APP_API_URL || ''}/game_audio/${category}/${prefix}_${randomNum}.mp3`;
  }, []);

  // Play a queue of audio files sequentially
  const playAudioQueue = useCallback((urls, onComplete) => {
    audioQueueRef.current = [...urls];
    
    const playNext = () => {
      if (audioQueueRef.current.length === 0) {
        setIsPlaying(false);
        onComplete?.();
        return;
      }
      
      const nextUrl = audioQueueRef.current.shift();
      if (audioRef.current) {
        audioRef.current.src = nextUrl;
        audioRef.current.play().catch(err => {
          console.error('Audio play error:', err);
          // Continue to next audio even if this one fails
          playNext();
        });
      }
    };
    
    setIsPlaying(true);
    playNext();
  }, []);

  // Handle audio ended event
  const handleAudioEnded = useCallback(() => {
    if (audioQueueRef.current.length > 0) {
      // Play next in queue
      const nextUrl = audioQueueRef.current.shift();
      if (audioRef.current) {
        audioRef.current.src = nextUrl;
        audioRef.current.play().catch(err => {
          console.error('Audio play error:', err);
        });
      }
    } else {
      // Queue finished
      setIsPlaying(false);
      
      if (phase === 'intro') {
        setPhase('buttons');
      } else if (phase === 'continue') {
        setPhase('buttons');
      } else if (phase === 'ending') {
        // Game session complete, proceed to next image
        onEnd?.();
      }
    }
  }, [phase, onEnd]);

  // Start intro audio on mount
  useEffect(() => {
    const openAudio = getRandomAudio('open');
    const introAudio = getRandomAudio('intro');
    
    // Small delay to ensure component is mounted
    const timer = setTimeout(() => {
      playAudioQueue([openAudio, introAudio], () => {
        setPhase('buttons');
      });
    }, 500);
    
    return () => {
      clearTimeout(timer);
      // Cleanup audio on unmount
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
      audioQueueRef.current = [];
    };
  }, [getRandomAudio, playAudioQueue]);

  // Handle Continue button
  const handleContinue = useCallback(() => {
    setContinueCount(c => c + 1);
    setPhase('continue');
    
    const praiseAudio = getRandomAudio('praise');
    const nextAudio = getRandomAudio('next');
    
    playAudioQueue([praiseAudio, nextAudio], () => {
      setPhase('buttons');
    });
  }, [getRandomAudio, playAudioQueue]);

  // Handle End button
  const handleEnd = useCallback(() => {
    setPhase('ending');
    
    const closeAudio = getRandomAudio('close');
    
    playAudioQueue([closeAudio], () => {
      onEnd?.();
    });
  }, [getRandomAudio, playAudioQueue, onEnd]);

  // Get game image URL based on image number
  const gameImageUrl = `${process.env.REACT_APP_API_URL || ''}/animated_assistant/game_${imageNumber}.png`;

  return (
    <div className="intro-page">
      {/* Back button (optional) */}
      {onBack && (
        <div className="intro-upload-top">
          <button className="intro-upload-btn" onClick={onBack}>← Zurück</button>
        </div>
      )}
      
      <div className="intro-card">
        <div className="assistant-stage">
          <img 
            src={gameImageUrl}
            alt={`Game session for image ${imageNumber}`}
            className="intro-assistant chat-bob"
            style={{ width: '200px', height: '200px' }}
          />
          
          <div className="chat-bubble">
            {/* Show "Speaking" message while audio is playing */}
            {isPlaying && (
              <span className="typed-text" style={{ whiteSpace: 'pre-wrap' }}>
                {t.speaking}
              </span>
            )}
            
            {/* Show buttons when not playing and in buttons phase */}
            {phase === 'buttons' && !isPlaying && (
              <div className="intro-form">
                <div style={{ 
                  display: 'flex', 
                  gap: '16px', 
                  justifyContent: 'center',
                  marginTop: '10px'
                }}>
                  <button
                    className="intro-continue"
                    onClick={handleContinue}
                    style={{ padding: '12px 24px', fontSize: '18px' }}
                  >
                    {t.continueBtn}
                  </button>
                  <button
                    onClick={handleEnd}
                    style={{ 
                      padding: '12px 24px', 
                      fontSize: '18px',
                      background: 'linear-gradient(45deg, #ffb3c1, #ffd1dc)',
                      color: '#5d4037',
                      border: 'none',
                      borderRadius: '12px',
                      fontWeight: '700',
                      cursor: 'pointer'
                    }}
                  >
                    {t.endBtn}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Hidden audio element for playback */}
      <audio
        ref={audioRef}
        onEnded={handleAudioEnded}
        onError={(e) => {
          console.error('Audio error:', e);
          handleAudioEnded(); // Continue even on error
        }}
      />
    </div>
  );
};

export default GamePage;
