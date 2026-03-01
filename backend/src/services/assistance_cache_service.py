"""
Assistance Cache Service - Structured saving of LLM responses and metadata
Organizes files by activity and image with proper naming conventions
Supports both standalone mode and sequence mode with different cache structures
"""
import json
import logging
import time
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class AssistanceCacheService:
    """Service for saving and managing assistance cache files"""
    
    def __init__(self):
        # Standalone mode cache
        self.cache_base = Path("../assistance_cache")
        
        # Sequence mode support (NEW)
        self.sequence_cache_service = None  # Will be set when in sequence mode
        
        # Create base cache directory
        self.cache_base.mkdir(parents=True, exist_ok=True)
    
    def save_chatgpt_response(
        self,
        image_name: str,
        activity: str,
        aoi_index: int,
        analysis: Dict[str, Any],
        voice_text: str,
        audio_url: Optional[str] = None,
        sequence_step: Optional[int] = None,  # NEW: For sequence mode
        start_timestamp: Optional[float] = None,  # NEW: Start timestamp from waiting message
        language: str = 'de'  # Language (German only)
    ) -> str:
        """
        Save ChatGPT response to structured JSON file
        
        Args:
            image_name: Image filename (e.g., "1.jpg")
            activity: "storytelling" only
            aoi_index: AOI index
            analysis: ChatGPT analysis result
            voice_text: Generated voice text
            audio_url: URL to corresponding audio file
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
                    logger.info("✅ Assistance Cache: Sequence mode auto-enabled")
                
                json_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_name,
                    file_type="json",
                    aoi_num=aoi_index,
                    assistance_mode="manual"
                )
                json_filename = json_path.name
                logger.debug(f"📂 Using sequence mode path: {json_path}")
            else:
                # STANDALONE MODE: Use traditional cache structure
                # Create activity-specific directory
                activity_dir = self.cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                
                # Generate structured filename: 1_asst_aoi_2.json
                image_base = Path(image_name).stem  # "1.jpg" -> "1"
                json_filename = f"{image_base}_asst_aoi_{aoi_index}.json"
                json_path = activity_dir / json_filename
                logger.debug(f"📂 Using standalone mode path: {json_path}")
            
            # Prepare data to save
            cache_data = {
                "metadata": {
                    "image_name": image_name,
                    "activity": activity,
                    "aoi_index": aoi_index,
                    "start_time": start_timestamp if start_timestamp else time.time(),  # Unix epoch float
                    "end_time": None  # Will be updated later via update-end-time endpoint
                },
                "llm_analysis": analysis,
                "voice_text": voice_text,
                "audio_url": audio_url,
                "voice_settings": {
                    "voice": "de-DE-KatjaNeural",
                    "language": "de-DE"
                }
            }
            
            # Save to JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved ChatGPT response: {json_filename}")
            
            return str(json_path)
            
        except Exception as e:
            logger.error(f"❌ Error saving ChatGPT response: {e}")
            return ""
    
    def save_chatgpt_response_two_aois(
        self,
        image_name: str,
        activity: str,
        primary_aoi_index: int,  # PRIMARY (assisted)
        secondary_aoi_index: int,  # SECONDARY (connected)
        analysis: Dict[str, Any],
        voice_text: str,
        audio_url: Optional[str] = None,
        sequence_step: Optional[int] = None,
        start_timestamp: Optional[float] = None,  # NEW: Start timestamp
        language: str = 'de'  # Language (German only)
    ) -> str:
        """
        Save ChatGPT response for two AOIs (storytelling only)
        
        Args:
            image_name: Image filename (e.g., "1.jpg")
            activity: "storytelling" only
            primary_aoi_index: PRIMARY AOI index (assisted)
            secondary_aoi_index: SECONDARY AOI index (connected)
            analysis: ChatGPT analysis result
            voice_text: Generated voice text
            audio_url: URL to corresponding audio file
            sequence_step: If provided, saves to sequence mode cache
            
        Returns:
            Path to saved JSON file
        """
        try:
            if activity != 'storytelling':
                logger.error(f"❌ Two AOI caching only supported for storytelling activity")
                return ""
            
            # SEQUENCE MODE: Use SequenceCacheService
            if sequence_step is not None:
                # Lazy-load sequence cache service when needed
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                    logger.info("✅ Assistance Cache: Sequence mode auto-enabled")
                
                # Use new naming convention for storytelling: {seq}_story_{img}_aoi_{primary}_aoi_{secondary}.json
                json_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_name,
                    file_type="json",
                    primary_aoi=primary_aoi_index,
                    secondary_aoi=secondary_aoi_index,
                    assistance_mode="manual"
                )
                json_filename = json_path.name
                logger.debug(f"📂 Using sequence mode path: {json_path}")
            else:
                # STANDALONE MODE: Use traditional cache structure with new naming
                activity_dir = self.cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                
                # New naming: {image}_story_aoi_{primary}_aoi_{secondary}.json
                json_filename = f"{image_name.split('.')[0]}_story_aoi_{primary_aoi_index}_aoi_{secondary_aoi_index}.json"
                json_path = activity_dir / json_filename
            
            # Prepare cache data
            cache_data = {
                "metadata": {
                    "image_name": image_name,
                    "activity": activity,
                    "primary_aoi_index": primary_aoi_index,  # PRIMARY (assisted)
                    "secondary_aoi_index": secondary_aoi_index,  # SECONDARY (connected)
                    "start_time": start_timestamp if start_timestamp else time.time(),  # Unix epoch float
                    "end_time": None  # Will be updated later
                },
                "analysis": analysis,
                "voice_text": voice_text,
                "audio_url": audio_url,
                "sequence_step": sequence_step,
                "voice_settings": {
                    "voice": "de-DE-KatjaNeural",
                    "language": "de-DE"
                }
            }
            
            # Save to JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved ChatGPT two-AOI response: {json_filename}")
            
            return str(json_path)
            
        except Exception as e:
            logger.error(f"❌ Error saving ChatGPT two-AOI response: {e}")
            return ""
    
    def load_cached_response(
        self,
        image_name: str,
        activity: str,
        aoi_index: int,
        sequence_step: Optional[int] = None  # NEW: For sequence mode
    ) -> Optional[Dict[str, Any]]:
        """
        Load cached ChatGPT response if it exists
        
        Args:
            image_name: Image filename
            activity: "storytelling" only
            aoi_index: AOI index
            sequence_step: If provided, loads from sequence mode cache
            
        Returns:
            Cached data or None
        """
        try:
            # SEQUENCE MODE: Use SequenceCacheService
            if sequence_step is not None:
                # Lazy-load sequence cache service when needed
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                
                json_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_name,
                    file_type="asst",
                    aoi_num=aoi_index
                )
                json_filename = json_path.name
                logger.debug(f"📂 Checking sequence mode cache: {json_path}")
            else:
                # STANDALONE MODE: Use traditional cache structure
                # Generate filename
                image_base = Path(image_name).stem
                json_filename = f"{image_base}_asst_aoi_{aoi_index}.json"
                json_path = self.cache_base / activity / json_filename
                logger.debug(f"📂 Checking standalone mode cache: {json_path}")
            
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                logger.info(f"📂 Loaded cached response: {json_filename}")
                return cache_data
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error loading cached response: {e}")
            return None
    
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
            logger.info(f"🔍 [MANUAL UPDATE] Received parameters: image_name={image_name}, activity={activity}, "
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
                    logger.info(f"📍 [MANUAL UPDATE] Taking TWO-AOI branch: primary_aoi={aoi_index}, secondary_aoi={secondary_aoi_index}")
                    logger.info(f"🔍 [MANUAL UPDATE] Calling get_file_path with: seq_num={sequence_step}, activity={activity}, "
                               f"image_name={image_name}, file_type='json', primary_aoi={aoi_index}, "
                               f"secondary_aoi={secondary_aoi_index}, assistance_mode='manual'")
                    
                    # Two-AOI file: {seq}_{activity}_{img}_aoi_{primary}_aoi_{secondary}.json
                    json_path = self.sequence_cache_service.get_file_path(
                        seq_num=sequence_step,
                        activity=activity,
                        image_name=image_name,
                        file_type="json",
                        primary_aoi=aoi_index,
                        secondary_aoi=secondary_aoi_index,
                        assistance_mode="manual"
                    )
                else:
                    # DIAGNOSTIC: Log single-AOI branch
                    logger.info(f"📍 [MANUAL UPDATE] Taking SINGLE-AOI branch: aoi_num={aoi_index}")
                    logger.info(f"🔍 [MANUAL UPDATE] Calling get_file_path with: seq_num={sequence_step}, activity={activity}, "
                               f"image_name={image_name}, file_type='json', aoi_num={aoi_index}, "
                               f"assistance_mode='manual'")
                    
                    # Single-AOI file: {seq}_{activity}_{img}_aoi_{aoi}.json
                    json_path = self.sequence_cache_service.get_file_path(
                        seq_num=sequence_step,
                        activity=activity,
                        image_name=image_name,
                        file_type="json",
                        aoi_num=aoi_index,
                        assistance_mode="manual"
                    )
            else:
                # STANDALONE MODE: Use traditional cache structure
                image_base = Path(image_name).stem
                if secondary_aoi_index is not None:
                    # Two-AOI file
                    json_filename = f"{image_base}_story_aoi_{aoi_index}_aoi_{secondary_aoi_index}.json"
                else:
                    # Single-AOI file
                    json_filename = f"{image_base}_asst_aoi_{aoi_index}.json"
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
    
    def clear_cache(self, activity: Optional[str] = None, image_name: Optional[str] = None):
        """Clear cache files"""
        try:
            if activity and image_name:
                # Clear specific image
                image_base = Path(image_name).stem
                activity_dir = self.cache_base / activity
                
                # Remove all files for this image
                pattern = f"{image_base}_asst_aoi_*.json"
                removed_count = 0
                
                for file_path in activity_dir.glob(pattern):
                    file_path.unlink()
                    removed_count += 1
                
                logger.info(f"🧹 Cleared {removed_count} cache files for {activity}/{image_name}")
                
            elif activity:
                # Clear entire activity
                activity_dir = self.cache_base / activity
                if activity_dir.exists():
                    import shutil
                    shutil.rmtree(activity_dir)
                    logger.info(f"🧹 Cleared all cache for {activity}")
            else:
                # Clear everything
                import shutil
                shutil.rmtree(self.cache_base)
                self.cache_base.mkdir(parents=True, exist_ok=True)
                logger.info(f"🧹 Cleared entire assistance cache")
                
        except Exception as e:
            logger.error(f"❌ Error clearing cache: {e}")
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache directory status"""
        try:
            status = {
                "cache_base": str(self.cache_base),
                "activities": {}
            }
            
            for activity in ["storytelling"]:
                activity_dir = self.cache_base / activity
                if activity_dir.exists():
                    files = list(activity_dir.glob("*.json"))
                    audio_files = list(activity_dir.glob("*.wav"))
                    
                    status["activities"][activity] = {
                        "json_files": len(files),
                        "audio_files": len(audio_files),
                        "files": [f.name for f in files]
                    }
                else:
                    status["activities"][activity] = {
                        "json_files": 0,
                        "audio_files": 0,
                        "files": []
                    }
            
            return status
            
        except Exception as e:
            logger.error(f"❌ Error getting cache status: {e}")
            return {"error": str(e)}
    
    def enable_sequence_mode(self, sequence_cache_service):
        """
        Enable sequence mode for this service
        
        Args:
            sequence_cache_service: Instance of SequenceCacheService
        """
        self.sequence_cache_service = sequence_cache_service
        logger.info("✅ Assistance Cache: Sequence mode enabled")
    
    def disable_sequence_mode(self):
        """Disable sequence mode (return to standalone mode)"""
        self.sequence_cache_service = None
        logger.info("✅ Assistance Cache: Sequence mode disabled")

# Global instance
_assistance_cache_service: Optional[AssistanceCacheService] = None

def get_assistance_cache_service() -> AssistanceCacheService:
    """Get the global assistance cache service instance"""
    global _assistance_cache_service
    if _assistance_cache_service is None:
        _assistance_cache_service = AssistanceCacheService()
    return _assistance_cache_service
