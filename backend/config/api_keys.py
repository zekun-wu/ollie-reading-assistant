"""
API keys configuration for Ollie.
Environment variables only.
"""
import os
from typing import Optional

class APIConfig:
    """Centralized API configuration management"""
    
    def __init__(self):
        # Environment variables only.
        self.chatgpt_api_key = os.getenv('CHATGPT_API_KEY')
        self.azure_speech_key = os.getenv('AZURE_SPEECH_KEY')
        self.azure_speech_region = os.getenv('AZURE_SPEECH_REGION', 'eastus')
    
    def get_chatgpt_key(self) -> Optional[str]:
        """Get ChatGPT API key"""
        return self.chatgpt_api_key
    
    def get_azure_speech_key(self) -> Optional[str]:
        """Get Azure Speech API key"""
        return self.azure_speech_key
    
    def get_azure_speech_region(self) -> str:
        """Get Azure Speech region"""
        return self.azure_speech_region
    
    def is_chatgpt_configured(self) -> bool:
        """Check if ChatGPT is configured"""
        return self.chatgpt_api_key is not None and len(self.chatgpt_api_key.strip()) > 0
    
    def is_azure_configured(self) -> bool:
        """Check if Azure TTS is configured"""
        return self.azure_speech_key is not None and len(self.azure_speech_key.strip()) > 0
    
    def get_configuration_status(self) -> dict:
        """Get configuration status for debugging"""
        return {
            "chatgpt_configured": self.is_chatgpt_configured(),
            "azure_configured": self.is_azure_configured(),
            "azure_region": self.azure_speech_region
        }

# Global instance
_api_config: Optional[APIConfig] = None

def get_api_config() -> APIConfig:
    """Get the global API configuration instance"""
    global _api_config
    if _api_config is None:
        _api_config = APIConfig()
    return _api_config
