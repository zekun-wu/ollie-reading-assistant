import React, { useState, useRef } from 'react';
import { PromptTypes, promptAliasForStorage } from '../constants';
import AudioPlayer from './AudioPlayer';
import LoadingSpinner from './LoadingSpinner';
import ErrorMessage from './ErrorMessage';
import './PictureBook.css';
import AssistantOverlay from './assistant/AssistantOverlay';

const PictureBook = ({ language, parentSupport = 'basic', isParentMode = false, childName, onBackToModeSelect }) => {
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedImages, setSelectedImages] = useState(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [narrationData, setNarrationData] = useState(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [isFullscreenMode, setIsFullscreenMode] = useState(false);
  const [gazeData, setGazeData] = useState(null);
  const [isEyeTrackingActive, setIsEyeTrackingActive] = useState(false);
  const [showMasks, setShowMasks] = useState(false);
  const [currentObject, setCurrentObject] = useState(null);
  const [lastCrop, setLastCrop] = useState(null); // { url, object_id, ts }
  const [assistantState, setAssistantState] = useState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
  const [parentNotice, setParentNotice] = useState(null); // { type: 'curiosity' | 'attention', text: string, ts: number }
  const parentNoticeTimerRef = useRef(null);
  const isParentBasic = isParentMode && parentSupport === 'basic';
  const isParentGuided = isParentMode && parentSupport === 'guided';
  const isParentAny = isParentBasic || isParentGuided;
  const bookImageRef = useRef(null);
  const [parentGuidedPanel, setParentGuidedPanel] = useState(null); // { type: 'curiosity'|'mindwandering', data: any, ts: number }
  const [isGazeFrozen, setIsGazeFrozen] = useState(false); // Track freeze state for gaze processing
  const ttsVoiceRef = useRef('en-US-AnaNeural');
  const lockedObjectRef = useRef(null);
  const pendingGuidanceRef = useRef(null); // curiosity guidance
  const nudgeGuidanceRef = useRef(null);   // mind-wandering guidance
  const nudgeModeRef = useRef(false);
  const canStartGuidanceRef = useRef(false);
  const playedGuidanceOnceRef = useRef(false);
  const tipShownRef = useRef(false);
  const audioPlayerRef = useRef(null);
  const gazeIntervalRef = useRef(null);
  const idleTimerRef = useRef(null);
  const fullscreenImageRef = useRef(null);
  const toastTimerRef = useRef(null);
  const fixationHeartbeatRef = useRef(null);
  const lastHeartbeatTsRef = useRef(0);
  
  // STEP 1: Request cancellation system
  const activeRequestRef = useRef(null);
  const pendingRequestsRef = useRef(new Set());

  // STEP 1: Helper functions for request management
  const generateRequestId = (type, imageFilename, objectIndex = null) => {
    const timestamp = Date.now();
    const objPart = objectIndex ? `_${objectIndex}` : '';
    return `${type}_${imageFilename}${objPart}_${timestamp}`;
  };

  const cancelActiveGuidance = (reason = 'new request') => {
    if (activeRequestRef.current) {
      console.log(`🚫 [STEP1] Cancelling active guidance request: ${activeRequestRef.current} (${reason})`);
      pendingRequestsRef.current.delete(activeRequestRef.current);
      activeRequestRef.current = null;
    }
  };

  const registerGuidanceRequest = (requestId, type) => {
    // Cancel any existing request
    cancelActiveGuidance('new guidance request');
    
    // Register new request
    activeRequestRef.current = requestId;
    pendingRequestsRef.current.add(requestId);
    console.log(`✅ [STEP1] Registered ${type} guidance request: ${requestId}`);
  };

  const isRequestActive = (requestId) => {
    return activeRequestRef.current === requestId && pendingRequestsRef.current.has(requestId);
  };

  const completeGuidanceRequest = (requestId, reason = 'completed') => {
    if (pendingRequestsRef.current.has(requestId)) {
      pendingRequestsRef.current.delete(requestId);
      if (activeRequestRef.current === requestId) {
        activeRequestRef.current = null;
      }
      console.log(`🧹 [STEP1] Completed guidance request: ${requestId} (${reason})`);
    }
  };

  // Label-map assets and fixation buffers
  const labelCanvasRef = useRef(null);
  const labelCtxRef = useRef(null);
  const labelReadyRef = useRef(false);
  const indexToObjectRef = useRef(new Map());
  const labelHistoryRef = useRef([]);
  const lastSelectedLabelRef = useRef(0);
  const cropTimerRef = useRef(null);
  const lastCropKeyRef = useRef(null);
  const lastCropTsRef = useRef(0);
  const fixationStartTsRef = useRef(0);
  const lastAoiIndexRef = useRef(0);

  // Sample images from the pictures folder
  const allImages = [
    'http://localhost:8001/pictures/1.jpg',
    'http://localhost:8001/pictures/2.jpg',
    'http://localhost:8001/pictures/3.jpg',
    'http://localhost:8001/pictures/4.jpg',
    'http://localhost:8001/pictures/5.jpg'
  ];

  // Now showing 1 image per page
  const totalPages = allImages.length;

  // Get current page image
  const getCurrentPageImage = () => {
    return allImages[currentPage];
  };

  const speakTTS = async (text) => {
    try {
      const fd = new FormData();
      fd.append('text', text);
      fd.append('language', 'en-US');
      fd.append('voice', ttsVoiceRef.current);
      const r = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
      if (r.ok) {
        const d = await r.json();
        return `http://localhost:8001${d.audio_url}`;
      }
    } catch {}
    return null;
  };

  const showParentNotice = (type, text) => {
    if (!isParentMode || parentSupport !== 'basic') {
      return;
    }
    
    // Persistent notice until parent confirms
    if (parentNoticeTimerRef.current) {
      clearTimeout(parentNoticeTimerRef.current);
      parentNoticeTimerRef.current = null;
    }
    setParentNotice({ type, text, ts: Date.now() });
    // Freeze gaze tracking while notice is shown (fullscreen only) and auto-unfreeze after timeout
    try {
      if (isFullscreenMode) {
        const imageFilename = getCurrentImageFilename();
        const fdFreeze = new FormData();
        fdFreeze.append('image_filename', imageFilename);
        fdFreeze.append('frozen', 'true');
        fdFreeze.append('child_name', childName || '');
        fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
      }
    } catch {}
    // No auto-clear; stays until parent taps Got it
  };

  // Unified banner logic for both parent modes
  const showImmediateParentBanner = (type) => {
    if (isParentBasic) {
      // Keep existing simple notice for basic mode
      showParentNotice(type, buildParentBasicText(type));
    } else if (isParentGuided) {
      // Show immediate placeholder panel for guided mode
      // Different messages for curiosity vs mindwandering
      const placeholderMessage = type === 'mindwandering' 
        ? "We detected your child is mindwandering… preparing a suggestion…"
        : "We detected your child is interested here… preparing a suggestion…";
      
      setParentGuidedPanel({
        type: type, // 'curiosity' or 'mindwandering'
        data: { 
          question: placeholderMessage, 
          follow_up: "Please wait while we analyze this area.",
          pending_message: "Analyzing..."
        },
        ts: Date.now(),
        pending: true // Flag to indicate this is placeholder content
      });
    }
  };

  // Unfreeze whenever a notice is programmatically cleared
  React.useEffect(() => {
    if (!isParentBasic) return;
    if (parentNotice == null) {
      try {
        if (isFullscreenMode) {
          const imageFilename = getCurrentImageFilename();
          const fdUnfreeze = new FormData();
          fdUnfreeze.append('image_filename', imageFilename);
          fdUnfreeze.append('frozen', 'false');
          fdUnfreeze.append('child_name', childName || '');
          fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze });
        }
      } catch {}
    }
  }, [parentNotice, isParentBasic, isFullscreenMode]);

  // Freeze gaze tracking while guided panel is visible (fullscreen), unfreeze when dismissed
  React.useEffect(() => {
    if (!isParentGuided) return;
    try {
      if (parentGuidedPanel && isFullscreenMode) {
        const imageFilename = getCurrentImageFilename();
        const fdFreeze = new FormData();
        fdFreeze.append('image_filename', imageFilename);
        fdFreeze.append('frozen', 'true');
        fdFreeze.append('child_name', childName || '');
        fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
      }
    } catch {}
  }, [parentGuidedPanel, isParentGuided, isFullscreenMode, childName]);

  // Removed useEffect - using direct freeze calls before setAssistantState instead

  // Consistent short, rule-based text for parent basic notices
  const buildParentBasicText = (type) => {
    if (type === 'curiosity') {
      return 'Curiosity: Ask one short question about this.';
    }
    return 'Attention: Gently bring focus back here with a simple cue.';
  };

  // Utilities to compose a parent-guided script from existing LLM fields
  const truncateWords = (text, maxWords) => {
    try {
      if (!text) return '';
      const words = String(text).split(/\s+/).filter(Boolean);
      if (words.length <= maxWords) return String(text);
      return words.slice(0, maxWords).join(' ') + '…';
    } catch {
      return String(text || '');
    }
  };

  const withPunctuation = (text) => {
    if (!text) return '';
    const s = String(text).trim();
    if (!s) return '';
    return /[.!?]$/.test(s) ? s : s + '.';
  };

  const stripLeadingHint = (text) => {
    try {
      const s = String(text || '').trim();
      return s.replace(/^hint\s*:\s*/i, '');
    } catch {
      return String(text || '');
    }
  };

  const composeParentGuidedScript = (panel) => {
    const data = panel?.data || {};
    // Prefer new backend fields if present
    if (data.hook || data.question || data.hint || data.follow_up || data.answer) {
      const hook = data.hook || '';
      const question = data.question || '';
      const answer = (typeof data.answer === 'string') ? stripLeadingHint(data.answer).trim() : '';
      const hint = (typeof data.hint === 'string') ? stripLeadingHint(data.hint).trim() : '';
      const followUp = data.follow_up || '';
      return { hook, question, answer, hint, followUp };
    }
    if (panel?.type === 'mindwandering') {
      // For parent nudge mode, use parent_cue and exploratory_question
      // For child nudge mode, use attention_hook and rephrased_question
      const hook = data.parent_cue || data.attention_hook || "Let's take a look here!";
      const question = data.exploratory_question || data.rephrased_question || '';
      const hint = '';
      const followUp = 'Point to it with your finger.';
      return { hook, question, hint, followUp };
    }
    // Curiosity guidance
    const rawHook = data.simple_explanation || '';
    const hook = rawHook ? withPunctuation(truncateWords(rawHook, 8)) : 'Wow, look at this!';
    const question = data.guided_question || data.question_repeat || '';
    const baseHint = stripLeadingHint(data.simple_explanation || '');
    const hint = baseHint ? ('Hint: ' + truncateWords(baseHint, 12)) : '';
    const followUp = data.follow_up_activity || 'Can you point to it at home?';
    return { hook, question, hint, followUp };
  };

  const playGuidanceFromPending = async () => {
    if (isParentAny) return;
    const guidance = pendingGuidanceRef.current;
    if (!guidance || playedGuidanceOnceRef.current) return;
    const text = `${guidance.simple_explanation || ''} ${guidance.guided_question || ''}`.trim();
    const url = await speakTTS(text);
    playedGuidanceOnceRef.current = true;
    setAssistantState({ visible: true, phase: 'guidance', image: 'question', text, audioUrl: url, guidance, showActions: false });
  };

  const playNudgeFromPending = async () => {
    if (isParentAny) return;
    const guidance = nudgeGuidanceRef.current;
    if (!guidance) return;
    const text = `${guidance.attention_hook || ''} ${guidance.rephrased_question || ''}`.trim();
    const url = await speakTTS(text);
    setAssistantState({ visible: true, phase: 'guidance', image: 'question', text, audioUrl: url, guidance, showActions: false });
  };

  const getCurrentImageFilename = () => {
    const url = getCurrentPageImage();
    return url.split('/').pop();
  };

  // Get current page mask image
  const getCurrentPageMaskImage = () => {
    const imageNumber = currentPage + 1;
    return `http://localhost:8001/segmented_pictures/${imageNumber}_masks.jpg`;
  };

  const handleImageSelect = (imagePath) => {
    const newSelected = new Set(selectedImages);
    if (newSelected.has(imagePath)) {
      newSelected.delete(imagePath);
    } else {
      newSelected.add(imagePath);
    }
    setSelectedImages(newSelected);
    setNarrationData(null);
    setError(null);
  };

  const handleNextPage = () => {
    if (currentPage < totalPages - 1) {
      setCurrentPage(currentPage + 1);
      setSelectedImages(new Set());
      setNarrationData(null);
      setShowTranscript(false);
      setError(null);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 0) {
      setCurrentPage(currentPage - 1);
      setSelectedImages(new Set());
      setNarrationData(null);
      setShowTranscript(false);
      setError(null);
    }
  };

  const handleToggleTranscript = () => {
    setShowTranscript(!showTranscript);
  };

  const handleEnterEyeTrackingMode = async (userGesture = true) => {
    // GUARD: Don't start if already active, but allow fullscreen upgrade
    if ((isEyeTrackingActive || gazeIntervalRef.current) && !userGesture) {
      console.log('⚠️ Eye tracking already active - skipping auto-start');
      return;
    }
    
    // For user gesture (double-click), allow fullscreen upgrade even if tracking active
    if (userGesture && isEyeTrackingActive && !isFullscreenMode) {
      console.log('🖥️ Upgrading to fullscreen mode...');
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
      setIsFullscreenMode(true);
      return;
    }
    
    try {
      console.log('🎯 Starting Eye-Tracking Mode...');

      // Step 1: Connect to Tobii eye tracker
      console.log('🔌 Connecting to Tobii Pro Fusion...');
      const connectResponse = await fetch('http://localhost:8001/eye-tracking/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const connectResult = await connectResponse.json();
      console.log('Connection result:', connectResult);

      if (!connectResult.success) {
        throw new Error(connectResult.message || 'Failed to connect to eye tracker');
      }

      // Step 2: Set current image context
      const currentImageFile = getCurrentPageImage().split('/').pop(); // Extract filename
      console.log(`📸 Setting image context to: ${currentImageFile}`);

      const imageFormData = new FormData();
      imageFormData.append('image_filename', currentImageFile);

      const setImageResponse = await fetch('http://localhost:8001/eye-tracking/set-image', {
        method: 'POST',
        body: imageFormData,
      });

      const setImageResult = await setImageResponse.json();
      console.log('Set image result:', setImageResult);

      // Step 3: Start eye tracking
      console.log('👁️ Starting gaze data collection...');
      const startResponse = await fetch('http://localhost:8001/eye-tracking/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const startResult = await startResponse.json();
      console.log('Start tracking result:', startResult);

      if (!startResult.success) {
        throw new Error(startResult.message || 'Failed to start eye tracking');
      }

      // Step 4: Enter browser fullscreen (requires user gesture)
      if (userGesture) {
        console.log('🖥️ Entering fullscreen mode...');
        if (document.documentElement.requestFullscreen) {
          await document.documentElement.requestFullscreen();
        }
        setIsFullscreenMode(true);
      } else {
        // Skip fullscreen when not triggered by a gesture to avoid Permission errors
        console.log('⚠️ Skipping fullscreen (no user gesture)');
      }
      setIsEyeTrackingActive(true);

      // Load label-map assets before polling
      await loadLabelAssetsForCurrentImage();

      // Start real-time gaze data fetching
      startGazeDataPolling();

      console.log('✅ Eye-Tracking Mode activated successfully!');

    } catch (error) {
      console.error('❌ Failed to enter Eye-Tracking Mode:', error);
      alert(`Failed to start Eye-Tracking Mode: ${error.message}`);
      // Still show fullscreen mode even if eye tracking fails
      setIsFullscreenMode(true);
    }
  };

  const startGazeDataPolling = () => {
    // CLEANUP: Clear any existing intervals first
    if (gazeIntervalRef.current) {
      console.log('🧹 Cleaning up existing gaze polling interval');
      clearInterval(gazeIntervalRef.current);
      gazeIntervalRef.current = null;
    }
    
    console.log('🎯 Starting gaze data polling...');
    // Poll for gaze data every 50ms (20 FPS)
    gazeIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:8001/eye-tracking/gaze-data');
        const result = await response.json();

        if (result.success && result.current_position) {
          setGazeData(result.current_position); // Always show gaze indicator
          
          // ONLY process gaze for fixations when NOT frozen
          if (!isGazeFrozen) {
            processGazeForObject(result.current_position);
            resetIdleNudgeTimer();
          } else {
            console.log('⏸️ GAZE FROZEN: Gaze processing paused');
          }
        }
      } catch (error) {
        console.error('❌ Error fetching gaze data:', error);
      }
    }, 50);
  };

  const stopGazeDataPolling = () => {
    if (gazeIntervalRef.current) {
      clearInterval(gazeIntervalRef.current);
      gazeIntervalRef.current = null;
    }
    setGazeData(null);
    clearIdleNudgeTimer();
  };

  const clearIdleNudgeTimer = () => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
  };

  const resetIdleNudgeTimer = () => {
    clearIdleNudgeTimer();
    // 5 seconds of no processed gaze => mindwandering
    idleTimerRef.current = setTimeout(async () => {
      // GUARD: Only block mindwandering if user has truly exited fullscreen mode
      const actuallyInFullscreen = !!document.fullscreenElement;
      console.log(`🔍 DEBUG: Fullscreen check - React state: ${isFullscreenMode}, DOM state: ${actuallyInFullscreen}`);
      
      if (!actuallyInFullscreen) {
        console.log('🚫 DEBUG: Skipping mindwandering - not in actual fullscreen mode');
        return;
      }
      
      console.log('✅ DEBUG: Mindwandering detection triggered - 5s idle detected');
      
      // STEP 1: Declare requestId outside try block so it's accessible in catch
      let requestId = null;
      
      try {
        const imageFilename = getCurrentImageFilename();
        
        // STEP 1: Generate request ID and register it
        requestId = generateRequestId('mindwandering', imageFilename);
        registerGuidanceRequest(requestId, 'mindwandering');
        
        const fd = new FormData();
        fd.append('image_filename', imageFilename);
        // For mindwandering, mark mode=mindwandering and audience/assistance
        fd.append('mode', 'mindwandering');
        if (isParentMode) {
          fd.append('audience', 'parent');
          fd.append('assistance', parentSupport === 'guided' ? 'parent_guided' : 'parent_basic');
        } else {
          fd.append('assistance', 'child');
        }
        fd.append('child_name', childName || '');
        
        const resp = await fetch('http://localhost:8001/aoi/mindwandering', { method: 'POST', body: fd });
        if (!resp.ok) {
          // STEP 1: Complete request on error
          completeGuidanceRequest(requestId, 'API error');
          return;
        }
        const data = await resp.json();
        if (data && data.success) {
          // STEP 1: Check if request is still active before processing
          if (!isRequestActive(requestId)) {
            console.log(`🚫 [STEP1] Ignoring cancelled mindwandering request: ${requestId}`);
            return;
          }
          // CRITICAL: Set nudge mode FIRST before any other operations
          nudgeModeRef.current = true;
          console.log(`🎯 DEBUG: nudgeModeRef set to TRUE for mindwandering`);
          
          // lock highlight to nudged AOI and show assistant intro
          const obj = indexToObjectRef.current.get(data.index) || null;
          if (obj) lockedObjectRef.current = obj;
          // Trigger assistant intro immediately
          const introText = "Hi! I found something you might like. Please give me a moment while I think of a fun idea.";
          let introAudioUrl = null;
          if (!isParentBasic) {
            const fdtts = new FormData();
            fdtts.append('text', introText);
            fdtts.append('language', 'en-US');
            fdtts.append('voice', 'en-US-AnaNeural');
            try {
              const r = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fdtts });
              if (r.ok) { const j = await r.json(); introAudioUrl = `http://localhost:8001${j.audio_url}`; }
            } catch {}
          }
          // Unified parent banner for mindwandering attention shift
          showImmediateParentBanner('mindwandering');
          if (!isParentAny) {
            // FREEZE IMMEDIATELY before showing assistant
            try {
              const fdFreeze = new FormData();
              fdFreeze.append('image_filename', imageFilename);
              fdFreeze.append('frozen', 'true');
              fdFreeze.append('child_name', childName || '');
              fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
            } catch {}
            
            setAssistantState({ visible: true, phase: 'intro', image: 'hi', text: introText, audioUrl: introAudioUrl, guidance: null, showActions: false });
          }

          // If guidance path provided, fetch it; else poll standard log
          let guidance = null;
          if (data.guidance_path) {
            try {
              const gp = data.guidance_path.startsWith('http') ? data.guidance_path : `http://localhost:8001${data.guidance_path}`;
              const gr = await fetch(gp, { cache: 'no-store' });
              if (gr.ok) guidance = await gr.json();
            } catch {}
          }
          if (!guidance) {
            // fallback: poll responses log
            const imageName = imageFilename.split('.').shift();
            setTimeout(async () => {
              try {
                const audience = (isParentMode && parentSupport === 'guided') ? 'parent' : 'child';
                const mode = 'mindwandering';
                const safeChild = (childName || 'default').replace(/[^A-Za-z0-9_\-]/g, '_');
                const log = await fetch(`http://localhost:8001/responses/question/${safeChild}/${imageName}_${mode}_${audience}_eyetracking_guidance.json?t=${Date.now()}`);
                if (log.ok) {
                  const events = await log.json();
                  const filtered = events.filter(ev => ev.object_id === data.object_id);
                  if (filtered.length) {
                    const latest = filtered[filtered.length - 1];
                    const gUrl = latest.guidance_path.startsWith('http') ? latest.guidance_path : `http://localhost:8001${latest.guidance_path}`;
                    const gResp = await fetch(gUrl);
                    if (gResp.ok) guidance = await gResp.json();
                  }
                }
              } catch {}
            }, 1200);
          }

          // store guidance for later playback after intro ends
          if (!isParentAny) {
            if (guidance) {
              nudgeGuidanceRef.current = guidance;
              if (canStartGuidanceRef.current) {
                await playNudgeFromPending();
              }
            } else {
              // If no immediate guidance, start polling for mindwandering guidance
              const imageName = imageFilename.split('.').shift();
              setTimeout(async () => {
                try {
                  console.log(`🔍 DEBUG: Starting mindwandering guidance polling for ${data.object_id}`);
                  // Use explicit mindwandering mode for polling
                  const audience = (isParentMode && parentSupport === 'guided') ? 'parent' : 'child';
                  const safeChild = (childName || 'default').replace(/[^A-Za-z0-9_\-]/g, '_');
                  const mindwanderingUrl = `http://localhost:8001/responses/question/${safeChild}/${imageName}_mindwandering_${audience}_eyetracking_guidance.json?t=${Date.now()}`;
                  console.log(`🔍 Polling mindwandering guidance at: ${mindwanderingUrl}`);
                  
                  const log = await fetch(mindwanderingUrl, { cache: 'no-store' });
                  if (log.ok) {
                    const events = await log.json();
                    const filtered = events.filter(ev => ev.object_id === data.object_id);
                    if (filtered.length) {
                      const latest = filtered[filtered.length - 1];
                      const gUrl = latest.guidance_path.startsWith('http') ? latest.guidance_path : `http://localhost:8001${latest.guidance_path}`;
                      const gResp = await fetch(gUrl);
                      if (gResp.ok) {
                        const mindwanderingGuidance = await gResp.json();
                        console.log(`✅ Mindwandering guidance loaded:`, mindwanderingGuidance);
                        nudgeGuidanceRef.current = mindwanderingGuidance;
                        
                        // Update parent guided panel with mindwandering guidance
                        if (isParentGuided) {
                          setParentGuidedPanel({ 
                            type: 'mindwandering', 
                            data: mindwanderingGuidance, 
                            ts: Date.now(), 
                            pending: false 
                          });
                        }
                      }
                    }
                  }
                } catch (e) {
                  console.warn('Mindwandering guidance polling failed:', e);
                }
              }, 1200);
            }
          }
          
          // STEP 1: Complete the request after processing
          completeGuidanceRequest(requestId, 'processing complete');
        } else {
          // STEP 1: Complete request if not successful
          completeGuidanceRequest(requestId, 'API returned not successful');
        }
      } catch (e) {
        console.warn('Idle mindwandering failed:', e);
        // STEP 1: Complete request on error (only if requestId was created)
        if (requestId) {
          completeGuidanceRequest(requestId, 'exception caught');
        }
      }
    }, 5000);
  };

  const handleExitFullscreen = async () => {
    try {
      console.log('🛑 Exiting Eye-Tracking Mode...');

      // Stop gaze data polling and clear all timers
      stopGazeDataPolling();
      clearIdleNudgeTimer(); // Clear mindwandering timer immediately
      setIsEyeTrackingActive(false);
      
      // STEP 1: Cancel any active guidance requests
      cancelActiveGuidance('exiting fullscreen');

      // finalize any ongoing fixation to AOI log
      await finalizeCurrentFixation();

      // Don't reset gaze data - preserve it for analysis
      // Removed automatic reset that was deleting saved files
      console.log('✅ Preserving gaze data files for analysis');

      // Stop eye tracking
      console.log('⏸️ Stopping gaze data collection...');
      const stopResponse = await fetch('http://localhost:8001/eye-tracking/stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const stopResult = await stopResponse.json();
      console.log('Stop tracking result:', stopResult);

    } catch (error) {
      console.error('⚠️ Error stopping eye tracking:', error);
      // Continue with exit even if stopping fails
    }

    setIsFullscreenMode(false);
    setCurrentObject(null);
    setLastCrop(null);
    setAssistantState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
    labelHistoryRef.current = [];
    lastSelectedLabelRef.current = 0;
    labelReadyRef.current = false;
    // Exit browser fullscreen if active
    if (document.exitFullscreen && document.fullscreenElement) {
      document.exitFullscreen().catch(console.error);
    }

    console.log('✅ Eye-Tracking Mode deactivated');
  };

  // Auto-enter eye-tracking on mount (enter fullscreen & start tracking)
  React.useEffect(() => {
    // Add delay to avoid React StrictMode double-execution
    const timer = setTimeout(() => {
      if (!isFullscreenMode && !isEyeTrackingActive && !gazeIntervalRef.current) {
        console.log('🚀 Auto-starting eye tracking on mount');
        handleEnterEyeTrackingMode(false);
      }
    }, 100);
    
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // One-time tip per mount: show assistant instruction to double-click to start
  React.useEffect(() => {
    if (tipShownRef.current) return;
    tipShownRef.current = true;
    const text = "When you're ready, double-click the picture to start!";
    (async () => {
      if (!isParentAny) {
        // Show bubble immediately; load TTS in background
        setAssistantState({ visible: true, phase: 'tip', image: 'read', text, audioUrl: null, guidance: null, showActions: false });
        let url = null;
        try {
          const fd = new FormData();
          fd.append('text', text);
          fd.append('language', 'en-US');
          fd.append('voice', ttsVoiceRef.current);
          const r = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
          if (r.ok) { const d = await r.json(); url = `http://localhost:8001${d.audio_url}`; }
        } catch {}
        if (url) setAssistantState(prev => ({ ...prev, audioUrl: url }));
      }
    })();
  }, []);

  // Listen for keyboard shortcuts in fullscreen mode
  React.useEffect(() => {
    const handleKeyDown = (event) => {
      if (isFullscreenMode) {
        if (event.key === 'Escape') {
          handleExitFullscreen();
        } else if (event.key === 's' || event.key === 'S') {
          // Toggle mask display
          setShowMasks(prev => !prev);
          console.log(`🎭 ${showMasks ? 'Hiding' : 'Showing'} segmentation masks`);
        } else if (event.key === 'c' || event.key === 'C') {
          // Force capture crop of current object
          if (isEyeTrackingActive && currentObject) {
            triggerCropCapture(currentObject);
          }
        }
      }
    };

    const handleFullscreenChange = () => {
      // If browser exits fullscreen but component thinks it's still fullscreen
      if (!document.fullscreenElement && isFullscreenMode) {
        handleExitFullscreen(); // Use full cleanup instead of just setIsFullscreenMode(false)
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('fullscreenchange', handleFullscreenChange);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, [isFullscreenMode]);

  // Cleanup gaze polling on component unmount
  React.useEffect(() => {
    return () => {
      stopGazeDataPolling();
      clearIdleNudgeTimer(); // Ensure mindwandering timer is cleared
      if (fixationHeartbeatRef.current) {
        clearInterval(fixationHeartbeatRef.current);
        fixationHeartbeatRef.current = null;
      }
      lastHeartbeatTsRef.current = 0;
    };
  }, []);

  const generateDescription = async () => {
    if (selectedImages.size === 0) {
      setError('Please select at least one image!');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Get all selected image URLs and extract filenames
      const selectedImageUrls = Array.from(selectedImages);
      const imageFilenames = selectedImageUrls.map(url => url.split('/').pop()); // e.g., ["1.png", "2.png"]

      // Join filenames with commas for the backend
      const filenamesString = imageFilenames.join(',');

      // Use the backend endpoint that accepts multiple image filenames
      const formData = new FormData();
      formData.append('image_filenames', filenamesString);

      formData.append('language', language);

      const apiResponse = await fetch('http://localhost:8001/generate-from-filename', {
        method: 'POST',
        body: formData,
      });

      if (!apiResponse.ok) {
        const errorData = await apiResponse.json();
        throw new Error(errorData.detail || 'Failed to generate description');
      }

      const data = await apiResponse.json();
      setNarrationData(data);

      // Auto-play audio if available
      if (data.audio_url) {
        setTimeout(() => {
          if (audioPlayerRef.current && audioPlayerRef.current.play) {
            try {
              audioPlayerRef.current.play();
              console.log('Audio auto-play started successfully');
            } catch (error) {
              console.log('Auto-play failed, user interaction may be required:', error);
              // Audio auto-play failed, but that's okay - user can click play manually
            }
          }
        }, 800); // Give a bit more time for the component to render
      }

    } catch (err) {
      console.error('Error generating description:', err);
      setError(err.message || 'Something went wrong. Please try again!');
    } finally {
      setIsLoading(false);
    }
  };

  // AOI fixation posting helpers
  const postFixation = async (index, durationMs) => {
    const imageFilename = getCurrentImageFilename(); // Move to top
    try {
      const form = new FormData();
      form.append('image_filename', imageFilename);
      form.append('object_index', String(index));
      form.append('duration_ms', String(Math.max(0, Math.round(durationMs))));
      form.append('mode', 'curiosity');
      if (isParentMode) form.append('audience', 'parent');
      // Assistance tagging for AOI separation
      form.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
      form.append('child_name', childName || '');
      const resp = await fetch('http://localhost:8001/aoi/fixation', { method: 'POST', body: form });
      try {
        const data = await resp.json();
        if (data && data.success && data.just_saved && data.crop_url) {
          const url = data.crop_url.startsWith('http') ? data.crop_url : `http://localhost:8001${data.crop_url}`;
          setLastCrop({ url, object_id: `idx${index}`, ts: Date.now() });
          // Child-alone assistant intro + TTS; in parent basic mode, suppress voice/LLM
          const introText = "Hi! I can see you're really curious about this. I'm here to help. Please give me a moment while I think of a good idea.";
          let introAudioUrl = null;
          if (!isParentBasic) {
            const fd = new FormData();
            fd.append('text', introText);
            fd.append('language', 'en-US');
            fd.append('voice', ttsVoiceRef.current);
            try {
              const ttsResp = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
              if (ttsResp.ok) {
                const ttsData = await ttsResp.json();
                introAudioUrl = `http://localhost:8001${ttsData.audio_url}`;
              }
            } catch {}
          }
          // Block duplicate guidance while assistant is active
          if (assistantState.visible) {
            console.log('🚫 DEBUG: Blocking duplicate guidance - assistant already active');
            return;
          }
          
          // Ensure we are in curiosity mode (not mindwandering) for this flow
          nudgeModeRef.current = false;
          nudgeGuidanceRef.current = null;
          pendingGuidanceRef.current = null;
          canStartGuidanceRef.current = false;
          playedGuidanceOnceRef.current = false;
          lockedObjectRef.current = indexToObjectRef.current.get(index) || null;
          // Unified parent banner for both modes
          showImmediateParentBanner('curiosity');
          // Keep notice visible during parent-basic; auto-clear when object changes again
          if (!isParentAny) {
            // FREEZE IMMEDIATELY before showing assistant
            try {
              const fdFreeze = new FormData();
              fdFreeze.append('image_filename', imageFilename);
              fdFreeze.append('frozen', 'true');
              fdFreeze.append('child_name', childName || '');
              const response = await fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
              if (response.ok) {
                setIsGazeFrozen(true); // Set local freeze state
                
                // STOP heartbeat timer when frozen
                if (fixationHeartbeatRef.current) {
                  clearInterval(fixationHeartbeatRef.current);
                  fixationHeartbeatRef.current = null;
                }
              }
            } catch (error) {
              // Silent error handling
            }
            
            setAssistantState({ visible: true, phase: 'intro', image: 'hi', text: introText, audioUrl: introAudioUrl, guidance: null, showActions: false });
          }
          // Kick off polling for guidance json saved by backend
          const imageName = imageFilename.split('.').shift();
          const objectId = `idx${index}`;
          // Removed duplicate freeze call - already done above

          // Verify crop file exists; if missing, force-generate via crops/extract
          try {
            const headResp = await fetch(url, { method: 'GET', cache: 'no-store' });
            if (!headResp.ok) {
              const form2 = new FormData();
              form2.append('image_filename', imageFilename);
              form2.append('object_index', String(index));
              form2.append('include_alpha', 'true');
              const r2 = await fetch('http://localhost:8001/crops/extract', { method: 'POST', body: form2 });
              if (r2.ok) {
                const d2 = await r2.json();
                if (d2 && d2.success && d2.url) {
                  const ensuredUrl = d2.url.startsWith('http') ? d2.url : `http://localhost:8001${d2.url}`;
                  setLastCrop({ url: ensuredUrl, object_id: `idx${index}`, ts: Date.now() });
                }
              }
            }
          } catch {}
          // Start guidance polling for child-alone and parent-guided modes
          if (!isParentBasic) {
            startGuidancePolling(imageName, objectId);
          }
          if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
          toastTimerRef.current = setTimeout(() => setLastCrop(null), 2000);
        }
      } catch {}
    } catch (e) {
      console.error('AOI fixation post failed:', e);
    }
  };

  const postFixationProgress = async (index, deltaMs) => {
    try {
      const imageFilename = getCurrentImageFilename();
      const form = new FormData();
      form.append('image_filename', imageFilename);
      form.append('object_index', String(index));
      form.append('duration_ms', String(Math.max(0, Math.round(deltaMs))));
      form.append('phase', 'progress');
      form.append('mode', 'curiosity');
      if (isParentMode) form.append('audience', 'parent');
      form.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
      form.append('child_name', childName || '');
      const resp = await fetch('http://localhost:8001/aoi/fixation', { method: 'POST', body: form });
      try {
        const data = await resp.json();
        if (data && data.success && data.just_saved && data.crop_url) {
          const url = data.crop_url.startsWith('http') ? data.crop_url : `http://localhost:8001${data.crop_url}`;
          setLastCrop({ url, object_id: `idx${index}`, ts: Date.now() });
          const introText = "Hi! I can see you're really curious about this. I'm here to help. Please give me a moment while I think of a good idea.";
          let introAudioUrl = null;
          if (!isParentAny) {
            const fd = new FormData();
            fd.append('text', introText);
            fd.append('language', 'en-US');
            fd.append('voice', ttsVoiceRef.current);
            try {
              const ttsResp = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
              if (ttsResp.ok) {
                const ttsData = await ttsResp.json();
                introAudioUrl = `http://localhost:8001${ttsData.audio_url}`;
              }
            } catch {}
          }
          nudgeModeRef.current = false;
          nudgeGuidanceRef.current = null;
          pendingGuidanceRef.current = null;
          canStartGuidanceRef.current = false;
          playedGuidanceOnceRef.current = false;
          lockedObjectRef.current = indexToObjectRef.current.get(index) || null;
          // Unified parent banner for both modes (progress)
          showImmediateParentBanner('curiosity');
          if (!isParentBasic) {
            setAssistantState({ visible: true, phase: 'intro', image: 'hi', text: introText, audioUrl: introAudioUrl, guidance: null, showActions: false });
          }
          const imageName = imageFilename.split('.').shift();
          const objectId = `idx${index}`;
          if (!isParentBasic) {
            try {
              const fdFreeze = new FormData();
              fdFreeze.append('image_filename', imageFilename);
              fdFreeze.append('frozen', 'true');
              fdFreeze.append('child_name', childName || '');
              fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
            } catch {}
            startGuidancePolling(imageName, objectId);
          }
          if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
          toastTimerRef.current = setTimeout(() => setLastCrop(null), 2000);
          stopFixationHeartbeat();
          
          // CRITICAL: Post end event to finalize this fixation in the log
          try {
            const totalDuration = Date.now() - fixationStartTsRef.current;
            const endForm = new FormData();
            endForm.append('image_filename', imageFilename);
            endForm.append('object_index', String(index));
            endForm.append('duration_ms', String(Math.max(0, Math.round(totalDuration))));
            endForm.append('phase', 'end');
            endForm.append('mode', 'curiosity');
            if (isParentMode) endForm.append('audience', 'parent');
            endForm.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
            endForm.append('child_name', childName || '');
            fetch('http://localhost:8001/aoi/fixation', { method: 'POST', body: endForm });
          } catch {}
          
          // Reset fixation tracking
          fixationStartTsRef.current = 0;
          lastAoiIndexRef.current = 0;
        }
      } catch {}
    } catch (e) {
      // ignore network errors for progress heartbeats
    }
  };

  const stopFixationHeartbeat = () => {
    if (fixationHeartbeatRef.current) {
      clearInterval(fixationHeartbeatRef.current);
      fixationHeartbeatRef.current = null;
    }
    lastHeartbeatTsRef.current = 0;
  };

  const startFixationHeartbeat = () => {
    stopFixationHeartbeat();
    lastHeartbeatTsRef.current = Date.now();
    fixationHeartbeatRef.current = setInterval(async () => {
      try {
        const idx = lastAoiIndexRef.current;
        const startedAt = fixationStartTsRef.current;
        if (!idx || !startedAt) return;
        const now = Date.now();
        const prev = lastHeartbeatTsRef.current || now;
        const delta = now - prev;
        if (delta > 0) {
          await postFixationProgress(idx, delta);
          lastHeartbeatTsRef.current = now;
        }
      } catch {}
    }, 1000);
  };

  const startGuidancePolling = async (imageName, objectId, explicitMode = null) => {
    // Immediately freeze gaze tracking, show highlight + placeholder banner in parent-guided
    try {
      const imageFilename = getCurrentImageFilename();
      const fdFreeze = new FormData();
      fdFreeze.append('image_filename', imageFilename);
      fdFreeze.append('frozen', 'true');
      fdFreeze.append('child_name', childName || '');
      fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
      // Do NOT stop eye-tracking; keep gaze indicator alive. We only freeze AOI writes.
      // Load labels to acquire bbox for highlight
      try {
        const labelsUrl = `http://localhost:8001/segmented_pictures/${imageName}_labels.json`;
        const lr = await fetch(labelsUrl, { cache: 'no-store' });
        if (lr.ok) {
          const lj = await lr.json();
          const found = (lj.objects || []).find(o => o.object_id === objectId);
          if (found) {
            lockedObjectRef.current = { index: found.index, bbox: found.bbox };
          }
        }
      } catch {}
      // Don't set placeholder here - it's already set by showImmediateParentBanner
    } catch {}

    let attempts = 0;
    const maxAttempts = 60; // up to ~30s if interval is 500ms
    const intervalMs = 500;
    const timer = setInterval(async () => {
      attempts += 1;
      
      // CHECK FREEZE STATE before each poll - respect freeze like fixation processing
      try {
        const freezeResponse = await fetch(`http://localhost:8001/aoi/freeze/status?image_filename=${imageName}.jpg&child_name=${encodeURIComponent(childName || '')}`);
        if (freezeResponse.ok) {
          const freezeData = await freezeResponse.json();
          if (freezeData.frozen) {
            return; // Skip this polling cycle
          }
        }
      } catch {
        // Continue polling if freeze check fails
      }
      
      try {
        const audience = (isParentMode && parentSupport === 'guided') ? 'parent' : 'child';
        // Use explicit mode if provided, otherwise check nudgeMode ref
        const canonicalMode = explicitMode || (nudgeModeRef.current ? PromptTypes.mindwandering : PromptTypes.curiosity);
        const alias = promptAliasForStorage(canonicalMode);
        const safeChild = (childName || 'default').replace(/[^A-Za-z0-9_\-]/g, '_');
        const primaryUrl = `http://localhost:8001/responses/question/${safeChild}/${imageName}_${alias}_${audience}_eyetracking_guidance.json?t=${Date.now()}`;
        const listResp = await fetch(primaryUrl, { cache: 'no-store' });
        if (listResp.ok) {
          const events = await listResp.json();
          // find latest for objectId
          const filtered = events.filter(ev => ev.object_id === objectId);
          if (filtered.length > 0) {
            const latest = filtered[filtered.length - 1];
            const guidanceUrl = latest.guidance_path.startsWith('http') ? latest.guidance_path : `http://localhost:8001${latest.guidance_path}`;
            const gResp = await fetch(guidanceUrl, { cache: 'no-store' });
            if (gResp.ok) {
              const guidance = await gResp.json();
              clearInterval(timer);
              // stash curiosity guidance; playback happens after intro/wait audio ends
              pendingGuidanceRef.current = guidance;
              if (isParentGuided && guidance) {
                setParentGuidedPanel({ type: nudgeModeRef.current ? 'mindwandering' : 'curiosity', data: guidance, ts: Date.now(), pending: false });
              }
            }
          }
        }
      } catch (e) {
        // Silent error handling
      }
      if (attempts >= maxAttempts) {
        clearInterval(timer);
        // Timeout: keep highlight and show a gentle fallback in banner (already present); guidance may still arrive later
        if (isParentGuided) {
          setParentGuidedPanel({ type: nudgeModeRef.current ? 'mindwandering' : 'curiosity', data: { question: "We think your child is interested here. Try asking: 'What's happening right here?'", follow_up: "What else do you notice?" }, ts: Date.now(), pending: false });
        }
      }
    }, intervalMs);
  };

  const finalizeCurrentFixation = async () => {
    if (!lastAoiIndexRef.current || !fixationStartTsRef.current) return;
    const duration = Date.now() - fixationStartTsRef.current;
    await postFixation(lastAoiIndexRef.current, duration);
    fixationStartTsRef.current = 0;
    if (fixationHeartbeatRef.current) {
      clearInterval(fixationHeartbeatRef.current);
      fixationHeartbeatRef.current = null;
    }
    lastHeartbeatTsRef.current = 0;
  };

  // Load label-map PNG + JSON for current image
  const loadLabelAssetsForCurrentImage = async () => {
    try {
      const imageNumber = currentPage + 1;
      const jsonUrl = `http://localhost:8001/segmented_pictures/${imageNumber}_labels.json`;
      const pngUrl = `http://localhost:8001/segmented_pictures/${imageNumber}_labels.png`;

      console.log('🧩 Loading label assets:', jsonUrl, pngUrl);

      // Load JSON mapping
      const mappingResp = await fetch(jsonUrl, { cache: 'no-store' });
      if (!mappingResp.ok) throw new Error('Failed to load labels JSON');
      const mapping = await mappingResp.json();
      const map = new Map();
      for (const obj of mapping.objects || []) {
        map.set(obj.index, obj);
      }
      indexToObjectRef.current = map;

      // Prepare offscreen canvas
      if (!labelCanvasRef.current) {
        labelCanvasRef.current = document.createElement('canvas');
      }

      // Load PNG and draw to canvas
      await new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          labelCanvasRef.current.width = img.naturalWidth;
          labelCanvasRef.current.height = img.naturalHeight;
          const ctx = labelCanvasRef.current.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(img, 0, 0);
          labelCtxRef.current = ctx;
          labelReadyRef.current = true;
          console.log('✅ Label map ready:', img.naturalWidth, 'x', img.naturalHeight);
          resolve();
        };
        img.onerror = reject;
        img.src = pngUrl + `?t=${Date.now()}`; // bust cache
      });

    } catch (e) {
      console.error('❌ Failed to load label assets:', e);
      labelReadyRef.current = false;
      indexToObjectRef.current = new Map();
    }
  };

  // Also reload label assets when page changes while in fullscreen
  React.useEffect(() => {
    if (isFullscreenMode) {
      loadLabelAssetsForCurrentImage();
      setCurrentObject(null);
      labelHistoryRef.current = [];
      lastSelectedLabelRef.current = 0;
    }
  }, [currentPage, isFullscreenMode]);

  // Convert viewport gaze point to image pixel and sample label index (0..255) with small spatial smoothing
  const sampleLabelAtGaze = (gaze) => {
    try {
      if (!labelReadyRef.current || !labelCtxRef.current || !fullscreenImageRef.current) return 0;
      const imgEl = fullscreenImageRef.current;
      const rect = imgEl.getBoundingClientRect();
      const nx = (gaze.x - rect.left) / rect.width;
      const ny = (gaze.y - rect.top) / rect.height;
      if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return 0;
      const px = Math.max(0, Math.min(imgEl.naturalWidth - 1, Math.floor(nx * imgEl.naturalWidth)));
      const py = Math.max(0, Math.min(imgEl.naturalHeight - 1, Math.floor(ny * imgEl.naturalHeight)));

      // Spatial smoothing (3x3 neighborhood mode)
      const counts = new Map();
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const sx = Math.max(0, Math.min(imgEl.naturalWidth - 1, px + dx));
          const sy = Math.max(0, Math.min(imgEl.naturalHeight - 1, py + dy));
          const data = labelCtxRef.current.getImageData(sx, sy, 1, 1).data;
          const label = data[0];
          counts.set(label, (counts.get(label) || 0) + 1);
        }
      }
      let modeLabel = 0;
      let modeCount = 0;
      counts.forEach((c, l) => {
        if (c > modeCount) {
          modeLabel = l;
          modeCount = c;
        }
      });
      return modeLabel;
    } catch (e) {
      console.error('Label sampling error:', e);
      return 0;
    }
  };

  // Turn gaze stream into fixation-based selection
  const processGazeForObject = async (gaze) => {
    if (!labelReadyRef.current) return;
    const now = Date.now();
    const label = sampleLabelAtGaze(gaze);

    // Update history window (<= 300ms)
    const windowMs = 300;
    const minFixationMs = 150;
    const minConfidence = 0.6;

    labelHistoryRef.current.push({ t: now, label });
    while (labelHistoryRef.current.length && (now - labelHistoryRef.current[0].t) > windowMs) {
      labelHistoryRef.current.shift();
    }

    // Compute mode and confidence
    const counts = new Map();
    for (const e of labelHistoryRef.current) {
      counts.set(e.label, (counts.get(e.label) || 0) + 1);
    }
    let modeLabel = 0;
    let modeCount = 0;
    counts.forEach((c, l) => {
      if (c > modeCount) {
        modeLabel = l;
        modeCount = c;
      }
    });

    const total = labelHistoryRef.current.length || 1;
    const confidence = modeCount / total;

    // Approximate dwell time for mode label
    const dwellMs = modeCount * 50; // polling is 50ms

    if (modeLabel !== 0 && confidence >= minConfidence && dwellMs >= minFixationMs) {
      if (lastSelectedLabelRef.current !== modeLabel) {
        // ALWAYS finalize previous fixation if exists before starting new one
        if (lastAoiIndexRef.current && fixationStartTsRef.current) {
          const duration = now - fixationStartTsRef.current;
          await postFixation(lastAoiIndexRef.current, duration);
        }
        // stop any running heartbeat for previous fixation
        if (fixationHeartbeatRef.current) {
          clearInterval(fixationHeartbeatRef.current);
          fixationHeartbeatRef.current = null;
        }
        lastHeartbeatTsRef.current = 0;
        // start new fixation clock
        lastAoiIndexRef.current = modeLabel;
        fixationStartTsRef.current = now;

        lastSelectedLabelRef.current = modeLabel;
        const obj = indexToObjectRef.current.get(modeLabel) || null;
        setCurrentObject(obj || null);
        // Do not auto-clear parent notice on object change; it should persist until parent dismisses
        // start heartbeat for this new fixation
        lastHeartbeatTsRef.current = Date.now();
        fixationHeartbeatRef.current = setInterval(async () => {
          try {
            const idx = lastAoiIndexRef.current;
            const startedAt = fixationStartTsRef.current;
            if (!idx || !startedAt) return;
            const nowTs = Date.now();
            const prev = lastHeartbeatTsRef.current || nowTs;
            const delta = nowTs - prev;
            if (delta > 0) {
              const imageFilename = getCurrentImageFilename();
              const form = new FormData();
              form.append('image_filename', imageFilename);
              form.append('object_index', String(idx));
              form.append('duration_ms', String(Math.max(0, Math.round(delta))));
              form.append('phase', 'progress');
      // Ensure correct audience/assistance tagging in parent mode for curiosity accumulation
      form.append('mode', 'curiosity');
      if (isParentMode) form.append('audience', 'parent');
      form.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
              form.append('child_name', childName || '');
              const resp = await fetch('http://localhost:8001/aoi/fixation', { method: 'POST', body: form });
              try {
                const data = await resp.json();
                if (data && data.success && data.just_saved && data.crop_url) {
                  const url = data.crop_url.startsWith('http') ? data.crop_url : `http://localhost:8001${data.crop_url}`;
                  setLastCrop({ url, object_id: `idx${idx}`, ts: Date.now() });
                  const introText = "Hi! I can see you're really curious about this. I'm here to help. Please give me a moment while I think of a good idea.";
                  let introAudioUrl = null;
                  if (!isParentBasic) {
                    const fd = new FormData();
                    fd.append('text', introText);
                    fd.append('language', 'en-US');
                    fd.append('voice', ttsVoiceRef.current);
                    try {
                      const ttsResp = await fetch('http://localhost:8001/tts/speak', { method: 'POST', body: fd });
                      if (ttsResp.ok) {
                        const ttsData = await ttsResp.json();
                        introAudioUrl = `http://localhost:8001${ttsData.audio_url}`;
                      }
                    } catch {}
                  }
                  // Block duplicate guidance while assistant is active
                  if (assistantState.visible) {
                    console.log('🚫 DEBUG: Blocking duplicate guidance - assistant already active (progress)');
                    return;
                  }
                  
                  nudgeModeRef.current = false;
                  nudgeGuidanceRef.current = null;
                  pendingGuidanceRef.current = null;
                  canStartGuidanceRef.current = false;
                  playedGuidanceOnceRef.current = false;
                  lockedObjectRef.current = indexToObjectRef.current.get(idx) || null;
          // Unified parent banner for both modes (progress heartbeat)
          showImmediateParentBanner('curiosity');
                  if (!isParentBasic) {
                    // FREEZE IMMEDIATELY before showing assistant
                    try {
                      const fdFreeze = new FormData();
                      fdFreeze.append('image_filename', imageFilename);
                      fdFreeze.append('frozen', 'true');
                      fdFreeze.append('child_name', childName || '');
                      fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
                            } catch {}
                    
                    setAssistantState({ visible: true, phase: 'intro', image: 'hi', text: introText, audioUrl: introAudioUrl, guidance: null, showActions: false });
                  }
                  const imageName = imageFilename.split('.').shift();
                  const objectId = `idx${idx}`;
                  if (!isParentBasic) {
                    try {
                      const fdFreeze = new FormData();
                      fdFreeze.append('image_filename', imageFilename);
                      fdFreeze.append('frozen', 'true');
                      fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdFreeze });
                    } catch {}
                    startGuidancePolling(imageName, objectId);
                  }
                  if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
                  toastTimerRef.current = setTimeout(() => setLastCrop(null), 2000);
                  // stop heartbeat to avoid repeated triggers
                  if (fixationHeartbeatRef.current) {
                    clearInterval(fixationHeartbeatRef.current);
                    fixationHeartbeatRef.current = null;
                  }
                  lastHeartbeatTsRef.current = 0;
                  
                  // CRITICAL: Post end event to finalize this fixation in the log
                  try {
                    const totalDuration = Date.now() - fixationStartTsRef.current;
                    const endForm = new FormData();
                    endForm.append('image_filename', imageFilename);
                    endForm.append('object_index', String(idx));
                    endForm.append('duration_ms', String(Math.max(0, Math.round(totalDuration))));
                    endForm.append('phase', 'end');
                    endForm.append('mode', 'curiosity');
                    if (isParentMode) endForm.append('audience', 'parent');
                    endForm.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
                    endForm.append('child_name', childName || '');
                    fetch('http://localhost:8001/aoi/fixation', { method: 'POST', body: endForm });
                  } catch {}
                  
                  // Reset fixation tracking
                  fixationStartTsRef.current = 0;
                  lastAoiIndexRef.current = 0;
                }
              } catch {}
            }
            lastHeartbeatTsRef.current = nowTs;
          } catch {}
        }, 1000);
      }
    } else {
      // Clear when background dominates long enough OR when switching to any other object
      if ((modeLabel === 0 && confidence >= 0.7 && dwellMs >= minFixationMs) || 
          (modeLabel !== lastSelectedLabelRef.current && lastSelectedLabelRef.current !== 0)) {
        if (lastAoiIndexRef.current && fixationStartTsRef.current) {
          const duration = now - fixationStartTsRef.current;
          await postFixation(lastAoiIndexRef.current, duration);
        }
        if (fixationHeartbeatRef.current) {
          clearInterval(fixationHeartbeatRef.current);
          fixationHeartbeatRef.current = null;
        }
        lastHeartbeatTsRef.current = 0;
        lastSelectedLabelRef.current = 0;
        lastAoiIndexRef.current = 0;
        fixationStartTsRef.current = 0;
        setCurrentObject(null);
      }
    }
  };

  // Trigger backend crop when a new object is stably selected
  React.useEffect(() => {
    if (!isFullscreenMode || !isEyeTrackingActive || !currentObject) return;
    // Debounce a bit to avoid bursts
    if (cropTimerRef.current) clearTimeout(cropTimerRef.current);
    cropTimerRef.current = setTimeout(() => {
      triggerCropCapture(currentObject);
    }, 350);
    return () => {
      if (cropTimerRef.current) clearTimeout(cropTimerRef.current);
    };
  }, [currentObject, isFullscreenMode, isEyeTrackingActive]);

  const triggerCropCapture = async (obj) => {
    try {
      const imageFilename = getCurrentImageFilename();
      const objectIndex = obj.index; // from labels.json mapping
      if (!objectIndex) return;

      const key = `${imageFilename}:${objectIndex}`;
      const now = Date.now();
      const cooldownMs = 1000; // 1s per same object
      if (lastCropKeyRef.current === key && now - lastCropTsRef.current < cooldownMs) {
        return;
      }
      lastCropKeyRef.current = key;
      lastCropTsRef.current = now;

      const form = new FormData();
      form.append('image_filename', imageFilename);
      form.append('object_index', String(objectIndex));
      form.append('include_alpha', 'true');

      form.append('assistance', isParentMode ? (parentSupport === 'guided' ? 'parent_guided' : 'parent_basic') : 'child');
      form.append('child_name', childName || '');
      const resp = await fetch('http://localhost:8001/crops/extract', {
        method: 'POST',
        body: form
      });
      if (!resp.ok) return;
      const data = await resp.json();
      // Only show toast when a new crop was just saved (not skipped or already_saved)
      if (data && data.success && data.url && !data.already_saved && !data.skipped) {
        const url = data.url.startsWith('http') ? data.url : `http://localhost:8001${data.url}`;
        setLastCrop({ url, object_id: data.object_id, ts: now });
        // Auto-hide after 2 seconds
        if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
        toastTimerRef.current = setTimeout(() => setLastCrop(null), 2000);
      }
    } catch (e) {
      console.error('Crop capture failed:', e);
    }
  };

  // If in fullscreen mode, render only the image
  if (isFullscreenMode) {
    return (
      <div className="fullscreen-eye-tracking">
        <img
          src={showMasks ? getCurrentPageMaskImage() : getCurrentPageImage()}
          alt={`Picture book page ${currentPage + 1}${showMasks ? ' with masks' : ''}`}
          className="fullscreen-image"
          ref={fullscreenImageRef}
        />

        {/* Dimming layer during assistant playback */}
        {!isParentAny && assistantState.visible && (
          <div className="assistant-dim" />
        )}

        {/* Parent basic detection notice banner (fullscreen, parent-basic only) */}
        {isParentBasic && parentNotice && (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              display: 'flex',
              justifyContent: 'center',
              zIndex: 12,
              pointerEvents: 'none'
            }}
          >
            <div
              style={{
                marginTop: '24px',
                maxWidth: '720px',
                width: 'calc(100% - 32px)',
                background: 'rgba(255, 255, 255, 0.98)',
                border: '3px solid rgba(255, 182, 193, 0.85)',
                color: '#5d4037',
                padding: '16px 18px',
                borderRadius: '14px',
                boxShadow: '0 14px 36px rgba(0,0,0,0.18)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                fontSize: '20px',
                fontWeight: 800,
                pointerEvents: 'auto'
              }}
            >
              <span style={{ fontSize: 24 }}>{parentNotice.type === 'curiosity' ? '🔍' : '⏳'}</span>
              <span>{parentNotice.text}</span>
              <div style={{ flex: 1 }} />
              <button
                onClick={() => {
                  // For curiosity, keep AOI highlight until confirmation; clearing notice will also allow highlight to disappear
                  setParentNotice(null);
                  // Unfreeze gaze tracking after parent acknowledges
                  try {
                    const imageFilename = getCurrentImageFilename();
                    const fdUnfreeze = new FormData();
                    fdUnfreeze.append('image_filename', imageFilename);
                    fdUnfreeze.append('frozen', 'false');
                    fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze });
                  } catch {}
                  // Resume eye-tracking after dismiss, if still in fullscreen
                  try {
                    if (isFullscreenMode && !isEyeTrackingActive) {
                      handleEnterEyeTrackingMode(false);
                    }
                  } catch {}
                }}
                style={{
                  border: 'none',
                  background: 'linear-gradient(45deg, #ffb3c1, #ffd1dc)',
                  color: '#5d4037',
                  fontWeight: 800,
                  borderRadius: '10px',
                  padding: '8px 12px',
                  cursor: 'pointer'
                }}
              >
                Got it
              </button>
            </div>
          </div>
        )}

        {/* Parent guided suggestions panel (fullscreen) */}
        {isParentGuided && parentGuidedPanel && (() => {
          const script = composeParentGuidedScript(parentGuidedPanel);
          const isPending = parentGuidedPanel.pending;
          return (
          <div
            style={{
              position: 'fixed', top: 0, left: 0, right: 0,
              display: 'flex', justifyContent: 'center', zIndex: 13,
              pointerEvents: 'none'
            }}
          >
            <div
              style={{
                marginTop: '24px', maxWidth: '720px', width: 'calc(100% - 32px)',
                background: isPending ? 'rgba(255, 248, 225, 0.98)' : 'rgba(255, 255, 255, 0.98)', 
                border: isPending ? '3px solid rgba(255, 193, 7, 0.85)' : '3px solid rgba(255, 182, 193, 0.85)',
                color: '#5d4037', padding: '16px 18px', borderRadius: '14px',
                boxShadow: '0 14px 36px rgba(0,0,0,0.18)', pointerEvents: 'auto'
              }}
            >
              <div style={{ fontWeight: 900, fontSize: 18, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                {isPending && <span>🔄</span>}
                {isPending ? 'Analyzing area...' : 'Guided suggestion'}
              </div>
              {isPending ? (
                <div style={{ fontSize: 16, fontStyle: 'italic' }}>
                  {parentGuidedPanel.data.question || "We detected your child is interested here… preparing a suggestion…"}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8, fontSize: 16 }}>
                  {script.question && (<div><b>Question</b>: {script.question}</div>)}
                  {script.answer && (<div><b>Answer</b>: {script.answer}</div>)}
                  {!script.answer && script.hint && (<div><b>Hint</b>: {script.hint}</div>)}
                  {script.followUp && (<div><b>Follow-up</b>: {script.followUp}</div>)}
                </div>
              )}
              <div style={{ display: 'flex', gap: 10, marginTop: 12, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => {
                    setParentGuidedPanel(null);
                    // Unfreeze gaze tracking and clear highlight on guided dismiss
                    try {
                      const imageFilename = getCurrentImageFilename();
                      const fdUnfreeze = new FormData();
                      fdUnfreeze.append('image_filename', imageFilename);
                      fdUnfreeze.append('frozen', 'false');
                      fdUnfreeze.append('child_name', childName || '');
                      fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze });
                    } catch {}
                    lockedObjectRef.current = null;
                    // Resume eye-tracking after dismiss, if still in fullscreen
                    try {
                      if (isFullscreenMode && !isEyeTrackingActive) {
                        handleEnterEyeTrackingMode(false);
                      }
                    } catch {}
                  }}
                  style={{
                    border: 'none', background: 'linear-gradient(45deg, #ffb3c1, #ffd1dc)', color: '#5d4037',
                    fontWeight: 800, borderRadius: '10px', padding: '8px 12px', cursor: 'pointer'
                  }}
                >
                  {isPending ? 'Cancel' : 'Got it'}
                </button>
              </div>
            </div>
          </div>
          );
        })()}

        {/* Locked AOI highlight: child-alone assistant OR parent-basic curiosity notice OR parent-guided panel */}
        {( (assistantState.visible || (isParentBasic && parentNotice && parentNotice.type === 'curiosity') || (isParentGuided && parentGuidedPanel)) && lockedObjectRef.current && fullscreenImageRef.current ) && (() => {
          const imgEl = fullscreenImageRef.current;
          const rect = imgEl.getBoundingClientRect();
          const iw = imgEl.naturalWidth || 1;
          const ih = imgEl.naturalHeight || 1;
          const sx = rect.width / iw;
          const sy = rect.height / ih;
          const [x1, y1, x2, y2] = lockedObjectRef.current.bbox;
          const left = rect.left + x1 * sx;
          const top = rect.top + y1 * sy;
          const width = (x2 - x1) * sx;
          const height = (y2 - y1) * sy;
          return (
            <div
              className="assistant-lock-bbox"
              style={{ left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` }}
            />
          );
        })()}

        {/* Animated Assistant Overlay */}
        {!isParentAny && assistantState.visible && (
          <AssistantOverlay
            phase={assistantState.phase}
            imageKey={assistantState.image}
            text={assistantState.text}
            audioUrl={assistantState.audioUrl}
            showActions={!!assistantState.showActions}
            onAudioEnded={async () => {
              if (assistantState.phase === 'intro') {
                canStartGuidanceRef.current = true;
                if (nudgeModeRef.current && nudgeGuidanceRef.current) {
                  await playNudgeFromPending();
                } else if (!nudgeModeRef.current && pendingGuidanceRef.current) {
                  await playGuidanceFromPending();
                } else {
                  const waitText = "Thanks for waiting. I'm still thinking of the best way to help.";
                  const url = await speakTTS(waitText);
                  setAssistantState({ visible: true, phase: 'wait', image: 'read', text: waitText, audioUrl: url, guidance: null, showActions: false });
                }
              } else if (assistantState.phase === 'wait') {
                canStartGuidanceRef.current = true;
                if (nudgeModeRef.current && nudgeGuidanceRef.current) {
                  await playNudgeFromPending();
                } else if (pendingGuidanceRef.current) {
                  await playGuidanceFromPending();
                } else {
                  setAssistantState(prev => ({ ...prev, audioUrl: null }));
                }
              } else if (assistantState.phase === 'tip') {
                // Close the one-time tip after speech ends
                setAssistantState(prev => ({ ...prev, visible: false, audioUrl: null }));
              } else if (assistantState.phase === 'guidance') {
                setAssistantState(prev => ({ ...prev, audioUrl: null, showActions: true }));
                
                // AUTO-UNFREEZE after guidance audio ends in child mode
                try {
                  const imageFilename = getCurrentImageFilename();
                  const fdUnfreeze = new FormData();
                  fdUnfreeze.append('image_filename', imageFilename);
                  fdUnfreeze.append('frozen', 'false');
                  fdUnfreeze.append('child_name', childName || '');
                  const response = await fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze });
                  if (response.ok) {
                    setIsGazeFrozen(false); // Clear local freeze state
                  }
                } catch {}
              }
            }}
            onRepeat={() => {
              if (assistantState.phase === 'guidance' || assistantState.showActions) {
                const text = assistantState.text;
                (async () => {
                  try {
                    const url = await speakTTS(text);
                    if (url) setAssistantState(prev => ({ ...prev, audioUrl: url }));
                  } catch {}
                })();
              }
            }}
            onSkip={() => {
              if (assistantState.phase === 'guidance' || assistantState.showActions) {
                const imageFilename = getCurrentImageFilename();
                try {
                  const fdUnfreeze = new FormData();
                  fdUnfreeze.append('image_filename', imageFilename);
                  fdUnfreeze.append('frozen', 'false');
                  fdUnfreeze.append('child_name', childName || '');
                  fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze }).then(response => {
                    if (response.ok) {
                      setIsGazeFrozen(false); // Clear local freeze state
                    }
                  });
                } catch {}
                setAssistantState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
                lockedObjectRef.current = null;
                nudgeGuidanceRef.current = null;
                nudgeModeRef.current = false;
              }
            }}
            onClose={() => {
              const imageFilename = getCurrentImageFilename();
              try {
                const fdUnfreeze = new FormData();
                fdUnfreeze.append('image_filename', imageFilename);
                fdUnfreeze.append('frozen', 'false');
                fetch('http://localhost:8001/aoi/freeze', { method: 'POST', body: fdUnfreeze }).then(response => {
                  if (response.ok) {
                    setIsGazeFrozen(false); // Clear local freeze state
                  }
                });
              } catch {}
              setAssistantState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
              lockedObjectRef.current = null;
              nudgeGuidanceRef.current = null;
              nudgeModeRef.current = false;
            }}
          />
        )}

        {/* Gaze indicator */}
        {isEyeTrackingActive && gazeData && (
          <div
            className="gaze-indicator"
            style={{
              left: `${gazeData.x}px`,
              top: `${gazeData.y}px`,
            }}
          />
        )}

        {/* Selected object bbox overlay */}
        {isEyeTrackingActive && currentObject && fullscreenImageRef.current && (() => {
          const imgEl = fullscreenImageRef.current;
          const rect = imgEl.getBoundingClientRect();
          const iw = imgEl.naturalWidth || 1;
          const ih = imgEl.naturalHeight || 1;
          const sx = rect.width / iw;
          const sy = rect.height / ih;
          const [x1, y1, x2, y2] = currentObject.bbox;
          const left = rect.left + x1 * sx;
          const top = rect.top + y1 * sy;
          const width = (x2 - x1) * sx;
          const height = (y2 - y1) * sy;
          return (
            <div
              className="object-bbox"
              style={{
                position: 'fixed',
                left: `${left}px`,
                top: `${top}px`,
                width: `${width}px`,
                height: `${height}px`,
                border: '4px solid #00ff88',
                backgroundColor: 'rgba(0,255,136,0.14)',
                boxShadow: '0 0 0 2px rgba(255,255,255,0.9) inset, 0 0 12px rgba(0,255,136,0.95), 0 0 26px rgba(0,255,136,0.6)',
                pointerEvents: 'none',
                zIndex: 5
              }}
            />
          );
        })()}

        {/* Debug: Show if gaze data exists but no indicator */}
        {isEyeTrackingActive && !gazeData && (
          <div className="gaze-debug">
            👁️ Waiting for gaze data...
          </div>
        )}

        {/* Eye tracking status */}
        <div className="eye-tracking-status">
          <div className={`status-indicator ${isEyeTrackingActive ? 'active' : 'inactive'}`}>
            {isEyeTrackingActive ? '👁️ Eye Tracking Active' : '⏸️ Eye Tracking Paused'}
          </div>
          {gazeData && (
            <div className="gaze-coords">
              X: {Math.round(gazeData.x)}, Y: {Math.round(gazeData.y)}
            </div>
          )}
          {currentObject && (
            <div className="current-object">
              Object: {currentObject.object_id}
            </div>
          )}
          <div className="mask-toggle-hint">
            Press 'S' to {showMasks ? 'hide' : 'show'} segmentation masks
          </div>
        </div>

        {/* Last crop toast */}
        {lastCrop && (
          <div
            style={{
              position: 'fixed',
              right: '16px',
              bottom: '16px',
              background: 'rgba(0,0,0,0.65)',
              padding: '8px 10px',
              borderRadius: '8px',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              zIndex: 6
            }}
          >
            <img src={lastCrop.url} alt="crop" style={{ width: 72, height: 72, objectFit: 'contain', background: '#222', borderRadius: 4 }} />
            <div style={{ fontSize: 12, lineHeight: 1.2 }}>
              Saved crop
              <div style={{ opacity: 0.8 }}>{lastCrop.object_id}</div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="picture-book">
      {/* Compact header with back button and navigation */}
      <div className="compact-header">
        <button
          className="back-button"
          onClick={onBackToModeSelect}
        >
          ← Back to Mode Selection
        </button>

        <div className="top-navigation">
          <button
            onClick={handlePrevPage}
            disabled={currentPage === 0}
            className="nav-button prev-button"
          >
            ← Previous
          </button>

          <div className="page-info">
            <span className="page-counter">
              Page {currentPage + 1} of {totalPages}
            </span>
            {selectedImages.size > 0 && (
              <span className="selection-counter">
                ✓ Ready!
              </span>
            )}
          </div>

          <button
            onClick={handleNextPage}
            disabled={currentPage === totalPages - 1}
            className="nav-button next-button"
          >
            Next →
          </button>
        </div>

        {/* Eye-tracking starts automatically; ESC exits */}
      </div>

      {/* Main image area - takes most of the space */}
      <div className="main-image-area">
          <div className={`image-card`}>
            <img
              src={getCurrentPageImage()}
              alt={`Picture book page ${currentPage + 1}`}
              className="book-image"
              ref={bookImageRef}
              onDoubleClick={() => { if (!isFullscreenMode) handleEnterEyeTrackingMode(true); }}
            />
          </div>
        </div>

      {/* Assistant overlay also in non-fullscreen mode */}
      {!isParentBasic && assistantState.visible && (
        <AssistantOverlay
          phase={assistantState.phase}
          imageKey={assistantState.image}
          text={assistantState.text}
          audioUrl={assistantState.audioUrl}
          showActions={!!assistantState.showActions}
          onAudioEnded={async () => {
            if (assistantState.phase === 'intro') {
              canStartGuidanceRef.current = true;
              if (nudgeModeRef.current && nudgeGuidanceRef.current) {
                await playNudgeFromPending();
              } else if (!nudgeModeRef.current && pendingGuidanceRef.current) {
                await playGuidanceFromPending();
              } else {
                const waitText = "Thanks for waiting. I'm still thinking of the best way to help.";
                const url = await speakTTS(waitText);
                setAssistantState({ visible: true, phase: 'wait', image: 'read', text: waitText, audioUrl: url, guidance: null, showActions: false });
              }
            } else if (assistantState.phase === 'wait') {
              canStartGuidanceRef.current = true;
              if (nudgeModeRef.current && nudgeGuidanceRef.current) {
                await playNudgeFromPending();
              } else if (pendingGuidanceRef.current) {
                await playGuidanceFromPending();
              } else {
                setAssistantState(prev => ({ ...prev, audioUrl: null }));
              }
            } else if (assistantState.phase === 'tip') {
              setAssistantState(prev => ({ ...prev, visible: false, audioUrl: null }));
            } else if (assistantState.phase === 'guidance') {
              setAssistantState(prev => ({ ...prev, audioUrl: null, showActions: true }));
            }
          }}
          onRepeat={() => {
            if (assistantState.phase === 'guidance' || assistantState.showActions) {
              const text = assistantState.text;
              (async () => {
                try {
                  const url = await speakTTS(text);
                  if (url) setAssistantState(prev => ({ ...prev, audioUrl: url }));
                } catch {}
              })();
            }
          }}
          onSkip={() => {
            if (assistantState.phase === 'guidance' || assistantState.showActions || assistantState.phase === 'tip') {
              setAssistantState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
              lockedObjectRef.current = null;
              nudgeGuidanceRef.current = null;
              nudgeModeRef.current = false;
            }
          }}
          onClose={() => {
            setAssistantState({ visible: false, phase: 'idle', image: 'main', text: '', audioUrl: null, guidance: null, showActions: false });
            lockedObjectRef.current = null;
            nudgeGuidanceRef.current = null;
            nudgeModeRef.current = false;
          }}
        />
      )}

      {/* Guided suggestion banner is fullscreen-only now */}

      {/* Story narration UI removed for eye-tracking only mode */}
    </div>
  );
};

export default PictureBook;

