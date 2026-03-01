"""
Area of Interest (AOI) API Routes - REST endpoints for AOI tracking
"""
from fastapi import APIRouter, HTTPException, Form, Query
from typing import Optional, Dict, Any
import logging
import json
from pathlib import Path
from dependencies import get_state_manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/summary/{image_filename}")
async def get_aoi_summary(image_filename: str):
    """Get AOI tracking summary for an image"""
    try:
        state_manager = get_state_manager()
        aoi_service = state_manager._aoi_service
        
        if not aoi_service:
            raise HTTPException(status_code=500, detail="AOI service not available")
        
        summary = aoi_service.get_aoi_summary()
        return {
            "success": True,
            "image_filename": image_filename,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting AOI summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset-guidance/{image_filename}")
async def reset_guidance_flags(image_filename: str):
    """Reset guidance issued flags for testing"""
    try:
        state_manager = get_state_manager()
        aoi_service = state_manager._aoi_service
        
        if not aoi_service:
            raise HTTPException(status_code=500, detail="AOI service not available")
        
        aoi_service.reset_guidance_flags()
        
        return {
            "success": True,
            "message": "Guidance flags reset for testing",
            "image_filename": image_filename
        }
        
    except Exception as e:
        logger.error(f"❌ Error resetting guidance flags: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{image_filename}")
async def get_aoi_data(image_filename: str):
    """Get detailed AOI data for an image"""
    try:
        state_manager = get_state_manager()
        aoi_service = state_manager._aoi_service
        
        if not aoi_service:
            raise HTTPException(status_code=500, detail="AOI service not available")
        
        if aoi_service.current_image != image_filename:
            # Load AOI definitions if different image
            loaded = aoi_service.load_aoi_definitions(image_filename)
            if not loaded:
                return {
                    "success": False,
                    "message": f"No AOI definitions found for {image_filename}"
                }
        
        from dataclasses import asdict
        
        return {
            "success": True,
            "image_filename": image_filename,
            "aoi_data": {
                str(aoi_index): asdict(data) 
                for aoi_index, data in aoi_service.aoi_data.items()
            },
            "summary": aoi_service.get_aoi_summary()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting AOI data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def aoi_health_check():
    """Health check for AOI system"""
    try:
        state_manager = get_state_manager()
        aoi_service = state_manager._aoi_service
        
        if not aoi_service:
            return {
                "status": "unhealthy",
                "message": "AOI service not initialized"
            }
        
        summary = aoi_service.get_aoi_summary()
        
        return {
            "status": "healthy",
            "aoi_system": summary,
            "timestamp": state_manager.get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in AOI health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
