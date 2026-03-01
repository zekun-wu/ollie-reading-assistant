"""
WebSocket Manager - Real-time communication between frontend and backend
Handles connection management and message routing
"""
import asyncio
import logging
from typing import Dict, Optional, Any, List
from fastapi import WebSocket
import json

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Manages WebSocket connections for real-time communication
    Supports broadcasting and targeted messaging
    """
    
    def __init__(self):
        # Active connections: client_id -> WebSocket
        self.connections: Dict[str, WebSocket] = {}
        # Client metadata: client_id -> metadata
        self.client_metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        
        async with self._lock:
            # Close existing connection if any
            if client_id in self.connections:
                try:
                    await self.connections[client_id].close()
                except:
                    pass
            
            self.connections[client_id] = websocket
            self.client_metadata[client_id] = {
                "connected_at": asyncio.get_event_loop().time(),
                "message_count": 0
            }
        
        logger.info(f"🔌 WebSocket connected: {client_id}")
        
        # Send welcome message
        await self.send_to_client(client_id, {
            "type": "connection_established",
            "client_id": client_id,
            "message": "Connected to EyeReadDemo v7"
        })
    
    async def disconnect(self, client_id: str):
        """Remove a WebSocket connection"""
        async with self._lock:
            if client_id in self.connections:
                try:
                    await self.connections[client_id].close()
                except:
                    pass
                
                del self.connections[client_id]
                if client_id in self.client_metadata:
                    del self.client_metadata[client_id]
        
        logger.info(f"🔌 WebSocket disconnected: {client_id}")
    
    async def send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific client"""
        async with self._lock:
            if client_id not in self.connections:
                logger.warning(f"📤 Cannot send to {client_id}: not connected")
                return False
            
            try:
                websocket = self.connections[client_id]
                await websocket.send_json(message)
                
                # Update metadata
                if client_id in self.client_metadata:
                    self.client_metadata[client_id]["message_count"] += 1
                
                logger.debug(f"📤 Sent to {client_id}: {message.get('type', 'unknown')}")
                return True
                
            except Exception as e:
                logger.error(f"❌ Error sending to {client_id}: {e}")
                # Remove broken connection
                await self.disconnect(client_id)
                return False
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[List[str]] = None) -> int:
        """Broadcast message to all connected clients"""
        if exclude is None:
            exclude = []
        
        sent_count = 0
        client_ids = list(self.connections.keys())
        
        for client_id in client_ids:
            if client_id not in exclude:
                if await self.send_to_client(client_id, message):
                    sent_count += 1
        
        logger.info(f"📢 Broadcast to {sent_count} clients: {message.get('type', 'unknown')}")
        return sent_count
    
    async def send_state_update(self, client_id: str, state_data: Dict[str, Any]):
        """Send state update to client"""
        message = {
            "type": "state_update",
            "timestamp": asyncio.get_event_loop().time(),
            **state_data
        }
        return await self.send_to_client(client_id, message)
    
    async def send_guidance_ready(self, client_id: str, guidance_data: Dict[str, Any]):
        """Send guidance ready notification to client"""
        message = {
            "type": "guidance_ready",
            "timestamp": asyncio.get_event_loop().time(),
            **guidance_data
        }
        return await self.send_to_client(client_id, message)
    
    async def send_error(self, client_id: str, error_message: str, error_code: Optional[str] = None):
        """Send error message to client"""
        message = {
            "type": "error",
            "message": error_message,
            "timestamp": asyncio.get_event_loop().time()
        }
        if error_code:
            message["error_code"] = error_code
            
        return await self.send_to_client(client_id, message)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.connections)
    
    def get_client_list(self) -> List[str]:
        """Get list of connected client IDs"""
        return list(self.connections.keys())
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """Get detailed connection information"""
        async with self._lock:
            return {
                "total_connections": len(self.connections),
                "clients": {
                    client_id: {
                        "connected": True,
                        **metadata
                    }
                    for client_id, metadata in self.client_metadata.items()
                }
            }
    
    async def cleanup(self):
        """Cleanup all connections"""
        logger.info("🧹 Cleaning up WebSocket connections")
        
        client_ids = list(self.connections.keys())
        for client_id in client_ids:
            await self.disconnect(client_id)
        
        logger.info("✅ WebSocket cleanup complete")
    
    async def ping_all_clients(self) -> Dict[str, bool]:
        """Ping all clients to check connection health"""
        results = {}
        client_ids = list(self.connections.keys())
        
        for client_id in client_ids:
            try:
                await self.send_to_client(client_id, {
                    "type": "ping",
                    "timestamp": asyncio.get_event_loop().time()
                })
                results[client_id] = True
            except Exception as e:
                logger.warning(f"🏓 Ping failed for {client_id}: {e}")
                results[client_id] = False
        
        return results
