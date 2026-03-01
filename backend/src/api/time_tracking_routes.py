"""
Time Tracking API Routes
Endpoints for tracking picture viewing time across assistance conditions
"""
from fastapi import APIRouter, Form, HTTPException
from typing import Optional
import logging

from services.time_tracking_service import get_time_tracking_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/start")
async def start_time_tracking(
    image_filename: str = Form(...),
    activity: str = Form(...),
    assistance_condition: str = Form(...),
    child_name: str = Form("Guest"),
    sequence_step: Optional[int] = Form(None)  # NEW: For sequence mode
):
    """
    Start tracking viewing time for a picture
    
    Args:
        image_filename: Name of the image file (e.g., "1.jpg")
        activity: Type of activity ("storytelling" only)
        assistance_condition: Condition type ("assistance" or "eye_assistance")
        child_name: Name of the child (optional, defaults to "Guest")
        sequence_step: Sequence step number (optional, for sequence mode)
    
    Returns:
        session_id: Unique identifier for this viewing session
    """
    try:
        time_service = get_time_tracking_service()
        
        # Validate assistance condition
        if assistance_condition not in ["assistance", "eye_assistance"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid assistance condition: {assistance_condition}"
            )
        
        # Validate activity
        if activity not in ["storytelling"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid activity: {activity} (only storytelling supported)"
            )
        
        # Start session (with optional sequence_step)
        session_id = time_service.start_session(
            image_filename=image_filename,
            activity=activity,
            assistance_condition=assistance_condition,
            child_name=child_name,
            sequence_step=sequence_step  # NEW: Pass sequence_step
        )
        
        logger.info(f"▶️ Started time tracking: {session_id}")
        
        return {
            "success": True,
            "session_id": session_id,
            "image_filename": image_filename,
            "activity": activity,
            "assistance_condition": assistance_condition,
            "child_name": child_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error starting time tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/assistance-start")
async def assistance_start(
    session_id: str = Form(...),
    assistance_index: Optional[int] = Form(None)
):
    """
    Record server time when an assistance highlight appears.
    Server records time.time() when this request is received.
    Optional assistance_index (1-based) avoids wrong index when requests arrive out of order.
    """
    try:
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            raise HTTPException(status_code=400, detail="assistance_index must be a positive integer")
        time_service = get_time_tracking_service()
        ok = time_service.record_assistance_start(session_id, assistance_index=assistance_index)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error recording assistance start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assistance-end")
async def assistance_end(
    session_id: str = Form(...),
    assistance_index: Optional[int] = Form(None)
):
    """
    Record server time when an assistance highlight disappears.
    Server records time.time() when this request is received.
    Optional assistance_index (1-based) avoids wrong index when requests arrive out of order.
    """
    try:
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            raise HTTPException(status_code=400, detail="assistance_index must be a positive integer")
        time_service = get_time_tracking_service()
        ok = time_service.record_assistance_end(session_id, assistance_index=assistance_index)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error recording assistance end: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assistance-voice-start")
async def assistance_voice_start(
    session_id: str = Form(...),
    assistance_index: Optional[int] = Form(None)
):
    """
    Record server time when LLM main-content voice starts (not waiting message).
    Server records time.time() when this request is received.
    Optional assistance_index (1-based) avoids wrong index when requests arrive out of order.
    """
    try:
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            raise HTTPException(status_code=400, detail="assistance_index must be a positive integer")
        time_service = get_time_tracking_service()
        ok = time_service.record_voice_start(session_id, assistance_index=assistance_index)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error recording assistance voice start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assistance-voice-end")
async def assistance_voice_end(
    session_id: str = Form(...),
    assistance_index: Optional[int] = Form(None)
):
    """
    Record server time when LLM main-content voice stops (not waiting message).
    Server records time.time() when this request is received.
    Optional assistance_index (1-based) avoids wrong index when requests arrive out of order.
    """
    try:
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            raise HTTPException(status_code=400, detail="assistance_index must be a positive integer")
        time_service = get_time_tracking_service()
        ok = time_service.record_voice_end(session_id, assistance_index=assistance_index)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error recording assistance voice end: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_time_tracking(
    session_id: str = Form(...)
):
    """
    End tracking and save viewing time
    
    Args:
        session_id: Session identifier from start_time_tracking
    
    Returns:
        Session summary with duration
    """
    try:
        time_service = get_time_tracking_service()
        
        # End session
        result = time_service.end_session(session_id)
        
        if not result.get('success'):
            raise HTTPException(
                status_code=404,
                detail=result.get('error', 'Session not found')
            )
        
        logger.info(f"⏹️ Ended time tracking: {session_id} - {result.get('duration_seconds')}s")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ending time tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary/{image_filename}")
async def get_time_summary(
    image_filename: str,
    activity: str,
    assistance_condition: str
):
    """
    Get time tracking summary for a specific picture
    
    Args:
        image_filename: Name of the image file
        activity: Type of activity
        assistance_condition: Condition type
    
    Returns:
        Complete time tracking data with all sessions and summary
    """
    try:
        time_service = get_time_tracking_service()
        
        # Validate inputs
        if assistance_condition not in ["assistance", "eye_assistance"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid assistance condition: {assistance_condition}"
            )
        
        if activity not in ["storytelling"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid activity: {activity} (only storytelling supported)"
            )
        
        # Get summary
        summary = time_service.get_time_summary(
            image_filename=image_filename,
            activity=activity,
            assistance_condition=assistance_condition
        )
        
        if not summary:
            return {
                "success": True,
                "exists": False,
                "message": "No time tracking data found for this picture"
            }
        
        return {
            "success": True,
            "exists": True,
            "data": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting time summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/{assistance_condition}/{activity}")
async def export_all_summaries(
    assistance_condition: str,
    activity: str
):
    """
    Export all time tracking data for a specific condition and activity
    
    Args:
        assistance_condition: Condition type
        activity: Type of activity
    
    Returns:
        List of all time tracking summaries
    """
    try:
        time_service = get_time_tracking_service()
        
        # Validate inputs
        if assistance_condition not in ["assistance", "eye_assistance"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid assistance condition: {assistance_condition}"
            )
        
        if activity not in ["storytelling"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid activity: {activity} (only storytelling supported)"
            )
        
        # Get all summaries
        summaries = time_service.get_all_summaries(
            assistance_condition=assistance_condition,
            activity=activity
        )
        
        return {
            "success": True,
            "assistance_condition": assistance_condition,
            "activity": activity,
            "total_pictures": len(summaries),
            "summaries": summaries
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error exporting summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup")
async def cleanup_session(
    session_id: str = Form(...)
):
    """
    Force cleanup of an active session (e.g., on error or page close)
    
    Args:
        session_id: Session identifier to cleanup
    
    Returns:
        Success status
    """
    try:
        time_service = get_time_tracking_service()
        time_service.cleanup_session(session_id)
        
        return {
            "success": True,
            "message": "Session cleaned up"
        }
        
    except Exception as e:
        logger.error(f"❌ Error cleaning up session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

