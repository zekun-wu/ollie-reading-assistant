"""
Eye-Tracking TTS Service - Separate from Manual Assistance
Handles voice generation for curiosity guidance with eye_ filename prefix
"""
import logging
import requests
from typing import Optional, Dict, Any
from pathlib import Path
import sys

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

try:
    from config.api_keys import get_api_config
except ImportError as e:
    print(f"❌ Failed to import API config: {e}")
    def get_api_config():
        return None

class EyeTrackingTTSService:
    """TTS service for eye-tracking assistance with separate cache"""
    
    def __init__(self):
        self.api_config = get_api_config()
        self.voice_name = "de-DE-KatjaNeural"  # German voice
        # Standalone mode cache (under audio_cache so /audio mount serves it)
        self.audio_cache_base = Path("../audio_cache/eye")
        
        # Sequence mode support (NEW)
        self.sequence_cache_service = None  # Will be set when in sequence mode
        
        # Create base audio cache directory
        self.audio_cache_base.mkdir(parents=True, exist_ok=True)
        
    def synthesize_speech(
        self,
        text: str,
        image_name: str,
        activity: str,
        aoi_index: Optional[int] = None,
        audio_type: str = "main",  # "waiting", "main", "exploratory"
        sequence_step: Optional[int] = None,  # NEW: For sequence mode
        primary_aoi: Optional[int] = None,  # NEW: For storytelling with 2 AOIs
        secondary_aoi: Optional[int] = None,  # NEW: For storytelling with 2 AOIs
        language: str = 'de'  # Language (German only)
    ) -> Dict[str, Any]:
        """
        Synthesize speech for eye-tracking guidance with eye_ prefix
        
        Args:
            text: Text to convert to speech
            image_name: Image name (e.g., "1.jpg" -> "1")
            activity: "storytelling" only
            aoi_index: AOI index
            audio_type: "waiting", "main", or "exploratory"
            sequence_step: If provided, saves to sequence mode cache
            
        Returns:
            Dict with audio file path and metadata
        """
        try:
            if not self.api_config or not self.api_config.is_azure_configured():
                logger.warning("⚠️ Azure TTS not configured for eye-tracking")
                return {
                    "success": False,
                    "error": "Azure TTS not configured",
                    "fallback": True
                }
            
            # Extract image base for logging (used in both modes)
            image_base = Path(image_name).stem
            
            # SEQUENCE MODE: Use SequenceCacheService
            if sequence_step is not None:
                # Lazy-load sequence cache service when needed
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                    logger.info("✅ Eye-Tracking TTS: Sequence mode auto-enabled")
                
                # Map audio_type to file_type for SequenceCacheService
                if audio_type == "waiting":
                    file_type = "waiting"
                    aoi_num = None
                    primary_aoi = None
                    secondary_aoi = None
                elif audio_type in ["main", "exploratory"]:
                    # For sequence mode, drop distinction between main/explore
                    file_type = "audio"
                    if activity == "storytelling" and primary_aoi is not None and secondary_aoi is not None:
                        # For storytelling with 2 AOIs
                        aoi_num = None
                        # primary_aoi and secondary_aoi already set
                    else:
                        raise ValueError(f"Missing AOI indices for storytelling audio")
                else:
                    raise ValueError(f"Unknown audio_type for sequence mode: {audio_type}")
                
                audio_path = self.sequence_cache_service.get_file_path(
                    seq_num=sequence_step,
                    activity=activity,
                    image_name=image_name,
                    file_type=file_type,
                    aoi_num=aoi_num,
                    primary_aoi=primary_aoi,
                    secondary_aoi=secondary_aoi
                )
                audio_filename = audio_path.name
                logger.debug(f"📂 Eye-tracking sequence mode audio: {audio_path}")
                
            # STANDALONE MODE: Use traditional cache structure
            else:
                # Create activity-specific directory
                activity_dir = self.audio_cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                
                # Generate structured filename with eye_ prefix
                if audio_type == "waiting":
                    audio_filename = f"{image_base}_eye_waiting.wav"
                elif audio_type == "main":
                    audio_filename = f"{image_base}_eye_main_aoi_{aoi_index}.wav"
                elif audio_type == "exploratory":
                    audio_filename = f"{image_base}_eye_explore_aoi_{aoi_index}.wav"
                else:
                    audio_filename = f"{image_base}_eye_asst_aoi_{aoi_index}.wav"
                
                audio_path = activity_dir / audio_filename
                logger.debug(f"📂 Eye-tracking standalone mode audio: {audio_path}")
            
            # Check if already cached
            if audio_path.exists():
                # Generate correct URL based on mode
                if sequence_step is not None:
                    audio_url = f"/mixed/{sequence_step}/{audio_filename}"
                else:
                    audio_url = f"/audio/eye/{activity}/{audio_filename}"
                
                logger.info("Eye-TTS: cached %s", audio_filename)
                
                return {
                    "success": True,
                    "audio_path": str(audio_path),
                    "audio_url": audio_url,
                    "cached": True
                }
            
            # Map language to Azure voice
            # Always use German voice
            voice_name = "de-DE-KatjaNeural"
            xml_lang = "de-DE"
            
            # Prepare SSML for child-friendly speech
            ssml = f"""
            <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{xml_lang}">
                <voice name="{voice_name}">
                    <prosody rate="1" pitch="+10%">
                        {text}
                    </prosody>
                </voice>
            </speak>
            """
            
            # Azure TTS API endpoint
            region = self.api_config.get_azure_speech_region()
            endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
            
            headers = {
                'Ocp-Apim-Subscription-Key': self.api_config.get_azure_speech_key(),
                'Content-Type': 'application/ssml+xml',
                'X-Microsoft-OutputFormat': 'riff-24khz-16bit-mono-pcm',
                'User-Agent': 'EyeReadDemo-v7-EyeTracking'
            }
            
            logger.info(f"🔊 Eye-TTS: Generating {audio_type} for {image_base} AOI {aoi_index}")
            
            # Make TTS request
            response = requests.post(endpoint, headers=headers, data=ssml.encode('utf-8'), timeout=30)
            
            if response.status_code == 200:
                # Save audio file
                with open(audio_path, 'wb') as f:
                    f.write(response.content)
                
                # Generate correct URL based on mode
                if sequence_step is not None:
                    audio_url = f"/mixed/{sequence_step}/{audio_filename}"
                else:
                    audio_url = f"/audio/eye/{activity}/{audio_filename}"
                
                logger.info("Eye-TTS: generated %s", audio_filename)
                
                return {
                    "success": True,
                    "audio_path": str(audio_path),
                    "audio_url": audio_url,
                    "text": text,
                    "voice": self.voice_name,
                    "cached": False
                }
            else:
                logger.error(f"❌ Eye-tracking Azure TTS error: {response.status_code}")
                return {
                    "success": False,
                    "error": f"Azure TTS error: {response.status_code}",
                    "fallback": True
                }
                
        except Exception as e:
            logger.error(f"❌ Error in eye-tracking speech synthesis: {e}")
            return {
                "success": False,
                "error": str(e),
                "fallback": True
            }
    
    def enable_sequence_mode(self, sequence_cache_service):
        """
        Enable sequence mode for this service
        
        Args:
            sequence_cache_service: Instance of SequenceCacheService
        """
        self.sequence_cache_service = sequence_cache_service
        logger.info("✅ Eye-Tracking TTS: Sequence mode enabled")
    
    def disable_sequence_mode(self):
        """Disable sequence mode (return to standalone mode)"""
        self.sequence_cache_service = None
        logger.info("✅ Eye-Tracking TTS: Sequence mode disabled")

# Global instance
_eye_tracking_tts_service: Optional[EyeTrackingTTSService] = None

def get_eye_tracking_tts_service() -> EyeTrackingTTSService:
    """Get the global eye-tracking TTS service instance"""
    global _eye_tracking_tts_service
    if _eye_tracking_tts_service is None:
        _eye_tracking_tts_service = EyeTrackingTTSService()
    return _eye_tracking_tts_service
