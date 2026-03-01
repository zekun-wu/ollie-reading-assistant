"""
Time Tracking Service - Tracks viewing duration across assistance conditions
Records session-based viewing time for each picture in each condition.
All timestamps are server-side time.time() (Unix epoch float) for alignment with gaze.json.
Supports both standalone mode and sequence mode with different cache structures
"""
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


class TimeTrackingService:
    """Service for tracking picture viewing time across conditions"""
    
    def __init__(self):
        # Base directory for time cache (standalone mode)
        self.base_dir = Path(__file__).parent.parent.parent / "time_cache"
        
        # Directory mapping for each assistance condition (standalone mode)
        self.condition_dirs = {
            "base": self.base_dir / "base_time_cache",
            "assistance": self.base_dir / "assistance_time_cache",
            "eye_assistance": self.base_dir / "eye_assistance_time_cache"
        }
        
        # Active sessions tracking (in-memory)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Sequence mode support (NEW)
        self.sequence_cache_service = None  # Will be set when in sequence mode
        
        # Create directories
        self._ensure_directories()
        
        logger.info("✅ Time Tracking Service initialized")
    
    def _ensure_directories(self):
        """Ensure all required directories exist"""
        for condition, base_path in self.condition_dirs.items():
            for activity in ["storytelling"]:
                dir_path = base_path / activity
                dir_path.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(
        self, 
        image_filename: str, 
        activity: str, 
        assistance_condition: str,
        sequence_step: Optional[int] = None
    ) -> Path:
        """
        Get the file path for storing time tracking data
        
        Args:
            image_filename: Image file name
            activity: "storytelling" only
            assistance_condition: "base", "assistance", or "eye_assistance"
            sequence_step: If provided, use sequence mode cache structure
            
        Returns:
            Path to time tracking JSON file
        """
        # SEQUENCE MODE: Use mixed/{step}/timeline.json
        if sequence_step is not None:
            # Lazy-load sequence cache service when needed
            if self.sequence_cache_service is None:
                from services.sequence_cache_service import get_sequence_cache_service
                self.sequence_cache_service = get_sequence_cache_service()
                logger.info("✅ Time Tracking: Sequence mode auto-enabled")
            
            file_path = self.sequence_cache_service.get_time_tracking_path(sequence_step)
            logger.debug(f"📂 Using sequence mode path: {file_path}")
            return file_path
        
        # STANDALONE MODE: Use traditional cache structure
        base_path = self.condition_dirs.get(assistance_condition)
        if not base_path:
            raise ValueError(f"Invalid assistance condition: {assistance_condition}")
        
        # Extract image name without extension
        image_name = Path(image_filename).stem
        
        # Build path: time_cache/{condition}_time_cache/{activity}/{image}.json
        file_path = base_path / activity / f"{image_name}.json"
        logger.debug(f"📂 Using standalone mode path: {file_path}")
        return file_path
    
    def _load_time_data(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Load existing time tracking data from JSON file"""
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"📂 Loaded time data from {file_path}")
            return data
        except Exception as e:
            logger.error(f"❌ Error loading time data from {file_path}: {e}")
            return None
    
    def _save_time_data(self, file_path: Path, data: Dict[str, Any]):
        """Save time tracking data to JSON file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Saved time data to {file_path}")
        except Exception as e:
            logger.error(f"❌ Error saving time data to {file_path}: {e}")
            raise
    
    def start_session(
        self, 
        image_filename: str, 
        activity: str, 
        assistance_condition: str,
        child_name: str = "Guest",
        sequence_step: Optional[int] = None
    ) -> str:
        """
        Start a new viewing session. All timestamps stored as server time.time() (Unix epoch float).
        
        Args:
            image_filename: Image file name
            activity: "storytelling" only (used for path logic)
            assistance_condition: "base", "assistance", or "eye_assistance"
            child_name: Ignored for stored schema; kept for API compatibility
            sequence_step: If provided, saves to sequence mode cache
            
        Returns:
            session_id: Unique identifier for this session
        """
        unique_id = str(uuid.uuid4())[:8]
        session_id = f"session_{int(time.time() * 1000)}_{unique_id}"
        start_time = time.time()
        
        self.active_sessions[session_id] = {
            "session_id": session_id,
            "image_filename": image_filename,
            "activity": activity,
            "assistance_condition": assistance_condition,
            "sequence_step": sequence_step,
            "start_time": start_time,
            "assistance_events": [],
            "voice_events": [],
        }
        
        mode_str = f"sequence step {sequence_step}" if sequence_step else "standalone"
        logger.info(f"▶️ Started session {session_id} for {image_filename} ({assistance_condition}, {mode_str})")
        return session_id

    def record_assistance_start(self, session_id: str, assistance_index: Optional[int] = None) -> bool:
        """
        Record server time when an assistance highlight begins.
        Call when the highlight appears.
        If assistance_index is provided (1-based), use it; else infer from event counts.
        """
        if session_id not in self.active_sessions:
            return False
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            logger.warning(f"Invalid assistance_index {assistance_index}, ignoring")
            assistance_index = None
        events = self.active_sessions[session_id]["assistance_events"]
        if assistance_index is None:
            index = (len(events) // 2) + 1
        else:
            index = assistance_index
        events.append({"event": "start", "index": index, "time": time.time()})
        logger.debug(f"Assistance {index} start recorded for session {session_id}")
        return True

    def record_assistance_end(self, session_id: str, assistance_index: Optional[int] = None) -> bool:
        """
        Record server time when an assistance highlight ends.
        Call when the highlight disappears.
        If assistance_index is provided (1-based), use it; else infer from event counts.
        """
        if session_id not in self.active_sessions:
            return False
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            logger.warning(f"Invalid assistance_index {assistance_index}, ignoring")
            assistance_index = None
        events = self.active_sessions[session_id]["assistance_events"]
        if assistance_index is None:
            num_starts = sum(1 for e in events if e["event"] == "start")
            num_ends = len(events) - num_starts
            index = num_ends + 1
        else:
            index = assistance_index
        events.append({"event": "end", "index": index, "time": time.time()})
        logger.debug(f"Assistance {index} end recorded for session {session_id}")
        return True

    def record_voice_start(self, session_id: str, assistance_index: Optional[int] = None) -> bool:
        """
        Record server time when the LLM main-content voice starts playing (not waiting message).
        Call when main-content TTS starts.
        If assistance_index is provided (1-based), use it; else infer from assistance_events.
        """
        if session_id not in self.active_sessions:
            return False
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            logger.warning(f"Invalid assistance_index {assistance_index}, ignoring")
            assistance_index = None
        assistance_events = self.active_sessions[session_id]["assistance_events"]
        voice_events = self.active_sessions[session_id]["voice_events"]
        if assistance_index is None:
            index = sum(1 for e in assistance_events if e["event"] == "start")
        else:
            index = assistance_index
        voice_events.append({"event": "start", "index": index, "time": time.time()})
        logger.debug(f"Voice {index} start recorded for session {session_id}")
        return True

    def record_voice_end(self, session_id: str, assistance_index: Optional[int] = None) -> bool:
        """
        Record server time when the LLM main-content voice stops (not waiting message).
        Call when main-content TTS ends.
        If assistance_index is provided (1-based), use it; else infer from voice_events.
        """
        if session_id not in self.active_sessions:
            return False
        if assistance_index is not None and (not isinstance(assistance_index, int) or assistance_index < 1):
            logger.warning(f"Invalid assistance_index {assistance_index}, ignoring")
            assistance_index = None
        voice_events = self.active_sessions[session_id]["voice_events"]
        if assistance_index is None:
            index = sum(1 for e in voice_events if e["event"] == "start")
        else:
            index = assistance_index
        voice_events.append({"event": "end", "index": index, "time": time.time()})
        logger.debug(f"Voice {index} end recorded for session {session_id}")
        return True
    
    def _build_session_entry(self, session_data: Dict[str, Any], end_time: float) -> Dict[str, Any]:
        """Build one viewing_sessions entry: start_time, end_time, nested assistance_N { highlight_start, voice_start, voice_end, highlight_end }.
        Semantics: highlight_end = assistance end (voice end for 1st/2nd in continuous mode; Enter/Esc timestamp for 3rd+).
        """
        entry = {
            "start_time": session_data["start_time"],
            "end_time": end_time,
        }
        assistance_events = session_data.get("assistance_events", [])
        voice_events = session_data.get("voice_events", [])
        by_idx_assist: Dict[int, Dict[str, float]] = {}
        for e in assistance_events:
            idx = e["index"]
            if idx not in by_idx_assist:
                by_idx_assist[idx] = {}
            by_idx_assist[idx][f"highlight_{e['event']}"] = e["time"]
        by_idx_voice: Dict[int, Dict[str, float]] = {}
        for e in voice_events:
            idx = e["index"]
            if idx not in by_idx_voice:
                by_idx_voice[idx] = {}
            by_idx_voice[idx][f"voice_{e['event']}"] = e["time"]
        for idx in sorted(set(by_idx_assist.keys()) | set(by_idx_voice.keys())):
            assist = by_idx_assist.get(idx, {})
            voice = by_idx_voice.get(idx, {})
            # Nested object: highlight_start, voice_start, voice_end, highlight_end (assistance end = voice end or Enter/Esc)
            obj = {}
            if "highlight_start" in assist:
                obj["highlight_start"] = assist["highlight_start"]
            if "voice_start" in voice:
                obj["voice_start"] = voice["voice_start"]
            if "voice_end" in voice:
                obj["voice_end"] = voice["voice_end"]
            if "highlight_end" in assist:
                obj["highlight_end"] = assist["highlight_end"]  # assistance end (1st/2nd=voice end, 3rd+=Enter/Esc)
            if obj:
                entry[f"assistance_{idx}"] = obj
        return entry

    def end_session(self, session_id: str) -> Dict[str, Any]:
        """
        End an active viewing session and save to file.
        Persists only image_filename, assistance_condition, viewing_sessions (all timestamps server time).
        """
        if session_id not in self.active_sessions:
            return {"success": False, "error": "Session not found"}
        
        session_data = self.active_sessions[session_id]
        end_time = time.time()
        duration_seconds = end_time - session_data["start_time"]
        
        file_path = self._get_file_path(
            session_data["image_filename"],
            session_data["activity"],
            session_data["assistance_condition"],
            sequence_step=session_data.get("sequence_step"),
        )
        
        existing_data = self._load_time_data(file_path)
        if not existing_data:
            existing_data = {
                "image_filename": session_data["image_filename"],
                "assistance_condition": session_data["assistance_condition"],
                "viewing_sessions": [],
            }
        # Ensure we only persist the new schema (in case we loaded legacy data)
        payload = {
            "image_filename": existing_data.get("image_filename") or session_data["image_filename"],
            "assistance_condition": existing_data.get("assistance_condition") or session_data["assistance_condition"],
            "viewing_sessions": list(existing_data.get("viewing_sessions", [])),
        }
        session_entry = self._build_session_entry(session_data, end_time)
        payload["viewing_sessions"].append(session_entry)
        
        self._save_time_data(file_path, payload)
        del self.active_sessions[session_id]
        
        logger.info(f"⏹️ Ended session {session_id} - Duration: {duration_seconds:.2f}s")
        return {
            "success": True,
            "session_id": session_id,
            "duration_seconds": round(duration_seconds, 3),
            "viewing_sessions": payload["viewing_sessions"],
        }
    
    def get_time_summary(
        self, 
        image_filename: str, 
        activity: str, 
        assistance_condition: str
    ) -> Optional[Dict[str, Any]]:
        """Get time tracking summary for a specific picture"""
        file_path = self._get_file_path(image_filename, activity, assistance_condition)
        return self._load_time_data(file_path)
    
    def get_all_summaries(self, assistance_condition: str, activity: str) -> List[Dict[str, Any]]:
        """Get summaries for all pictures in a specific condition and activity"""
        base_path = self.condition_dirs.get(assistance_condition)
        if not base_path:
            return []
        
        activity_path = base_path / activity
        if not activity_path.exists():
            return []
        
        summaries = []
        for json_file in activity_path.glob("*.json"):
            data = self._load_time_data(json_file)
            if data:
                summaries.append(data)
        
        return summaries
    
    def cleanup_session(self, session_id: str):
        """Force cleanup of an active session (e.g., on error)"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info(f"🧹 Cleaned up session {session_id}")
    
    def enable_sequence_mode(self, sequence_cache_service):
        """
        Enable sequence mode for this service
        
        Args:
            sequence_cache_service: Instance of SequenceCacheService
        """
        self.sequence_cache_service = sequence_cache_service
        logger.info("✅ Time Tracking: Sequence mode enabled")
    
    def disable_sequence_mode(self):
        """Disable sequence mode (return to standalone mode)"""
        self.sequence_cache_service = None
        logger.info("✅ Time Tracking: Sequence mode disabled")

# Global instance
_time_tracking_service: Optional[TimeTrackingService] = None

def get_time_tracking_service() -> TimeTrackingService:
    """Get the global time tracking service instance"""
    global _time_tracking_service
    if _time_tracking_service is None:
        _time_tracking_service = TimeTrackingService()
    return _time_tracking_service

