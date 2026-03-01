import React, { useState, useEffect, useRef, useCallback } from 'react';
import './PictureBookReader.css';
import { useManualAssistance } from '../hooks/useManualAssistance';
import { useTimeTracking } from '../hooks/useTimeTracking';
import AOIHighlighter from './assistance/AOIHighlighter';
import GamePage from './GamePage';

const AssistanceBook = ({ 
  activity, 
  childName,
  childAge,
  onBackToModeSelect,
  websocket = null,              // NEW: WebSocket for gaze data collection
  condition = 'assistance',      // NEW: Condition for gaze data collection
  // Sequence mode props
  lockedToSingleImage = false,  // If true, disable navigation and use provided image
  imageFilename = null,          // Override image (used in sequence mode)
  onComplete = null,             // Callback when user completes this step
  onPrevious = null,             // Callback to go to previous step in sequence
  sequenceStep = null,           // Sequence step number for cache routing
  language = 'de',               // Language (German only)
  // Video recording callbacks
  onEnterFullscreen = null,      // Callback when entering fullscreen
  onExitFullscreen = null        // Callback when exiting fullscreen
}) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [autoMode, setAutoMode] = useState(false); // First 3 assistances: 3-sec auto-advance; then Enter required
  const exitingRef = useRef(false); // Prevent double exit
  const assistanceStartingRef = useRef(false); // Prevent duplicate session starts
  const autoAdvanceTimerRef = useRef(null); // 3-sec between assistances
  const autoModeRef = useRef(autoMode); // current autoMode for timeout callback (align with FullscreenReader)
  const assistanceCountRef = useRef(0); // Count auto-advances; after 3, require Enter
  const [assistanceCount, setAssistanceCount] = useState(0); // For keepHighlightUntilEnter (2 = showing 3rd)
  
  const [hasExitedFullscreen, setHasExitedFullscreen] = useState(false);
  
  // Game session state
  const [showGamePage, setShowGamePage] = useState(false);
  
  // Image navigation state (only used when NOT locked)
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
  
  // Time tracking - only track when in fullscreen mode (must run before useManualAssistance so we can pass callbacks)
  const timeTracking = useTimeTracking(
    isFullscreen ? currentImageFile : null,
    activity,
    'assistance',
    childName,
    sequenceStep
  );
  
  // Manual assistance system - receives timeline assistance/voice start/end callbacks
  const getCurrentAssistanceIndex = useCallback(() => assistanceCountRef.current + 1, []);
  const manualAssistance = useManualAssistance(
    sequenceStep,
    childName,
    childAge,
    language,
    assistanceCount === 2,
    timeTracking.recordAssistanceStart,
    timeTracking.recordAssistanceEnd,
    timeTracking.recordVoiceStart,
    timeTracking.recordVoiceEnd,
    getCurrentAssistanceIndex
  );
  
  // Send end_timestamp to backend when user dismisses assistance
  const sendEndTimestamp = async () => {
    const endTimestamp = Date.now() / 1000; // Unix epoch float
    const assistanceData = manualAssistance.assistanceData;
    
    if (!assistanceData?.image_filename || assistanceData?.aoi?.index === undefined) {
      return;
    }
    
    try {
      let body = `image_filename=${encodeURIComponent(assistanceData.image_filename)}&activity=${activity}&aoi_index=${assistanceData.aoi.index}&end_timestamp=${endTimestamp}&condition=assistance`;
      
      // Include start_timestamp (highlight start time)
      if (assistanceData.highlight_start_time) {
        body += `&start_timestamp=${assistanceData.highlight_start_time}`;
      }
      
      if (assistanceData.sequence_step) {
        body += `&sequence_step=${assistanceData.sequence_step}`;
      }
      
      if (assistanceData.secondary_aoi_index !== undefined && assistanceData.secondary_aoi_index !== null) {
        body += `&secondary_aoi_index=${assistanceData.secondary_aoi_index}`;
      }
      
      await fetch('http://localhost:8080/api/manual-assistance/update-end-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body
      });
    } catch (error) {
      console.error('❌ Error sending end_timestamp:', error);
    }
  }
  
  // Reset guards when image changes (for sequence mode - component doesn't remount)
  useEffect(() => {
    assistanceStartingRef.current = false;
    exitingRef.current = false;
  }, [currentImageFile]);

  // First 3 assistances: auto-advance after 3 sec per assistance; after 3, require Enter
  useEffect(() => {
    if (!isFullscreen) {
      setAutoMode(false);
      return;
    }
    setAutoMode(true);
    assistanceCountRef.current = 0;
    setAssistanceCount(0);
  }, [isFullscreen]);
  
  useEffect(() => {
    autoModeRef.current = autoMode;
  }, [autoMode]);
  
  // Auto-advance: when in auto mode and current assistance is "done" (audio finished, not processing), wait 3 sec then next
  const manualAssistanceRef = useRef(manualAssistance);
  manualAssistanceRef.current = manualAssistance;
  useEffect(() => {
    if (!autoMode || !manualAssistance.assistanceData || manualAssistance.assistanceData?.type === 'completion' || manualAssistance.isPlayingAudio || manualAssistance.isProcessing || assistanceCountRef.current >= 2) {
      if (autoAdvanceTimerRef.current) {
        clearTimeout(autoAdvanceTimerRef.current);
        autoAdvanceTimerRef.current = null;
      }
      return;
    }
    autoAdvanceTimerRef.current = setTimeout(async () => {
      autoAdvanceTimerRef.current = null;
      if (!autoModeRef.current) return; // Auto mode may have been turned off (e.g. after 3 assistances)
      const currentIndex = assistanceCountRef.current + 1;
      await timeTracking.recordAssistanceEnd(currentIndex);
      await sendEndTimestamp();
      manualAssistanceRef.current.getNextAssistance();
      assistanceCountRef.current += 1;
      if (assistanceCountRef.current >= 3) {
        setAutoMode(false);
        return;
      }
      setAssistanceCount(assistanceCountRef.current);
    }, 3000);
    return () => {
      if (autoAdvanceTimerRef.current) {
        clearTimeout(autoAdvanceTimerRef.current);
        autoAdvanceTimerRef.current = null;
      }
    };
  }, [autoMode, manualAssistance.assistanceData, manualAssistance.isPlayingAudio, manualAssistance.isProcessing]);
  
  // Reset hasExitedFullscreen when image changes (new sequence step)
  useEffect(() => {
    setHasExitedFullscreen(false);
  }, [currentImageFile, sequenceStep]);
  
  // Navigation functions with automatic assistance restart
  const goToPreviousImage = () => {
    if (currentImageIndex > 0) {
      const newIndex = currentImageIndex - 1;
      setCurrentImageIndex(newIndex);
      
      // If in fullscreen mode, automatically start assistance for new image
      if (isFullscreen) {
        const newImageFile = availableImages[newIndex];
        manualAssistance.switchToNewImage(newImageFile, activity);
      }
    }
  };
  
  const goToNextImage = () => {
    if (currentImageIndex < availableImages.length - 1) {
      const newIndex = currentImageIndex + 1;
      setCurrentImageIndex(newIndex);
      
      // If in fullscreen mode, automatically start assistance for new image
      if (isFullscreen) {
        const newImageFile = availableImages[newIndex];
        manualAssistance.switchToNewImage(newImageFile, activity);
      }
    }
  };

  // Old manual guidance functions removed - now using automatic assistance

  const enterFullscreen = useCallback(async () => {
    // Guard: Prevent duplicate session starts from rapid double-clicks
    if (assistanceStartingRef.current) {
      console.warn('⚠️ [AssistanceBook] Assistance session already starting, skipping');
      return;
    }
    assistanceStartingRef.current = true;
    
    // Request browser fullscreen API FIRST - while user gesture is still valid
    try {
      await document.documentElement.requestFullscreen();
    } catch (e) {
      console.error('Fullscreen request failed:', e);
      assistanceStartingRef.current = false;
      return;
    }
    
    // Call video recording callback after entering fullscreen
    if (onEnterFullscreen) {
      await onEnterFullscreen({
        condition,
        image: currentImageFile
      });
    }
    
    setIsFullscreen(true);
    
    // NEW: Start gaze tracking via WebSocket
    if (websocket) {
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
    
    // START AUTOMATIC ASSISTANCE immediately after fullscreen
    try {
      await manualAssistance.startAssistanceSession(currentImageFile, activity);
    } catch (error) {
      console.error('❌ Failed to start assistance:', error);
    }
  }, [websocket, currentImageFile, activity, condition, childName, sequenceStep, manualAssistance, onEnterFullscreen]);
  
  const exitFullscreen = useCallback(async () => {
    // Prevent double exit
    if (exitingRef.current) {
      console.warn('[AssistanceBook] Already exiting, skipping');
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
        console.error('❌ [AssistanceBook] onExitFullscreen error:', error);
      }
    }
    
    // Stop manual assistance session
    try {
      await manualAssistance.stopAssistanceSession();
    } catch (error) {
      console.error('❌ Error stopping assistance:', error);
    }
    
    // Stop gaze tracking via WebSocket
    if (websocket) {
      console.log('[TRACE] stop_tracking', {
        sender: 'AssistanceBook',
        image_filename: currentImageFile
      });
      websocket.sendMessage({
        type: 'stop_tracking',
        image_filename: currentImageFile
      });
    }
    
    // Exit browser fullscreen
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch (e) {
        console.error('[AssistanceBook] Error exiting fullscreen:', e);
      }
    }
    
    // Clear component state
    setIsFullscreen(false);
    setHasExitedFullscreen(true); // Mark that user has exited fullscreen once
    setShowGamePage(true); // Show game session after exiting fullscreen
    console.log('✅ [AssistanceBook] Exit complete, showing GamePage');
    
    // Reset flags after delay
    setTimeout(() => {
      exitingRef.current = false;
      assistanceStartingRef.current = false;  // Reset session start guard
    }, 500);
  }, [websocket, currentImageFile, manualAssistance, condition, onExitFullscreen]);

  // Handle escape key and fullscreen changes
  useEffect(() => {
    const handleKeyPress = async (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        e.preventDefault(); // Prevent default browser fullscreen handling
        const currentIndex = assistanceCountRef.current + 1;
        await timeTracking.recordAssistanceEnd(currentIndex);
        await sendEndTimestamp(); // Send end timestamp before exiting
        await exitFullscreen();
      } else if (e.key === 'ArrowLeft' && !lockedToSingleImage) {
        // Only allow arrow navigation in standalone mode (not in sequence mode)
        e.preventDefault();
        goToPreviousImage();
      } else if (e.key === 'ArrowRight' && !lockedToSingleImage) {
        // Only allow arrow navigation in standalone mode (not in sequence mode)
        e.preventDefault();
        goToNextImage();
      } else if (e.key === 'Enter' && isFullscreen) {
        // Continue (original popup's Continue) when audio finished
        const currentlyPlaying = manualAssistance.isPlayingAudio;
        const currentlyProcessing = manualAssistance.isProcessing;
        const inCompletionState = manualAssistance.assistanceData?.type === 'completion';

        if (!currentlyPlaying && !currentlyProcessing) {
          e.preventDefault();
          if (inCompletionState) {
            await exitFullscreen();
          } else {
            const currentIndex = assistanceCountRef.current + 1;
            await timeTracking.recordAssistanceEnd(currentIndex);
            await sendEndTimestamp();
            manualAssistance.getNextAssistance();
            assistanceCountRef.current += 1;
            setAssistanceCount(prev => prev + 1);
          }
        }
      } else if ((e.key === 's' || e.key === 'S') && isFullscreen) {
        // Stop (original popup's Stop)
        e.preventDefault();
        const currentIndex = assistanceCountRef.current + 1;
        await timeTracking.recordAssistanceEnd(currentIndex);
        await sendEndTimestamp(); // Send end timestamp before stopping
        manualAssistance.stopAssistanceSession();
      }
    };
    
    const handleFullscreenChange = async () => {
      // If browser exited fullscreen but our component is still in fullscreen mode
      if (!document.fullscreenElement && isFullscreen && !exitingRef.current) {
        exitingRef.current = true; // Prevent recursive calls
        
        console.log('[AssistanceBook] Browser-initiated fullscreen exit detected');
        
        // CRITICAL: Call video callback FIRST (before any state changes)
        if (onExitFullscreen) {
          try {
            console.log('🎥 [AssistanceBook] Calling onExitFullscreen (browser-exit)', { condition, image: currentImageFile });
            await onExitFullscreen({
              condition,
              image: currentImageFile
            });
            console.log('✅ [AssistanceBook] onExitFullscreen completed (browser-exit)');
          } catch (error) {
            console.error('❌ [AssistanceBook] onExitFullscreen error (browser-exit):', error);
          }
        }
        
        // Stop gaze tracking via WebSocket
        if (websocket) {
          console.log('[TRACE] stop_tracking', {
            sender: 'AssistanceBook(browser-exit)',
            image_filename: currentImageFile
          });
          websocket.sendMessage({
            type: 'stop_tracking',
            image_filename: currentImageFile
          });
        }
        
        // Stop manual assistance session
        try {
          await manualAssistance.stopAssistanceSession();
        } catch (error) {
          console.error('❌ Error stopping assistance on browser exit:', error);
        }
        
        setHasExitedFullscreen(true);
        setShowGamePage(true); // Show game session after exiting fullscreen
        setIsFullscreen(false);
        console.log('✅ [AssistanceBook] Exit complete (browser-initiated), showing GamePage');
        
        setTimeout(() => {
          exitingRef.current = false;
          assistanceStartingRef.current = false;  // Reset session start guard
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
  }, [isFullscreen, exitFullscreen, currentImageIndex, availableImages.length, websocket, currentImageFile, manualAssistance, manualAssistance.isPlayingAudio, lockedToSingleImage, onExitFullscreen, condition]);

  // If showing game page, render GamePage
  if (showGamePage) {
    // Extract image number from filename (e.g., "3.jpg" -> 3)
    const imageNumber = parseInt(currentImageFile.replace(/\D/g, ''), 10) || 1;
    console.log('🎮 [AssistanceBook] Rendering GamePage for image:', imageNumber);
    
    const handleGameEnd = () => {
      console.log('🎮 [AssistanceBook] Game session ended, proceeding to next');
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
      <div style={{
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
      }}>
        <img 
          src={`http://localhost:8080/pictures/${activity}/${currentImageFile}`}
          alt={`Picture book page ${currentImageIndex + 1}`}
          style={{
            width: '100vw',
            height: '100vh',
            objectFit: activity === 'storytelling' ? 'contain' : 'cover',
            display: 'block',
            border: 'none',
            outline: 'none',
            backgroundColor: '#000'
          }}
        />
        
        {/* AOI Highlighting - blinking bounding box */}
        <AOIHighlighter 
          aoiBbox={manualAssistance.currentAOI?.bbox}
          imageSize={{ 
            width: activity === 'storytelling' ? 1344 : 1500, 
            height: activity === 'storytelling' ? 768 : 959 
          }}
          isActive={manualAssistance.currentState === 'presenting_main'}
        />
        
        {/* Manual Assistance: no popup in assistance-only mode; keep AOI highlight and TTS */}
      </div>
    );
  }

  // Thumbnail view - Same as BaselineBook but with assistance features
  return (
    <div>
      {/* Header with back button - same as BaselineBook */}
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
              src={`http://localhost:8080/pictures/${activity}/${currentImageFile}`}
              alt={`Picture book page ${currentImageIndex + 1}`}
              className="main-image"
              onDoubleClick={() => {
                console.log('🖱️ [AssistanceBook] Double-click detected', { 
                  hasExitedFullscreen, 
                  isFullscreen 
                });
                if (!hasExitedFullscreen) {
                  console.log('➡️ [AssistanceBook] Entering fullscreen (first time)');
                  enterFullscreen();
                }
                // After exiting fullscreen, double-click does nothing (review mode skipped)
              }}
            />
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

export default AssistanceBook;
