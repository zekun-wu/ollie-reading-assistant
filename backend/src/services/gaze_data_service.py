"""
Gaze Data Service - Manages raw gaze data collection and storage
Saves gaze.json files for research analysis across all assistance conditions
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy import function to avoid circular dependency
def get_sequence_cache_service():
    """Lazy import of SequenceCacheService"""
    from .sequence_cache_service import SequenceCacheService
    if not hasattr(get_sequence_cache_service, '_instance'):
        get_sequence_cache_service._instance = SequenceCacheService()
    return get_sequence_cache_service._instance


def get_gaze_data_service():
    """Singleton accessor for GazeDataService (used by session_profile_service for reset)."""
    if not hasattr(get_gaze_data_service, '_instance'):
        get_gaze_data_service._instance = GazeDataService()
    return get_gaze_data_service._instance


class GazeDataService:
    """Service for collecting and saving raw gaze data"""
    
    def __init__(self):
        # Will be set based on user_number from session profile
        self.base_dir = None
        self.sequence_cache_service = None  # Lazy-load for sequence mode
    
    def reset(self):
        """Reset cached values for new session (called when user_number changes)"""
        self.base_dir = None
        self.sequence_cache_service = None
        logger.info("🔄 Gaze Data Service reset for new session")
    
    def _get_user_number(self) -> Optional[int]:
        """Get user number from session profile service"""
        try:
            from services.session_profile_service import get_session_profile_service
            profile_service = get_session_profile_service()
            return profile_service.get_user_number()
        except Exception as e:
            logger.warning(f"⚠️ Could not get user_number from session profile: {e}")
            return None
    
    def _get_base_dir(self) -> Path:
        """Get or initialize base_dir based on user_number"""
        if self.base_dir is not None:
            return self.base_dir
        
        user_number = self._get_user_number()
        backend_dir = Path(__file__).parent.parent.parent
        
        if user_number:
            # Use record/{user_number}/gaze_data/ structure
            self.base_dir = backend_dir / "record" / str(user_number) / "gaze_data"
            logger.debug("Using user-based gaze_data directory: %s", self.base_dir)
        else:
            # Fallback to old structure for backward compatibility
            self.base_dir = backend_dir / "gaze_data"
            logger.warning("⚠️ No user_number found, using fallback gaze_data/ directory")
        
        return self.base_dir
        
    def save_gaze_session(
        self,
        samples: List[Dict],
        child_name: str,
        condition: str,
        activity: str,
        image_name: str,
        start_time: float,
        end_time: float,
        sequence_step: Optional[int] = None
    ) -> Dict:
        """
        Save raw gaze samples to gaze.json
        
        Args:
            samples: List of gaze points [{"t": timestamp, "x": x, "y": y, "v": validity}, ...]
            child_name: Child's name
            condition: 'base', 'assistance', or 'eye_assistance'
            activity: 'storytelling' only
            image_name: Image filename (e.g., '1.jpg')
            start_time: Session start timestamp (Unix epoch)
            end_time: Session end timestamp (Unix epoch)
            sequence_step: Sequence step number (None for standalone)
            
        Returns:
            Dict with success status and file path
        """
        try:
            # Determine file path based on mode
            if sequence_step is not None:
                # Sequence mode: backend/record/{user_number}/mixed/{step}/gaze.json
                file_path = self._get_sequence_path(sequence_step)
            else:
                # Standalone mode: backend/gaze_data/{condition}_gaze/{activity}/{child}_{img}_gaze.json
                file_path = self._get_standalone_path(condition, activity, child_name, image_name)
            
            # Load child_age from session profile
            try:
                from services.session_profile_service import get_session_profile_service
                profile_service = get_session_profile_service()
                child_age = profile_service.get_child_age() or ""
            except Exception as e:
                logger.warning(f"⚠️ Could not load child_age from profile: {e}")
                child_age = ""
            
            # Calculate statistics (includes duration_ms)
            stats = self._calculate_statistics(samples, start_time, end_time)
            
            # Build simplified JSON structure
            data = {
                "samples": samples,
                "statistics": stats,
                "child_name": child_name,
                "child_age": child_age
            }
            
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"💾 Saved {len(samples)} gaze points to {file_path}")
            
            return {
                "success": True,
                "file_path": str(file_path),
                "sample_count": len(samples),
                "statistics": stats
            }
            
        except Exception as e:
            logger.error(f"❌ Error saving gaze session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_sequence_path(self, sequence_step: int) -> Path:
        """Get path for gaze.json in sequence mode"""
        if self.sequence_cache_service is None:
            self.sequence_cache_service = get_sequence_cache_service()
        
        return self.sequence_cache_service.get_gaze_path(sequence_step)
    
    def _get_standalone_path(self, condition: str, activity: str, child_name: str, image_name: str) -> Path:
        """Generate path for standalone mode - NO activity subfolder"""
        # Extract image number from filename (e.g., "1.jpg" -> "1")
        image_base = Path(image_name).stem
        
        # Map condition to directory name
        condition_map = {
            'base': 'baseline_gaze',
            'baseline': 'baseline_gaze',
            'assistance': 'assistance_gaze',
            'eye_assistance': 'eye_assistance_gaze'
        }
        
        condition_dir_name = condition_map.get(condition, f"{condition}_gaze")
        base_dir = self._get_base_dir()
        # NO activity subfolder - directly under condition_dir
        condition_dir = base_dir / condition_dir_name
        
        return condition_dir / f"{child_name}_{image_base}_gaze.json"
    
    def _calculate_statistics(self, samples: List[Dict], start_time: float, end_time: float) -> Dict:
        """Calculate statistics about gaze data including duration"""
        # Calculate duration
        duration_ms = int((end_time - start_time) * 1000)
        
        if not samples:
            return {
                "total_samples": 0,
                "valid_samples": 0,
                "invalid_samples": 0,
                "sampling_rate_hz": 0.0,
                "duration_ms": duration_ms
            }
        
        valid_samples = sum(1 for s in samples if s.get("v", 0) == 1)
        invalid_samples = len(samples) - valid_samples
        
        # Calculate sampling rate
        duration_sec = end_time - start_time
        sampling_rate = len(samples) / duration_sec if duration_sec > 0 else 0
        
        return {
            "total_samples": len(samples),
            "valid_samples": valid_samples,
            "invalid_samples": invalid_samples,
            "sampling_rate_hz": round(sampling_rate, 1),
            "duration_ms": duration_ms
        }
