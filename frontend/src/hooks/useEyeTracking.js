import { useState, useEffect, useCallback, useRef } from 'react';

// Eye-tracking status constants
export const EYE_TRACKING_STATUS = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  TRACKING: 'tracking',
  ERROR: 'error'
};

export const useEyeTracking = () => {
  const [status, setStatus] = useState(EYE_TRACKING_STATUS.DISCONNECTED);
  const [currentGaze, setCurrentGaze] = useState(null);
  const [gazeHistory, setGazeHistory] = useState([]);
  const [eyeTrackingHealth, setEyeTrackingHealth] = useState(null);
  const [error, setError] = useState(null);
  
  // Refs for managing intervals
  const gazePollingRef = useRef(null);
  const healthCheckRef = useRef(null);
  
  // API base URL
  const API_BASE = 'http://localhost:8080/api/eye-tracking';
  
  // Connect to eye tracker
  const connect = useCallback(async () => {
    try {
      setStatus(EYE_TRACKING_STATUS.CONNECTING);
      setError(null);
      
      const response = await fetch(`${API_BASE}/connect`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        setStatus(EYE_TRACKING_STATUS.CONNECTED);
        setEyeTrackingHealth(result.status);
        console.log('✅ Eye tracker connected:', result.status);
      } else {
        setStatus(EYE_TRACKING_STATUS.ERROR);
        setError(result.message);
        console.error('❌ Eye tracker connection failed:', result.message);
      }
      
      return result.success;
    } catch (err) {
      setStatus(EYE_TRACKING_STATUS.ERROR);
      setError(err.message);
      console.error('❌ Eye tracker connection error:', err);
      return false;
    }
  }, []);
  
  // Start eye tracking
  const startTracking = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/start`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        setStatus(EYE_TRACKING_STATUS.TRACKING);
        console.log('✅ Eye tracking started');
        
        // Start polling for gaze data
        startGazePolling();
        startHealthMonitoring();
      } else {
        setError(result.message);
        console.error('❌ Eye tracking start failed:', result.message);
      }
      
      return result.success;
    } catch (err) {
      setError(err.message);
      console.error('❌ Eye tracking start error:', err);
      return false;
    }
  }, []);
  
  // Stop eye tracking
  const stopTracking = useCallback(async () => {
    try {
      // Stop polling
      if (gazePollingRef.current) {
        clearInterval(gazePollingRef.current);
        gazePollingRef.current = null;
      }
      if (healthCheckRef.current) {
        clearInterval(healthCheckRef.current);
        healthCheckRef.current = null;
      }
      
      const response = await fetch(`${API_BASE}/stop`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        setStatus(EYE_TRACKING_STATUS.CONNECTED);
        setCurrentGaze(null);
        console.log('✅ Eye tracking stopped');
      }
      
      return result.success;
    } catch (err) {
      setError(err.message);
      console.error('❌ Eye tracking stop error:', err);
      return false;
    }
  }, []);
  
  // Disconnect from eye tracker
  const disconnect = useCallback(async () => {
    try {
      // Stop polling first
      await stopTracking();
      
      const response = await fetch(`${API_BASE}/disconnect`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        setStatus(EYE_TRACKING_STATUS.DISCONNECTED);
        setEyeTrackingHealth(null);
        setCurrentGaze(null);
        setGazeHistory([]);
        console.log('✅ Eye tracker disconnected');
      }
      
      return result.success;
    } catch (err) {
      setError(err.message);
      console.error('❌ Eye tracker disconnect error:', err);
      return false;
    }
  }, [stopTracking]);
  
  // Start polling for gaze data
  const startGazePolling = useCallback(() => {
    if (gazePollingRef.current) return; // Already polling
    
    gazePollingRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/gaze-data?count=5`);
        const result = await response.json();
        
        if (result.success && result.gaze_data.length > 0) {
          const latestGaze = result.gaze_data[result.gaze_data.length - 1];
          
          // Only update if we have valid gaze data
          if (latestGaze.validity === 'valid' && latestGaze.x !== null && latestGaze.y !== null) {
            setCurrentGaze({
              x: latestGaze.x,
              y: latestGaze.y,
              timestamp: latestGaze.timestamp,
              validity: latestGaze.validity
            });
            
            // Add to history (keep last 100 points)
            setGazeHistory(prev => {
              const newHistory = [...prev, latestGaze];
              return newHistory.slice(-100); // Keep last 100 points
            });
          }
        }
      } catch (err) {
        console.error('❌ Gaze data polling error:', err);
      }
    }, 25); // Poll at 40Hz for ultra-smooth visualization
  }, []);
  
  // Start health monitoring
  const startHealthMonitoring = useCallback(() => {
    if (healthCheckRef.current) return; // Already monitoring
    
    healthCheckRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/health`);
        const result = await response.json();
        
        if (result.status === 'healthy') {
          setEyeTrackingHealth(result.eye_tracking);
        }
      } catch (err) {
        console.error('❌ Health check error:', err);
      }
    }, 2000); // Check every 2 seconds
  }, []);
  
  // Set image context for eye tracking
  const setImageContext = useCallback(async (imageFilename) => {
    try {
      const formData = new FormData();
      formData.append('image_filename', imageFilename);
      
      const response = await fetch(`${API_BASE}/set-image`, {
        method: 'POST',
        body: formData,
      });
      
      const result = await response.json();
      console.log('🖼️ Image context set:', imageFilename);
      return result.success;
    } catch (err) {
      console.error('❌ Set image context error:', err);
      return false;
    }
  }, []);
  
  /**
   * Switch to a new image while keeping connection alive
   * For use in sequence mode - avoids expensive reconnection
   * 
   * @param {string} newImageFilename - New image to track
   * @returns {Promise<boolean>} Success status
   */
  const switchImage = useCallback(async (newImageFilename) => {
    try {
      console.log(`🔄 Switching to new image: ${newImageFilename} (keeping connection alive)`);
      
      // Stop tracking current image (but keep connection)
      if (status === EYE_TRACKING_STATUS.TRACKING) {
        await stopTracking();
      }
      
      // Set new image context
      const contextSet = await setImageContext(newImageFilename);
      if (!contextSet) {
        console.error('❌ Failed to set new image context');
        return false;
      }
      
      // Restart tracking for new image
      const trackingRestarted = await startTracking();
      if (!trackingRestarted) {
        console.error('❌ Failed to restart tracking for new image');
        return false;
      }
      
      console.log(`✅ Successfully switched to ${newImageFilename}`);
      return true;
      
    } catch (err) {
      console.error('❌ Error switching image:', err);
      setError(err.message);
      return false;
    }
  }, [status, stopTracking, setImageContext, startTracking]);
  
  // Get gaze statistics
  const getGazeStats = useCallback(() => {
    if (gazeHistory.length === 0) return null;
    
    const validGazes = gazeHistory.filter(g => g.validity === 'valid');
    const totalPoints = validGazes.length;
    
    if (totalPoints === 0) return null;
    
    // Calculate average position
    const avgX = validGazes.reduce((sum, g) => sum + g.x, 0) / totalPoints;
    const avgY = validGazes.reduce((sum, g) => sum + g.y, 0) / totalPoints;
    
    // Calculate data quality (% valid points)
    const dataQuality = (totalPoints / gazeHistory.length) * 100;
    
    return {
      totalPoints: gazeHistory.length,
      validPoints: totalPoints,
      dataQuality: dataQuality.toFixed(1),
      averagePosition: { x: avgX.toFixed(3), y: avgY.toFixed(3) },
      timeSpan: gazeHistory.length > 0 ? 
        (gazeHistory[gazeHistory.length - 1].timestamp - gazeHistory[0].timestamp).toFixed(1) : 0
    };
  }, [gazeHistory]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (gazePollingRef.current) {
        clearInterval(gazePollingRef.current);
      }
      if (healthCheckRef.current) {
        clearInterval(healthCheckRef.current);
      }
    };
  }, []);
  
  return {
    // State
    status,
    currentGaze,
    gazeHistory,
    eyeTrackingHealth,
    error,
    
    // Actions
    connect,
    startTracking,
    stopTracking,
    disconnect,
    setImageContext,
    switchImage,  // NEW: For sequence mode
    
    // Utilities
    getGazeStats,
    
    // Status checks
    isConnected: status === EYE_TRACKING_STATUS.CONNECTED || status === EYE_TRACKING_STATUS.TRACKING,
    isTracking: status === EYE_TRACKING_STATUS.TRACKING,
    hasError: status === EYE_TRACKING_STATUS.ERROR
  };
};
