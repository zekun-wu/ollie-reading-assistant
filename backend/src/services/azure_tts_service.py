"""
Azure Text-to-Speech Service for Manual Assistance
Handles voice generation using Azure Speech Services
"""
import logging
import requests
import uuid
import time
from typing import Optional, Dict, Any
import hashlib
from pathlib import Path
import sys

# Add backend directory to path for config import
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

try:
    from config.api_keys import get_api_config
except ImportError as e:
    logger.error(f"❌ Failed to import API config: {e}")
    def get_api_config():
        return None

logger = logging.getLogger(__name__)

class AzureTTSService:
    """Service for Azure Text-to-Speech synthesis"""
    
    def __init__(self):
        self.api_config = get_api_config()
        self.voice_name = "de-DE-KatjaNeural"  # Child-friendly German voice
        # Standalone mode cache
        self.audio_cache_base = Path("../audio_cache")
        
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
        audio_type: str = "assistance",
        sequence_step: Optional[int] = None,  # NEW: For sequence mode
        primary_aoi: Optional[int] = None,  # NEW: For storytelling with 2 AOIs
        secondary_aoi: Optional[int] = None,  # NEW: For storytelling with 2 AOIs
        language: str = 'de'  # Language (German only)
    ) -> Dict[str, Any]:
        """
        Synthesize speech using Azure TTS with structured saving
        
        Args:
            text: Text to convert to speech
            image_name: Image name (e.g., "1.jpg" -> "1")
            activity: "storytelling" only
            aoi_index: AOI index for assistance files
            audio_type: "waiting", "main", "exploratory", or "assistance"
            sequence_step: If provided, saves to sequence mode cache
            
        Returns:
            Dict with audio file path and metadata
        """
        try:
            if not self.api_config or not self.api_config.is_azure_configured():
                logger.warning("⚠️ Azure TTS not configured, using fallback")
                return {
                    "success": False,
                    "error": "Azure TTS not configured",
                    "fallback": True
                }
            
            # INTRO AUDIO: Special handling (shared for both modes)
            if image_name == "intro" or image_name.startswith("group_intro_"):
                # Detect intro step based on text content
                if "My name is Ollie" in text or "reading friend today" in text:
                    audio_type_name = "greeting"
                else:
                    audio_type_name = "welcome"

                # Create a short hash of the text so different names generate different files
                text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
                hashed_filename = f"intro_{audio_type_name}_{text_hash}.wav"

                # Use sequence cache for intro audio in sequence mode
                if sequence_step is not None:
                    # Lazy-load sequence cache service when needed
                    if self.sequence_cache_service is None:
                        from services.sequence_cache_service import get_sequence_cache_service
                        self.sequence_cache_service = get_sequence_cache_service()
                        logger.info("✅ Azure TTS: Sequence mode auto-enabled")

                    intro_dir = self.sequence_cache_service.get_intro_audio_dir()
                    audio_path = intro_dir / hashed_filename
                else:
                    # Standalone mode: audio_cache/intro/intro_{type}_{hash}.wav
                    intro_dir = self.audio_cache_base / "intro"
                    intro_dir.mkdir(exist_ok=True)
                    audio_path = intro_dir / hashed_filename

                audio_filename = audio_path.name
                logger.debug(f"📂 Intro audio path: {audio_path}")
                
            # SEQUENCE MODE: Use SequenceCacheService for assistance audio
            elif sequence_step is not None:
                # Lazy-load sequence cache service when needed
                if self.sequence_cache_service is None:
                    from services.sequence_cache_service import get_sequence_cache_service
                    self.sequence_cache_service = get_sequence_cache_service()
                    logger.info("✅ Azure TTS: Sequence mode auto-enabled")
                
                # Map audio_type to file_type for SequenceCacheService
                if audio_type == "waiting":
                    file_type = "waiting"
                    aoi_num = None
                    primary_aoi = None
                    secondary_aoi = None
                elif audio_type == "baseline":
                    file_type = "baseline"
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
                logger.debug(f"📂 Sequence mode audio path: {audio_path}")
                
            # STANDALONE MODE: Use traditional cache structure
            else:
                # Create activity-specific directory
                activity_dir = self.audio_cache_base / activity
                activity_dir.mkdir(exist_ok=True)
                
                # Generate structured filename
                image_base = Path(image_name).stem  # "1.jpg" -> "1"
                
                if audio_type == "waiting":
                    audio_filename = f"{image_base}_waiting.wav"
                elif audio_type == "main":
                    audio_filename = f"{image_base}_main_aoi_{aoi_index}.wav"
                elif audio_type == "exploratory":
                    audio_filename = f"{image_base}_explore_aoi_{aoi_index}.wav"
                else:  # legacy assistance
                    audio_filename = f"{image_base}_asst_aoi_{aoi_index}.wav"
                
                audio_path = activity_dir / audio_filename
                logger.debug(f"📂 Standalone mode audio path: {audio_path}")
            
            # Check if already cached
            if audio_path.exists():
                # Generate correct URL based on mode and file type
                if image_name == "intro" and sequence_step is not None:
                    audio_url = f"/mixed/intro_audio/{audio_filename}"
                elif sequence_step is not None:
                    audio_url = f"/mixed/{sequence_step}/{audio_filename}"
                else:
                    audio_url = f"/audio/{activity}/{audio_filename}"
                
                logger.info("TTS: cached %s", audio_filename)
                
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
                'User-Agent': 'EyeReadDemo-v7'
            }
            
            logger.info(f"🔊 Generating speech for: {text[:50]}...")
            
            # Make TTS request
            response = requests.post(endpoint, headers=headers, data=ssml.encode('utf-8'), timeout=30)
            
            if response.status_code == 200:
                # Save audio file
                with open(audio_path, 'wb') as f:
                    f.write(response.content)
                
                # Generate correct URL based on mode and file type
                if image_name == "intro" and sequence_step is not None:
                    audio_url = f"/mixed/intro_audio/{audio_filename}"
                elif sequence_step is not None:
                    audio_url = f"/mixed/{sequence_step}/{audio_filename}"
                else:
                    audio_url = f"/audio/{activity}/{audio_filename}"
                
                logger.info("TTS: generated %s", audio_filename)
                
                return {
                    "success": True,
                    "audio_path": str(audio_path),
                    "audio_url": audio_url,
                    "text": text,
                    "voice": self.voice_name,
                    "cached": False
                }
            else:
                logger.error(f"❌ Azure TTS API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"Azure TTS error: {response.status_code}",
                    "fallback": True
                }
                
        except Exception as e:
            logger.error(f"❌ Error in speech synthesis: {e}")
            return {
                "success": False,
                "error": str(e),
                "fallback": True
            }
    
    def cleanup_old_audio(self, max_age_hours: int = 24):
        """Clean up old audio files"""
        try:
            current_time = time.time()
            cleaned_count = 0
            
            for audio_file in self.audio_cache_dir.glob("*.wav"):
                file_age = current_time - audio_file.stat().st_mtime
                if file_age > (max_age_hours * 3600):
                    audio_file.unlink()
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned up {cleaned_count} old audio files")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up audio files: {e}")
    
    def enable_sequence_mode(self, sequence_cache_service):
        """
        Enable sequence mode for this service
        
        Args:
            sequence_cache_service: Instance of SequenceCacheService
        """
        self.sequence_cache_service = sequence_cache_service
        logger.info("✅ Azure TTS: Sequence mode enabled")
    
    def disable_sequence_mode(self):
        """Disable sequence mode (return to standalone mode)"""
        self.sequence_cache_service = None
        logger.info("✅ Azure TTS: Sequence mode disabled")

# Global instance
_azure_tts_service: Optional[AzureTTSService] = None

def get_azure_tts_service() -> AzureTTSService:
    """Get the global Azure TTS service instance"""
    global _azure_tts_service
    if _azure_tts_service is None:
        _azure_tts_service = AzureTTSService()
    return _azure_tts_service
