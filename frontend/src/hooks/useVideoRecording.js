import { useState, useRef, useEffect } from 'react';

/**
 * Hook for recording screen video with per-clip segmentation
 */
export const useVideoRecording = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const sessionIdRef = useRef(null);
  const chunksRef = useRef([]);
  const currentClipTypeRef = useRef(null);
  const currentMetadataRef = useRef(null);

  /**
   * Start screen recording session (call once at demo start)
   */
  const startSession = async () => {
    try {
      setIsInitializing(true);
      
      // Generate session ID
      sessionIdRef.current = `session_${Date.now()}`;
      
      console.log('🎥 Starting camera recording session:', sessionIdRef.current);
      
      // Request camera access (default camera, no preview)
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30 }
        },
        audio: true // Capture audio from microphone
      });

      streamRef.current = stream;

      // Handle when camera disconnects
      stream.getVideoTracks()[0].onended = () => {
        console.log('⚠️ Camera disconnected');
        stopSession();
      };

      // Start recording immediately
      startRecordingClip();
      
      setIsRecording(true);
      setIsInitializing(false);

      console.log('✅ Video recording session started');
      return true;
    } catch (error) {
      console.error('❌ Failed to start video recording:', error);
      setIsInitializing(false);
      
      if (error.name === 'NotAllowedError') {
        alert('Please allow camera access to record the demo session.');
      } else if (error.name === 'NotFoundError') {
        alert('No camera found. Please connect a camera and try again.');
      } else {
        alert('Failed to start video recording. Please check your camera and try again.');
      }
      return false;
    }
  };

  /**
   * Start recording a new clip segment
   */
  const startRecordingClip = () => {
    if (!streamRef.current) {
      console.warn('⚠️ No stream available');
      return;
    }

    const options = {
      mimeType: 'video/webm;codecs=vp9,opus'
    };

    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options.mimeType = 'video/webm;codecs=vp8,opus';
    }

    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options.mimeType = 'video/webm';
    }

    const mediaRecorder = new MediaRecorder(streamRef.current, options);
    mediaRecorderRef.current = mediaRecorder;
    chunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };

    mediaRecorder.start(1000); // Collect data every second
  };

  /**
   * Save current clip and start next clip
   * @param {string} clipType - 'start', 'full', 'post', or 'end'
   * @param {object} metadata - { condition, imageNum }
   */
  const saveClip = async (clipType, metadata = {}) => {
    if (!mediaRecorderRef.current || !isRecording) {
      console.warn('⚠️ Cannot save clip: not recording');
      return;
    }

    try {
      console.log(`💾 Saving clip: ${clipType}`, metadata);

      // Stop current recording
      if (mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();

        // Wait for the stop event and data collection
        await new Promise((resolve) => {
          mediaRecorderRef.current.onstop = resolve;
          // Add timeout to prevent hanging
          setTimeout(resolve, 2000);
        });
      }

      // Create blob from chunks
      const blob = new Blob(chunksRef.current, { type: 'video/webm' });
      
      // Upload clip if there's data
      if (blob.size > 0) {
        await uploadVideoClip(blob, clipType, metadata);
      } else {
        console.warn('⚠️ Clip has no data, skipping upload');
      }

      // Start recording next clip (unless this is the end)
      if (clipType !== 'end' && streamRef.current && streamRef.current.active) {
        startRecordingClip();
        console.log(`🎬 Started recording next clip after ${clipType}`);
      }

    } catch (error) {
      console.error('❌ Error saving clip:', error);
      // Try to restart recording even if upload failed
      if (clipType !== 'end' && streamRef.current && streamRef.current.active) {
        try {
          startRecordingClip();
        } catch (e) {
          console.error('❌ Failed to restart recording:', e);
        }
      }
    }
  };

  /**
   * Stop entire recording session
   */
  const stopSession = async () => {
    if (!isRecording) {
      return;
    }

    try {
      console.log('🛑 Stopping video recording session');

      // Stop recording if active
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }

      setIsRecording(false);
      
      // Stop all tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }

      mediaRecorderRef.current = null;
      chunksRef.current = [];

      console.log('✅ Video recording session stopped');
    } catch (error) {
      console.error('❌ Error stopping recording session:', error);
      setIsRecording(false);
    }
  };

  /**
   * Upload video clip to backend
   */
  const uploadVideoClip = async (blob, clipType, metadata) => {
    try {
      const formData = new FormData();
      
      // Extract image number from filename if provided
      const imageNum = metadata.image 
        ? (metadata.image.match(/\d+/)?.[0] || 'unknown')
        : 'unknown';
      
      // Generate filename based on clip type
      let filename;
      if (clipType === 'start') {
        filename = `${sessionIdRef.current}_start.webm`;
      } else if (clipType === 'end') {
        filename = `${sessionIdRef.current}_end.webm`;
      } else if (clipType === 'full' || clipType === 'post') {
        const condition = metadata.condition || 'unknown';
        filename = `${sessionIdRef.current}_${condition}_${imageNum}_${clipType}.webm`;
      } else {
        filename = `${sessionIdRef.current}_${clipType}.webm`;
      }
      
      formData.append('video', blob, filename);
      formData.append('session_id', sessionIdRef.current || 'unknown');
      formData.append('clip_type', clipType);
      formData.append('condition', metadata.condition || 'unknown');
      formData.append('image_num', imageNum);
      
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8080';
      const response = await fetch(`${apiUrl}/api/video/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const result = await response.json();
        console.log(`✅ Video clip uploaded: ${filename}`, result);
      } else {
        console.error('❌ Failed to upload video clip:', response.statusText);
      }
    } catch (error) {
      console.error('❌ Error uploading video clip:', error);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isRecording) {
        stopSession();
      }
    };
  }, [isRecording]);

  return {
    isRecording,
    isInitializing,
    sessionId: sessionIdRef.current,
    startSession,
    saveClip,
    stopSession
  };
};

