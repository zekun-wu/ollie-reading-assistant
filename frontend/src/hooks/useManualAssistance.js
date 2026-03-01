/**
 * Manual Assistance Hook - Completely separate from eye-tracking assistance
 * Used exclusively by AssistanceBook.js
 * Manages random AOI selection, LLM responses, and TTS playback
 */
import { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8080/api/manual-assistance';

export const useManualAssistance = (sequenceStep = null, childName = null, childAge = null, language = 'de', keepHighlightUntilEnter = false, onHighlightShow = null, onHighlightHide = null, onVoiceStart = null, onVoiceEnd = null, getCurrentAssistanceIndex = null) => {
  const [isActive, setIsActive] = useState(false);
  const [sessionKey, setSessionKey] = useState(null);
  const [currentState, setCurrentState] = useState('idle'); // idle, waiting, processing, presenting_main, presenting_exploratory, completed
  const [currentAOI, setCurrentAOI] = useState(null);
  const [assistanceData, setAssistanceData] = useState(null);
  const [waitingMessage, setWaitingMessage] = useState(null);
  const [error, setError] = useState(null);
  const [currentActivity, setCurrentActivity] = useState(null);
  const [currentImageFile, setCurrentImageFile] = useState(null);
  
  // Audio management (separate from eye-tracking audio)
  const audioRef = useRef(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [audioQueue, setAudioQueue] = useState([]); // Queue for waiting → assistance audio
  const [startTimestamp, setStartTimestamp] = useState(null); // NEW: Track when waiting message appears
  const [highlightStartTime, setHighlightStartTime] = useState(null); // NEW: Track when highlight appears
  const [isProcessing, setIsProcessing] = useState(false); // Guard against multiple simultaneous requests
  const completedMainCountRef = useRef(0); // How many main-content playbacks completed this session; play continue_de only on 3rd
  
  const startAssistanceSession = async (imageFilename, activity) => {
    try {
      setError(null);
      setCurrentState('waiting');
      
      // NEW: Capture start timestamp when waiting message appears
      const waitingStartTime = Date.now() / 1000; // Unix timestamp
      setStartTimestamp(waitingStartTime);
      console.log(`⏰ Assistance started (waiting message) at: ${waitingStartTime}`);
      
      const modeStr = sequenceStep ? ` [sequence step ${sequenceStep}]` : '';
      console.log(`🤖 Starting manual assistance session${modeStr}...`);
      
      // Build request body
      let body = `activity=${activity}`;
      if (sequenceStep !== null) {
        body += `&sequence_step=${sequenceStep}`;
      }
      if (childName) {
        body += `&child_name=${encodeURIComponent(childName)}`;
      }
      if (childAge) {
        body += `&child_age=${encodeURIComponent(childAge)}`;
      }
      body += `&language=${language}`;
      
      // Start session and get waiting message
      const response = await fetch(`${API_BASE}/start/${imageFilename}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body
      });
      
      const result = await response.json();
      console.log('🔍 Backend session response:', result);
      
      if (result.success) {
         completedMainCountRef.current = 0;
         // Set state BEFORE playing waiting message
         setCurrentActivity(activity);
         setCurrentImageFile(imageFilename);
         setSessionKey(result.session_key);
         setWaitingMessage(result.waiting_message);
         setIsActive(true);
        
        console.log('✅ Manual assistance session started');
        
        // Play waiting message voice immediately (pass image/activity directly)
        await playWaitingMessageWithParams(result.waiting_message, imageFilename, activity);
        
        // Start first AOI assistance (pass activity AND imageFilename directly to avoid state timing issues)
        const nextResult = await getNextAssistanceWithKey(result.session_key, activity, imageFilename);
        
        return true;
      } else {
        setError(result.error);
        return false;
      }
      
    } catch (error) {
      console.error('❌ Error starting manual assistance:', error);
      setError(error.message);
      return false;
    }
  };
  
  const getNextAssistanceWithKey = async (useSessionKey, activityOverride = null, imageFilenameOverride = null) => {
    try {
      const keyToUse = useSessionKey || sessionKey;
      if (!keyToUse) {
        console.log('❌ No session key for getNextAssistance');
        return false;
      }
      
      // Guard: Prevent multiple simultaneous requests
      console.log('🔍 [GUARD CHECK] isProcessing:', isProcessing, 'isPlayingAudio:', isPlayingAudio);
      if (isProcessing || isPlayingAudio) {
        console.log('⚠️ [GUARD BLOCKED] Already processing or playing audio, ignoring request');
        return false;
      }
      
      console.log('✅ [GUARD PASSED] Starting new assistance request');
      setIsProcessing(true);
      setCurrentState('processing');
      
      // NEW: Include start_timestamp in request body
      let body = '';
      if (startTimestamp) {
        body = `start_timestamp=${startTimestamp}`;
      }
      
      const response = await fetch(`${API_BASE}/next-aoi/${keyToUse}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body
      });
      
      const result = await response.json();
      
      if (result.success) {
        if (result.completed) {
          // All AOIs exhausted
          setCurrentState('completed');
          setAssistanceData({
            type: 'completion',
            message: result.message,
            voice_text: result.voice_text
          });
          
          console.log('🎉 Manual assistance completed - all AOIs explored');
          
          // Play completion message
          await playCompletionMessage(result.voice_text);
          
        } else {
          // New AOI selected with split LLM response
          setCurrentAOI(result.aoi);
          setCurrentState('presenting_main');
          
          // Capture highlight start time (when highlight actually appears)
          const highlightStart = Date.now() / 1000; // Unix epoch float
          setHighlightStartTime(highlightStart);
          console.log(`🎯 Highlight appeared at: ${highlightStart}`);
          if (typeof onHighlightShow === 'function') {
            const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
            onHighlightShow(idx);
          }
          
          console.log(`🎯 Selected AOI ${result.aoi.index} for manual assistance`);
          
          // Set initial assistance data (no popup text yet)
          const newAssistanceData = {
            type: 'llm_response',
            aoi: result.aoi,
            analysis: result.analysis,
            voice_texts: result.voice_texts,
            main_audio: result.main_audio,
            activity: activityOverride || currentActivity,
            stage: 'main',
            image_filename: imageFilenameOverride || currentImageFile,  // NEW: For end_timestamp tracking (use parameter to avoid state timing issues)
            sequence_step: sequenceStep,  // NEW: For end_timestamp tracking
            highlight_start_time: highlightStart,  // NEW: Capture when highlight appears
            secondary_aoi_index: result.secondary_aoi_index  // NEW: For two-AOI storytelling
          };
          
          console.log('📋 [ASSISTANCE_DATA] Set with image_filename and sequence_step:', {
            image_filename: newAssistanceData.image_filename,
            aoi_index: result.aoi?.index,
            sequence_step: newAssistanceData.sequence_step,
            imageFilenameOverride: imageFilenameOverride,
            currentImageFile: currentImageFile
          });
          
          setAssistanceData(newAssistanceData);
          
          // Play the main content voice first
          if (result.main_audio?.audio_url) {
            console.log('🔊 Playing main content voice...');
            await playMainContentVoice(result.main_audio.audio_url, result);
          }
        }
        
        console.log('🔓 [GUARD] Setting isProcessing = false (success)');
        setIsProcessing(false);
        return true;
      } else {
        setError(result.error);
        console.log('🔓 [GUARD] Setting isProcessing = false (error)');
        setIsProcessing(false);
        return false;
      }
      
    } catch (error) {
      console.error('❌ Error getting next assistance:', error);
      setError(error.message);
      console.log('🔓 [GUARD] Setting isProcessing = false (catch)');
      setIsProcessing(false);
      return false;
    }
  };

  const getNextAssistance = async () => {
    return await getNextAssistanceWithKey(null);
  };
  
  const skipAssistance = async () => {
    try {
      console.log('⏭️ Stopping assistance...');
      
      // Stop any playing audio immediately
      stopAudio();
      if (typeof onHighlightHide === 'function') {
        const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
        onHighlightHide(idx);
      }
      
      // Show goodbye message
      setCurrentState('stopped');
      setAssistanceData({
        type: 'stopped',
        message: language === 'de' ? 'Bis bald!' : 'See you soon!'
      });
      
      // Hide after 2 seconds
      setTimeout(() => {
        setCurrentAOI(null);
        setAssistanceData(null);
        setCurrentState('idle');
        setIsActive(false);
      }, 2000);
      
      return true;
      
    } catch (error) {
      console.error('❌ Error stopping assistance:', error);
      return false;
    }
  };
  
  const stopAssistanceSession = async () => {
    try {
      console.log('🛑 Stopping manual assistance session...');
      
      // Stop audio
      stopAudio();
      if (typeof onHighlightHide === 'function') {
        const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
        onHighlightHide(idx);
      }
      
      // Stop session
      if (sessionKey) {
        await fetch(`${API_BASE}/stop/${sessionKey}`, {
          method: 'POST'
        });
      }
      
       // Reset all state
       setIsActive(false);
       setSessionKey(null);
       setCurrentState('idle');
       setCurrentAOI(null);
       setAssistanceData(null);
       setWaitingMessage(null);
       setCurrentActivity(null);
       setCurrentImageFile(null);
       setError(null);
      
      console.log('✅ Manual assistance session stopped');
      
      return true;
      
    } catch (error) {
      console.error('❌ Error stopping assistance session:', error);
      return false;
    }
  };
  
  const playWaitingMessageWithParams = async (waitingMsg, imageFilename, activity) => {
    try {
      console.log('🔊 Playing waiting message with params:', { imageFilename, activity });
      
      // Generate TTS for waiting message
      setIsPlayingAudio(true);
      
      try {
        // Build request body
        let body = `text=${encodeURIComponent(waitingMsg.voice_text)}&image_name=${encodeURIComponent(imageFilename)}&activity=${encodeURIComponent(activity)}&language=${encodeURIComponent(language)}`;
        if (sequenceStep !== null) {
          body += `&sequence_step=${sequenceStep}`;
        }
        
        const response = await fetch('http://localhost:8080/api/manual-assistance/tts/waiting', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: body
        });
        
        if (response.ok) {
          const result = await response.json();
          
          if (result.success && result.audio_url) {
            // Play the actual audio
            const audio = new Audio(`http://localhost:8080${result.audio_url}`);
            audio.onended = () => {
              setIsPlayingAudio(false);
              console.log('✅ Waiting message audio completed');
            };
            audio.onerror = () => {
              setIsPlayingAudio(false);
              console.log('❌ Waiting message audio failed');
            };
            
            await audio.play();
            audioRef.current = audio;
          } else {
            // Fallback to simulation
            await new Promise(resolve => setTimeout(resolve, 2000));
            setIsPlayingAudio(false);
          }
        } else {
          // Fallback to simulation
          await new Promise(resolve => setTimeout(resolve, 2000));
          setIsPlayingAudio(false);
        }
      } catch (audioError) {
        console.log('⚠️ Audio generation failed, using simulation');
        await new Promise(resolve => setTimeout(resolve, 2000));
        setIsPlayingAudio(false);
      }
      
      console.log('✅ Waiting message completed');
      
    } catch (error) {
      console.error('❌ Error playing waiting message:', error);
      setIsPlayingAudio(false);
    }
  };

  const playWaitingMessage = async (waitingMsg) => {
    try {
      console.log('🔊 Playing waiting message...');
      
      // Generate TTS for waiting message
      setIsPlayingAudio(true);
      
      try {
        // Build request body
        let body = `text=${encodeURIComponent(waitingMsg.voice_text)}&image_name=${encodeURIComponent(currentImageFile)}&activity=${encodeURIComponent(currentActivity)}&language=${encodeURIComponent(language)}`;
        if (sequenceStep !== null) {
          body += `&sequence_step=${sequenceStep}`;
        }
        
        const response = await fetch('http://localhost:8080/api/manual-assistance/tts/waiting', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: body
        });
        
        if (response.ok) {
          const result = await response.json();
          
          if (result.success && result.audio_url) {
            // Play the actual audio
            const audio = new Audio(`http://localhost:8080${result.audio_url}`);
            audio.onended = () => {
              setIsPlayingAudio(false);
              console.log('✅ Waiting message audio completed');
            };
            audio.onerror = () => {
              setIsPlayingAudio(false);
              console.log('❌ Waiting message audio failed');
            };
            
            await audio.play();
            audioRef.current = audio;
          } else {
            // Fallback to simulation
            await new Promise(resolve => setTimeout(resolve, 2000));
            setIsPlayingAudio(false);
          }
        } else {
          // Fallback to simulation
          await new Promise(resolve => setTimeout(resolve, 2000));
          setIsPlayingAudio(false);
        }
      } catch (audioError) {
        console.log('⚠️ Audio generation failed, using simulation');
        await new Promise(resolve => setTimeout(resolve, 2000));
        setIsPlayingAudio(false);
      }
      
      console.log('✅ Waiting message completed');
      
    } catch (error) {
      console.error('❌ Error playing waiting message:', error);
      setIsPlayingAudio(false);
    }
  };
  
  const playMainContentVoice = async (audioUrl, assistanceData) => {
    try {
      const fullUrl = `http://localhost:8080${audioUrl}`;
      console.log(`🔊 [ManualAssistance] Playing main content voice from: ${fullUrl}`);
      setIsPlayingAudio(true);
      
      const audio = new Audio(fullUrl);
      audio.onended = async () => {
        console.log(`✅ [ManualAssistance] Main content voice completed: ${fullUrl}`);
        if (typeof onVoiceEnd === 'function') {
          const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
          onVoiceEnd(idx);
        }
        // After main content, play completion message (keep isPlayingAudio true throughout)
        // Pass false to not manage audio state - we'll handle it here
        await playCompletionMessage(assistanceData.analysis?.child_explanation || assistanceData.analysis?.child_story, false);
        
        // Only set to false after BOTH main and completion messages are done
        setIsPlayingAudio(false);
        completedMainCountRef.current += 1;
        const count = completedMainCountRef.current;
        // Only 1st and 2nd: clear highlight when voice ends (auto-advance). 3rd+ keep highlight until Enter.
        if (count < 3) {
          if (typeof onHighlightHide === 'function') {
            const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
            onHighlightHide(idx);
          }
          setCurrentState('completed');
          setCurrentAOI(null);
        }
        // Only 3rd completion: play continue message (4th+ must not play it)
        if (count === 3) {
          const base = 'http://localhost:8080';
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
        console.log('✅ All audio completed (main + completion)');
      };
      audio.onerror = (e) => {
        console.error(`❌ [ManualAssistance] Audio error for ${fullUrl}:`, e);
        console.error(`   Audio element error code: ${audio.error?.code}`);
        console.error(`   Audio element error message: ${audio.error?.message}`);
        setIsPlayingAudio(false);
        if (typeof onVoiceEnd === 'function') {
          const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
          onVoiceEnd(idx);
        }
        if (typeof onHighlightHide === 'function') {
          const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
          onHighlightHide(idx);
        }
        setCurrentState('completed');
        setCurrentAOI(null);
        console.log('❌ Main content voice failed');
      };
      
      await audio.play();
      if (typeof onVoiceStart === 'function') {
        const idx = typeof getCurrentAssistanceIndex === 'function' ? getCurrentAssistanceIndex() : undefined;
        onVoiceStart(idx);
      }
      console.log(`✅ [ManualAssistance] Audio started playing: ${fullUrl}`);
      audioRef.current = audio;
      
    } catch (error) {
      console.error('❌ [ManualAssistance] Error playing main content voice:', error);
      setIsPlayingAudio(false);
    }
  };


  const playCompletionMessage = async (voiceText, manageAudioState = true) => {
    try {
      console.log('🔊 Playing completion message...');
      
      // TODO: Generate TTS for completion message
      // For now, just simulate audio delay
      if (manageAudioState) {
        setIsPlayingAudio(true);
      }
      await new Promise(resolve => setTimeout(resolve, 3000)); // 3 second completion voice
      
      if (manageAudioState) {
        setIsPlayingAudio(false);
      }
      
      console.log('✅ Completion message completed');
      
    } catch (error) {
      console.error('❌ Error playing completion message:', error);
      if (manageAudioState) {
        setIsPlayingAudio(false);
      }
    }
  };
  
  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlayingAudio(false);
    setAudioQueue([]);
  };
  
  const switchToNewImage = async (newImageFilename, activity) => {
    try {
      console.log(`🔄 Switching assistance from ${currentImageFile} to ${newImageFilename}`);
      
      // Stop current session
      await stopAssistanceSession();
      
      // Start new session with new image
      await startAssistanceSession(newImageFilename, activity);
      
      console.log(`✅ Assistance switched to ${newImageFilename}`);
      return true;
      
    } catch (error) {
      console.error('❌ Error switching assistance to new image:', error);
      return false;
    }
  };
  
  return {
    // State
    isActive,
    currentState,
    currentAOI,
    assistanceData,
    waitingMessage,
    error,
    isPlayingAudio,
    isProcessing,
    
    // Actions
    startAssistanceSession,
    getNextAssistance,
    skipAssistance,
    stopAssistanceSession,
    switchToNewImage,
    
    // Audio ref
    audioRef
  };
};
