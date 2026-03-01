"""
Eye-Tracking API Routes - REST endpoints for eye tracker control
"""
from fastapi import APIRouter, HTTPException, Form
from typing import Optional, Dict, Any
import logging
from dependencies import get_state_manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/status")
async def get_eye_tracking_status():
    """Get current status of the eye tracking system"""
    try:
        state_manager = get_state_manager()
        if not state_manager._eye_tracking_service:
            return {
                "success": False,
                "message": "Eye tracking service not initialized"
            }
        
        status = state_manager._eye_tracking_service.get_status()
        return {
            "success": True,
            "status": status
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting eye tracking status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/connect")
async def connect_eye_tracker():
    """Connect to Tobii eye tracker"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        # Check if already connected
        if eye_service.is_connected:
            logger.info("Eye tracker connect: already connected")
            return {
                "success": True,
                "message": "Eye tracker already connected",
                "status": eye_service.get_status()
            }
        
        success = await eye_service.find_and_connect_eyetracker()
        logger.info("Eye tracker connect: result=%s", success)
        
        return {
            "success": success,
            "message": "Eye tracker connected successfully" if success else "Failed to connect to eye tracker",
            "status": eye_service.get_status()
        }
        
    except Exception as e:
        logger.error(f"❌ Error connecting to eye tracker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start")
async def start_eye_tracking():
    """Start real-time gaze data collection"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        if not eye_service.is_connected:
            # Try to connect first
            if not await eye_service.find_and_connect_eyetracker():
                return {
                    "success": False,
                    "message": "Eye tracker not connected. Please connect first."
                }
        
        success = eye_service.start_tracking()
        
        return {
            "success": success,
            "message": "Eye tracking started successfully" if success else "Failed to start eye tracking",
            "status": eye_service.get_status()
        }
        
    except Exception as e:
        logger.error(f"❌ Error starting eye tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_eye_tracking():
    """Stop gaze data collection"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        success = eye_service.stop_tracking()
        
        return {
            "success": success,
            "message": "Eye tracking stopped" if success else "Failed to stop eye tracking",
            "status": eye_service.get_status()
        }
        
    except Exception as e:
        logger.error(f"❌ Error stopping eye tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/set-image")
async def set_current_image(image_filename: str = Form(...)):
    """Set the current image being viewed for context"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        image_path = f"../pictures/storytelling/{image_filename}"
        eye_service.set_image_context(image_path)
        
        return {
            "success": True,
            "message": f"Image context set to {image_filename}",
            "image_path": image_path
        }
        
    except Exception as e:
        logger.error(f"❌ Error setting image context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gaze-data")
async def get_current_gaze_data(count: int = 10):
    """Get the latest gaze data points"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        if not eye_service.is_tracking:
            return {
                "success": False,
                "message": "Eye tracking not active",
                "gaze_data": []
            }
        
        gaze_data = eye_service.get_latest_gaze_data(count)
        current_position = eye_service.get_current_gaze_position()
        
        # SIMPLE AOI PROCESSING: Use the working gaze data directly
        if current_position and state_manager._aoi_service and not state_manager._aoi_service.is_frozen:
            try:
                x = current_position['x']
                y = current_position['y']
                
                # Process with 25ms increments (frontend polling rate)
                aoi_result = state_manager._aoi_service.process_fixation_sync(x, y, 25)
                
                if aoi_result and aoi_result.get('guidance_triggered'):
                    guidance_info = aoi_result['guidance_triggered']
                    logger.info(f"🎯 API Route: AOI {guidance_info['aoi_index']} triggered")
                    
                    # Find actively reading session (only current image)
                    for image_filename, session in state_manager.sessions.items():
                        if session.is_actively_reading and session.current_state.value == 'tracking':
                            logger.info(f"  ✅ API Route: Using session {image_filename}")
                            gaze_data = {
                                "aoi_index": guidance_info['aoi_index'],
                                "aoi_bbox": guidance_info.get('aoi_bbox'),  # ← ADD BBOX
                                "aoi_center": guidance_info.get('center'),  # ← ADD CENTER
                                "total_duration": guidance_info['total_duration'],
                                "x": x, "y": y,
                                "detection_method": "simple_api_based"
                            }
                            
                            # Add to guidance queue instead of processing immediately
                            state_manager._add_guidance_to_queue(image_filename, "curiosity", gaze_data)
                            break  # Only process first (and only) actively reading session
                            
            except Exception as e:
                logger.error(f"❌ Simple AOI processing error: {e}")
        
        return {
            "success": True,
            "gaze_data": gaze_data,
            "current_position": current_position,
            "buffer_size": len(eye_service.gaze_buffer),
            "timestamp": state_manager.get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting gaze data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/disconnect")
async def disconnect_eye_tracker():
    """Disconnect from eye tracker"""
    try:
        state_manager = get_state_manager()
        eye_service = state_manager._eye_tracking_service
        
        if not eye_service:
            raise HTTPException(status_code=500, detail="Eye tracking service not available")
        
        eye_service.disconnect()
        
        return {
            "success": True,
            "message": "Eye tracker disconnected",
            "status": eye_service.get_status()
        }
        
    except Exception as e:
        logger.error(f"❌ Error disconnecting eye tracker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def eye_tracking_health_check():
    """Health check for eye tracking system"""
    try:
        state_manager = get_state_manager()
        
        if not state_manager._eye_tracking_service:
            return {
                "status": "unhealthy",
                "message": "Eye tracking service not initialized"
            }
        
        eye_service = state_manager._eye_tracking_service
        status = eye_service.get_status()
        
        return {
            "status": "healthy",
            "eye_tracking": status,
            "simulation_mode": eye_service.simulation_mode,
            "tobii_available": eye_service.tobii_available,
            "timestamp": state_manager.get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in eye tracking health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
