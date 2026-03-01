"""
EyeReadDemo v7 - Redesigned Backend
Main FastAPI application with WebSocket support and proper state management
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
import logging

from core.state_manager import GazeStateManager
from core.websocket_manager import WebSocketManager
from dependencies import set_managers
from api.gaze_routes import router as gaze_router
from api.guidance_routes import router as guidance_router
from api.eye_tracking_routes import router as eye_tracking_router
from api.aoi_routes import router as aoi_router
from api.manual_assistance_routes import router as manual_assistance_router
from api.time_tracking_routes import router as time_tracking_router
from api.session_profile_routes import router as session_profile_router
from api.sequence_routes import router as sequence_router
from api.video_routes import router as video_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global managers
state_manager = GazeStateManager()
websocket_manager = WebSocketManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # #region agent log
    import sys
    import json
    try:
        with open(r"c:\Users\ZekunWu\Desktop\EyeReadDemo-v7\.cursor\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"hypothesisId": "H1", "location": "main.py:lifespan", "message": "Python executable and path", "data": {"executable": sys.executable, "path_first5": sys.path[:5], "in_venv": "venv" in sys.executable.replace("\\", "/")}, "timestamp": __import__("time").time(), "sessionId": "debug-session", "runId": "run1"}) + "\n")
    except Exception:
        pass
    # #endregion
    logger.info("🚀 EyeReadDemo v7 Backend Starting...")
    
    # Initialize services
    await state_manager.initialize()
    logger.info("✅ State Manager initialized")
    
    # Set up dependency injection
    set_managers(state_manager, websocket_manager)
    logger.info("✅ Dependencies configured")
    
    yield
    
    # Cleanup
    await state_manager.cleanup()
    await websocket_manager.cleanup()
    logger.info("🛑 EyeReadDemo v7 Backend Shutdown Complete")

app = FastAPI(
    title="EyeReadDemo v7 API",
    description="Redesigned eye-tracking reading assistant with proper state management",
    version="7.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(gaze_router, prefix="/api/gaze", tags=["gaze"])
app.include_router(guidance_router, prefix="/api/guidance", tags=["guidance"])
app.include_router(eye_tracking_router, prefix="/api/eye-tracking", tags=["eye-tracking"])
app.include_router(aoi_router, prefix="/api/aoi", tags=["aoi"])
app.include_router(manual_assistance_router, prefix="/api/manual-assistance", tags=["manual-assistance"])
app.include_router(time_tracking_router, prefix="/api/time-tracking", tags=["time-tracking"])
app.include_router(session_profile_router, prefix="/api/session", tags=["session"])
app.include_router(sequence_router, prefix="/api/sequences", tags=["sequences"])
app.include_router(video_router, prefix="/api/video", tags=["video"])

# Serve static files (pictures) - path relative to backend/src/
app.mount("/pictures", StaticFiles(directory="../pictures"), name="pictures")

# Serve audio files for TTS - path relative to backend/src/
app.mount("/audio", StaticFiles(directory="../audio_cache"), name="audio")

# Serve animated assistant images - path relative to backend/src/
app.mount("/animated_assistant", StaticFiles(directory="../animated_assistant"), name="animated_assistant")

# Serve game session audio files - path relative to backend/src/
app.mount("/game_audio", StaticFiles(directory="../audio_cache/game"), name="game_audio")

# NEW: Serve sequence mode mixed files - dynamically based on user_number
# We'll create a custom route handler instead of static mount
@app.get("/mixed/{file_path:path}")
async def serve_mixed_file(file_path: str):
    """
    Serve mixed files from record/{user_number}/mixed/ directory
    Dynamically determines user_number from session profile
    """
    try:
        # Get user_number from session profile
        from services.session_profile_service import get_session_profile_service
        profile_service = get_session_profile_service()
        user_number = profile_service.get_user_number()
        
        # main.py is at backend/src/main.py, so parent.parent = backend/
        backend_dir = Path(__file__).parent.parent
        
        # ALWAYS try user-based path first if user_number exists
        if user_number:
            # Use record/{user_number}/mixed/ structure
            file_full_path = backend_dir / "record" / str(user_number) / "mixed" / file_path
            
            # If file doesn't exist in user path, check if it exists in old location
            if not file_full_path.exists():
                old_path = backend_dir / "mixed" / file_path
                logger.warning(f"⚠️ [MIXED FILE REQUEST] File not found in user path, checking old location: {old_path}")
                if old_path.exists():
                    logger.warning(f"⚠️ [MIXED FILE REQUEST] Found file in old location, but user_number={user_number} exists - this is unexpected!")
                    # Still use user path - don't serve from old location
        else:
            # Fallback to old structure only if no user_number
            file_full_path = backend_dir / "mixed" / file_path
            logger.warning(f"⚠️ [MIXED FILE REQUEST] No user_number found, using fallback: mixed/")
        
        if not file_full_path.parent.exists():
            logger.error(f"❌ [MIXED FILE REQUEST] Parent directory does not exist: {file_full_path.parent}")
        
        if file_full_path.exists() and file_full_path.is_file():
            logger.info("Serving mixed file: %s", file_path)
            return FileResponse(file_full_path)
        else:
            error_msg = f"File not found: {file_path} (Full path: {file_full_path})"
            logger.error(f"❌ [MIXED FILE REQUEST] {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MIXED FILE REQUEST] Error serving mixed file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "EyeReadDemo v7 Backend",
        "version": "7.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "state_manager": await state_manager.get_health_status(),
        "websocket_connections": websocket_manager.get_connection_count(),
        "timestamp": state_manager.get_current_timestamp()
    }

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Main WebSocket endpoint for real-time communication"""
    try:
        await websocket_manager.connect(websocket, client_id)
        logger.info(f"🔌 WebSocket connected: {client_id}")
        
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            
            # Process message through state manager
            response = await state_manager.process_websocket_message(
                client_id, data, websocket_manager
            )
            
            logger.info(f"📤 WebSocket response to {client_id}: {response}")
            
            if response:
                await websocket_manager.send_to_client(client_id, response)
                
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: {client_id}")
        await websocket_manager.disconnect(client_id)
        await state_manager.clear_all_previous_stories()
    except Exception as e:
        logger.error(f"❌ WebSocket error for {client_id}: {e}")
        await websocket_manager.disconnect(client_id)
        await state_manager.clear_all_previous_stories()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,  # Disable reload for stable eye-tracking testing
        log_level="info",
        access_log=False  # Disable HTTP request logging
    )
