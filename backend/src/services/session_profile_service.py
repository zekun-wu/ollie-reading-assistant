"""
Session Profile Service - Manages saving and loading child name and age
Stores profile data once at session start, can be read by other services
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class SessionProfileService:
    """Service for managing session profile (child name and age)"""
    
    def __init__(self):
        # Store current user_number in memory for loading
        self._current_user_number: Optional[int] = None
        # Old profile location (for migration/cleanup)
        self._old_profile_file = Path("../session_data") / "session_profile.json"
    
    def _reset_dependent_services(self):
        """Reset services that cache user_number when starting a new session"""
        logger.info("🔄 Resetting dependent services for new session...")
        
        # Reset SequenceCacheService
        try:
            from services.sequence_cache_service import get_sequence_cache_service
            scs = get_sequence_cache_service()
            if hasattr(scs, 'reset'):
                scs.reset()
        except Exception as e:
            logger.warning(f"⚠️ Could not reset SequenceCacheService: {e}")
        
        # Reset GazeDataService
        try:
            from services.gaze_data_service import get_gaze_data_service
            gds = get_gaze_data_service()
            if hasattr(gds, 'reset'):
                gds.reset()
        except Exception as e:
            logger.warning(f"⚠️ Could not reset GazeDataService: {e}")
        
        # Reset AOI Service (if it has cached user data)
        try:
            from services.aoi_service import get_aoi_service
            aoi = get_aoi_service()
            if hasattr(aoi, 'reset'):
                aoi.reset()
        except Exception as e:
            pass  # AOI service may not need reset
        
        logger.info("✅ Dependent services reset complete")
    
    def _get_profile_path(self, user_number: Optional[int] = None) -> Path:
        """Get profile file path based on user_number"""
        if user_number is None:
            user_number = self._current_user_number
        
        if user_number is None:
            # Fallback: try to find from old location or return None
            return self._old_profile_file
        
        # Use user-specific path: backend/record/{user_number}/profile.json
        backend_dir = Path(__file__).parent.parent.parent
        profile_dir = backend_dir / "record" / str(user_number)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir / "profile.json"
    
    def save_profile(self, child_name: str, child_age: str = "", user_number: Optional[int] = None) -> Dict:
        """
        Save child name, age, and user number to session profile
        Saves to backend/record/{user_number}/profile.json
        
        Args:
            child_name: Child's name
            child_age: Child's age (optional)
            user_number: User/participant number (1-100, optional)
            
        Returns:
            Dict with success status and profile data
        """
        try:
            if user_number is None:
                logger.warning("⚠️ No user_number provided, cannot save to user-specific directory")
                return {
                    "success": False,
                    "error": "user_number is required to save profile"
                }
            
            profile_data = {
                "child_name": child_name,
                "child_age": child_age or "",
                "user_number": user_number
            }
            
            # Get user-specific profile path
            profile_file = self._get_profile_path(user_number)
            
            # Save to user-specific JSON file
            with open(profile_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            # Reset dependent services that cache user_number BEFORE updating
            # This ensures they will fetch the new user_number on next access
            self._reset_dependent_services()
            
            # Store user_number in memory for future loads
            self._current_user_number = user_number
            
            # Remove old profile file if it exists (migration)
            if self._old_profile_file.exists():
                try:
                    self._old_profile_file.unlink()
                    logger.info(f"🗑️ Removed old profile file: {self._old_profile_file}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not remove old profile file: {e}")
            
            logger.info("Saved session profile: user_number=%s", user_number)
            
            return {
                "success": True,
                "profile": profile_data,
                "file_path": str(profile_file)
            }
            
        except Exception as e:
            logger.error(f"❌ Error saving session profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def load_profile(self, user_number: Optional[int] = None) -> Optional[Dict]:
        """
        Load child name and age from session profile
        Loads from backend/record/{user_number}/profile.json
        
        Args:
            user_number: Optional user number to load. If None, uses cached user_number.
        
        Returns:
            Dict with child_name, child_age, and user_number, or None if not found
        """
        try:
            # Try user-specific path first
            profile_file = self._get_profile_path(user_number)
            
            if profile_file.exists():
                with open(profile_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                
                # Cache user_number for future loads
                if profile_data.get('user_number'):
                    self._current_user_number = profile_data.get('user_number')
                
                logger.debug(f"📂 Loaded session profile from: {profile_file}")
                logger.debug(f"   Child: {profile_data.get('child_name')}, age: {profile_data.get('child_age', '')}, user_number: {profile_data.get('user_number')}")
                
                return profile_data
            
            # Fallback: try old location for backward compatibility
            if self._old_profile_file.exists():
                logger.warning(f"⚠️ Loading from old profile location: {self._old_profile_file}")
                with open(self._old_profile_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                
                # If we have user_number, migrate to new location
                if profile_data.get('user_number'):
                    self._current_user_number = profile_data.get('user_number')
                    # Save to new location
                    self.save_profile(
                        profile_data.get('child_name', 'Guest'),
                        profile_data.get('child_age', ''),
                        profile_data.get('user_number')
                    )
                
                return profile_data
            
            logger.debug("📂 No session profile found")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error loading session profile: {e}")
            return None
    
    def get_child_name(self) -> str:
        """Get child name from profile, defaulting to 'Guest'"""
        profile = self.load_profile()
        return profile.get('child_name', 'Guest') if profile else 'Guest'
    
    def get_child_age(self) -> Optional[str]:
        """Get child age from profile, or None if not found"""
        profile = self.load_profile()
        return profile.get('child_age') if profile else None
    
    def get_user_number(self) -> Optional[int]:
        """Get user number from profile, or None if not found"""
        # Try cached value first
        if self._current_user_number is not None:
            return self._current_user_number
        
        # Load from file
        profile = self.load_profile()
        user_number = profile.get('user_number') if profile else None
        
        # Cache it
        if user_number:
            self._current_user_number = user_number
        
        return user_number
    
    def clear_profile(self, user_number: Optional[int] = None):
        """Clear the session profile"""
        try:
            profile_file = self._get_profile_path(user_number)
            
            if profile_file.exists():
                profile_file.unlink()
                logger.info(f"🗑️ Cleared session profile: {profile_file}")
            
            # Also clear old profile if it exists
            if self._old_profile_file.exists():
                self._old_profile_file.unlink()
                logger.info(f"🗑️ Cleared old session profile: {self._old_profile_file}")
            
            # Clear cached user_number
            self._current_user_number = None
            
        except Exception as e:
            logger.error(f"❌ Error clearing session profile: {e}")

# Global instance
_session_profile_service: Optional[SessionProfileService] = None

def get_session_profile_service() -> SessionProfileService:
    """Get the global session profile service instance"""
    global _session_profile_service
    if _session_profile_service is None:
        _session_profile_service = SessionProfileService()
    return _session_profile_service

