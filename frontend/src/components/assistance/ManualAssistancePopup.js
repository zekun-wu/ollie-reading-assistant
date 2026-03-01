/**
 * Manual Assistance Popup - Completely separate from eye-tracking guidance
 * Used exclusively by AssistanceBook.js
 * Positioned near highlighted AOI with transparent design
 */
import React from 'react';
import TypingText from './TypingText';

const ManualAssistancePopup = ({ 
  currentState,
  assistanceData,
  waitingMessage,
  aoiPosition,
  imageSize,
  onStop,
  onNext,
  onExit,
  isPlayingAudio,
  error,
  activity,
  language = 'de'  // Language (German only)
}) => {
  
  // NEW: Send end_timestamp to backend when user dismisses popup
  const sendEndTimestamp = async (imageFilename, aoiIndex, sequenceStep = null, secondaryAoiIndex = null) => {
    const endTimestamp = Date.now() / 1000; // Unix timestamp
    
    try {
      let body = `image_filename=${encodeURIComponent(imageFilename)}&activity=${activity}&aoi_index=${aoiIndex}&end_timestamp=${endTimestamp}&condition=assistance`;
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
  
  // NEW: Wrap onNext with end timestamp tracking
  const handleNext = async () => {
    if (assistanceData?.image_filename && assistanceData?.aoi?.index !== undefined) {
      await sendEndTimestamp(
        assistanceData.image_filename,
        assistanceData.aoi.index,
        assistanceData.sequence_step,
        assistanceData.secondary_aoi_index  // NEW: Pass secondary AOI
      );
    } else {
      
    }
    onNext();
  };
  
  // NEW: Wrap onStop with end timestamp tracking
  const handleStop = async () => {
    if (assistanceData?.image_filename && assistanceData?.aoi?.index !== undefined) {
      await sendEndTimestamp(
        assistanceData.image_filename,
        assistanceData.aoi.index,
        assistanceData.sequence_step,
        assistanceData.secondary_aoi_index  // NEW: Pass secondary AOI
      );
    } else {
      
    }
    onStop();
  };
  
  
  // Calculate smart popup position to avoid AOI overlap
  const calculatePosition = () => {
    if (!aoiPosition || !imageSize) {
      // Default center position when no AOI
      return {
        left: '50%',
        top: '20%',
        transform: 'translateX(-50%)'
      };
    }
    
    // AOI dimensions in percentage
    const aoi_x1_percent = (aoiPosition[0] / imageSize.width) * 100;
    const aoi_y1_percent = (aoiPosition[1] / imageSize.height) * 100;
    const aoi_x2_percent = (aoiPosition[2] / imageSize.width) * 100;
    const aoi_y2_percent = (aoiPosition[3] / imageSize.height) * 100;
    
    const aoi_width_percent = aoi_x2_percent - aoi_x1_percent;
    const aoi_height_percent = aoi_y2_percent - aoi_y1_percent;
    const aoi_center_x = (aoi_x1_percent + aoi_x2_percent) / 2;
    const aoi_center_y = (aoi_y1_percent + aoi_y2_percent) / 2;
    
    // Popup dimensions (estimate)
    const popup_width_percent = 50; // ~600px on 1200px screen (much larger for 150px Ollie)
    const popup_height_percent = 25; // Estimated popup height (taller for larger Ollie)
    
    let final_x, final_y;
    
    // 4-Position Edge Alignment Algorithm
    // Try positions in priority order: Top → Right → Bottom → Left
    const gap_px = 10; // 10px gap in percentage (approximate)
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
    // Fallback: Best fit position (closest to AOI center)
    else {
      // Force fit in the position with most available space
      const spaces = [
        { pos: 'top', space: aoi_y1_percent },
        { pos: 'right', space: 100 - aoi_x2_percent },
        { pos: 'bottom', space: 100 - aoi_y2_percent },
        { pos: 'left', space: aoi_x1_percent }
      ];
      
      const bestSpace = spaces.reduce((max, current) => current.space > max.space ? current : max);
      
      if (bestSpace.pos === 'top') {
        final_x = Math.max(2, Math.min(48, aoi_center_x - popup_width_percent / 2));
        final_y = 2;
      } else if (bestSpace.pos === 'right') {
        final_x = Math.max(2, 98 - popup_width_percent);
        final_y = Math.max(2, Math.min(73, aoi_center_y - popup_height_percent / 2));
      } else if (bestSpace.pos === 'bottom') {
        final_x = Math.max(2, Math.min(48, aoi_center_x - popup_width_percent / 2));
        final_y = Math.max(2, 98 - popup_height_percent);
      } else { // left
        final_x = 2;
        final_y = Math.max(2, Math.min(73, aoi_center_y - popup_height_percent / 2));
      }
    }
    
    return {
      left: `${final_x}%`,
      top: `${final_y}%`,
      transform: 'translateX(0%)'  // No centering since we calculated exact position
    };
  };
  
  const position = calculatePosition();
  
  // Determine popup content based on state
  const getPopupContent = () => {
    const isGerman = language === 'de';
    
    switch (currentState) {
      case 'waiting':
        return {
          message: waitingMessage?.popup_text || (isGerman ? "Lass mich dir helfen! 🤖" : "Let me help you! 🤖"),
          showControls: false,
          isLoading: true
        };
        
      case 'processing':
        return {
          message: isGerman ? "Ich schaue mir dieses Bild an... 🔍" : "Looking at this picture... 🔍",
          showControls: false,
          isLoading: true
        };
        
      case 'presenting_main':
        return {
          message: isGerman ? "Schaue dir bitte den hervorgehobenen Teil an" : "Take a look at the highlighted part please",
          showControls: false,
          isLoading: false
        };
        
        
      case 'presenting':  // Legacy fallback
        return {
          message: assistanceData?.message || (isGerman ? "Hier ist etwas Interessantes!" : "Here's something interesting!"),
          showControls: !isPlayingAudio,
          isLoading: false
        };
        
      case 'stopped':
        return {
          message: assistanceData?.message || (isGerman ? "Bis bald!" : "See you soon!"),
          showControls: false,
          isLoading: false,
          isStopped: true
        };
        
      case 'completed':
        return {
          message: assistanceData?.message || (isGerman ? "Toll, dass du erkundet hast!" : "Great job exploring!"),
          showControls: false,
          isLoading: false,
          isCompleted: true
        };
        
      default:
        return {
          message: isGerman ? "Bereite vor..." : "Getting ready...",
          showControls: false,
          isLoading: true
        };
    }
  };
  
  const content = getPopupContent();
  
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
        {/* Ollie icon for manual assistance - using teach.png for both activities */}
        <img 
          src="http://localhost:8080/animated_assistant/teach.png"
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
          
          {/* Main message with typing effect */}
          <div style={{
            fontSize: '0.95rem',
            fontWeight: '500',
            color: 'rgba(255, 255, 255, 0.9)',
            lineHeight: '1.4',
            minHeight: '1.4em',
            paddingRight: isPlayingAudio ? '25px' : '0'
          }}>
            <TypingText 
              text={content.message}
              speed={30}
              style={{
                color: 'rgba(255, 255, 255, 0.9)'
              }}
            />
          </div>
        </div>
      </div>
      
      {/* Control buttons */}
      {content.showControls && (
        <div style={{
          display: 'flex',
          gap: '10px',
          justifyContent: 'center'
        }}>
          <button
            onClick={handleStop}
            style={{
              background: 'rgba(244, 67, 54, 0.1)',
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
              e.target.style.background = 'rgba(244, 67, 54, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.target.style.background = 'rgba(244, 67, 54, 0.1)';
            }}
          >
            🛑 Stop
          </button>
          
          <button
            onClick={handleNext}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              color: 'rgba(255, 255, 255, 0.9)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '8px',
              padding: '6px 12px',
              fontWeight: '500',
              cursor: 'pointer',
              fontSize: '0.85rem',
              backdropFilter: 'blur(5px)',
              transition: 'all 0.3s ease'
            }}
            onMouseEnter={(e) => {
              e.target.style.background = 'rgba(255, 255, 255, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.target.style.background = 'rgba(255, 255, 255, 0.1)';
            }}
          >
            ✅ Continue
          </button>
        </div>
      )}
      
      {/* Completion controls */}
      {content.isCompleted && (
        <button
          onClick={onExit}
          style={{
            background: 'rgba(255, 255, 255, 0.15)',
            color: 'rgba(255, 255, 255, 0.9)',
            border: '1px solid rgba(255, 255, 255, 0.3)',
            borderRadius: '8px',
            padding: '8px 16px',
            fontWeight: '600',
            cursor: 'pointer',
            fontSize: '0.9rem',
            marginTop: '10px',
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
          ✅ Done Exploring
        </button>
      )}
      
      {/* Error display */}
      {error && (
        <div style={{
          marginTop: '10px',
          padding: '10px',
          background: 'rgba(244, 67, 54, 0.1)',
          border: '1px solid rgba(244, 67, 54, 0.3)',
          borderRadius: '8px',
          color: '#d32f2f',
          fontSize: '0.9rem'
        }}>
          ❌ {error}
        </div>
      )}
      
      {/* CSS animations handled by inline styles */}
    </div>
  );
};

export default ManualAssistancePopup;
