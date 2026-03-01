"""
Guidance API Routes - REST endpoints for guidance generation and management
"""
from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from typing import Optional, Dict, Any
import logging
from dependencies import get_state_manager, get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/request")
async def request_guidance(
    image_filename: str = Form(...),
    guidance_type: str = Form(...),  # 'curiosity'
    client_id: str = Form(...),
    gaze_data: Optional[str] = Form(None),  # JSON string
    priority: Optional[int] = Form(1)
):
    """Request guidance generation"""
    try:
        import json
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        gaze_data_dict = json.loads(gaze_data) if gaze_data else None
        
        result = await state_manager.request_guidance(
            image_filename, guidance_type, gaze_data_dict
        )
        
        # Notify client via WebSocket
        if result["success"]:
            await websocket_manager.send_to_client(client_id, {
                "type": "guidance_request_accepted",
                "request_id": result.get("request_id"),
                "guidance_type": guidance_type,
                "state": result["state"]
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error requesting guidance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dismiss")
async def dismiss_guidance(
    image_filename: str = Form(...),
    client_id: str = Form(...)
):
    """Dismiss current guidance and resume tracking"""
    try:
        state_manager = get_state_manager()
        websocket_manager = get_websocket_manager()
        
        result = await state_manager.dismiss_guidance(image_filename)
        
        # Notify client via WebSocket
        if result["success"]:
            await websocket_manager.send_to_client(client_id, {
                "type": "guidance_dismissed",
                "state": result["state"],
                "message": "Guidance dismissed, tracking resumed"
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error dismissing guidance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{image_filename}")
async def get_guidance_status(image_filename: str):
    """Get current guidance status for an image"""
    try:
        state_manager = get_state_manager()
        session_state = await state_manager.get_session_state(image_filename)
        
        if not session_state.get("exists"):
            return {"exists": False, "message": "No active session"}
        
        return {
            "exists": True,
            "state": session_state["state"],
            "has_active_request": session_state["has_active_request"],
            "queue_length": session_state["queue_length"],
            "is_generating": session_state["state"] == "generating_guidance",
            "is_ready": session_state["state"] == "guidance_ready",
            "last_update": session_state["last_update"]
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting guidance status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate")
async def generate_guidance_mock(
    image_filename: str = Form(...),
    guidance_type: str = Form(...),
    client_id: str = Form(...),
    image_file: Optional[UploadFile] = File(None)
):
    """Mock guidance generation endpoint (for testing)"""
    try:
        # This is a mock endpoint for testing the system
        # In the real implementation, this would be handled internally
        
        logger.info(f"🤖 Mock guidance generation: {guidance_type} for {image_filename}")
        
        # Simulate generation delay
        import asyncio
        await asyncio.sleep(1)
        
        # Mock guidance response
        mock_guidance = {
            "type": guidance_type,
            "message": f"This is a mock {guidance_type} guidance message!",
            "audio_url": None,
            "suggestions": [
                "Look at the colorful characters",
                "What do you think happens next?",
                "Can you find the hidden objects?"
            ] if guidance_type == "curiosity" else [
                "Let's refocus on the story",
                "Take a deep breath",
                "What was happening in the picture?"
            ],
            "timestamp": get_state_manager().get_current_timestamp()
        }
        
        # Send guidance to client
        websocket_manager = get_websocket_manager()
        await websocket_manager.send_guidance_ready(client_id, {
            "image_filename": image_filename,
            "guidance": mock_guidance
        })
        
        return {
            "success": True,
            "message": "Mock guidance generated",
            "guidance": mock_guidance
        }
        
    except Exception as e:
        logger.error(f"❌ Error in mock guidance generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def guidance_health_check():
    """Health check for guidance system"""
    try:
        # Check if guidance generation is working
        return {
            "status": "healthy",
            "guidance_system": "operational",
            "mock_mode": True,  # We're in mock mode for now
            "timestamp": get_state_manager().get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in guidance health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
