"""
Gaze API Routes - REST endpoints for gaze tracking operations
"""
from fastapi import APIRouter, HTTPException, Form, Depends
from typing import Optional, Dict, Any
import logging
from dependencies import get_state_manager, get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/start")
async def start_gaze_tracking(
    image_filename: str = Form(...),
    client_id: str = Form(...)
):
    """Start gaze tracking for an image"""
    try:
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        result = await state_manager.start_tracking(image_filename, client_id)
        
        # Notify via WebSocket if connected
        if result["success"]:
            await websocket_manager.send_state_update(client_id, {
                "image_filename": image_filename,
                "gaze_state": result["state"],
                "tracking_active": True
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error starting gaze tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_gaze_tracking(
    image_filename: str = Form(...),
    client_id: str = Form(...)
):
    """Stop gaze tracking for an image"""
    try:
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        result = await state_manager.stop_tracking(image_filename)
        
        # Notify via WebSocket if connected
        if result["success"]:
            await websocket_manager.send_state_update(client_id, {
                "image_filename": image_filename,
                "gaze_state": result["state"],
                "tracking_active": False
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error stopping gaze tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/state/{image_filename}")
async def get_gaze_state(image_filename: str):
    """Get current gaze state for an image"""
    try:
        state_manager = get_state_manager()
        result = await state_manager.get_session_state(image_filename)
        return result
        
    except Exception as e:
        logger.error(f"❌ Error getting gaze state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/freeze")
async def freeze_gaze(
    image_filename: str = Form(...),
    reason: str = Form(...),  # 'curiosity'
    client_id: str = Form(...),
    gaze_data: Optional[str] = Form(None)  # JSON string of gaze data
):
    """Freeze gaze tracking (legacy endpoint - use WebSocket for new implementations)"""
    try:
        import json
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        gaze_data_dict = json.loads(gaze_data) if gaze_data else None
        
        result = await state_manager.request_guidance(
            image_filename, reason, gaze_data_dict
        )
        
        # Notify via WebSocket
        if result["success"]:
            await websocket_manager.send_state_update(client_id, {
                "image_filename": image_filename,
                "gaze_state": result["state"],
                "frozen": True,
                "freeze_reason": reason
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error freezing gaze: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unfreeze")
async def unfreeze_gaze(
    image_filename: str = Form(...),
    client_id: str = Form(...)
):
    """Unfreeze gaze tracking (legacy endpoint)"""
    try:
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        result = await state_manager.dismiss_guidance(image_filename)
        
        # Notify via WebSocket
        if result["success"]:
            await websocket_manager.send_state_update(client_id, {
                "image_filename": image_filename,
                "gaze_state": result["state"],
                "frozen": False
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error unfreezing gaze: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def gaze_health_check():
    """Health check for gaze tracking system"""
    try:
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        health_status = await state_manager.get_health_status()
        websocket_info = await websocket_manager.get_connection_info()
        
        return {
            "status": "healthy",
            "state_manager": health_status,
            "websockets": websocket_info,
            "timestamp": state_manager.get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in gaze health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
