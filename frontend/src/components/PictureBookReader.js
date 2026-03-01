import React, { useState, useEffect, useRef, useCallback } from 'react';
import './PictureBookReader.css';
import FullscreenReader from './FullscreenReader';
import { useTimeTracking } from '../hooks/useTimeTracking';
import GamePage from './GamePage';

const FixationVisualization = ({ currentFixation, eyeTracking, imageRef }) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const smoothPositionRef = useRef({ x: 0.5, y: 0.5 }); // Start at center
  const lastUpdateRef = useRef(Date.now());
  
  useEffect(() => {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    
    if (!canvas || !image) return;
    
    const ctx = canvas.getContext('2d');
    const imageRect = image.getBoundingClientRect();
    
    // Set canvas size to match image
    canvas.width = imageRect.width;
    canvas.height = imageRect.height;
    
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      const now = Date.now();
      const deltaTime = (now - lastUpdateRef.current) / 1000; // seconds
      lastUpdateRef.current = now;
      
      // Get current gaze position for smooth interpolation
      const currentGaze = eyeTracking.currentGaze;
      let targetX = smoothPositionRef.current.x;
      let targetY = smoothPositionRef.current.y;
      
      // Update target position based on current gaze or fixation
      if (currentFixation) {
        targetX = currentFixation.x;
        targetY = currentFixation.y;
      } else if (currentGaze && currentGaze.validity === 'valid') {
        targetX = currentGaze.x;
        targetY = currentGaze.y;
      }
      
      // Smooth interpolation to target position
      const smoothingFactor = 8.0; // Higher = faster transition
      const lerpSpeed = Math.min(1.0, deltaTime * smoothingFactor);
      
      smoothPositionRef.current.x += (targetX - smoothPositionRef.current.x) * lerpSpeed;
      smoothPositionRef.current.y += (targetY - smoothPositionRef.current.y) * lerpSpeed;
      
      // Draw the smooth purple indicator
      const x = smoothPositionRef.current.x * canvas.width;
      const y = smoothPositionRef.current.y * canvas.height;
      
      // Dynamic radius based on fixation state - LARGER SIZE
      let baseRadius = 20; // Much larger base size
      let opacity = 0.7;
      
      if (currentFixation) {
        // Growing radius during fixation
        const durationFactor = Math.min(currentFixation.duration / 2000, 1.5); // Grow over 2 seconds
        baseRadius = 20 + (durationFactor * 15); // 20px to 35px
        opacity = 0.8;
      } else if (currentGaze && currentGaze.validity === 'valid') {
        // Normal size when just tracking
        baseRadius = 18; // Larger normal size
        opacity = 0.6;
      }
      
      // Subtle pulsing effect
      const pulse = 1 + Math.sin(now / 400) * 0.15;
      const radius = baseRadius * pulse;
      
      // Main purple circle with smooth transitions
      const alpha = opacity * (0.8 + Math.sin(now / 600) * 0.2);
      ctx.fillStyle = `rgba(138, 43, 226, ${alpha})`;
      ctx.strokeStyle = `rgba(138, 43, 226, ${Math.min(alpha + 0.2, 1)})`;
      ctx.lineWidth = 2;
      
      // Outer glow effect
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius * 2);
      gradient.addColorStop(0, `rgba(138, 43, 226, ${alpha * 0.3})`);
      gradient.addColorStop(1, 'rgba(138, 43, 226, 0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius * 2, 0, 2 * Math.PI);
      ctx.fill();
      
      // Main circle - NO INNER DOT
      ctx.fillStyle = `rgba(138, 43, 226, ${alpha})`;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
      
      // Duration text for fixations (minimal and elegant)
      if (currentFixation && currentFixation.duration > 800) {
        const textAlpha = Math.min((currentFixation.duration - 800) / 1000, 0.8);
        ctx.fillStyle = `rgba(255, 255, 255, ${textAlpha})`;
        ctx.font = '10px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(`${Math.round(currentFixation.duration)}ms`, x, y - radius - 12);
      }
      
      animationRef.current = requestAnimationFrame(draw);
    };
    
    draw();
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [currentFixation, eyeTracking.currentGaze, imageRef]);
  
  return (
    <canvas 
      ref={canvasRef}
      className="fixation-overlay"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 10
      }}
    />
  );
};

const PictureBookReader = ({ 
  imageFilename = '1.jpg',
  activity = 'storytelling',
  sequenceStep = null,  // NEW: Sequence step number for cache routing
  childName = 'Guest',
  eyeTracking,
  gaze,
  websocket,
  condition = 'eye_assistance',  // NEW: Condition for gaze data collection
  onStartTracking,
  onStopTracking,
  onBackToModeSelect,            // Back button callback
  // NEW: Sequence mode props
  lockedToSingleImage = false,  // If true, disable navigation and use provided image
  onComplete = null,             // Callback when user completes this step
  onPrevious = null,             // Callback to go to previous step in sequence
  // Gaze indicator toggle props
  showGazeIndicator = false,     // Whether to show gaze indicator in fullscreen (off by default)
  onGazeIndicatorToggle = null,  // Callback when toggle changes
  // NEW: Video recording callbacks
  onEnterFullscreen = null,      // Callback when entering fullscreen
  onExitFullscreen = null,       // Callback when exiting fullscreen
  language = 'de',               // Language (German only)
  recordAssistanceStart = null,  // Optional: from SequenceReader for timeline.json (server-time)
  recordAssistanceEnd = null,    // Optional: from SequenceReader for timeline.json (server-time)
  recordVoiceStart = null,      // Optional: LLM main-content voice start (timeline.json)
  recordVoiceEnd = null         // Optional: LLM main-content voice end (timeline.json)
}) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [autoMode, setAutoMode] = useState(false); // First 3 assistances: auto-dismiss on audio end; then Enter required
  const [fixations, setFixations] = useState([]);
  const [currentFixation, setCurrentFixation] = useState(null);
  const [showMockGuidance, setShowMockGuidance] = useState(false);
  const imageRef = useRef(null);
  const exitingRef = useRef(false); // Prevent double exit
  const assistanceCountRef = useRef(0); // Count auto-dismissals; after 3, require Enter
  
  // Intro audio state for eye-tracking mode
  const [isPlayingIntroAudio, setIsPlayingIntroAudio] = useState(false);
  const introAudioRef = useRef(null);
  
  const [hasExitedFullscreen, setHasExitedFullscreen] = useState(false);
  
  // Game session state
  const [showGamePage, setShowGamePage] = useState(false);
  
  // Gaze indicator toggle state (local state synchronized with parent)
  const [gazeIndicatorEnabled, setGazeIndicatorEnabled] = useState(showGazeIndicator);
  
  // Sync local state with parent prop when it changes (e.g., navigating between sequence steps)
  useEffect(() => {
    setGazeIndicatorEnabled(showGazeIndicator);
  }, [showGazeIndicator]);
  
  // Handle toggle change
  const handleGazeIndicatorToggle = (newValue) => {
    
    setGazeIndicatorEnabled(newValue);
    if (onGazeIndicatorToggle) {
      onGazeIndicatorToggle(newValue);
    }
  };
  
  // Image navigation state
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  
  // Define available images based on activity
  const getAvailableImages = () => {
    if (activity === 'storytelling') {
      return ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg', '7.jpg', '8.jpg', '9.jpg'];
    } else {
      return ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.png'];
    }
  };
  
  const availableImages = getAvailableImages();
  
  // Use provided imageFilename in locked mode, otherwise use navigation
  const currentImageFile = lockedToSingleImage && imageFilename 
    ? imageFilename 
    : availableImages[currentImageIndex];
  
  // Reset guards when image changes (for sequence mode - component doesn't remount)
  useEffect(() => {
    exitingRef.current = false;
  }, [currentImageFile]);

  // First 3 assistances: auto-dismiss on audio end; after 3, require Enter
  useEffect(() => {
    if (!isFullscreen) {
      setAutoMode(false);
      return;
    }
    setAutoMode(true);
    assistanceCountRef.current = 0;
  }, [isFullscreen]);

  const onAssistanceCompleted = useCallback(() => {
    assistanceCountRef.current += 1;
    if (assistanceCountRef.current >= 3) {
      setAutoMode(false);
    }
    return assistanceCountRef.current < 3; // true = dismiss and load next; false = keep highlight until Enter
  }, []);
  
  // Reset hasExitedFullscreen when image changes (new sequence step)
  useEffect(() => {
    setHasExitedFullscreen(false);
  }, [currentImageFile, sequenceStep]);
  
  // Time tracking - only track when in fullscreen mode (use props when provided by SequenceReader)
  const timeTracking = useTimeTracking(
    isFullscreen ? currentImageFile : null,
    activity,
    'eye_assistance',
    childName,
    sequenceStep
  );
  const recordAssistanceStartFn = recordAssistanceStart ?? timeTracking.recordAssistanceStart;
  const recordAssistanceEndFn = recordAssistanceEnd ?? timeTracking.recordAssistanceEnd;
  const recordVoiceStartFn = recordVoiceStart ?? timeTracking.recordVoiceStart;
  const recordVoiceEndFn = recordVoiceEnd ?? timeTracking.recordVoiceEnd;
  
  // Generate and play intro audio for eye-tracking mode
  const generateAndPlayEyeTrackingIntro = async () => {
    try {
      setIsPlayingIntroAudio(true);
      
      const message = language === 'de' 
        ? "Ich beobachte, wo du hinschaust."
        : "I will follow wherever your gaze goes.";
      
      const response = await fetch('http://localhost:8080/api/manual-assistance/tts/baseline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          text: message,
          image_name: currentImageFile,
          activity: activity,
          sequence_step: sequenceStep || '',
          language: language
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.success && result.audio_url) {
          const audio = new Audio(`http://localhost:8080${result.audio_url}`);
          introAudioRef.current = audio;
          audio.onended = () => {
            setIsPlayingIntroAudio(false);
            introAudioRef.current = null;
          };
          audio.onerror = () => {
            setIsPlayingIntroAudio(false);
            introAudioRef.current = null;
          };
          await audio.play();
        } else {
          setIsPlayingIntroAudio(false);
        }
      } else {
        setIsPlayingIntroAudio(false);
      }
    } catch (error) {
      console.error('❌ Error playing eye-tracking intro:', error);
      setIsPlayingIntroAudio(false);
    }
  };
  
  // Navigation functions with eye-tracking session switching
  const goToPreviousImage = async () => {
    
    if (currentImageIndex > 0) {
      const newIndex = currentImageIndex - 1;
      const newImageFile = availableImages[newIndex];
      setCurrentImageIndex(newIndex);
      
      // If in fullscreen and tracking, restart tracking for new image
      if (isFullscreen && gaze.isTracking) {
        gaze.stopTracking();
        
        await new Promise(resolve => setTimeout(resolve, 500));
        
        await eyeTracking.setImageContext(newImageFile);
        gaze.startTracking(activity, newImageFile);
        
        // Also start reading session for the new image
        if (websocket && websocket.isConnected) {
          await new Promise(resolve => setTimeout(resolve, 500));
          websocket.sendMessage({
            type: 'start_reading_session',
            image_filename: newImageFile
          });
          
        }
      }
    }
  };
  
  const goToNextImage = async () => {
    
    if (currentImageIndex < availableImages.length - 1) {
      const newIndex = currentImageIndex + 1;
      const newImageFile = availableImages[newIndex];
      setCurrentImageIndex(newIndex);
      
      // If in fullscreen and tracking, restart tracking for new image
      if (isFullscreen && gaze.isTracking) {
        gaze.stopTracking();
        
        await new Promise(resolve => setTimeout(resolve, 500));
        
        await eyeTracking.setImageContext(newImageFile);
        gaze.startTracking(activity, newImageFile);
        
        // Also start reading session for the new image
        if (websocket && websocket.isConnected) {
          await new Promise(resolve => setTimeout(resolve, 500));
          websocket.sendMessage({
            type: 'start_reading_session',
            image_filename: newImageFile
          });
          
        }
      }
    }
  };
  
  // Process gaze data into fixations
  useEffect(() => {
    if (!eyeTracking.gazeHistory || eyeTracking.gazeHistory.length === 0) {
      return;
    }
    
    // CRITICAL: Don't process fixations if guidance is showing (frozen state)
    const isFrozen = gaze.gazeState === 'frozen_curiosity' || 
                    gaze.gazeState === 'generating_guidance' ||
                    gaze.gazeState === 'guidance_ready' ||
                    showMockGuidance;
                    
    if (isFrozen) {
      return; // Don't process new fixations while frozen
    }
    
    const processFixations = () => {
      const validGazes = eyeTracking.gazeHistory.filter(g => 
        g.validity === 'valid' && g.x !== null && g.y !== null
      );
      
      if (validGazes.length < 5) return;
      
      const FIXATION_THRESHOLD = 0.03; // 3% of screen
      const MIN_FIXATION_DURATION = 150; // 150ms
      const detectedFixations = [];
      let currentFix = null;
      
      validGazes.forEach((gaze, index) => {
        if (!currentFix) {
          currentFix = {
            startTime: gaze.timestamp,
            x: gaze.x,
            y: gaze.y,
            points: [gaze],
            duration: 0
          };
        } else {
          const distance = Math.sqrt(
            Math.pow(gaze.x - currentFix.x, 2) + 
            Math.pow(gaze.y - currentFix.y, 2)
          );
          
          if (distance < FIXATION_THRESHOLD) {
            // Continue current fixation
            currentFix.points.push(gaze);
            currentFix.duration = (gaze.timestamp - currentFix.startTime) * 1000;
            
            // Update average position
            const points = currentFix.points;
            currentFix.x = points.reduce((sum, p) => sum + p.x, 0) / points.length;
            currentFix.y = points.reduce((sum, p) => sum + p.y, 0) / points.length;
          } else {
            // End current fixation if long enough
            if (currentFix.duration >= MIN_FIXATION_DURATION) {
              detectedFixations.push({
                x: currentFix.x,
                y: currentFix.y,
                duration: currentFix.duration,
                pointCount: currentFix.points.length,
                startTime: currentFix.startTime,
                endTime: currentFix.points[currentFix.points.length - 1].timestamp
              });
            }
            
            // Start new fixation
            currentFix = {
              startTime: gaze.timestamp,
              x: gaze.x,
              y: gaze.y,
              points: [gaze],
              duration: 0
            };
          }
        }
      });
      
      // Set current ongoing fixation
      if (currentFix && currentFix.points.length >= 3) {
        const now = Date.now() / 1000;
        const duration = (now - currentFix.startTime) * 1000;
        
        if (duration >= MIN_FIXATION_DURATION) {
          setCurrentFixation({
            x: currentFix.x,
            y: currentFix.y,
            duration: duration,
            pointCount: currentFix.points.length
          });
        }
      } else {
        setCurrentFixation(null);
      }
      
      setFixations(detectedFixations);
    };
    
    processFixations();
  }, [eyeTracking.gazeHistory, gaze.gazeState, showMockGuidance]);
  
  const enterFullscreen = useCallback(async () => {
    console.info('[ET] enter_fullscreen', { image: currentImageFile, activity, sequenceStep, condition });
    
    // Request browser fullscreen API FIRST - while user gesture is still valid
    try {
      await document.documentElement.requestFullscreen();
    } catch (e) {
      console.error('Fullscreen request failed:', e);
      // Continue anyway - the component fullscreen will still work
    }
    
    // Call video recording callback after entering fullscreen
    if (onEnterFullscreen) {
      await onEnterFullscreen({
        condition,
        image: currentImageFile
      });
    }
    
    setIsFullscreen(true);
    
    // NEW: Start gaze tracking via WebSocket (for ALL conditions)
    if (websocket) {
      console.info('[ET][WS] start_tracking send');
      websocket.sendMessage({
        type: 'start_tracking',
        image_filename: currentImageFile,
        activity: activity,
        condition: condition,
        child_name: childName,
        sequence_step: sequenceStep
      });
    } else {
      
    }
    
    // Start eye tracking when entering fullscreen
    try {
      
      
      // Check if already connected
      if (eyeTracking.isConnected) {
        console.info('[ET] already_connected');
      } else {
        
        const connected = await eyeTracking.connect();
        if (!connected) {
          
          
          // Show more helpful error message
          const errorMsg = eyeTracking.error || 'Unknown connection error';
          alert(`Failed to connect to eye tracker.\n\nError: ${errorMsg}\n\nPlease:\n1. Check Tobii hardware is connected\n2. Ensure no other apps are using the eye tracker\n3. Try restarting the backend`);
          return;
        }
      }
      
      
      const trackingStarted = await eyeTracking.startTracking();
      if (!trackingStarted) {
        
        alert('Failed to start eye tracking. Please check hardware.');
        return;
      }
      
      
      await eyeTracking.setImageContext(currentImageFile);  // Use current image, not hardcoded
      
      await new Promise(resolve => setTimeout(resolve, 1000));
      gaze.startTracking(activity, currentImageFile);  // Pass activity AND current image
      
      
      if (websocket && websocket.isConnected) {
        console.info('[ET][WS] start_reading_session send');
        websocket.sendMessage({
          type: 'start_reading_session',
          image_filename: currentImageFile  // Use current image, not prop
        });
        
      }
      
      // Play intro audio for eye-tracking mode
      try {
        generateAndPlayEyeTrackingIntro();
      } catch {}
      
    } catch (error) {
      
      alert(`Eye tracking startup failed: ${error.message}`);
    }
  }, [eyeTracking, gaze, currentImageFile, activity, websocket, condition, childName, sequenceStep, onEnterFullscreen, language]);
  
  const exitFullscreen = useCallback(async () => {
    // Prevent double exit
    if (exitingRef.current) {
      console.warn('[PictureBookReader] Already exiting, skipping');
      return;
    }
    
    exitingRef.current = true;
    
    // ===== CRITICAL: Call video callback FIRST, before any state changes =====
    if (onExitFullscreen) {
      try {
        await onExitFullscreen({
          condition,
          image: currentImageFile
        });
      } catch (error) {
        console.error('❌ [PictureBookReader] onExitFullscreen error:', error);
      }
    } else {
      console.warn('⚠️ [PictureBookReader] onExitFullscreen is undefined');
    }
    
    // Dismiss any active guidance first
    if (showMockGuidance) {
      gaze.dismissGuidance(currentImageFile);
      setShowMockGuidance(false);
    }
    
    // Stop all assistance
    if (gaze && gaze.stopAssistance) {
      gaze.stopAssistance(currentImageFile);
    }
    
    // Stop any playing waiting audio
    if (gaze && gaze.stopWaitingAudio) {
      gaze.stopWaitingAudio();
    }
    
    // Stop intro audio if playing
    if (introAudioRef.current) {
      introAudioRef.current.pause();
      introAudioRef.current = null;
      setIsPlayingIntroAudio(false);
    }
    
    // Stop gaze tracking via WebSocket
    if (websocket) {
      console.info('[ET][WS] stop_tracking send');
      websocket.sendMessage({
        type: 'stop_tracking',
        image_filename: currentImageFile
      });
    }
    
    // Stop reading session
    if (websocket && websocket.isConnected) {
      console.info('[ET][WS] stop_reading_session send');
      websocket.sendMessage({
        type: 'stop_reading_session',
        image_filename: currentImageFile
      });
    }
    
    // Stop eye tracking
    await onStopTracking();
    
    // Exit browser fullscreen
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch (e) {
        console.error('[PictureBookReader] Error exiting fullscreen:', e);
      }
    }
    
    // Clear component state
    setIsFullscreen(false);
    setFixations([]);
    setCurrentFixation(null);
    setHasExitedFullscreen(true); // Mark that user has exited fullscreen once
    setShowGamePage(true); // Show game session after exiting fullscreen
    console.log('✅ [PictureBookReader] Exit complete, showing GamePage');
    
    // Reset exit flag after delay
    setTimeout(() => {
      exitingRef.current = false;
    }, 500);
  }, [websocket, currentImageFile, onStopTracking, showMockGuidance, gaze, condition, onExitFullscreen]);
  
  const showMockGuidancePanel = () => {
    
    
    // Trigger actual guidance request through the state machine
    // This should properly freeze the eye tracking
    gaze.requestGuidance('curiosity');
    setShowMockGuidance(true);
  };
  
  const dismissGuidance = () => {
    
    
    // Properly dismiss guidance through the state machine with current image
    // This should unfreeze the eye tracking
    gaze.dismissGuidance(currentImageFile);
    setShowMockGuidance(false);
  };
  
  // Handle escape key and fullscreen changes
  useEffect(() => {
    const handleKeyPress = async (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        
        e.preventDefault(); // Prevent default browser fullscreen handling
        await exitFullscreen();
      } else if (e.key === 'ArrowLeft' && !lockedToSingleImage) {
        // Only allow arrow navigation in standalone mode (not in sequence mode)
        e.preventDefault();
        goToPreviousImage();
      } else if (e.key === 'ArrowRight' && !lockedToSingleImage) {
        // Only allow arrow navigation in standalone mode (not in sequence mode)
        e.preventDefault();
        goToNextImage();
      }
    };
    
    const handleFullscreenChange = async () => {
      // If browser exited fullscreen but our component is still in fullscreen mode
      if (!document.fullscreenElement && isFullscreen && !exitingRef.current) {
        exitingRef.current = true; // Prevent recursive calls
        
        console.log('[PictureBookReader] Browser-initiated fullscreen exit detected');
        
        // Close current assistance in timeline and send update-end-time so last assistance is recorded
        const idx = gaze?.getCurrentAssistanceIndex?.();
        if (typeof recordAssistanceEndFn === 'function') {
          try {
            await recordAssistanceEndFn(idx ?? undefined);
          } catch (e) {
            console.error('❌ [PictureBookReader] recordAssistanceEnd on fullscreen exit:', e);
          }
        }
        const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8080';
        const endTimestamp = Date.now() / 1000;
        const aoiIndex = gaze?.triggeredAOI?.index ?? gaze?.currentGuidance?.triggered_aoi?.index;
        const secondaryAoiIndex = gaze?.currentGuidance?.secondary_aoi_index;
        const sequenceStepVal = gaze?.currentGuidance?.sequence_step;
        const startTimestamp = gaze?.currentGuidance?.highlight_start_time;
        if (currentImageFile && aoiIndex !== undefined) {
          let body = `image_filename=${encodeURIComponent(currentImageFile)}&activity=${activity}&aoi_index=${aoiIndex}&end_timestamp=${endTimestamp}&condition=eye_assistance`;
          if (sequenceStepVal) body += `&sequence_step=${sequenceStepVal}`;
          if (startTimestamp != null) body += `&start_timestamp=${startTimestamp}`;
          if (secondaryAoiIndex !== undefined && secondaryAoiIndex !== null) {
            body += `&secondary_aoi_index=${secondaryAoiIndex}`;
          }
          try {
            await fetch(`${API_BASE}/api/manual-assistance/update-end-time`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body
            });
          } catch (e) {
            console.error('❌ [PictureBookReader] update-end-time on fullscreen exit:', e);
          }
        }
        
        // CRITICAL: Call video callback (before any state changes)
        if (onExitFullscreen) {
          try {
            await onExitFullscreen({
              condition,
              image: currentImageFile
            });
          } catch (error) {
            console.error('❌ [PictureBookReader] onExitFullscreen error (browser-exit):', error);
          }
        }
        
        // Stop gaze tracking via WebSocket
        if (websocket) {
          websocket.sendMessage({
            type: 'stop_tracking',
            image_filename: currentImageFile
          });
        }
        
        // Stop eye tracking
        await onStopTracking();
        
        setHasExitedFullscreen(true);
        setShowGamePage(true); // Show game session after exiting fullscreen
        setIsFullscreen(false);
        setShowMockGuidance(false);
        setFixations([]);
        setCurrentFixation(null);
        console.log('✅ [PictureBookReader] Exit complete (browser-initiated), showing GamePage');
        
        setTimeout(() => {
          exitingRef.current = false;
        }, 500);
      }
    };
    
    // Add event listeners for both fullscreen and thumbnail modes
    document.addEventListener('keydown', handleKeyPress, true); // Use capture phase
    
    if (isFullscreen) {
      document.addEventListener('fullscreenchange', handleFullscreenChange);
      return () => {
        document.removeEventListener('keydown', handleKeyPress, true);
        document.removeEventListener('fullscreenchange', handleFullscreenChange);
      };
    } else {
      return () => {
        document.removeEventListener('keydown', handleKeyPress, true);
      };
    }
  }, [isFullscreen, exitFullscreen, currentImageIndex, availableImages.length, websocket, currentImageFile, lockedToSingleImage, onStopTracking, showMockGuidance, gaze, onExitFullscreen, condition, recordAssistanceEndFn, activity]);
  
  // If showing game page, render GamePage
  if (showGamePage) {
    // Extract image number from filename (e.g., "3.jpg" -> 3)
    const imageNumber = parseInt(currentImageFile.replace(/\D/g, ''), 10) || 1;
    console.log('🎮 [PictureBookReader] Rendering GamePage for image:', imageNumber);
    
    const handleGameEnd = () => {
      console.log('🎮 [PictureBookReader] Game session ended, proceeding to next');
      setShowGamePage(false);
      // Call onComplete to move to next image in sequence
      if (onComplete) {
        onComplete();
      }
    };
    
    return (
      <GamePage
        imageNumber={imageNumber}
        onEnd={handleGameEnd}
        language={language}
      />
    );
  }

  if (isFullscreen) {
    return (
      <FullscreenReader 
        imageFilename={currentImageFile}
        activity={activity}
        currentFixation={currentFixation}
        eyeTracking={eyeTracking}
        gaze={gaze}
        showGazeIndicator={gazeIndicatorEnabled}
        onExit={exitFullscreen}
        autoMode={autoMode}
        onAssistanceCompleted={onAssistanceCompleted}
        recordAssistanceEnd={recordAssistanceEndFn}
        recordVoiceStart={recordVoiceStartFn}
        recordVoiceEnd={recordVoiceEndFn}
      />
    );
  }
  
  // Thumbnail view
  return (
    <div>
      {/* Header with back button - same as BaselineBook and AssistanceBook */}
      <div className="mode-header">
        <button
          className="back-button"
          onClick={onBackToModeSelect}
        >
          ← Back to Intro
        </button>
      </div>
      
      <div className="picture-book-container">
      <div className="image-navigation">
        {/* Show prev/next buttons for standalone mode */}
        {!lockedToSingleImage && (
          <button 
            className="nav-button prev-button"
            onClick={goToPreviousImage}
            disabled={currentImageIndex === 0}
          >
            ← Previous
          </button>
        )}
        
        {/* Show "Previous Step" button in locked sequence mode */}
        {lockedToSingleImage && onPrevious && (
          <button 
            className="nav-button prev-button"
            onClick={onPrevious}
          >
            ← Previous Step
          </button>
        )}
        
        <div className="image-display">
          <img 
            src={`${(process.env.REACT_APP_API_URL || '')}/pictures/${activity}/${currentImageFile}`}
            alt={`Picture book page ${currentImageIndex + 1}`}
            className="main-image"
            onDoubleClick={() => {
              console.log('🖱️ [PictureBookReader] Double-click detected', { 
                hasExitedFullscreen, 
                isFullscreen 
              });
              if (!hasExitedFullscreen) {
                console.log('➡️ [PictureBookReader] Entering fullscreen (first time)');
                enterFullscreen();
              }
              // After exiting fullscreen, double-click does nothing (review mode skipped)
            }}
            onError={(e) => {
              
              e.target.style.display = 'none';
              e.target.parentElement.style.background = 'linear-gradient(45deg, #667eea, #764ba2)';
              e.target.parentElement.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; height: 400px; color: white; font-size: 1.2rem;">
                  📖 Image: ${currentImageFile}<br/>
                  (Image not found - check path)
                </div>
              `;
            }}
          />
          
          {/* Simple Gaze Tracker Toggle - Bottom Right */}
          {lockedToSingleImage && condition === 'eye_assistance' && (
            <div className="gaze-toggle-simple">
              <label>
                <input 
                  type="checkbox"
                  checked={gazeIndicatorEnabled}
                  onChange={(e) => handleGazeIndicatorToggle(e.target.checked)}
                />
                <span className="gaze-toggle-slider"></span>
              </label>
              <span className="gaze-toggle-label-text">Gaze Tracker</span>
            </div>
          )}
        </div>
        
        {/* Show "Next" button for standalone mode */}
        {!lockedToSingleImage && (
          <button 
            className="nav-button next-button"
            onClick={goToNextImage}
            disabled={currentImageIndex === availableImages.length - 1}
          >
            Next →
          </button>
        )}
        
        {/* Show "Next Step" button in locked sequence mode */}
        {lockedToSingleImage && onComplete && (
          <button 
            className="nav-button next-button"
            onClick={onComplete}
          >
            Next Step →
          </button>
        )}
      </div>
      
      <div className="image-info">
        <span className="page-indicator">
          {lockedToSingleImage 
            ? `Sequence Mode: ${currentImageFile}`
            : `${currentImageIndex + 1} of ${availableImages.length}`
          }
        </span>
      </div>
      </div>
    </div>
  );
};

export default PictureBookReader;
