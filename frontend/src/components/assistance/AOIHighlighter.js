/**
 * AOI Highlighter - Blinking bounding box overlay for manual assistance
 * Completely separate from eye-tracking visualization
 *
 * Blinks exactly 5 times (5 full on-off cycles) then hides; assistance end is tracked separately.
 * FIXED: Now properly accounts for letterboxing when objectFit: 'contain' is used
 */
import React, { useEffect, useState, useRef } from 'react';

const BLINK_INTERVAL_MS = 800;
const BLINK_CYCLES = 5; // full on-off cycles; 2 toggles per cycle

const AOIHighlighter = ({ aoiBbox, imageSize, isActive }) => {
  const [isVisible, setIsVisible] = useState(true);
  const [showHighlight, setShowHighlight] = useState(false);
  const [dimensions, setDimensions] = useState({ width: window.innerWidth, height: window.innerHeight });
  const toggleCountRef = useRef(0);
  const intervalIdRef = useRef(null);

  useEffect(() => {
    if (!isActive) {
      setShowHighlight(false);
      return;
    }
    setShowHighlight(true);
    setIsVisible(true);
    toggleCountRef.current = 0;

    intervalIdRef.current = setInterval(() => {
      toggleCountRef.current += 1;
      setIsVisible(prev => !prev);
      if (toggleCountRef.current >= BLINK_CYCLES * 2) {
        setShowHighlight(false);
        if (intervalIdRef.current) {
          clearInterval(intervalIdRef.current);
          intervalIdRef.current = null;
        }
      }
    }, BLINK_INTERVAL_MS);

    return () => {
      if (intervalIdRef.current) {
        clearInterval(intervalIdRef.current);
        intervalIdRef.current = null;
      }
    };
  }, [isActive]);

  // Update dimensions on resize
  useEffect(() => {
    const handleResize = () => {
      setDimensions({ width: window.innerWidth, height: window.innerHeight });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (!aoiBbox || !imageSize || !isActive || !showHighlight) {
    return null;
  }
  
  // Calculate actual displayed image dimensions accounting for object-fit: contain
  const imageAspect = imageSize.width / imageSize.height;
  const viewportAspect = dimensions.width / dimensions.height;
  
  let displayedWidth, displayedHeight, offsetX, offsetY;
  
  if (viewportAspect > imageAspect) {
    // Letterboxing on sides (black bars left/right)
    displayedHeight = dimensions.height;
    displayedWidth = displayedHeight * imageAspect;
    offsetX = (dimensions.width - displayedWidth) / 2;
    offsetY = 0;
  } else {
    // Letterboxing on top/bottom (black bars top/bottom)
    displayedWidth = dimensions.width;
    displayedHeight = displayedWidth / imageAspect;
    offsetX = 0;
    offsetY = (dimensions.height - displayedHeight) / 2;
  }
  
  // Scale bbox to displayed image size
  const scaleX = displayedWidth / imageSize.width;
  const scaleY = displayedHeight / imageSize.height;
  
  const [x1, y1, x2, y2] = aoiBbox;
  
  // Calculate pixel positions with letterboxing offset
  const left = offsetX + (x1 * scaleX);
  const top = offsetY + (y1 * scaleY);
  const width = (x2 - x1) * scaleX;
  const height = (y2 - y1) * scaleY;
  
  return (
    <div
      style={{
        position: 'fixed',
        left: `${left}px`,
        top: `${top}px`,
        width: `${width}px`,
        height: `${height}px`,
        pointerEvents: 'none',
        zIndex: 15
      }}
    >
      {/* Blinking area overlay */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        background: isVisible ? 'rgba(255, 107, 107, 0.3)' : 'rgba(255, 107, 107, 0.1)',
        borderRadius: '8px',
        transition: 'background 0.3s ease',
        boxShadow: isVisible ? '0 0 30px rgba(255, 107, 107, 0.6)' : '0 0 10px rgba(255, 107, 107, 0.2)'
      }} />
      
      {/* Animated border */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        border: `3px solid ${isVisible ? '#FF6B6B' : 'rgba(255, 107, 107, 0.4)'}`,
        borderRadius: '8px',
        transition: 'border-color 0.3s ease'
      }} />
      
      {/* Pulsing glow effect */}
      {isVisible && (
        <div style={{
          position: 'absolute',
          top: '-10px',
          left: '-10px',
          width: 'calc(100% + 20px)',
          height: 'calc(100% + 20px)',
          background: 'radial-gradient(ellipse at center, rgba(255, 107, 107, 0.2) 0%, transparent 70%)',
          borderRadius: '12px',
          animation: 'pulse 2s ease-in-out infinite'
        }} />
      )}
      
      {/* Corner accent markers */}
      {isVisible && (
        <>
          {/* Top-left corner */}
          <div style={{
            position: 'absolute',
            top: '-8px',
            left: '-8px',
            width: '16px',
            height: '16px',
            background: 'radial-gradient(circle, #FF6B6B 0%, rgba(255, 107, 107, 0.3) 100%)',
            borderRadius: '50%',
            boxShadow: '0 0 15px rgba(255, 107, 107, 0.8)'
          }} />
          
          {/* Top-right corner */}
          <div style={{
            position: 'absolute',
            top: '-8px',
            right: '-8px',
            width: '16px',
            height: '16px',
            background: 'radial-gradient(circle, #FF6B6B 0%, rgba(255, 107, 107, 0.3) 100%)',
            borderRadius: '50%',
            boxShadow: '0 0 15px rgba(255, 107, 107, 0.8)'
          }} />
          
          {/* Bottom-left corner */}
          <div style={{
            position: 'absolute',
            bottom: '-8px',
            left: '-8px',
            width: '16px',
            height: '16px',
            background: 'radial-gradient(circle, #FF6B6B 0%, rgba(255, 107, 107, 0.3) 100%)',
            borderRadius: '50%',
            boxShadow: '0 0 15px rgba(255, 107, 107, 0.8)'
          }} />
          
          {/* Bottom-right corner */}
          <div style={{
            position: 'absolute',
            bottom: '-8px',
            right: '-8px',
            width: '16px',
            height: '16px',
            background: 'radial-gradient(circle, #FF6B6B 0%, rgba(255, 107, 107, 0.3) 100%)',
            borderRadius: '50%',
            boxShadow: '0 0 15px rgba(255, 107, 107, 0.8)'
          }} />
        </>
      )}
      
      {/* CSS for pulse animation */}
      <style>{`
        @keyframes pulse {
          0% { 
            transform: scale(1);
            opacity: 0.7;
          }
          50% { 
            transform: scale(1.05);
            opacity: 0.3;
          }
          100% { 
            transform: scale(1);
            opacity: 0.7;
          }
        }
      `}</style>
    </div>
  );
};

export default AOIHighlighter;
