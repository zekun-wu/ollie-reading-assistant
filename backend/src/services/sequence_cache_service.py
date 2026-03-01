"""
Sequence Cache Service - Manages cache structure for sequence mode only
Organizes files by sequence step number with unified naming convention

File Structure:
    backend/mixed/
        ├── intro_audio/
        │   ├── intro_greeting.wav
        │   └── intro_welcome.wav
        └── {step}/
            ├── timeline.json
            ├── {seq}_{act}_{img}_{aoi}_asst.json
            ├── {seq}_{act}_{img}_{aoi}_eye_asst.json
            ├── {seq}_{act}_{img}_{aoi}_main.wav
            ├── {seq}_{act}_{img}_{aoi}_explore.wav
            └── {seq}_{act}_{img}_waiting.wav

Naming Convention:
    - seq: sequence step number (1, 2, 3, ...)
    - act: activity abbreviation ("story" for storytelling)
    - img: image number extracted from filename (e.g., "1" from "1.jpg")
    - aoi: AOI number (only for main/explore audio and assistance JSON)
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SequenceCacheService:
    """Manages sequence mode cache structure - separate from standalone mode"""
    
    def __init__(self):
        """Initialize sequence cache service"""
        # Will be set based on user_number from session profile
        self.mixed_base = None
        self.intro_audio_dir = None
        self._user_number = None
        
        logger.info("✅ Sequence Cache Service initialized")
    
    def reset(self):
        """Reset cached values for new session (called when user_number changes)"""
        self.mixed_base = None
        self.intro_audio_dir = None
        self._user_number = None
        logger.info("🔄 Sequence Cache Service reset for new session")
    
    def _get_user_number(self) -> Optional[int]:
        """Get user number from session profile service"""
        if self._user_number is not None:
            return self._user_number
        
        try:
            from services.session_profile_service import get_session_profile_service
            profile_service = get_session_profile_service()
            user_number = profile_service.get_user_number()
            if user_number:
                self._user_number = user_number
                return user_number
        except Exception as e:
            logger.warning(f"⚠️ Could not get user_number from session profile: {e}")
        
        return None
    
    def _get_mixed_base(self) -> Path:
        """Get or initialize mixed_base directory based on user_number"""
        if self.mixed_base is not None:
            return self.mixed_base
        
        user_number = self._get_user_number()
        backend_dir = Path(__file__).parent.parent.parent
        
        if user_number:
            # Use record/{user_number}/mixed/ structure
            self.mixed_base = backend_dir / "record" / str(user_number) / "mixed"
            logger.info(f"📁 Using user-based mixed directory: {self.mixed_base}")
        else:
            # Fallback to old structure for backward compatibility
            self.mixed_base = backend_dir / "mixed"
            logger.warning("⚠️ No user_number found, using fallback mixed/ directory")
        
        # Initialize intro audio directory
        self.intro_audio_dir = self.mixed_base / "intro_audio"
        
        return self.mixed_base
    
    def get_sequence_step_dir(self, sequence_step: int) -> Path:
        """
        Get or create directory for a specific sequence step
        
        Args:
            sequence_step: Step number in the sequence (1-based)
            
        Returns:
            Path to the step directory
        """
        if sequence_step < 1:
            raise ValueError(f"Sequence step must be >= 1, got {sequence_step}")
        
        mixed_base = self._get_mixed_base()
        step_dir = mixed_base / str(sequence_step)
        step_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"📂 Ensured sequence step directory: {step_dir}")
        return step_dir
    
    def get_intro_audio_dir(self) -> Path:
        """
        Get or create intro audio directory
        
        Returns:
            Path to intro audio directory
        """
        mixed_base = self._get_mixed_base()
        intro_dir = mixed_base / "intro_audio"
        intro_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"📂 Ensured intro audio directory: {intro_dir}")
        return intro_dir
    
    def _get_activity_abbrev(self, activity: str) -> str:
        """
        Convert activity name to abbreviation
        
        Args:
            activity: "storytelling" only
            
        Returns:
            "story"
        """
        if activity == "storytelling":
            return "story"
        else:
            raise ValueError(f"Unknown activity: {activity} (only storytelling supported)")
    
    def _extract_image_number(self, image_name: str) -> str:
        """
        Extract image number from filename
        
        Args:
            image_name: e.g., "1.jpg", "2.png"
            
        Returns:
            Image number as string, e.g., "1", "2"
        """
        return Path(image_name).stem
    
    def generate_filename(
        self,
        seq_num: int,
        activity: str,
        image_name: str,
        file_type: str,
        aoi_num: Optional[int] = None,
        assistance_mode: Optional[str] = None,
        primary_aoi: Optional[int] = None,
        secondary_aoi: Optional[int] = None
    ) -> str:
        """
        Generate sequence mode filename following naming convention
        
        Args:
            seq_num: Sequence step number
            activity: "storytelling" only
            image_name: Image filename (e.g., "1.jpg")
            file_type: Type of file - "audio", "json", "waiting", "baseline"
            aoi_num: AOI number (for single AOI files)
            assistance_mode: "manual" or "eye_tracking" (for JSON files)
            primary_aoi: Primary AOI number (for storytelling with 2 AOIs)
            secondary_aoi: Secondary AOI number (for storytelling with 2 AOIs)
            
        Returns:
            Filename string
            
        Examples:
            - generate_filename(2, "storytelling", "1.png", "json", primary_aoi=4, secondary_aoi=7, assistance_mode="manual") -> "2_story_1_aoi_4_aoi_7.json"
            - generate_filename(2, "storytelling", "1.png", "audio", primary_aoi=4, secondary_aoi=7) -> "2_story_1_aoi_4_aoi_7.wav"
            - generate_filename(2, "storytelling", "1.png", "json", primary_aoi=4, secondary_aoi=7, assistance_mode="eye_tracking") -> "2_story_1_aoi_4_aoi_7_eye.json"
        """
        # Get activity abbreviation
        act = self._get_activity_abbrev(activity)
        
        # Extract image number
        img_num = self._extract_image_number(image_name)
        
        # Build filename based on file type
        if file_type == "waiting":
            # Waiting audio: {seq}_{act}_{img}_waiting.wav
            filename = f"{seq_num}_{act}_{img_num}_waiting.wav"
            
        elif file_type == "baseline":
            # Baseline audio: {seq}_{act}_{img}_baseline.wav
            filename = f"{seq_num}_{act}_{img_num}_baseline.wav"
            
        elif file_type == "audio":
            # Audio files: Drop _main suffix, use same base name as JSON
            if activity == "storytelling" and primary_aoi is not None and secondary_aoi is not None:
                # Storytelling with 2 AOIs: {seq}_story_{img}_aoi_{primary}_aoi_{secondary}.wav
                filename = f"{seq_num}_{act}_{img_num}_aoi_{primary_aoi}_aoi_{secondary_aoi}.wav"
            else:
                raise ValueError(f"AOI numbers required for storytelling audio files")
            
        elif file_type == "json":
            # JSON cache files: Add _eye suffix for eye-tracking
            # DIAGNOSTIC: Log parameters for JSON file generation
            logger.info(f"🔍 [GENERATE_FILENAME] JSON file requested - activity={activity}, "
                       f"primary_aoi={primary_aoi}, secondary_aoi={secondary_aoi}, aoi_num={aoi_num}, "
                       f"assistance_mode={assistance_mode}")
            
            if activity == "storytelling" and primary_aoi is not None and secondary_aoi is not None:
                # DIAGNOSTIC: Log storytelling condition matched
                logger.info(f"✅ [GENERATE_FILENAME] Storytelling condition matched: primary_aoi={primary_aoi}, secondary_aoi={secondary_aoi}")
                
                # Storytelling with 2 AOIs: {seq}_story_{img}_aoi_{primary}_aoi_{secondary}[_eye].json
                base_name = f"{seq_num}_{act}_{img_num}_aoi_{primary_aoi}_aoi_{secondary_aoi}"
                if assistance_mode == "eye_tracking":
                    filename = f"{base_name}_eye.json"
                else:
                    filename = f"{base_name}.json"
            else:
                # DIAGNOSTIC: Log why condition failed
                logger.error(f"❌ [GENERATE_FILENAME] Condition not matched!")
                logger.error(f"   Storytelling check: activity==storytelling? {activity == 'storytelling'}, "
                            f"primary_aoi is not None? {primary_aoi is not None}, "
                            f"secondary_aoi is not None? {secondary_aoi is not None}")
                raise ValueError(f"AOI numbers required for storytelling JSON files")
            
        else:
            raise ValueError(f"Unknown file type: {file_type}")
        
        logger.debug(f"📝 Generated filename: {filename}")
        return filename
    
    def get_file_path(
        self,
        seq_num: int,
        activity: str,
        image_name: str,
        file_type: str,
        aoi_num: Optional[int] = None,
        assistance_mode: Optional[str] = None,
        primary_aoi: Optional[int] = None,
        secondary_aoi: Optional[int] = None
    ) -> Path:
        """
        Get full file path for a sequence mode file
        
        Args:
            seq_num: Sequence step number
            activity: "storytelling" only
            image_name: Image filename (e.g., "1.jpg")
            file_type: Type of file
            aoi_num: AOI number (if applicable)
            assistance_mode: "manual" or "eye_tracking" (for JSON files)
            primary_aoi: Primary AOI number (for storytelling with 2 AOIs)
            secondary_aoi: Secondary AOI number (for storytelling with 2 AOIs)
            
        Returns:
            Full Path to the file
        """
        step_dir = self.get_sequence_step_dir(seq_num)
        filename = self.generate_filename(
            seq_num, activity, image_name, file_type, 
            aoi_num, assistance_mode, primary_aoi, secondary_aoi
        )
        file_path = step_dir / filename
        
        logger.debug(f"📍 Generated file path: {file_path}")
        return file_path
    
    def get_time_tracking_path(self, seq_num: int) -> Path:
        """
        Get path for time tracking file (always named timeline.json)
        
        Args:
            seq_num: Sequence step number
            
        Returns:
            Path to timeline.json
        """
        step_dir = self.get_sequence_step_dir(seq_num)
        time_path = step_dir / "timeline.json"
        
        logger.debug(f"⏱️ Time tracking path: {time_path}")
        return time_path
    
    def get_intro_audio_path(self, audio_type: str) -> Path:
        """
        Get path for intro audio files
        
        Args:
            audio_type: "greeting" or "welcome"
            
        Returns:
            Path to intro audio file
        """
        if audio_type not in ["greeting", "welcome"]:
            raise ValueError(f"Unknown intro audio type: {audio_type}")
        
        intro_dir = self.get_intro_audio_dir()
        filename = f"intro_{audio_type}.wav"
        audio_path = intro_dir / filename
        
        logger.debug(f"🎵 Intro audio path: {audio_path}")
        return audio_path
    
    def get_gaze_path(self, seq_num: int) -> Path:
        """
        Get path for gaze data file (always named gaze.json)
        
        Args:
            seq_num: Sequence step number
            
        Returns:
            Path to gaze.json
        """
        step_dir = self.get_sequence_step_dir(seq_num)
        gaze_path = step_dir / "gaze.json"
        
        logger.debug(f"👁️ Gaze data path: {gaze_path}")
        return gaze_path


# Global instance (will be created when needed in sequence mode)
_sequence_cache_service: Optional[SequenceCacheService] = None


def get_sequence_cache_service() -> SequenceCacheService:
    """Get or create the global SequenceCacheService instance"""
    global _sequence_cache_service
    if _sequence_cache_service is None:
        _sequence_cache_service = SequenceCacheService()
    return _sequence_cache_service
