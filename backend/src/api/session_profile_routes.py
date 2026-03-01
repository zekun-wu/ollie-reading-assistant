"""
Session Profile API Routes
Endpoint for saving child name and age once at session start
"""
from fastapi import APIRouter, Form, HTTPException
from typing import Optional
import logging

from services.session_profile_service import get_session_profile_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/profile")
async def save_session_profile(
    child_name: str = Form(...),
    child_age: Optional[str] = Form(""),
    user_number: Optional[int] = Form(None)
):
    """
    Save child name, age, and user number to session profile (called once when intro completes)
    
    Args:
        child_name: Name of the child
        child_age: Age of the child (optional)
        user_number: User/participant number (1-100, optional)
    
    Returns:
        Success status and saved profile data
    """
    try:
        profile_service = get_session_profile_service()
        
        result = profile_service.save_profile(
            child_name=child_name,
            child_age=child_age or "",
            user_number=user_number
        )
        
        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Failed to save session profile')
            )
        
        logger.info(f"✅ Session profile saved: {child_name}, age: {child_age or 'not provided'}, user_number: {user_number or 'not provided'}")
        
        return {
            "success": True,
            "message": "Session profile saved",
            "profile": result.get('profile')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error saving session profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profile")
async def get_session_profile():
    """
    Get current session profile (child name and age)
    
    Returns:
        Profile data or empty if not set
    """
    try:
        profile_service = get_session_profile_service()
        profile = profile_service.load_profile()
        
        if not profile:
            return {
                "success": True,
                "exists": False,
                "profile": None
            }
        
        return {
            "success": True,
            "exists": True,
            "profile": profile
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting session profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

