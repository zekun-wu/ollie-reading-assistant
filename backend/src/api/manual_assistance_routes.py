"""
Manual Assistance API Routes - Completely separate from eye-tracking assistance
Handles random AOI selection, LLM integration, and TTS for AssistanceBook.js
"""
from fastapi import APIRouter, HTTPException, Form
from typing import Optional, Dict, Any
import logging
import time
from services.manual_assistance_service import get_manual_assistance_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/start/{image_filename}")
async def start_manual_assistance(
    image_filename: str, 
    activity: str = Form(...),
    sequence_step: Optional[int] = Form(None),  # NEW: For sequence mode
    child_name: Optional[str] = Form(None),  # NEW: Child's name for personalized voice
    child_age: Optional[str] = Form(None),  # NEW: Child's age
    language: str = Form('de')  # Language (German only)
):
    """
    Start manual assistance session for AssistanceBook.js
    
    Args:
        image_filename: Image file name (e.g., "1.jpg")
        activity: "storytelling" only
        sequence_step: Optional sequence step number for sequence mode
        language: Language code ('en' or 'de')
    """
    try:
        service = get_manual_assistance_service()
        result = service.start_assistance_session(
            image_filename, 
            activity, 
            sequence_step=sequence_step,  # NEW: Pass sequence_step
            child_name=child_name,  # NEW: Pass child name
            child_age=child_age,  # NEW: Pass child age
            language=language  # NEW: Pass language
        )
        
        if result["success"]:
            # Also get waiting message for immediate display
            waiting_msg = service.get_waiting_message(language=language)
            result.update({
                "waiting_message": waiting_msg,
                "status": "session_started"
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error starting manual assistance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/next-aoi/{session_key}")
async def get_next_random_aoi(
    session_key: str,
    start_timestamp: Optional[float] = Form(None)  # NEW: Start timestamp from frontend
):
    """Get next random AOI for manual assistance"""
    try:
        service = get_manual_assistance_service()
        result = service.select_random_aoi(session_key, start_timestamp=start_timestamp)
        
        if result["success"] and not result.get("completed"):
            # Start LLM processing for the selected AOI
            # This will be implemented in next phase
            result.update({
                "status": "aoi_selected",
                "llm_processing": True
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error getting next AOI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop/{session_key}")
async def stop_manual_assistance(session_key: str):
    """Stop manual assistance session"""
    try:
        service = get_manual_assistance_service()
        result = service.stop_assistance_session(session_key)
        return result
        
    except Exception as e:
        logger.error(f"❌ Error stopping manual assistance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/waiting-message")
async def get_waiting_message(language: str = 'de'):
    """Get random waiting message for immediate display"""
    try:
        service = get_manual_assistance_service()
        waiting_msg = service.get_waiting_message(language=language)
        
        return {
            "success": True,
            "waiting_message": waiting_msg
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting waiting message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def manual_assistance_health():
    """Health check for manual assistance system"""
    try:
        service = get_manual_assistance_service()
        active_sessions = len(service.sessions)
        config_status = service.api_config.get_configuration_status()
        
        return {
            "status": "healthy",
            "active_sessions": active_sessions,
            "service_type": "manual_assistance",
            "api_configuration": config_status,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"❌ Manual assistance health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config-status")
async def get_config_status():
    """Get API configuration status for debugging"""
    try:
        service = get_manual_assistance_service()
        config_status = service.api_config.get_configuration_status()
        
        return {
            "success": True,
            "configuration": config_status,
            "chatgpt_key_preview": service.api_config.chatgpt_api_key[:10] + "..." if service.api_config.chatgpt_api_key else "Not set",
            "azure_key_preview": service.api_config.azure_speech_key[:10] + "..." if service.api_config.azure_speech_key else "Not set"
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting config status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update-end-time")
async def update_end_timestamp(
    image_filename: str = Form(...),
    activity: str = Form(...),
    aoi_index: int = Form(...),
    end_timestamp: float = Form(...),
    condition: str = Form(...),  # "assistance" or "eye_assistance"
    sequence_step: Optional[int] = Form(None),
    secondary_aoi_index: Optional[int] = Form(None),  # NEW: For two-AOI files
    start_timestamp: Optional[float] = Form(None)  # NEW: For updating start_time from frontend
):
    """
    Update end_timestamp in cached JSON files for both manual and eye-tracking assistance
    
    Args:
        image_filename: Image file name (e.g., "1.jpg")
        activity: "storytelling" only
        aoi_index: Index of the AOI that was shown
        end_timestamp: Unix timestamp when user dismissed the popup
        condition: "assistance" or "eye_assistance"
        sequence_step: Optional sequence step number for sequence mode
        secondary_aoi_index: Optional secondary AOI index for two-AOI files
    """
    try:
        if condition == "assistance":
            # Manual assistance - update asst.json
            from services.assistance_cache_service import get_assistance_cache_service
            cache_service = get_assistance_cache_service()
            result = cache_service.update_end_timestamp(
                image_filename, 
                activity, 
                aoi_index, 
                end_timestamp,
                sequence_step=sequence_step,
                secondary_aoi_index=secondary_aoi_index,  # NEW: Pass secondary AOI
                start_timestamp=start_timestamp  # NEW: Pass start_timestamp from frontend
            )
        elif condition == "eye_assistance":
            # Eye-tracking assistance - update eye_asst.json
            from services.eye_tracking_cache_service import get_eye_tracking_cache_service
            cache_service = get_eye_tracking_cache_service()
            result = cache_service.update_end_timestamp(
                image_filename,
                activity,
                aoi_index,
                end_timestamp,
                sequence_step=sequence_step,
                secondary_aoi_index=secondary_aoi_index,  # NEW: Pass secondary AOI
                start_timestamp=start_timestamp  # NEW: Pass start_timestamp from frontend
            )
        else:
            raise ValueError(f"Invalid condition: {condition}")
        
        if result.get("success"):
            logger.info(f"✅ Updated end_timestamp for {condition}: {image_filename}, AOI {aoi_index}")
            return {
                "success": True,
                "message": "End timestamp updated successfully"
            }
        else:
            logger.error(f"❌ Failed to update end_timestamp: {result.get('error')}")
            return {
                "success": False,
                "error": result.get("error", "Unknown error")
            }
        
    except Exception as e:
        logger.error(f"❌ Error updating end timestamp: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tts/waiting")
async def generate_waiting_tts(
    text: str = Form(...),
    image_name: str = Form("1.jpg"),
    activity: str = Form("storytelling"),
    sequence_step: Optional[int] = Form(None),  # NEW: For sequence mode
    language: str = Form('de')  # Language (German only)
):
    """Generate TTS for waiting messages"""
    try:
        from services.azure_tts_service import get_azure_tts_service
        
        tts_service = get_azure_tts_service()
        result = tts_service.synthesize_speech(
            text, 
            image_name,
            activity,
            None,  # No AOI index for waiting messages
            "waiting",
            sequence_step=sequence_step,  # NEW: Pass sequence_step
            language=language  # NEW: Pass language
        )
        
        if result.get("success"):
            logger.info("TTS waiting: %s", result.get("audio_url", "ok"))
            return {
                "success": True,
                "audio_url": result["audio_url"],
                "audio_path": result["audio_path"]
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "TTS generation failed"),
                "fallback": True
            }
        
    except Exception as e:
        logger.error(f"❌ Error generating waiting TTS: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback": True
        }

@router.post("/tts/baseline")
async def generate_baseline_tts(
    text: str = Form(...),
    image_name: str = Form("1.jpg"),
    activity: str = Form("storytelling"),
    sequence_step: Optional[int] = Form(None),  # NEW: For sequence mode
    language: str = Form('de')  # Language (German only)
):
    """Generate TTS for baseline mode messages"""
    try:
        from services.azure_tts_service import get_azure_tts_service
        
        tts_service = get_azure_tts_service()
        result = tts_service.synthesize_speech(
            text, 
            image_name,
            activity,
            None,  # No AOI index for baseline messages
            "baseline",  # NEW: Use "baseline" audio type
            sequence_step=sequence_step,  # NEW: Pass sequence_step
            language=language  # NEW: Pass language
        )
        
        if result.get("success"):
            logger.info("TTS baseline: %s", result.get("audio_url", "ok"))
            return {
                "success": True,
                "audio_url": result["audio_url"],
                "audio_path": result["audio_path"]
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Baseline TTS generation failed"),
                "fallback": True
            }
        
    except Exception as e:
        logger.error(f"❌ Error generating baseline TTS: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback": True
        }