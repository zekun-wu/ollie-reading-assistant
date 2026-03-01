import React, { useState, useEffect } from 'react';
import './App.css';
import IntroPage from './components/IntroPage';
import PictureBookReader from './components/PictureBookReader';
import AssistanceBook from './components/AssistanceBook';
import StartPage from './components/StartPage';
import SequenceReader from './components/SequenceReader';
import CompletionPage from './components/CompletionPage';
import { useEyeTracking } from './hooks/useEyeTracking';
import { useVideoRecording } from './hooks/useVideoRecording';

// WebSocket hook for real-time communication
const useWebSocket = (url, clientId) => {
  const [socket, setSocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [lastMessage, setLastMessage] = useState(null);

  useEffect(() => {
    if (!clientId) return;

    const ws = new WebSocket(`${url}/${clientId}`);
    
    ws.onopen = () => {
      console.info('[WS] connected', { url: `${url}/${clientId}` });
      setIsConnected(true);
      setSocket(ws);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type) {
          console.info('[WS] recv', { type: message.type, state: message.state, gaze_state: message.gaze_state });
        }
        setMessages(prev => [...prev, message]);
        setLastMessage(message);
      } catch (error) {
        console.error('[WS] parse_error', error);
      }
    };

    ws.onclose = (event) => {
      console.warn('[WS] closed', { code: event.code, reason: event.reason });
      setIsConnected(false);
      setSocket(null);
    };

    ws.onerror = (error) => {
      console.error('[WS] error', error);
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
          console.info('[WS] send', { type, image_filename, activity, sequence_step, condition });
        }
      }
      socket.send(JSON.stringify(message));
    }
  };

  return { socket, isConnected, messages, lastMessage, sendMessage };
};

// Gaze State Manager Hook
const useGazeState = (websocket, imageFilename, condition = 'eye_assistance', childName = 'Guest', shouldIgnore = false, language = 'de') => {
  const [gazeState, setGazeState] = useState('idle');
  const [isTracking, setIsTracking] = useState(false);
  const [currentGuidance, setCurrentGuidance] = useState(null);
  const [triggeredAOI, setTriggeredAOI] = useState(null);

  useEffect(() => {
    // Ignore WebSocket messages when in sequence mode
    if (shouldIgnore) {
      return;
    }
    
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
          setCurrentGuidance(message.guidance);
          setTriggeredAOI(message.guidance?.triggered_aoi);
          setGazeState('guidance_ready');
          break;
        case 'guidance_update':
          // Progressive update for multi-stage guidance
          setCurrentGuidance(message.guidance);
          
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
          // If state becomes guidance_ready but no guidance data, create simple guidance
          if (message.gaze_state === 'guidance_ready' && !currentGuidance) {
            setCurrentGuidance({
              type: 'curiosity',
              message: 'du bist neugierig!',
              suggestions: []
            });
          }
          break;
        case 'guidance_dismissed':
          setCurrentGuidance(null);
          setTriggeredAOI(null);
          setGazeState(message.state);
          break;
        case 'assistance_stopped':
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
      }
    }
  }, [websocket?.lastMessage, currentGuidance, shouldIgnore]);

  const startTracking = (activity = 'storytelling', customImageFilename = null) => {
    if (websocket) {
      const targetImage = customImageFilename || imageFilename;
      websocket.sendMessage({
        type: 'start_tracking',
        image_filename: targetImage,
        activity: activity,
        condition: condition,  // NEW: Pass condition for gaze data collection
        child_name: childName,  // NEW: Pass child name for gaze data collection
        language: language  // NEW: Pass language
      });
      
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

  return {
    gazeState,
    isTracking,
    currentGuidance,
    triggeredAOI,
    startTracking,
    stopTracking,
    requestGuidance,
    dismissGuidance,
    stopAssistance
  };
};

function App() {
  const [currentStep, setCurrentStep] = useState('start'); // flow: 'start' -> 'intro' -> 'reading' -> 'completion' -> 'complete'
  const [userConfig, setUserConfig] = useState({ assistance: 'mixed', eyeTracking: 'yes', activity: 'storytelling', language: 'de' });
  const [childName, setChildName] = useState('');
  const [childAge, setChildAge] = useState('');
  const [userNumber, setUserNumber] = useState(null);
  const [readingSequence, setReadingSequence] = useState(null); // sequence data fetched from backend
  const [clientId] = useState(`client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);

  // Eye-tracking integration (only for eye-tracking mode)
  const eyeTracking = useEyeTracking();
  
  // Video recording integration
  const videoRecording = useVideoRecording();
  
  // WebSocket connection - ALWAYS connected for gaze data collection
  const shouldUseEyeTracking = true;
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
  const wsUrl = deriveWsUrl();
  console.info('[WS] url_selected', wsUrl);
  const websocket = useWebSocket(wsUrl, clientId);
  
  // Gaze state management - ALWAYS active for gaze data collection
  const currentImageFilename = 'test.jpg';
  
  // Determine condition based on userConfig
  const currentCondition = 'eye_assistance';
  
  // Check if we're in sequence mode - if so, disable this gaze state
  const isInSequenceMode = readingSequence && currentStep === 'reading';
  
  const gaze = useGazeState(
    websocket,  // NEW: Always pass websocket (not just for eye-tracking)
    currentImageFilename,  // NEW: Always pass imageFilename
    currentCondition,
    childName || 'Guest',
    isInSequenceMode,  // NEW: Disable when in sequence mode
    userConfig.language  // NEW: Pass language
  );

  

  // Eye-tracking integration functions
  const startFullEyeTracking = async () => {
    
    
    const connected = await eyeTracking.connect();
    if (!connected) {
      
      return;
    }
    
    const trackingStarted = await eyeTracking.startTracking();
    if (!trackingStarted) {
      
      return;
    }
    
    await eyeTracking.setImageContext(currentImageFilename);
    await new Promise(resolve => setTimeout(resolve, 1000));
    gaze.startTracking(userConfig.activity);  // Pass activity to backend
    
    
  };

  const stopFullEyeTracking = async () => {
    
    gaze.stopTracking();
    await eyeTracking.stopTracking();
    
  };

  // Step handlers
  const handleStart = (language = 'de', userNumber = null) => {
    setUserConfig(prev => ({ ...prev, language }));
    setUserNumber(userNumber);
    setCurrentStep('intro');
  };

  const handleIntroComplete = async (name, age, config) => {
    setChildName(name);
    setChildAge(age);
    
    // Send name, age, and user number to backend once to save session profile
    try {
      const response = await fetch(`${(process.env.REACT_APP_API_URL || '')}/api/session/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `child_name=${encodeURIComponent(name || 'Guest')}&child_age=${encodeURIComponent(age || '')}&user_number=${userNumber || ''}`
      });
      if (response.ok) {
        console.log('✅ Session profile saved');
      }
    } catch (error) {
      console.warn('⚠️ Failed to save session profile:', error);
    }
    
    // Fetch sequence from backend using user number
    try {
      const apiUrl = process.env.REACT_APP_API_URL || '';
      const response = await fetch(`${apiUrl}/api/sequences/participant/${userNumber}`);
      if (response.ok) {
        const result = await response.json();
        if (result.success && result.sequence) {
          setReadingSequence(result.sequence);
          console.log(`✅ Loaded sequence for participant ${userNumber}`);
        } else {
          console.error('❌ Failed to load sequence:', result);
          alert('Failed to load reading sequence. Please try again.');
          return;
        }
      } else {
        console.error('❌ Failed to fetch sequence:', response.status);
        alert('Failed to load reading sequence. Please try again.');
        return;
      }
    } catch (error) {
      console.error('❌ Error fetching sequence:', error);
      alert('Failed to load reading sequence. Please try again.');
      return;
    }
    
    // Start video recording session
    try {
      await videoRecording.startSession();
    } catch (error) {
      console.warn('⚠️ Could not start video recording:', error);
    }
    
    setCurrentStep('reading');
  };
  
  
  const handleSequenceComplete = () => {
    // Show completion page (recording continues)
    setCurrentStep('completion');
  };
  
  const handleCompletionButtonClick = async () => {
    // Save end clip and stop recording
    if (videoRecording.isRecording) {
      await videoRecording.saveClip('end', {});
      await videoRecording.stopSession();
    }
    
    // Move to final complete page
    setCurrentStep('complete');
  };

  const handleBackToStart = () => {
    // Stop any active recording
    if (videoRecording.isRecording) {
      videoRecording.stopSession();
    }
    
    setCurrentStep('start');
    setUserConfig({ assistance: 'mixed', eyeTracking: 'yes', activity: 'storytelling', language: 'de' });
    setChildName('');
    setChildAge('');
    setReadingSequence(null);
  };

  const handleBackToIntro = () => {
    setCurrentStep('intro');
  };

  // Render current step
  switch (currentStep) {
    case 'start':
      return (
        <StartPage 
          onStart={handleStart}
        />
      );
    
    case 'intro':
      return (
        <IntroPage 
          onContinue={handleIntroComplete}
          onBack={handleBackToStart}
          config={userConfig}
          language={userConfig.language}
        />
      );

    case 'reading':
      // Sequence-only: always render SequenceReader
      if (readingSequence) {
        return (
          <SequenceReader
            sequence={readingSequence}
            childName={childName}
            childAge={childAge}
            onComplete={handleSequenceComplete}
            onBack={handleBackToIntro}
            videoRecording={videoRecording}
            language={userConfig.language}
          />
        );
      }
      return <div>Error: No sequence found</div>;

    case 'completion':
      return (
        <CompletionPage 
          onCompleted={handleCompletionButtonClick}
          childName={childName}
        />
      );

    case 'complete':
      return (
        <div className="completion-page">
          <div className="completion-card">
            <h1>🎉 Sequenz abgeschlossen!</h1>
            <p>Du hast alle Leseschritte abgeschlossen.</p>
            <div className="completion-actions">
              <button 
                onClick={handleBackToStart}
                className="btn-restart"
              >
                🔄 Neue Sitzung starten
              </button>
            </div>
          </div>
        </div>
      );
    
    default:
      return <div>Unknown step: {currentStep}</div>;
  }
}

export default App;
