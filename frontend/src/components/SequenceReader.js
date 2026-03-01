import React, { useState, useEffect, useCallback, useRef } from 'react';
import AssistanceBook from './AssistanceBook';
import PictureBookReader from './PictureBookReader';
import GroupIntroPage from './GroupIntroPage';
import { useEyeTracking } from '../hooks/useEyeTracking';
import { useTimeTracking } from '../hooks/useTimeTracking';
import './SequenceReader.css';

// WebSocket hook for eye-tracking mode
const useWebSocket = (url, clientId) => {
  const [socket, setSocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [lastMessage, setLastMessage] = useState(null);

  useEffect(() => {
    if (!clientId) return;

    const ws = new WebSocket(`${url}/${clientId}`);
    
    ws.onopen = () => {
      console.info('[WS][seq] connected', { url: `${url}/${clientId}` });
      setIsConnected(true);
      setSocket(ws);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type) {
          console.info('[WS][seq] recv', { type: message.type, state: message.state, gaze_state: message.gaze_state });
        }
        setMessages(prev => [...prev, message]);
        setLastMessage(message);
      } catch (error) {
        console.error('[WS][seq] parse_error', error);
      }
    };

    ws.onclose = (event) => {
      console.warn('[WS][seq] closed', { code: event.code, reason: event.reason });
      setIsConnected(false);
      setSocket(null);
    };

    ws.onerror = (error) => {
      console.error('[WS][seq] error', error);
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [url, clientId]);

  const sendMessage = (message) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      if (message?.type) {
        const { type, image_filename, activity, sequence_step, condition } = message;
        if (type === 'start_tracking' || type === 'stop_tracking' || type === 'start_reading_session' || type === 'stop_reading_session') {
          console.info('[WS][seq] send', { type, image_filename, activity, sequence_step, condition });
        }
      }
      socket.send(JSON.stringify(message));
    } else {
      
    }
  };

  return { socket, isConnected, messages, lastMessage, sendMessage };
};

// Gaze State Manager Hook
const useGazeState = (websocket, imageFilename, sequenceStep = null, condition = 'eye_assistance', childName = 'Guest', currentStepInfo = null, language = 'de', onHighlightShow = null, onHighlightHide = null) => {
  const [gazeState, setGazeState] = useState('idle');
  const [isTracking, setIsTracking] = useState(false);
  const [currentGuidance, setCurrentGuidance] = useState(null);
  const [triggeredAOI, setTriggeredAOI] = useState(null);
  const [isPlayingWaitingMessage, setIsPlayingWaitingMessage] = useState(false);
  const [highlightStartTime, setHighlightStartTime] = useState(null); // NEW: Track when highlight appears
  const assistanceIndexRef = useRef(0);  // 1-based current assistance index for timeline
  const waitingAudioRef = useRef(null);  // Ref to track waiting audio for cleanup
  const preloadedWaitingAudioRef = useRef(null);  // Preloaded audio for instant playback

  // Reset assistance index when moving to a new picture so timeline starts at assistance_1 again
  useEffect(() => {
    assistanceIndexRef.current = 0;
  }, [imageFilename]);

  // Preload waiting audio (German only)
  useEffect(() => {
    const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8080';
    const audioFile = 'waiting_de.wav';
    
    const audio = new Audio(`${API_BASE}/audio/waiting/${audioFile}`);
    audio.preload = 'auto';
    
    // Only set ref AFTER audio is fully loaded and ready to play instantly
    audio.addEventListener('canplaythrough', () => {
      preloadedWaitingAudioRef.current = audio;
      console.log(`✅ Waiting audio READY: ${audioFile}`);
    }, { once: true });
    
    audio.addEventListener('error', (e) => {
      console.error(`❌ Failed to preload waiting audio: ${audioFile}`, e);
    }, { once: true });
    
    audio.load();
    console.log(`🔊 Loading waiting audio: ${audioFile}`);
    
    return () => {
      preloadedWaitingAudioRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (websocket && websocket.lastMessage) {
      const message = websocket.lastMessage;
      
      switch (message.type) {
        case 'tracking_started':
          setIsTracking(true);
          setGazeState(message.state);
          break;
        case 'tracking_stopped':
          setIsTracking(false);
          setGazeState(message.state);
          break;
        case 'guidance_requested':
          setGazeState(message.state);
          break;
        case 'guidance_ready':
          console.log('🎯 GUIDANCE READY: Highlight starting, trigger waiting message');
          
          assistanceIndexRef.current += 1;
          const indexForHighlight = assistanceIndexRef.current;
          
          // Capture highlight start time (when highlight actually appears)
          const highlightStart = Date.now() / 1000; // Unix epoch float
          setHighlightStartTime(highlightStart);
          console.log(`🎯 Highlight appeared at: ${highlightStart} (assistance ${indexForHighlight})`);
          if (typeof onHighlightShow === 'function') {
            onHighlightShow(indexForHighlight);
          }
          
          // Add highlight_start_time to guidance object
          const guidanceWithTimestamp = {
            ...message.guidance,
            highlight_start_time: highlightStart
          };
          
          setCurrentGuidance(guidanceWithTimestamp);
          setTriggeredAOI(message.guidance?.triggered_aoi);
          setGazeState('guidance_ready');
          
          // Play pre-saved waiting message immediately when highlight starts
          if (!isPlayingWaitingMessage) {
            console.log('🎵 Playing pre-saved waiting message for highlight start');
            setIsPlayingWaitingMessage(true);
            playPreSavedWaitingMessage();
          }
          break;
        case 'guidance_update':
          console.log('🎯 GUIDANCE UPDATE: Main content ready, waiting for waiting message to finish');
          
          // Preserve highlight_start_time from previous guidance_ready
          const updatedGuidance = {
            ...message.guidance,
            highlight_start_time: currentGuidance?.highlight_start_time  // Preserve from guidance_ready
          };
          
          setCurrentGuidance(updatedGuidance);
          
          // DON'T stop waiting message - let it finish naturally
          // The FullscreenReader will wait for waiting message to finish before playing main content
          
          // Handle "See you soon!" message from stop_assistance
          if (message.guidance?.type === 'stopped') {
            setTriggeredAOI(null);
            setGazeState('tracking');
            
            // Hide popup after 2 seconds
            setTimeout(() => {
              setCurrentGuidance(null);
            }, 2000);
          }
          break;
        case 'state_update':
          setGazeState(message.gaze_state);
          setIsTracking(message.tracking_active || false);
          break;
        case 'guidance_dismissed':
          if (typeof onHighlightHide === 'function') {
            onHighlightHide(assistanceIndexRef.current);
          }
          setCurrentGuidance(null);
          setTriggeredAOI(null);
          setGazeState(message.state);
          setIsPlayingWaitingMessage(false); // Reset waiting message flag
          break;
        case 'assistance_stopped':
          if (typeof onHighlightHide === 'function') {
            onHighlightHide(assistanceIndexRef.current);
          }
          // Show goodbye message before clearing
          setCurrentGuidance({
            type: 'stopped',
            message: 'Bis bald!',
            stage: 'stopped'
          });
          setTriggeredAOI(null);
          setGazeState(message.state);
          
          // Hide popup after 2 seconds
          setTimeout(() => {
            setCurrentGuidance(null);
          }, 2000);
          break;
        default:
          break;
      }
    }
  }, [websocket?.lastMessage]);

  const startTracking = (activity = 'storytelling', customImageFilename = null) => {
    if (websocket) {
      const targetImage = customImageFilename || imageFilename;
      const message = {
        type: 'start_tracking',
        image_filename: targetImage,
        activity: 'storytelling',  // Always storytelling now
        condition: condition,  // NEW: Add condition for gaze data collection
        child_name: childName,  // NEW: Add child name for gaze data collection
        language: language  // NEW: Add language
      };
      
      // Add sequence_step if in sequence mode
      if (sequenceStep !== null) {
        message.sequence_step = sequenceStep;
      }
      
      websocket.sendMessage(message);
    }
  };

  const stopTracking = () => {
    if (websocket) {
      websocket.sendMessage({
        type: 'stop_tracking',
        image_filename: imageFilename
      });
    }
  };

  const requestGuidance = (guidanceType) => {
    if (websocket) {
      websocket.sendMessage({
        type: 'request_guidance',
        image_filename: imageFilename,
        request_type: guidanceType,
        gaze_data: { manual: true }
      });
    }
  };

  const dismissGuidance = (customImageFilename = null) => {
    if (websocket) {
      const targetImage = customImageFilename || imageFilename;
      websocket.sendMessage({
        type: 'dismiss_guidance',
        image_filename: targetImage
      });
    }
  };
  
  const stopAssistance = (customImageFilename = null) => {
    if (websocket) {
      const targetImage = customImageFilename || imageFilename;
      websocket.sendMessage({
        type: 'stop_assistance',
        image_filename: targetImage
      });
    }
  };
  
  // Stop waiting audio (used when navigating away or pressing ESC)
  const stopWaitingAudio = () => {
    if (waitingAudioRef.current) {
      waitingAudioRef.current.pause();
      waitingAudioRef.current.currentTime = 0;
      waitingAudioRef.current = null;
    }
    setIsPlayingWaitingMessage(false);
  };

  const playPreSavedWaitingMessage = async () => {
    try {
      console.log('🎵 Playing pre-saved waiting message (de)');
      
      let audio = preloadedWaitingAudioRef.current;
      
      // Fallback: if preloaded audio not ready yet, load on-demand
      if (!audio) {
        console.warn('⚠️ Preloaded audio not ready, loading on-demand');
        const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8080';
        audio = new Audio(`${API_BASE}/audio/waiting/waiting_de.wav`);
      }
      
      // Reset to start in case it was played before
      audio.currentTime = 0;
      waitingAudioRef.current = audio;
      
      audio.onended = () => {
        console.log('✅ Waiting message ended');
        setIsPlayingWaitingMessage(false);
        waitingAudioRef.current = null;
        
        // Reset to beginning for next play (no reload needed - audio is buffered)
        audio.currentTime = 0;
      };
      audio.onerror = (e) => {
        console.error('❌ Waiting message error:', e);
        setIsPlayingWaitingMessage(false);
        waitingAudioRef.current = null;
      };
      
      await audio.play();
    } catch (e) {
      console.error('❌ Waiting message error:', e);
      setIsPlayingWaitingMessage(false);
    }
  };

  return {
    gazeState,
    isTracking,
    currentGuidance,
    triggeredAOI,
    isPlayingWaitingMessage,
    getCurrentAssistanceIndex: () => assistanceIndexRef.current,
    startTracking,
    stopTracking,
    requestGuidance,
    dismissGuidance,
    stopAssistance,
    stopWaitingAudio,  // For cleanup on navigation/ESC
    playPreSavedWaitingMessage
  };
};

const SequenceReader = ({ sequence: initialSequence, childName, childAge, onComplete, onBack, videoRecording, language = 'de' }) => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isInitializing, setIsInitializing] = useState(false);
  const [initError, setInitError] = useState(null);
  
  // Convert sequence to state so we can update it (for gaze indicator toggle)
  const [sequence, setSequence] = useState(initialSequence);
  
  // Group tracking for intro pages
  const [seenGroups, setSeenGroups] = useState(new Set());
  const [showingGroupIntro, setShowingGroupIntro] = useState(null); // 'manual' | 'eye_tracking'
  
  // Track if first fullpage entry has occurred
  const isFirstFullpageRef = useRef(true);
  
  // Track previous step metadata for post clip naming
  const previousStepRef = useRef(null);
  
  // Helper function to map condition to group key
  const conditionToGroupKey = (condition) => {
    const map = {
      'assistance': 'manual',
      'eye_assistance': 'eye_tracking'
    };
    return map[condition] || condition;
  };
  
  // Initialize resources that might be needed
  const [clientId] = useState(`client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  
  // Always initialize eye-tracking (connect only when needed)
  const eyeTracking = useEyeTracking();
  
  // Check if ANY step in sequence needs eye-tracking
  const sequenceNeedsEyeTracking = sequence.some(step => step.condition === 'eye_assistance');
  
  // Always initialize WebSocket for gaze data collection across ALL conditions
  const deriveWsUrl = () => {
    if (process.env.REACT_APP_WS_URL) return process.env.REACT_APP_WS_URL;
    const api = process.env.REACT_APP_API_URL;
    if (api) return `${api.replace('http', 'ws')}/ws`;
    const loc = window.location;
    // Prefer backend 8080 when running dev on 3000
    if (loc.port === '3000') {
      return 'ws://localhost:8080/ws';
    }
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${loc.host}/ws`;
  };
  const websocket = useWebSocket(deriveWsUrl(), clientId);
  
  // Current step
  const currentStep = sequence[currentStepIndex];
  const isLastStep = currentStepIndex === sequence.length - 1;
  const sequenceStep = currentStepIndex + 1; // 1-based indexing for backend
  const condition = currentStep?.condition || 'eye_assistance';
  
  // Time tracking for eye-assistance step (server-time alignment with gaze)
  const timeTracking = useTimeTracking(
    condition === 'eye_assistance' ? currentStep?.image : null,
    currentStep?.activity || 'storytelling',
    'eye_assistance',
    childName || 'Guest',
    sequenceStep
  );
  
  // Group transition detection
  useEffect(() => {
    if (!currentStep || showingGroupIntro) return;
    
    const groupKey = conditionToGroupKey(currentStep.condition);
    
    if (!seenGroups.has(groupKey)) {
      setShowingGroupIntro(groupKey);
      // Don't mark as seen yet - will be marked when intro completes
    }
  }, [currentStepIndex, currentStep, seenGroups, showingGroupIntro]);
  
  // Handle group intro completion
  const handleGroupIntroComplete = () => {
    const groupKey = showingGroupIntro;
    setSeenGroups(prev => new Set([...prev, groupKey]));
    setShowingGroupIntro(null);
    // Now will render the actual reading component
  };
  
  // Gaze state management (pass timeline assistance callbacks for server-time recording; index passed for correct timeline assignment)
  const gaze = useGazeState(
    websocket,
    currentStep?.image || 'test.jpg',
    sequenceStep,
    condition,
    childName || 'Guest',
    currentStep,
    language,
    (index) => timeTracking.recordAssistanceStart(index),
    (index) => timeTracking.recordAssistanceEnd(index)
  );
  
  // Initialize eye tracker for gaze data collection (ALL conditions need it now)
  useEffect(() => {
    const initResources = async () => {
      // Always connect eye tracker for gaze data collection
      if (eyeTracking.isConnected) {
        return;
      }
      
      setIsInitializing(true);
      setInitError(null);
      
      
      const connected = await eyeTracking.connect();
      
      if (!connected) {
        const errorMsg = 'Failed to connect eye tracker. Gaze data collection will not work.';
        setInitError(errorMsg);
        
      } else {
      }
      
      setIsInitializing(false);
    };
    
    initResources();
  }, []); // Only run once on mount

  // Handle gaze indicator toggle for current step
  const handleGazeIndicatorToggle = useCallback((newValue) => {
    
    setSequence(prevSequence => {
      const newSequence = [...prevSequence];
      newSequence[currentStepIndex] = {
        ...newSequence[currentStepIndex],
        showGazeIndicator: newValue
      };
      return newSequence;
    });
  }, [currentStepIndex]);

  // Video recording callbacks
  const handleEnterFullscreen = useCallback(async (metadata) => {
    if (!videoRecording?.isRecording) return;

    const { condition, image } = metadata;
    
    // On first fullpage entry, save start.webm
    if (isFirstFullpageRef.current) {
      console.log('🎥 First fullpage entry - saving start.webm');
      await videoRecording.saveClip('start', {});
      isFirstFullpageRef.current = false;
    } else if (previousStepRef.current) {
      // Save previous post.webm with PREVIOUS step's metadata
      console.log('🎥 Entering fullpage - saving previous post.webm', previousStepRef.current);
      await videoRecording.saveClip('post', previousStepRef.current);
    }
    
    // Store current metadata for next post clip
    previousStepRef.current = { condition, image };
  }, [videoRecording]);

  const handleExitFullscreen = useCallback(async (metadata) => {
    console.log('🎥 [SequenceReader] handleExitFullscreen called', metadata);
    
    if (!videoRecording?.isRecording) {
      console.warn('⚠️ Video not recording, skipping');
      return;
    }

    const { condition, image } = metadata;
    
    // Save the full.webm clip
    console.log('🎥 Exiting fullpage - saving full.webm', { condition, image });
    await videoRecording.saveClip('full', { condition, image });
    
    // Update previous step for post clip
    previousStepRef.current = { condition, image };
  }, [videoRecording]);

  // Handle step completion (move forward)
  const handleStepComplete = useCallback(async () => {
    // Get current step info
    const currentStep = sequence[currentStepIndex];
    if (!currentStep) return;
    
    // Check if this is the last step
    if (isLastStep) {
      if (websocket?.sendMessage) {
        websocket.sendMessage({ type: 'sequence_complete' });
      }
      onComplete?.();
      return;
    }
    
    // Advance to next step
    setCurrentStepIndex(currentStepIndex + 1);
    
  }, [currentStepIndex, isLastStep, sequence, onComplete, websocket]);

  // Handle previous step (move backward)
  const handleStepPrevious = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  }, [currentStepIndex, sequence.length]);

  // Render appropriate component based on current step
  const renderCurrentComponent = () => {
    // Check if showing group intro
    if (showingGroupIntro) {
      return (
        <GroupIntroPage
          groupType={showingGroupIntro}
          childName={childName}
          onContinue={handleGroupIntroComplete}
          language={language}
        />
      );
    }
    
    if (!currentStep) {
      return <div>No step data</div>;
    }

    const { condition, activity, image } = currentStep;
    // Note: sequenceStep already defined above for useGazeState
    
    // Warn if eye tracker is unavailable for assistance (gaze data collection will be skipped)
    if (initError && condition === 'assistance') {
    }

    switch (condition) {
      case 'assistance':
        return (
          <AssistanceBook
            imageFilename={image}
            activity={activity}
            childName={childName}
            childAge={childAge}
            websocket={websocket}
            condition="assistance"
            lockedToSingleImage={true}
            sequenceStep={sequenceStep}
            language={language}
            onComplete={handleStepComplete}
            onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
            onBackToModeSelect={onBack}
            onEnterFullscreen={handleEnterFullscreen}
            onExitFullscreen={handleExitFullscreen}
          />
        );

      case 'eye_assistance':
        // Eye-assistance REQUIRES eye tracker
        if (!eyeTracking.isConnected && !isInitializing) {
          return (
            <div className="error-state">
              <h2>❌ Eye Tracker Not Connected</h2>
              <p>{initError || 'Please check eye tracker connection'}</p>
              <button onClick={onBack} className="btn-back-error">
                ← Back to Sequence Builder
              </button>
            </div>
          );
        }

        if (isInitializing) {
          return (
            <div className="initializing-state">
              <h2>🔌 Connecting to Eye Tracker...</h2>
              <p>Please wait while we set up the eye tracking hardware</p>
            </div>
          );
        }

        return (
          <PictureBookReader
            imageFilename={image}
            activity={activity}
            childName={childName}
            eyeTracking={eyeTracking}
            gaze={gaze}
            websocket={websocket}
            condition={condition}  // NEW: Pass condition for gaze data collection
            lockedToSingleImage={true}
            sequenceStep={sequenceStep}
            showGazeIndicator={currentStep.showGazeIndicator ?? false}  // Pass gaze indicator setting (off by default)
            onGazeIndicatorToggle={handleGazeIndicatorToggle}  // NEW: Pass toggle handler
            onComplete={handleStepComplete}
            onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
            onBackToModeSelect={onBack}
            onStartTracking={() => {}} // Tracking managed by sequence
            onStopTracking={() => {}}  // Tracking managed by sequence
            onEnterFullscreen={handleEnterFullscreen}
            onExitFullscreen={handleExitFullscreen}
            language={language}
            recordAssistanceStart={timeTracking.recordAssistanceStart}
            recordAssistanceEnd={timeTracking.recordAssistanceEnd}
            recordVoiceStart={timeTracking.recordVoiceStart}
            recordVoiceEnd={timeTracking.recordVoiceEnd}
          />
        );

      default:
        return <div>Unknown condition: {condition}</div>;
    }
  };

  return (
    <>
      {renderCurrentComponent()}
    </>
  );
};

export default SequenceReader;


