"""
Dependency injection for FastAPI routes
"""
from core.state_manager import GazeStateManager
from core.websocket_manager import WebSocketManager

# Global instances - initialized in main.py
_state_manager: GazeStateManager = None
_websocket_manager: WebSocketManager = None

def set_managers(state_manager: GazeStateManager, websocket_manager: WebSocketManager):
    """Set the global manager instances"""
    global _state_manager, _websocket_manager
    _state_manager = state_manager
    _websocket_manager = websocket_manager

def get_state_manager() -> GazeStateManager:
    """Get the state manager instance"""
    return _state_manager

def get_websocket_manager() -> WebSocketManager:
    """Get the websocket manager instance"""
    return _websocket_manager
