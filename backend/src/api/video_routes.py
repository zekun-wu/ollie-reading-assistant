"""
Video Upload API Routes
Endpoint for saving demo session recordings with per-clip segmentation
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

def _get_video_dir() -> Path:
    """Get video directory based on user_number from session profile"""
    backend_dir = Path(__file__).parent.parent.parent
    
    # Get user_number from session profile
    try:
        from services.session_profile_service import get_session_profile_service
        profile_service = get_session_profile_service()
        user_number = profile_service.get_user_number()
        
        if user_number:
            # Use record/{user_number}/video/ structure
            video_dir = backend_dir / "record" / str(user_number) / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Using user-based video directory: {video_dir}")
            return video_dir
    except Exception as e:
        logger.warning(f"⚠️ Could not get user_number from session profile: {e}")
    
    # Fallback to old structure
    video_dir = backend_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    logger.warning("⚠️ No user_number found, using fallback video/ directory")
    return video_dir

@router.post("/upload")
async def upload_video(
    video: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    clip_type: Optional[str] = Form(None),
    condition: Optional[str] = Form(None),
    image_num: Optional[str] = Form(None)
):
    """
    Upload and save demo session video clip
    
    Args:
        video: Video file (webm format)
        session_id: Session identifier to group clips
        clip_type: Type of clip (start, full, post, end)
        condition: Condition type (assistance, eye_assistance)
        image_num: Image number for this clip
    
    Returns:
        Success status and file path
    """
    try:
        # Validate file type
        if not video.content_type or not video.content_type.startswith('video/'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Expected video file."
            )
        
        # Use provided filename or generate one
        if video.filename and video.filename.endswith('.webm'):
            filename = video.filename
        else:
            # Generate filename with metadata
            if clip_type == 'start':
                filename = f"{session_id}_start.webm"
            elif clip_type == 'end':
                filename = f"{session_id}_end.webm"
            elif clip_type in ['full', 'post']:
                filename = f"{session_id}_{condition}_{image_num}_{clip_type}.webm"
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{session_id}_{clip_type}_{timestamp}.webm"
        
        video_dir = _get_video_dir()
        file_path = video_dir / filename
        
        # Save video file
        with open(file_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        file_size_mb = len(content) / (1024 * 1024)
        
        logger.info(
            f"✅ Video clip saved: {filename} "
            f"(Session: {session_id}, Type: {clip_type}, "
            f"Condition: {condition}, Image: {image_num}, "
            f"Size: {file_size_mb:.2f} MB)"
        )
        
        return JSONResponse({
            "success": True,
            "message": "Video clip uploaded successfully",
            "file_path": str(file_path),
            "filename": filename,
            "file_size_mb": round(file_size_mb, 2),
            "metadata": {
                "session_id": session_id,
                "clip_type": clip_type,
                "condition": condition,
                "image_num": image_num
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error uploading video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_videos(session_id: Optional[str] = None):
    """
    List all saved video recordings, optionally filtered by session_id
    
    Returns:
        List of video files with metadata
    """
    try:
        video_dir = _get_video_dir()
        videos = []
        for video_file in sorted(video_dir.glob("*.webm"), reverse=True):
            # Extract session_id from filename
            filename_parts = video_file.stem.split('_')
            session_id_from_file = None
            
            if len(filename_parts) >= 2 and filename_parts[0] == 'session':
                session_id_from_file = f"{filename_parts[0]}_{filename_parts[1]}"
            
            # Filter by session_id if provided
            if session_id and session_id_from_file != session_id:
                continue
            
            stat = video_file.stat()
            videos.append({
                "filename": video_file.name,
                "file_path": str(video_file),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "session_id": session_id_from_file
            })
        
        return {
            "success": True,
            "count": len(videos),
            "session_id": session_id,
            "videos": videos
        }
    except Exception as e:
        logger.error(f"❌ Error listing videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

