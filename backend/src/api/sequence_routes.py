"""
Sequence API Routes
Endpoints for retrieving predefined sequence configurations
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from services.sequence_config_service import get_sequence_config_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_sequences():
    """
    List all available predefined sequence IDs
    
    Returns:
        Dict with list of available sequence IDs
    """
    try:
        service = get_sequence_config_service()
        sequence_ids = service.list_sequences()
        return {
            "success": True,
            "sequences": sequence_ids
        }
    except Exception as e:
        logger.error(f"❌ Error listing sequences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/default/sequence")
async def get_default_sequence():
    """
    Convenience endpoint to get the default sequence
    
    Returns:
        Dict with default sequence data
    """
    return await get_sequence("default")


@router.get("/participant/{user_number}")
async def get_participant_sequence(user_number: int):
    """
    Get sequence for a specific participant by user number
    
    Args:
        user_number: Participant number (1-100)
    
    Returns:
        Dict with sequence data for the participant
        Falls back to default sequence if participant file doesn't exist
    """
    try:
        # Validate user number range
        if user_number < 1 or user_number > 100:
            raise HTTPException(
                status_code=400, 
                detail=f"User number must be between 1 and 100, got {user_number}"
            )
        
        service = get_sequence_config_service()
        sequence = service.get_participant_sequence(user_number)
        
        if sequence is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Could not load sequence for participant {user_number}"
            )
        
        return {
            "success": True,
            "sequence_id": f"participant_{user_number}",
            "user_number": user_number,
            "sequence": sequence,
            "step_count": len(sequence)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting participant sequence for {user_number}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sequence_id}")
async def get_sequence(sequence_id: str):
    """
    Get a specific predefined sequence by ID
    
    Args:
        sequence_id: ID of the sequence to retrieve (e.g., "default")
        
    Returns:
        Dict with sequence data
    """
    try:
        service = get_sequence_config_service()
        sequence = service.get_sequence(sequence_id)
        
        if sequence is None:
            raise HTTPException(status_code=404, detail=f"Sequence '{sequence_id}' not found")
        
        return {
            "success": True,
            "sequence_id": sequence_id,
            "sequence": sequence,
            "step_count": len(sequence)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting sequence '{sequence_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
