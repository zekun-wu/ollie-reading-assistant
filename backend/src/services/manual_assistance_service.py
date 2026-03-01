"""
Manual Assistance Service for AssistanceBook.js
Completely separate from eye-tracking assistance system
Handles random AOI selection, image cropping, and LLM integration
"""
import json
import os
import time
import logging
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import sys
import os
# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

try:
    from config.api_keys import get_api_config
    from services.image_cropping_service import get_image_cropping_service
    from services.chatgpt_service import get_chatgpt_service
    from services.azure_tts_service import get_azure_tts_service
    from services.assistance_cache_service import get_assistance_cache_service
except ImportError as e:
    print(f"❌ Failed to import API config: {e}")
    # Create a dummy config for now
    class DummyConfig:
        def get_configuration_status(self):
            return {"chatgpt_configured": False, "azure_configured": False, "error": "Import failed"}
        def is_chatgpt_configured(self):
            return False
        def is_azure_configured(self):
            return False
    
    def get_api_config():
        return DummyConfig()

logger = logging.getLogger(__name__)

@dataclass
class ManualAOI:
    """Manual assistance AOI data"""
    index: int
    bbox: List[int]  # [x1, y1, x2, y2]
    center: List[int]  # [x, y]
    area: int
    objects: Optional[List[str]] = None  # List of object names in this AOI (English)
    objects_de: Optional[List[str]] = None  # List of object names in this AOI (German)

@dataclass
class ManualAssistanceSession:
    """Manual assistance session state"""
    image_filename: str
    activity: str
    available_aois: List[ManualAOI]
    used_aoi_indices: List[int]
    current_aoi: Optional[ManualAOI]
    completed: bool
    sequence_step: Optional[int] = None  # NEW: For sequence mode
    child_name: Optional[str] = None  # NEW: Personalized child name
    child_age: Optional[str] = None  # NEW: Child's age
    assisted_aoi_indices: List[int] = None  # NEW: Track assisted AOIs for storytelling
    language: str = 'de'  # Language (German only)
    previous_stories: List[Dict[str, Any]] = field(default_factory=list)  # NEW: Track previous story JSON responses for continuity

class ManualAssistanceService:
    """
    Manual assistance service for AssistanceBook.js
    Completely independent from eye-tracking assistance
    """
    
    def __init__(self):
        self.sessions: Dict[str, ManualAssistanceSession] = {}
        self.labels_base_dir = Path("../segmented_pictures")  # Base directory
        self.images_dir = Path("../pictures")
        self.assistance_cache_dir = Path("../assistance_cache")
        
        # Create cache directory
        self.assistance_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load API configuration
        self.api_config = get_api_config()
        
        # Log configuration status
        config_status = self.api_config.get_configuration_status()
        
    def start_assistance_session(
        self, 
        image_filename: str, 
        activity: str, 
        sequence_step: Optional[int] = None,  # NEW: For sequence mode
        child_name: Optional[str] = None,  # NEW: Personalized child name
        child_age: Optional[str] = None,  # NEW: Child's age
        language: str = 'de'  # Language (German only)
    ) -> Dict[str, Any]:
        """
        Start a new manual assistance session
        
        Args:
            image_filename: Image file name (e.g., "1.jpg")
            activity: "storytelling" only
            sequence_step: Optional sequence step number for sequence mode
            
        Returns:
            Dict with success status and session key
        """
        try:
            session_key = f"{activity}_{image_filename}"
            
            # Load AOI definitions from activity-specific directory
            image_name = Path(image_filename).stem
            labels_file = self.labels_base_dir / activity / f"{image_name}_labels.json"
            
            if not labels_file.exists():
                logger.error(f"❌ No AOI definitions found: {labels_file}")
                return {
                    "success": False,
                    "error": f"No AOI definitions found for {image_filename}"
                }
            
            # Load and parse AOI data
            with open(labels_file, 'r') as f:
                labels_data = json.load(f)
            
            # Build available AOIs list
            available_aois = []
            for obj in labels_data.get('objects', []):
                aoi = ManualAOI(
                    index=obj['index'],
                    bbox=obj['bbox'],
                    center=obj['center'],
                    area=obj['area'],
                    objects=obj.get('objects', []),  # English objects
                    objects_de=obj.get('objects_de', [])  # German objects
                )
                available_aois.append(aoi)
            
            if not available_aois:
                logger.error(f"❌ No AOIs found in labels file")
                return {
                    "success": False,
                    "error": "No AOIs available for this image"
                }
            
            # Create new session with correct structure
            session = ManualAssistanceSession(
                image_filename=image_filename,
                activity=activity,
                available_aois=available_aois,
                used_aoi_indices=[],
                current_aoi=None,
                completed=False,
                sequence_step=sequence_step,  # NEW: Store sequence step
                child_name=child_name,  # NEW: Store child name
                child_age=child_age,  # NEW: Store child age
                assisted_aoi_indices=[],  # NEW: Initialize assisted AOIs tracking
                language=language  # NEW: Store language
            )
            
            self.sessions[session_key] = session
            
            
            return {
                "success": True,
                "session_key": session_key,
                "message": "Manual assistance session started",
                "available_aois": len(available_aois)
            }
            
        except Exception as e:
            logger.error(f"❌ Error starting manual assistance session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def stop_assistance_session(self, session_key: str) -> Dict[str, Any]:
        """Stop manual assistance session"""
        try:
            if session_key in self.sessions:
                session = self.sessions[session_key]
                session.completed = True  # Mark as completed
                del self.sessions[session_key]
                
            return {
                "success": True,
                "message": "Manual assistance session stopped"
            }
            
        except Exception as e:
            logger.error(f"❌ Error stopping manual assistance session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def select_random_aoi(self, session_key: str, start_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Select random AOI for assistance
        
        Args:
            session_key: Session identifier from start_assistance_session
            start_timestamp: Timestamp when waiting message appeared (from frontend)
            
        Returns:
            Dict with selected AOI data and guidance content
        """
        try:
            session = self.sessions.get(session_key)
            if not session or session.completed:
                return {
                    "success": False,
                    "error": "No active assistance session"
                }
            
            # Storytelling: select TWO unassisted AOIs
            unassisted_aois = [
                aoi for aoi in session.available_aois 
                if aoi.index not in session.assisted_aoi_indices
            ]
            
            # Check if we have at least 2 unassisted AOIs
            if len(unassisted_aois) < 2:
                if len(unassisted_aois) == 0:
                    # All AOIs assisted - completion message
                    session.completed = True
                    return {
                        "success": True,
                        "completed": True,
                        "message": "Wunderbar! Du hast so viele Teile dieses Bildes erkundet! Ich glaube, du bist bereit, den Rest alleine zu entdecken. Toll gemacht!",
                        "voice_text": "Wunderbar! Du hast so viele Teile dieses Bildes erkundet! Ich glaube, du bist bereit, den Rest alleine zu entdecken. Toll gemacht!"
                    }
                else:
                    # Only 1 unassisted AOI left - still use two-AOI approach with a random second
                    selected_aoi = unassisted_aois[0]
                    # Pick a random second AOI from all available (even if assisted before)
                    other_aois = [aoi for aoi in session.available_aois if aoi.index != selected_aoi.index]
                    if other_aois:
                        secondary_aoi = random.choice(other_aois)
                        session.assisted_aoi_indices.append(selected_aoi.index)
                        session.used_aoi_indices.append(selected_aoi.index)
                        session.current_aoi = selected_aoi
                        return self._process_two_aois(session, selected_aoi, secondary_aoi, start_timestamp)
                    else:
                        # Only one AOI total - complete
                        session.completed = True
                        return {
                            "success": True,
                            "completed": True,
                            "message": "Wunderbar! Du hast dieses Bild erkundet! Toll gemacht!",
                            "voice_text": "Wunderbar! Du hast dieses Bild erkundet! Toll gemacht!"
                        }
            
            # Select TWO random AOIs from unassisted pool
            selected_aois = random.sample(unassisted_aois, 2)
            primary_aoi = selected_aois[0]  # Assisted AOI
            secondary_aoi = selected_aois[1]  # Connected AOI
            
            # Mark only PRIMARY as assisted
            session.assisted_aoi_indices.append(primary_aoi.index)
            session.used_aoi_indices.append(primary_aoi.index)
            session.current_aoi = primary_aoi
            
            # Process two AOIs for storytelling
            return self._process_two_aois(session, primary_aoi, secondary_aoi, start_timestamp)
            
            
        except Exception as e:
            logger.error(f"❌ Error selecting random AOI: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_waiting_message(self, language: str = 'de') -> Dict[str, str]:
        """Get waiting message while processing"""
        if language == 'de':
            waiting_messages = [
                {
                    "popup_text": "Lass mich dir helfen! 🤖",
                    "voice_text": "Lass mich dir helfen, dieses Bild zu erkunden!"
                },
                {
                    "popup_text": "Bitte warte einen Moment... 🔍", 
                    "voice_text": "Bitte warte einen Moment, während ich mir dieses Bild anschaue."
                },
                {
                    "popup_text": "Ich schaue mir das Bild an... 👀",
                    "voice_text": "Ich schaue mir dieses Bild an, um etwas Interessantes für dich zu finden."
                }
            ]
        else:
            waiting_messages = [
                {
                    "popup_text": "Let me help you! 🤖",
                    "voice_text": "Let me help you explore this picture!"
                },
                {
                    "popup_text": "Please wait a moment... 🔍", 
                    "voice_text": "Please wait a moment while I look at this picture."
                },
                {
                    "popup_text": "Looking at the picture... 👀",
                    "voice_text": "I'm looking at this picture to find something interesting for you."
                }
            ]
        
        return random.choice(waiting_messages)
    
    def _get_objects_for_language(self, aoi: ManualAOI, language: str) -> Optional[List[str]]:
        """
        Get objects list for AOI based on language preference
        
        Args:
            aoi: ManualAOI instance
            language: 'en' or 'de'
            
        Returns:
            List of object names in the appropriate language, or None if no objects available
        """
        if language == 'de' and aoi.objects_de:
            return aoi.objects_de
        elif aoi.objects:
            return aoi.objects
        # Fallback: try the other language if preferred not available
        elif language == 'de' and aoi.objects:
            return aoi.objects
        elif language == 'en' and aoi.objects_de:
            return aoi.objects_de
        return None
    
    def _process_two_aois(self, session: ManualAssistanceSession, primary_aoi: ManualAOI, secondary_aoi: ManualAOI, start_timestamp: Optional[float]) -> Dict[str, Any]:
        """Process two AOIs for storytelling activity"""
        try:
            # Step 1: Crop both AOI images and full page
            cropping_service = get_image_cropping_service()
            aoi1_b64, aoi2_b64, full_b64 = cropping_service.crop_two_aois_from_image(
                session.image_filename, 
                session.activity, 
                primary_aoi.bbox,  # PRIMARY (assisted)
                secondary_aoi.bbox  # SECONDARY (connected)
            )
            
            if not aoi1_b64 or not aoi2_b64 or not full_b64:
                logger.error(f"❌ Failed to crop two AOIs {primary_aoi.index} and {secondary_aoi.index}")
                return {
                    "success": False,
                    "error": "Failed to crop AOI images"
                }
            
            # Step 2: Analyze with ChatGPT (two AOI method)
            chatgpt_service = get_chatgpt_service()
            analysis_result = chatgpt_service.analyze_two_aoi_images(
                aoi1_b64,  # PRIMARY
                aoi2_b64,  # SECONDARY
                full_b64,
                session.activity,
                primary_aoi.index,
                secondary_aoi.index,
                aoi1_objects=self._get_objects_for_language(primary_aoi, session.language),
                aoi2_objects=self._get_objects_for_language(secondary_aoi, session.language),
                child_name=session.child_name,
                child_age=session.child_age,
                language=session.language,  # NEW: Pass language
                image_filename=session.image_filename,  # NEW: For loading context
                previous_stories=session.previous_stories  # NEW: For continuity
            )
            
            if not analysis_result["success"]:
                logger.error(f"❌ ChatGPT two-AOI analysis failed: {analysis_result.get('error')}")
                return {
                    "success": False,
                    "error": f"LLM analysis failed: {analysis_result.get('error')}"
                }
            
            # Append response to previous_stories for next call
            if analysis_result.get("analysis"):
                # Store the analysis dict (which contains child_story)
                session.previous_stories.append(analysis_result["analysis"])
                logger.info(f"📚 Added story to previous_stories (total: {len(session.previous_stories)})")
            
            # Step 3: Generate voice texts
            voice_texts = chatgpt_service.create_voice_texts(
                analysis_result["analysis"], 
                session.activity,
                session.child_name or "little explorer"
            )
            
            # Step 4: Generate audio
            tts_service = get_azure_tts_service()
            main_tts_result = tts_service.synthesize_speech(
                voice_texts["main_voice"],
                session.image_filename,
                session.activity,
                primary_aoi.index,
                "main",  # audio_type
                session.sequence_step,
                primary_aoi=primary_aoi.index,
                secondary_aoi=secondary_aoi.index,
                language=session.language  # NEW: Pass language
            )
            
            if not main_tts_result["success"]:
                logger.error(f"❌ TTS generation failed: {main_tts_result.get('error')}")
                return {
                    "success": False,
                    "error": f"Audio generation failed: {main_tts_result.get('error')}"
                }
            
            # Step 5: Cache the response with new naming convention
            cache_service = get_assistance_cache_service()
            cache_service.save_chatgpt_response_two_aois(
                session.image_filename,
                session.activity,
                primary_aoi.index,  # PRIMARY (assisted)
                secondary_aoi.index,  # SECONDARY (connected)
                analysis_result["analysis"],
                voice_texts["main_voice"],
                main_tts_result.get("audio_url"),
                session.sequence_step,
                start_timestamp,  # Pass start_timestamp from frontend
                language=session.language  # NEW: Pass language
            )
            
            # Step 6: Return response (only PRIMARY AOI to frontend)
            return {
                "success": True,
                "aoi": {
                    "index": primary_aoi.index,  # Only return PRIMARY AOI
                    "bbox": primary_aoi.bbox,
                    "center": primary_aoi.center,
                    "area": primary_aoi.area
                },
                "analysis": analysis_result["analysis"],
                "voice_texts": voice_texts,
                "main_audio": main_tts_result,
                "activity": session.activity,
                "stage": "main",
                "image_filename": session.image_filename,
                "sequence_step": session.sequence_step,
                "start_timestamp": start_timestamp,
                # Store both AOI indices for data tracking
                "primary_aoi_index": primary_aoi.index,
                "secondary_aoi_index": secondary_aoi.index
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing two AOIs: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Global instance for manual assistance (separate from eye-tracking)
_manual_assistance_service: Optional[ManualAssistanceService] = None

def get_manual_assistance_service() -> ManualAssistanceService:
    """Get the global manual assistance service instance"""
    global _manual_assistance_service
    if _manual_assistance_service is None:
        _manual_assistance_service = ManualAssistanceService()
    return _manual_assistance_service
