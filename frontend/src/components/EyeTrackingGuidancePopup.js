/**
 * Enhanced Guidance Popup for Eye-Tracking Mode
 * Handles 3-stage progressive guidance: thinking → main content → exploratory
 */
import React, { useState, useEffect, useRef } from 'react';
import TypingText from './assistance/TypingText';

const EyeTrackingGuidancePopup = ({ 
  currentGuidance,
  triggeredAOI,
  activity,
  imageFilename,
  imageSize,
  onDismiss,
  onStop,
  language = 'de'  // Language (German only)
}) => {
  
  // NEW: Send end_timestamp to backend when user dismisses popup
  const sendEndTimestamp = async () => {
    const endTimestamp = Date.now() / 1000; // Unix timestamp
    const aoiIndex = triggeredAOI?.index || currentGuidance?.triggered_aoi?.index;
    const secondaryAoiIndex = currentGuidance?.secondary_aoi_index; // NEW: Get secondary AOI index
    const sequenceStep = currentGuidance?.sequence_step;
    
    if (!imageFilename || aoiIndex === undefined) {
      
      return;
    }
    
    try {
      let body = `image_filename=${encodeURIComponent(imageFilename)}&activity=${activity}&aoi_index=${aoiIndex}&end_timestamp=${endTimestamp}&condition=eye_assistance`;
      if (sequenceStep) {
        body += `&sequence_step=${sequenceStep}`;
      }
      if (secondaryAoiIndex !== undefined && secondaryAoiIndex !== null) {
        body += `&secondary_aoi_index=${secondaryAoiIndex}`;
      }
      
      await fetch('http://localhost:8080/api/manual-assistance/update-end-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body
      });
      
      
    } catch (error) {
      
    }
  };
  
  
  // Calculate smart popup position to avoid AOI overlap (copied from ManualAssistancePopup)
  const calculatePosition = () => {
    if (!triggeredAOI?.bbox || !imageSize) {
      // Default center position when no AOI
      return {
        left: '50%',
        top: '20%',
        transform: 'translateX(-50%)'
      };
    }
    
    const aoiPosition = triggeredAOI.bbox;
    
    // AOI dimensions in percentage
    const aoi_x1_percent = (aoiPosition[0] / imageSize.width) * 100;
    const aoi_y1_percent = (aoiPosition[1] / imageSize.height) * 100;
    const aoi_x2_percent = (aoiPosition[2] / imageSize.width) * 100;
    const aoi_y2_percent = (aoiPosition[3] / imageSize.height) * 100;
    
    const aoi_center_x = (aoi_x1_percent + aoi_x2_percent) / 2;
    const aoi_center_y = (aoi_y1_percent + aoi_y2_percent) / 2;
    
    // Popup dimensions (estimate)
    const popup_width_percent = 50; // ~600px on 1200px screen
    const popup_height_percent = 25; // Estimated popup height
    
    let final_x, final_y;
    
    // 4-Position Edge Alignment Algorithm
    const gap_px = 10; // 10px gap
    const gap_percent = (gap_px / 1200) * 100; // ~0.8% for 1200px screen
    
    // Position 2: Top-Center (above AOI, centered)
    if (aoi_y1_percent - popup_height_percent - gap_percent >= 2) {
      final_x = Math.max(2, Math.min(98 - popup_width_percent, aoi_center_x - popup_width_percent / 2));
      final_y = aoi_y1_percent - popup_height_percent - gap_percent;
    }
    // Position 4: Right-Middle (right of AOI, vertically centered)
    else if (aoi_x2_percent + popup_width_percent + gap_percent <= 98) {
      final_x = aoi_x2_percent + gap_percent;
      final_y = Math.max(2, Math.min(98 - popup_height_percent, aoi_center_y - popup_height_percent / 2));
    }
    // Position 6: Bottom-Center (below AOI, centered)
    else if (aoi_y2_percent + popup_height_percent + gap_percent <= 98) {
      final_x = Math.max(2, Math.min(98 - popup_width_percent, aoi_center_x - popup_width_percent / 2));
      final_y = aoi_y2_percent + gap_percent;
    }
    // Position 8: Left-Middle (left of AOI, vertically centered)
    else if (aoi_x1_percent - popup_width_percent - gap_percent >= 2) {
      final_x = aoi_x1_percent - popup_width_percent - gap_percent;
      final_y = Math.max(2, Math.min(98 - popup_height_percent, aoi_center_y - popup_height_percent / 2));
    }
    // Fallback: Best available space
    else {
      final_x = 25; // Center horizontally
      final_y = 10; // Top of screen
    }
    
    return {
      left: `${final_x}%`,
      top: `${final_y}%`,
      transform: 'translateX(0%)'
    };
  };
  
  const position = calculatePosition();
  
  const [currentStage, setCurrentStage] = useState('thinking');
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const audioRef = useRef(null);
  
  // Handle stage changes and audio playback
  useEffect(() => {
    if (!currentGuidance) return;
    
    const stage = currentGuidance.stage || 'thinking';
    
    if (stage === 'main_content' && currentGuidance.main_audio?.audio_url) {
      // Play main content audio
      setCurrentStage('main_content');
      playMainAudio(currentGuidance.main_audio.audio_url, currentGuidance);
    } else if (stage === 'thinking') {
      setCurrentStage('thinking');
    }
  }, [currentGuidance]);
  
  const playMainAudio = async (audioUrl, guidanceData) => {
    try {
      const fullUrl = `http://localhost:8080${audioUrl}`;
      console.log(`🔊 [EyeTrackingGuidancePopup] Attempting to play audio from: ${fullUrl}`);
      
      setIsPlayingAudio(true);
      
      const audio = new Audio(fullUrl);
      audio.onended = () => {
        console.log(`✅ [EyeTrackingGuidancePopup] Audio completed: ${fullUrl}`);
        setIsPlayingAudio(false);
        setCurrentStage('completed');
      };
      audio.onerror = (e) => {
        console.error(`❌ [EyeTrackingGuidancePopup] Audio error for ${fullUrl}:`, e);
        console.error(`   Audio element error code: ${audio.error?.code}`);
        console.error(`   Audio element error message: ${audio.error?.message}`);
        setIsPlayingAudio(false);
      };
      
      await audio.play();
      console.log(`✅ [EyeTrackingGuidancePopup] Audio started playing: ${fullUrl}`);
      audioRef.current = audio;
      
    } catch (error) {
      console.error(`❌ [EyeTrackingGuidancePopup] Error playing audio:`, error);
      setIsPlayingAudio(false);
    }
  };
  
  
  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlayingAudio(false);
  };
  
  const handleDismiss = async () => {
    await sendEndTimestamp();
    stopAudio();
    onDismiss();
  };
  
  if (!currentGuidance) {
    return null;
  }
  
  // Get display message based on stage
  const getDisplayMessage = () => {
    // Check if assistance was stopped
    if (currentGuidance.type === 'stopped' || currentGuidance.message === 'See you soon!' || currentGuidance.message === 'Bis bald!') {
      return language === 'de' ? "Bis bald!" : "See you soon!";
    }
    
    if (currentStage === 'thinking') {
      return currentGuidance.message || (language === 'de' 
        ? "Aha! Ich sehe, du bist neugierig darauf. Lass mich darüber nachdenken..."
        : "Aha! I see you are curious about this. Let me think about it...");
    } else if (currentStage === 'main_content') {
      return language === 'de' 
        ? "Schaue dir bitte den hervorgehobenen Teil an"
        : "Take a look at the highlighted part please";
    }
    return currentGuidance.message || (language === 'de' ? "du bist neugierig!" : "you are curious!");
  };
  
  const showButtons = false; // No buttons needed since we removed exploratory stage
  
  
  
  return (
    <div 
      style={{
        position: 'absolute',
        ...position,
        background: 'rgba(0, 0, 0, 0.3)',
        backdropFilter: 'blur(15px)',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        borderRadius: '12px',
        padding: '20px',
        maxWidth: '600px',
        textAlign: 'left',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.1)',
        zIndex: 30
      }}
    >
      {/* Intro page style layout: Ollie on left, text bubble on right */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '15px',
        marginBottom: '15px'
      }}>
        {/* Ollie icon for eye-tracking assistance - using super_read.png for both activities */}
        <img 
          src="http://localhost:8080/animated_assistant/super_read.png"
          alt="Ollie assistant"
          style={{
            width: '150px',
            height: '150px',
            objectFit: 'contain',
            opacity: 0.9,
            animation: 'bob 2.2s ease-in-out infinite',
            flexShrink: 0
          }}
          onError={(e) => {
            // Fallback to emoji if image fails to load
            e.target.style.display = 'none';
            e.target.nextSibling.style.display = 'inline';
          }}
        />
        <span style={{ 
          display: 'none', 
          fontSize: '2rem',
          opacity: 0.8,
          flexShrink: 0
        }}>
          🦉📖
        </span>
        
        {/* Text bubble like intro page */}
        <div style={{
          background: 'rgba(255, 255, 255, 0.1)',
          backdropFilter: 'blur(5px)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          borderRadius: '12px',
          padding: '12px 15px',
          flex: 1,
          position: 'relative'
        }}>
          {/* Stage-based guidance message with typing effect */}
          <div style={{
            fontSize: '0.95rem',
            fontWeight: '500',
            color: 'rgba(255, 255, 255, 0.9)',
            lineHeight: '1.4',
            minHeight: '1.4em',
            marginBottom: showButtons ? '15px' : '0'
          }}>
            {getDisplayMessage()}
          </div>
          
          
          {/* Buttons removed since exploratory stage is removed */}
          {false && (
            <div style={{
              display: 'flex',
              gap: '10px',
              justifyContent: 'center'
            }}>
              <button
                onClick={async () => {
                  console.log('🛑 [BUTTON] Stop button clicked - calling sendEndTimestamp');
                  await sendEndTimestamp();
                  console.log('🛑 [BUTTON] sendEndTimestamp completed - stopping audio');
                  stopAudio();
                  if (onStop) {
                    console.log('🛑 [BUTTON] Calling onStop');
                    onStop();
                  }
                  console.log('🛑 Stop assistance clicked');
                }}
                style={{
                  background: 'rgba(244, 67, 54, 0.15)',
                  color: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid rgba(244, 67, 54, 0.3)',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  backdropFilter: 'blur(5px)',
                  transition: 'all 0.3s ease'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = 'rgba(244, 67, 54, 0.25)';
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'rgba(244, 67, 54, 0.15)';
                }}
              >
                🛑 Stop
              </button>
              
              <button
                onClick={handleDismiss}
                style={{
                  background: 'rgba(255, 255, 255, 0.15)',
                  color: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  backdropFilter: 'blur(5px)',
                  transition: 'all 0.3s ease'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = 'rgba(255, 255, 255, 0.25)';
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'rgba(255, 255, 255, 0.15)';
                }}
              >
                ✅ Continue
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EyeTrackingGuidancePopup;
