/**
 * Time Tracking Hook - Tracks picture viewing duration
 * Automatically starts when component mounts and ends when unmounts
 * Works across all three assistance conditions
 */
import { useState, useEffect, useRef } from 'react';

const API_BASE = (process.env.REACT_APP_API_URL || '') + '/api/time-tracking';

export const useTimeTracking = (imageFilename, activity, assistanceCondition, childName = 'Guest', sequenceStep = null) => {
  const [sessionId, setSessionId] = useState(null);
  const [isTracking, setIsTracking] = useState(false);
  const [error, setError] = useState(null);
  
  // Use refs to track latest values for cleanup
  const sessionIdRef = useRef(null);
  const isTrackingRef = useRef(false);
  
  /**
   * Start a new viewing session
   */
  const startSession = async () => {
    // Don't start if already tracking or missing required params
    if (isTrackingRef.current || !imageFilename || !activity || !assistanceCondition) {
      console.log('⏸️ Time tracking: Skipping start (already tracking or missing params)');
      return null;
    }
    
    try {
      const modeStr = sequenceStep ? ` [sequence step ${sequenceStep}]` : '';
      console.log(`▶️ Time tracking: Starting session for ${imageFilename} (${assistanceCondition})${modeStr}`);
      
      const formData = new FormData();
      formData.append('image_filename', imageFilename);
      formData.append('activity', activity);
      formData.append('assistance_condition', assistanceCondition);
      formData.append('child_name', childName || 'Guest');
      
      // NEW: Add sequence_step if in sequence mode
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch(`${API_BASE}/start`, {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      
      if (result.success) {
        const newSessionId = result.session_id;
        setSessionId(newSessionId);
        setIsTracking(true);
        sessionIdRef.current = newSessionId;
        isTrackingRef.current = true;
        
        console.log(`✅ Time tracking session started: ${newSessionId}`);
        return newSessionId;
      } else {
        throw new Error(result.error || 'Failed to start session');
      }
    } catch (err) {
      console.error('❌ Error starting time tracking:', err);
      setError(err.message);
      return null;
    }
  };
  
  /**
   * End the current viewing session
   */
  const endSession = async () => {
    const currentSessionId = sessionIdRef.current;
    
    if (!currentSessionId || !isTrackingRef.current) {
      console.log('⏸️ Time tracking: No active session to end');
      return null;
    }
    
    try {
      console.log(`⏹️ Time tracking: Ending session ${currentSessionId}`);
      
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      
      const response = await fetch(`${API_BASE}/end`, {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log(`✅ Session ended - Duration: ${result.duration_seconds}s`);
        if (result.viewing_sessions) {
          console.log(`📊 Viewing sessions:`, result.viewing_sessions);
        }
        
        // Clear tracking state
        setSessionId(null);
        setIsTracking(false);
        sessionIdRef.current = null;
        isTrackingRef.current = false;
        
        return result;
      } else {
        throw new Error(result.error || 'Failed to end session');
      }
    } catch (err) {
      console.error('❌ Error ending time tracking:', err);
      setError(err.message);
      
      // Still clear state even on error
      setSessionId(null);
      setIsTracking(false);
      sessionIdRef.current = null;
      isTrackingRef.current = false;
      
      return null;
    }
  };
  
  /**
   * Force cleanup of session (without ending it properly)
   * Used when page closes unexpectedly
   */
  const cleanupSession = async () => {
    const currentSessionId = sessionIdRef.current;
    
    if (!currentSessionId) {
      return;
    }
    
    try {
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      
      await fetch(`${API_BASE}/cleanup`, {
        method: 'POST',
        body: formData
      });
      
      console.log(`🧹 Session cleaned up: ${currentSessionId}`);
    } catch (err) {
      console.error('❌ Error cleaning up session:', err);
    }
    
    // Clear state
    setSessionId(null);
    setIsTracking(false);
    sessionIdRef.current = null;
    isTrackingRef.current = false;
  };
  
  /**
   * Record server time when assistance highlight appears. Uses current session_id.
   * Call when the highlight is shown (server records time on request).
   * @param {number|null} assistanceIndex - Optional 1-based index; when provided, avoids wrong index when requests arrive out of order.
   */
  const recordAssistanceStart = async (assistanceIndex = null) => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || !isTrackingRef.current) return;
    try {
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      if (assistanceIndex != null) {
        formData.append('assistance_index', assistanceIndex);
      }
      const response = await fetch(`${API_BASE}/assistance-start`, {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result.success) {
        console.log('✅ Time tracking: assistance start recorded');
      }
    } catch (err) {
      console.error('❌ Error recording assistance start:', err);
    }
  };

  /**
   * Record server time when assistance highlight disappears. Uses current session_id.
   * Call when the highlight is cleared (server records time on request).
   * @param {number|null} assistanceIndex - Optional 1-based index; when provided, avoids wrong index when requests arrive out of order.
   */
  const recordAssistanceEnd = async (assistanceIndex = null) => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || !isTrackingRef.current) return;
    try {
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      if (assistanceIndex != null) {
        formData.append('assistance_index', assistanceIndex);
      }
      const response = await fetch(`${API_BASE}/assistance-end`, {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result.success) {
        console.log('✅ Time tracking: assistance end recorded');
      }
    } catch (err) {
      console.error('❌ Error recording assistance end:', err);
    }
  };

  /**
   * Record server time when LLM main-content voice starts (not waiting message).
   * Call when main-content TTS starts playing.
   * @param {number|null} assistanceIndex - Optional 1-based index; when provided, avoids wrong index when requests arrive out of order.
   */
  const recordVoiceStart = async (assistanceIndex = null) => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || !isTrackingRef.current) return;
    try {
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      if (assistanceIndex != null) {
        formData.append('assistance_index', assistanceIndex);
      }
      const response = await fetch(`${API_BASE}/assistance-voice-start`, {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result.success) {
        console.log('✅ Time tracking: voice start recorded');
      }
    } catch (err) {
      console.error('❌ Error recording voice start:', err);
    }
  };

  /**
   * Record server time when LLM main-content voice stops (not waiting message).
   * Call when main-content TTS ends.
   * @param {number|null} assistanceIndex - Optional 1-based index; when provided, avoids wrong index when requests arrive out of order.
   */
  const recordVoiceEnd = async (assistanceIndex = null) => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || !isTrackingRef.current) return;
    try {
      const formData = new FormData();
      formData.append('session_id', currentSessionId);
      if (assistanceIndex != null) {
        formData.append('assistance_index', assistanceIndex);
      }
      const response = await fetch(`${API_BASE}/assistance-voice-end`, {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result.success) {
        console.log('✅ Time tracking: voice end recorded');
      }
    } catch (err) {
      console.error('❌ Error recording voice end:', err);
    }
  };

  /**
   * Get time summary for the current picture
   */
  const getSummary = async () => {
    if (!imageFilename || !activity || !assistanceCondition) {
      return null;
    }
    
    try {
      const params = new URLSearchParams({
        activity,
        assistance_condition: assistanceCondition
      });
      
      const response = await fetch(
        `${API_BASE}/summary/${imageFilename}?${params}`
      );
      
      const result = await response.json();
      
      if (result.success && result.exists) {
        return result.data;
      }
      
      return null;
    } catch (err) {
      console.error('❌ Error getting time summary:', err);
      return null;
    }
  };
  
  // Auto-start session when component mounts or image changes
  useEffect(() => {
    let isMounted = true;
    
    const initSession = async () => {
      // First, end any existing session before starting new one
      if (isTrackingRef.current) {
        await endSession();
      }
      
      // Start new session if still mounted and have required params
      if (isMounted && imageFilename && activity && assistanceCondition) {
        await startSession();
      }
    };
    
    initSession();
    
    // Cleanup on unmount or before starting new session
    return () => {
      isMounted = false;
      if (isTrackingRef.current) {
        // Call endSession but don't block unmount
        endSession().catch(err => {
          console.error('Error ending session during cleanup:', err);
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageFilename, activity, assistanceCondition, childName, sequenceStep]);
  
  // Handle page close/refresh - try to end session gracefully
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isTrackingRef.current) {
        // Try to end session synchronously
        endSession();
      }
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  
  return {
    sessionId,
    isTracking,
    error,
    startSession,
    endSession,
    cleanupSession,
    getSummary,
    recordAssistanceStart,
    recordAssistanceEnd,
    recordVoiceStart,
    recordVoiceEnd
  };
};

