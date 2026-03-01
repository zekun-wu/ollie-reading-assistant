"""
Eye-Tracking Cache Service - Separate from Manual Assistance
Saves LLM responses for gaze-triggered curiosity guidance
Supports both standalone mode and sequence mode with different cache structures
"""
import json
import logging
import time
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class EyeTrackingCacheService:
    """Cache service for eye-tracking LLM responses"""
    
    def __init__(self):
        # Standalone mode cache
        self.cache_base = Path("../eye_assistance_cache")  # Separate cache
        
        # Sequence mode support (NEW)
        self.sequence_cache_service = None  # Will be set when in sequence mode
        
        # Create base cache directory
        self.cache_base.mkdir(parents=True, exist_ok=True)
    
    def save_llm_response(
        self,
        image_name: str,
        activity: str,
        aoi_index: int,
        analysis: Dict[str, Any],
        voice_texts: Dict[str, str],
        main_audio_url: Optional[str] = None,
        sequence_step: Optional[int] = None,  # NEW: For sequence mode
        start_timestamp: Optional[float] = None,  # NEW: Start timestamp from thinking message
        language: str = 'de'  # Language (German only)
    ) -> str:
        """
        Save eye-tracking LLM response with eye_ prefix
        
        Args:
            image_name: Image filename (e.g., "1.jpg")
            activity: "storytelling" only
            aoi_index: AOI index
            analysis: LLM analysis result
            voice_texts: Split voice texts
            main_audio_url: URL to main content audio
            sequence_step: If provided, saves to sequence mode cache
            
        Returns:
            Path to saved JSON file
        """
        try:
            # SEQUENCE MODE: Use SequenceCacheService
            if sequence_step is not None:
                # Lazy-load sequence cache service when needed
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                    logger.info("✅ Eye-Tracking Cache: Sequence mode auto-enabled")
                
                json_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_name,
                    file_type="json",
                    aoi_num=aoi_index,
                    assistance_mode="eye_tracking"
                )
                json_filename = json_path.name
                logger.debug(f"📂 Using sequence mode path: {json_path}")
            else:
                # STANDALONE MODE: Use traditional cache structure
                # Create activity-specific directory
                activity_dir = self.cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                
                # Generate structured filename: 1_eye_asst_aoi_5.json
                image_base = Path(image_name).stem
                json_filename = f"{image_base}_eye_asst_aoi_{aoi_index}.json"
                json_path = activity_dir / json_filename
                logger.debug(f"📂 Using standalone mode path: {json_path}")
            
            # Prepare data to save
            cache_data = {
                "metadata": {
                    "image_name": image_name,
                    "activity": activity,
                    "aoi_index": aoi_index,
                    "start_time": start_timestamp if start_timestamp else time.time(),  # Unix epoch float
                    "end_time": None,  # Will be updated later via update-end-time endpoint
                    "guidance_type": "eye_tracking_curiosity"
                },
                "llm_analysis": analysis,
                "voice_texts": voice_texts,
                "main_audio_url": main_audio_url,
                "voice_settings": {
                    "voice": "de-DE-KatjaNeural",
                    "language": "de-DE",
                    "rate": "0.7",
                    "pitch": "+8%"
                }
            }
            
            # Save to JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Eye-tracking: Saved LLM response: {json_filename}")
            
            return str(json_path)
            
        except Exception as e:
            logger.error(f"❌ Error saving eye-tracking LLM response: {e}")
            return ""
    
    def save_llm_response_two_aois(
        self,
        image_filename: str,
        activity: str,
        primary_aoi_index: int,
        secondary_aoi_index: int,
        llm_response: Dict[str, Any],
        main_audio_url: Optional[str],
        sequence_step: Optional[int] = None,
        start_timestamp: Optional[float] = None,  # NEW: Start timestamp
        language: str = 'de'  # Language (German only)
    ) -> bool:
        """Save LLM response for two AOIs with consistent naming convention"""
        try:
            from datetime import datetime
            
            if sequence_step is not None:
                # Sequence mode - use consistent naming with manual assistance
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                    logger.info("✅ Eye-Tracking Cache: Sequence mode auto-enabled")
                
                # Use consistent naming: {seq}_story_{img}_aoi_{primary}_aoi_{secondary}_eye.json
                json_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_filename,
                    file_type="json",
                    primary_aoi=primary_aoi_index,
                    secondary_aoi=secondary_aoi_index,
                    assistance_mode="eye_tracking"
                )
                save_path = json_path
                filename = json_path.name
            else:
                # Legacy mode
                image_name = Path(image_filename).stem
                filename = f"{image_name}_story_aoi_{primary_aoi_index}_aoi_{secondary_aoi_index}.json"
                activity_dir = self.cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                save_path = activity_dir / filename
            
            cache_data = {
                "metadata": {
                    "image_filename": image_filename,
                    "activity": activity,
                    "primary_aoi_index": primary_aoi_index,
                    "secondary_aoi_index": secondary_aoi_index,
                    "start_time": start_timestamp if start_timestamp else time.time(),  # Unix epoch float
                    "end_time": None,  # Will be updated later
                    "guidance_type": "eye_tracking_curiosity_two_aois"
                },
                "llm_response": llm_response,
                "main_audio_url": main_audio_url,
                "voice_settings": {
                    "voice": "de-DE-KatjaNeural",
                    "language": "de-DE",
                    "rate": "0.7",
                    "pitch": "+8%"
                }
            }
            
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Eye-tracking: Saved two-AOI response: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving two-AOI response: {e}")
            return False
    
    def update_end_timestamp(
        self,
        image_name: str,
        activity: str,
        aoi_index: int,
        end_timestamp: float,
        sequence_step: Optional[int] = None,
        secondary_aoi_index: Optional[int] = None,  # NEW: For two-AOI files
        start_timestamp: Optional[float] = None  # NEW: For updating start_time if provided
    ) -> Dict[str, Any]:
        """
        Update end_timestamp in existing cached JSON file
        
        Args:
            image_name: Image filename (e.g., "1.jpg")
            activity: "storytelling" only
            aoi_index: AOI index
            end_timestamp: Unix timestamp when user dismissed popup
            sequence_step: If provided, updates in sequence mode cache
            secondary_aoi_index: If provided, updates two-AOI file instead of single-AOI file
            
        Returns:
            Result dict with success status
        """
        try:
            # DIAGNOSTIC: Log all received parameters
            logger.info(f"🔍 [UPDATE] Received parameters: image_name={image_name}, activity={activity}, "
                       f"aoi_index={aoi_index}, secondary_aoi_index={secondary_aoi_index}, "
                       f"sequence_step={sequence_step}, end_timestamp={end_timestamp}, start_timestamp={start_timestamp}")
            # SEQUENCE MODE: Use SequenceCacheService
            if sequence_step is not None:
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                
                # Handle two-AOI files vs single-AOI files
                if secondary_aoi_index is not None:
                    # DIAGNOSTIC: Log two-AOI branch
                    logger.info(f"📍 [UPDATE] Taking TWO-AOI branch: primary_aoi={aoi_index}, secondary_aoi={secondary_aoi_index}")
                    logger.info(f"🔍 [UPDATE] Calling get_file_path with: seq_num={sequence_step}, activity={activity}, "
                               f"image_name={image_name}, file_type='json', primary_aoi={aoi_index}, "
                               f"secondary_aoi={secondary_aoi_index}, assistance_mode='eye_tracking'")
                    
                    # Two-AOI file: {seq}_{activity}_{img}_aoi_{primary}_aoi_{secondary}_eye.json
                    json_path = self.sequence_cache_service.get_file_path(
                        seq_num=sequence_step,
                        activity=activity,
                        image_name=image_name,
                        file_type="json",
                        primary_aoi=aoi_index,
                        secondary_aoi=secondary_aoi_index,
                        assistance_mode="eye_tracking"
                    )
                else:
                    # DIAGNOSTIC: Log single-AOI branch
                    logger.info(f"📍 [UPDATE] Taking SINGLE-AOI branch: aoi_num={aoi_index}")
                    logger.info(f"🔍 [UPDATE] Calling get_file_path with: seq_num={sequence_step}, activity={activity}, "
                               f"image_name={image_name}, file_type='json', aoi_num={aoi_index}, "
                               f"assistance_mode='eye_tracking'")
                    
                    # Single-AOI file: {seq}_{activity}_{img}_{aoi}_eye.json
                    json_path = self.sequence_cache_service.get_file_path(
                        seq_num=sequence_step,
                        activity=activity,
                        image_name=image_name,
                        file_type="json",
                        aoi_num=aoi_index,
                        assistance_mode="eye_tracking"
                    )
            else:
                # STANDALONE MODE: Use traditional cache structure
                image_base = Path(image_name).stem
                if secondary_aoi_index is not None:
                    # Two-AOI file
                    json_filename = f"{image_base}_story_aoi_{aoi_index}_aoi_{secondary_aoi_index}.json"
                else:
                    # Single-AOI file
                    json_filename = f"{image_base}_eye_asst_aoi_{aoi_index}.json"
                json_path = self.cache_base / activity / json_filename
            
            if not json_path.exists():
                error_msg = f"Cache file not found: {json_path}"
                logger.error(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
            
            # Load existing cache
            with open(json_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Update start_time if provided (from frontend highlight start time)
            if start_timestamp is not None:
                cache_data["metadata"]["start_time"] = start_timestamp
            
            # Update end_time
            cache_data["metadata"]["end_time"] = end_timestamp
            
            # Calculate duration if start_time exists
            start_time = cache_data["metadata"].get("start_time")
            duration = None
            if start_time:
                duration = end_timestamp - start_time
                cache_data["metadata"]["duration_seconds"] = duration
            
            # Save updated cache
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Updated end_timestamp in: {json_path.name} (duration: {duration:.2f}s)" if duration else f"✅ Updated end_timestamp in: {json_path.name}")
            
            return {
                "success": True,
                "file_path": str(json_path),
                "duration": duration
            }
            
        except Exception as e:
            error_msg = f"Error updating end_timestamp: {e}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    def enable_sequence_mode(self, sequence_cache_service):
        """
        Enable sequence mode for this service
        
        Args:
            sequence_cache_service: Instance of SequenceCacheService
        """
        self.sequence_cache_service = sequence_cache_service
        logger.info("✅ Eye-Tracking Cache: Sequence mode enabled")
    
    def disable_sequence_mode(self):
        """Disable sequence mode (return to standalone mode)"""
        self.sequence_cache_service = None
        logger.info("✅ Eye-Tracking Cache: Sequence mode disabled")

# Global instance
_eye_tracking_cache_service: Optional[EyeTrackingCacheService] = None

def get_eye_tracking_cache_service() -> EyeTrackingCacheService:
    """Get the global eye-tracking cache service instance"""
    global _eye_tracking_cache_service
    if _eye_tracking_cache_service is None:
        _eye_tracking_cache_service = EyeTrackingCacheService()
    return _eye_tracking_cache_service
