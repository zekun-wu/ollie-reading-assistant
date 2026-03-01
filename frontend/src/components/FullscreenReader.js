import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import EyeTrackingAOIHighlighter from './EyeTrackingAOIHighlighter';

// Isolated fullscreen styles - no external CSS dependencies
const fullscreenStyles = {
  container: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: '#000',
    zIndex: 999999,
    margin: 0,
    padding: 0,
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  },
  image: {
    width: '100vw',
    height: '100vh',
    objectFit: 'cover',
    display: 'block',
    border: 'none',
    outline: 'none'
  },
  canvas: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    pointerEvents: 'none',
    zIndex: 10
  },
};

const FixationCanvas = ({ currentFixation, eyeTracking }) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const smoothPositionRef = useRef({ x: 0.5, y: 0.5 });
  const lastUpdateRef = useRef(Date.now());
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      const now = Date.now();
      const deltaTime = (now - lastUpdateRef.current) / 1000;
      lastUpdateRef.current = now;
      
      const currentGaze = eyeTracking.currentGaze;
      let targetX = smoothPositionRef.current.x;
      let targetY = smoothPositionRef.current.y;
      
      if (currentFixation) {
        targetX = currentFixation.x;
        targetY = currentFixation.y;
      } else if (currentGaze && currentGaze.validity === 'valid') {
        targetX = currentGaze.x;
        targetY = currentGaze.y;
      }
      
      const smoothingFactor = 8.0;
      const lerpSpeed = Math.min(1.0, deltaTime * smoothingFactor);
      
      smoothPositionRef.current.x += (targetX - smoothPositionRef.current.x) * lerpSpeed;
      smoothPositionRef.current.y += (targetY - smoothPositionRef.current.y) * lerpSpeed;
      
      const x = smoothPositionRef.current.x * canvas.width;
      const y = smoothPositionRef.current.y * canvas.height;
      
      let baseRadius = 20;
      let opacity = 0.7;
      
      if (currentFixation) {
        const durationFactor = Math.min(currentFixation.duration / 2000, 1.5);
        baseRadius = 20 + (durationFactor * 15);
        opacity = 0.8;
      } else if (currentGaze && currentGaze.validity === 'valid') {
        baseRadius = 18;
        opacity = 0.6;
      }
      
      const pulse = 1 + Math.sin(now / 400) * 0.15;
      const radius = baseRadius * pulse;
      
      const alpha = opacity * (0.8 + Math.sin(now / 600) * 0.2);
      
      // Outer glow
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius * 2);
      gradient.addColorStop(0, `rgba(138, 43, 226, ${alpha * 0.3})`);
      gradient.addColorStop(1, 'rgba(138, 43, 226, 0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius * 2, 0, 2 * Math.PI);
      ctx.fill();
      
      // Main circle
      ctx.fillStyle = `rgba(138, 43, 226, ${alpha})`;
      ctx.strokeStyle = `rgba(138, 43, 226, ${Math.min(alpha + 0.2, 1)})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
      
      animationRef.current = requestAnimationFrame(draw);
    };
    
    draw();
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [currentFixation, eyeTracking.currentGaze]);
  
  return <canvas ref={canvasRef} style={fullscreenStyles.canvas} />;
};

const FullscreenReader = ({ 
  imageFilename, 
  activity, 
  currentFixation, 
  eyeTracking, 
  gaze,
  showGazeIndicator = false,
  onExit,
  autoMode = false,
  onAssistanceCompleted = null,
  recordAssistanceEnd = null,
  recordVoiceStart = null,  // Optional: LLM main-content voice start (timeline.json)
  recordVoiceEnd = null    // Optional: LLM main-content voice end (timeline.json)
}) => {
  // Replace popup state with headless audio state
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [currentStage, setCurrentStage] = useState('thinking');
  const audioRef = useRef(null);
  const autoModeRef = useRef(autoMode);
  const API_BASE = (process.env.REACT_APP_API_URL || '');

  useEffect(() => {
    autoModeRef.current = autoMode;
  }, [autoMode]);

  // Assistance end: 1st/2nd = voice end (audio.onended when shouldDismiss); 3rd+ = Enter or Esc only (key handler below)
  useEffect(() => {
    const handleKeyPress = async (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        await sendEndTimestamp(); // Record assistance end on Esc (1st/2nd/3rd+)
        stopAudio();  // Stop any playing audio before exiting
        if (gaze && gaze.stopWaitingAudio) {
          gaze.stopWaitingAudio();  // Stop waiting message audio
        }
        onExit();
      } else if (e.key === 'Enter') {
        if (!isPlayingAudio && gaze.gazeState === 'guidance_ready') {
          e.preventDefault();
          await sendEndTimestamp(); // Record assistance end on Enter (required for 3rd+ dismiss)
          stopAudio();
          gaze.dismissGuidance(imageFilename);
        }
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        await sendEndTimestamp(); // Send end timestamp before stopping
        stopAudio();
        if (gaze && gaze.stopAssistance) {
          gaze.stopAssistance(imageFilename);
        }
      }
    };
    document.addEventListener('keydown', handleKeyPress, true);
    return () => document.removeEventListener('keydown', handleKeyPress, true);
  }, [onExit, isPlayingAudio, gaze, imageFilename, recordAssistanceEnd, recordVoiceStart, recordVoiceEnd]);

  // Headless audio controller for guidance
  useEffect(() => {
    const guidance = gaze.currentGuidance;
    if (!guidance) return;
    
    // VALIDATION: Ignore guidance for different image to prevent stale audio playback
    if (guidance.image_filename && guidance.image_filename !== imageFilename) {
      console.warn(`⚠️ [FullscreenReader] Ignoring stale guidance for ${guidance.image_filename}, current image is ${imageFilename}`);
      return;
    }
    
    const stage = guidance.stage || 'thinking';
    
    console.log('🎵 [FullscreenReader] Guidance stage:', stage, 'isPlayingWaitingMessage:', gaze.isPlayingWaitingMessage);
    
    if (stage === 'main_content' && guidance.main_audio?.audio_url) {
      // Wait for waiting message to finish before playing main content
      if (gaze.isPlayingWaitingMessage) {
        console.log('⏳ Waiting for waiting message to finish...');
        const checkWaitingMessage = () => {
          if (!gaze.isPlayingWaitingMessage) {
            console.log('✅ Waiting message finished, playing main content');
            setCurrentStage('main_content');
            stopAudio();
            playMainAudio(guidance.main_audio.audio_url, guidance);
          } else {
            setTimeout(checkWaitingMessage, 100);
          }
        };
        checkWaitingMessage();
      } else {
        console.log('🎵 Playing main content immediately');
        setCurrentStage('main_content');
        stopAudio();
        playMainAudio(guidance.main_audio.audio_url, guidance);
      }
    } else if (stage === 'thinking') {
      setCurrentStage('thinking');
      // In original popup, waiting message was only visual text, not audio
      // So we don't play any waiting audio here
    }
  }, [gaze.currentGuidance, gaze.isPlayingWaitingMessage]);

  // Waiting message is now handled in SequenceReader.js when guidance_ready is received
  // No need for separate triggers here

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlayingAudio(false);
  };

  // playWaitingAudio is now handled in SequenceReader.js WebSocket message handler

  const playMainAudio = async (audioUrl, guidanceData) => {
    try {
      setIsPlayingAudio(true);
      const audio = new Audio(`${API_BASE}${audioUrl}`);
      audio.onended = async () => {
        const idx = gaze?.getCurrentAssistanceIndex?.();
        if (typeof recordVoiceEnd === 'function') {
          recordVoiceEnd(idx ?? undefined);
        }
        setIsPlayingAudio(false);
        setCurrentStage('completed');
        if (autoModeRef.current && gaze) {
          const shouldDismiss = onAssistanceCompleted?.() !== false;
          if (shouldDismiss) {
            await sendEndTimestamp(); // 1st/2nd: assistance end = voice end
            gaze.dismissGuidance(imageFilename);
          } else {
            // 3rd+: do NOT call sendEndTimestamp here; assistance end = Enter/Esc (key handler)
            // 3rd assistance: play continue message (highlight stays until Enter)
            const base = API_BASE || 'http://localhost:8080';
            const continueUrl = `${base}/audio/waiting/continue_de.wav`;
            try {
              setIsPlayingAudio(true);
              const continueAudio = new Audio(continueUrl);
              await new Promise((resolve, reject) => {
                continueAudio.onended = () => resolve();
                continueAudio.onerror = (e) => reject(e);
                continueAudio.play().catch(reject);
              });
            } catch (e) {
              console.warn('Continue message audio failed:', e);
            } finally {
              setIsPlayingAudio(false);
            }
          }
        }
      };
      audio.onerror = () => {
        const idx = gaze?.getCurrentAssistanceIndex?.();
        if (typeof recordVoiceEnd === 'function') {
          recordVoiceEnd(idx ?? undefined);
        }
        setIsPlayingAudio(false);
      };
      await audio.play();
      const idx = gaze?.getCurrentAssistanceIndex?.();
      if (typeof recordVoiceStart === 'function') {
        recordVoiceStart(idx ?? undefined);
      }
      audioRef.current = audio;
    } catch (e) {
      setIsPlayingAudio(false);
    }
  };


    const sendEndTimestamp = async () => {
      try {
        const idx = gaze?.getCurrentAssistanceIndex?.();
        if (typeof recordAssistanceEnd === 'function') {
          await recordAssistanceEnd(idx ?? undefined);
        }
        const endTimestamp = Date.now() / 1000;
        const aoiIndex = gaze.triggeredAOI?.index || gaze.currentGuidance?.triggered_aoi?.index;
        const secondaryAoiIndex = gaze.currentGuidance?.secondary_aoi_index; // NEW: Get secondary AOI index
        const sequenceStep = gaze.currentGuidance?.sequence_step;
        const startTimestamp = gaze.currentGuidance?.highlight_start_time; // NEW: Get highlight start time
        
        console.log('📤 [UPDATE] Sending end timestamp:', { 
          aoiIndex, 
          secondaryAoiIndex, 
          sequenceStep,
          startTimestamp,
          hasSecondary: secondaryAoiIndex !== undefined && secondaryAoiIndex !== null 
        });
        
        if (imageFilename && aoiIndex !== undefined) {
        let body = `image_filename=${encodeURIComponent(imageFilename)}&activity=${activity}&aoi_index=${aoiIndex}&end_timestamp=${endTimestamp}&condition=eye_assistance`;
        if (sequenceStep) body += `&sequence_step=${sequenceStep}`;
        if (startTimestamp) body += `&start_timestamp=${startTimestamp}`; // NEW: Add start_timestamp
        if (secondaryAoiIndex !== undefined && secondaryAoiIndex !== null) {
          body += `&secondary_aoi_index=${secondaryAoiIndex}`; // NEW: Add secondary AOI index
        }
        await fetch('http://localhost:8080/api/manual-assistance/update-end-time', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body
        });
      }
    } catch (e) {}
  };

  return createPortal(
    <div style={fullscreenStyles.container}>
      <img 
        src={`http://localhost:8080/pictures/${activity}/${imageFilename}`}
        alt="Picture book page"
        style={{
          ...fullscreenStyles.image,
          objectFit: activity === 'storytelling' ? 'contain' : 'cover'
        }}
        onError={(e) => {
          console.error('Fullscreen image load error:', e.target.src);
        }}
      />
      {showGazeIndicator && (
        <FixationCanvas 
          currentFixation={currentFixation}
          eyeTracking={eyeTracking}
        />
      )}
      <EyeTrackingAOIHighlighter 
        aoiBbox={gaze.triggeredAOI?.bbox}
        imageSize={{ 
          width: activity === 'storytelling' ? 1344 : 1500,
          height: activity === 'storytelling' ? 768 : 959 
        }}
        isActive={gaze.gazeState === 'guidance_ready'}
      />
      {/* Popup removed; handled via audio and keyboard controls */}
    </div>,
    document.body
  );
};

export default FullscreenReader;
