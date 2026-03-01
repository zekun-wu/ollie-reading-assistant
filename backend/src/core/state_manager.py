"""
Gaze State Manager - Core state management for eye-tracking and guidance
Implements explicit state machine to prevent race conditions
"""
import asyncio
import logging
import time
import threading
from datetime import datetime
from uuid import uuid4
from enum import Enum
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict, field
import json

logger = logging.getLogger(__name__)

class GazeState(Enum):
    """Explicit gaze states to prevent invalid transitions"""
    IDLE = "idle"
    TRACKING = "tracking"
    FROZEN_CURIOSITY = "frozen_curiosity"
    GENERATING_GUIDANCE = "generating_guidance"
    GUIDANCE_READY = "guidance_ready"
    PLAYING_GUIDANCE = "playing_guidance"
    AWAITING_DISMISSAL = "awaiting_dismissal"

@dataclass
class GuidanceRequest:
    """Structured guidance request"""
    request_id: str
    request_type: str  # 'curiosity'
    image_filename: str
    timestamp: datetime
    gaze_data: Optional[Dict] = None
    priority: int = 1  # Higher number = higher priority
    session_token: Optional[str] = None
    sequence_step: Optional[int] = None

@dataclass
class SessionState:
    """Complete session state for an image"""
    image_filename: str
    current_state: GazeState
    activity: str = 'storytelling'  # Always 'storytelling' now
    client_id: Optional[str] = None
    active_request: Optional[GuidanceRequest] = None
    request_queue: List[GuidanceRequest] = None
    last_update: datetime = None
    generation_task: Optional[asyncio.Task] = None
    is_actively_reading: bool = False  # True when in fullscreen reading mode
    sequence_step: Optional[int] = None  # For sequence mode cache routing
    condition: str = 'eye_assistance'  # NEW: Assistance condition ('base', 'assistance', 'eye_assistance')
    child_name: str = 'Guest'  # NEW: Child's name for file naming
    child_age: Optional[str] = None  # NEW: Child's age for personalization
    language: str = 'de'  # Language (German only)
    gaze_buffer: List[Dict] = None  # NEW: Buffer for raw gaze data collection
    start_time: Optional[float] = None  # NEW: Session start timestamp for gaze data
    last_processed_gaze_index: int = 0  # NEW: Track last processed index in eye tracker buffer
    session_token: str = ''  # NEW: Token to bind guidance strictly to a session
    assisted_aoi_indices: List[int] = field(default_factory=list)  # NEW: Track assisted AOIs for storytelling
    previous_stories: List[Dict[str, Any]] = field(default_factory=list)  # NEW: Track previous story JSON responses for continuity
    
    # HMM segment buffering (500ms windows)
    hmm_segment_buffer: List = field(default_factory=list)  # Buffer for current 500ms segment
    hmm_segment_start_time: Optional[float] = None  # Start time of current segment
    hmm_last_segment_time: Optional[float] = None  # Time of last processed segment
    
    # NEW: HMM-based AOI attention tracking
    aoi_attention_history: Dict[int, float] = field(default_factory=dict)  # AOI index -> latest focused timestamp
    last_focused_aoi: Optional[int] = None  # Most recently focused AOI
    last_focused_timestamp: Optional[float] = None  # When it was focused
    
    # NEW: Complete HMM temporal distance tracking
    hmm_temporal_distance_history: List[Dict] = field(default_factory=list)  # All temporal distance records
    
    def __post_init__(self):
        if self.request_queue is None:
            self.request_queue = []
        if self.last_update is None:
            self.last_update = datetime.now()
        if self.gaze_buffer is None:
            self.gaze_buffer = []
        if self.start_time is None:
            self.start_time = time.time()
        if self.previous_stories is None:
            self.previous_stories = []

class GazeStateManager:
    """
    Centralized state manager for all gaze tracking and guidance operations
    Prevents race conditions and ensures valid state transitions
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        GazeState.IDLE: [GazeState.TRACKING],
        GazeState.TRACKING: [
            GazeState.FROZEN_CURIOSITY, 
            GazeState.IDLE
        ],
        GazeState.FROZEN_CURIOSITY: [
            GazeState.GENERATING_GUIDANCE,
            GazeState.TRACKING  # If cancelled
        ],
        GazeState.GENERATING_GUIDANCE: [
            GazeState.GUIDANCE_READY,
            GazeState.TRACKING  # If failed/cancelled
        ],
        GazeState.GUIDANCE_READY: [
            GazeState.PLAYING_GUIDANCE,
            GazeState.TRACKING  # Allow direct dismiss from guidance_ready
        ],
        GazeState.PLAYING_GUIDANCE: [GazeState.AWAITING_DISMISSAL],
        GazeState.AWAITING_DISMISSAL: [GazeState.TRACKING]
    }
    
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()  # For async operations
        self._thread_lock = threading.Lock()  # NEW: For hardware callback (thread-safe)
        self._initialized = False
        self._eye_tracking_service = None
        self._gaze_data_service = None  # NEW: Gaze data service
        
        # Guidance queue system
        self._guidance_queue = []
        self._guidance_processor_running = False
        self._guidance_interval = 2.0  # 2 seconds between guidance
        self._guidance_processor_task = None
        
        # NEW: Gaze polling system
        self._gaze_polling_task = None
        self._gaze_polling_running = False
        self._gaze_poll_interval = 0.02  # 50 Hz (20ms) - Captures ALL 250 Hz points from hardware buffer
        
        # NEW: HMM assistance service
        from services.hmm_assistance_service import HMMAssistanceService
        self._hmm_service = HMMAssistanceService()
        
        # NEW: HMM assistance cooldown tracking (segment-based, not time-based)
        self._last_hmm_assistance_segment = {}  # Track last HMM assistance segment per image
        self._hmm_segment_counter = {}  # Track total segments processed per image
        
        # Store main event loop for thread-safe async calls
        self._main_loop = None
        
    async def initialize(self):
        """Initialize the state manager"""
        async with self._lock:
            if not self._initialized:
                # Initializing Gaze State Manager
                
                # Initialize eye tracking service
                from services.eye_tracking_service import get_eye_tracking_service
                self._eye_tracking_service = get_eye_tracking_service()
                
                # Initialize AOI service
                from services.aoi_service import get_aoi_service
                self._aoi_service = get_aoi_service()
                
                # Initialize fixation processor
                from services.fixation_processor import get_fixation_processor
                self._fixation_processor = get_fixation_processor()
                self._fixation_processor.set_fixation_callback(self._on_fixation_end)
                
                # NEW: Initialize gaze data service
                from services.gaze_data_service import GazeDataService
                self._gaze_data_service = GazeDataService()
                
                # Eye tracking service initialized
                # AOI and gaze data services initialized
                
                # NEW: Store main event loop for thread-safe async calls
                try:
                    self._main_loop = asyncio.get_running_loop()
                except RuntimeError:
                    logger.warning("⚠️ No running event loop found")
                
                # NEW: Register HMM callback for direct hardware processing
                if self._eye_tracking_service:
                    self._eye_tracking_service.set_hmm_callback(self._on_hardware_gaze_sample)
                
                # Start guidance queue processor
                self._guidance_processor_task = asyncio.create_task(self._guidance_queue_processor())
                # Guidance queue processor started
                
                # NEW: Start gaze polling task
                self._gaze_polling_task = asyncio.create_task(self._gaze_polling_loop())
                # Gaze polling task started
                
                self._initialized = True
                
    async def cleanup(self):
        """Cleanup all sessions and cancel running tasks"""
        async with self._lock:
            for session in self.sessions.values():
                if session.generation_task and not session.generation_task.done():
                    session.generation_task.cancel()
            
            # Cancel guidance processor
            if self._guidance_processor_task and not self._guidance_processor_task.done():
                self._guidance_processor_task.cancel()
            
            # NEW: Cancel gaze polling task
            self._gaze_polling_running = False
            if self._gaze_polling_task and not self._gaze_polling_task.done():
                self._gaze_polling_task.cancel()
                
            self.sessions.clear()

    async def clear_all_previous_stories(self):
        """Clear previous_stories for all sessions (e.g. on disconnect or sequence complete)."""
        async with self._lock:
            for session in self.sessions.values():
                session.previous_stories.clear()
            
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the state manager"""
        async with self._lock:
            return {
                "initialized": self._initialized,
                "active_sessions": len(self.sessions),
                "session_states": {
                    image: session.current_state.value 
                    for image, session in self.sessions.items()
                }
            }
    
    def get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string"""
        return datetime.now().isoformat()
    
    def _load_distance_matrix(self, image_filename: str, activity: str) -> Optional[Dict]:
        """Load distance matrix for an image"""
        try:
            from pathlib import Path
            image_name = Path(image_filename).stem
            distance_file = Path(f"../segmented_pictures/{activity}/{image_name}_distances.json")
            
            if not distance_file.exists():
                logger.warning(f"Distance file not found: {distance_file}")
                return None
                
            with open(distance_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading distance matrix: {e}")
            return None

    def _calculate_hmm_temporal_distances(
        self, 
        gazed_aoi_index: int, 
        unassisted_aois: List[int], 
        session: SessionState
    ) -> Dict[int, float]:
        """
        Calculate temporal distances based on HMM focused attention history
        
        Rules:
        - Currently gazed AOI: excluded from candidates (handled by caller)
        - Never focused AOIs: distance = 1.0
        - Most recently focused AOI: distance = 0.0
        - Other focused AOIs: proportional distance based on recency (0.0 to 1.0)
        
        Args:
            gazed_aoi_index: Currently gazed AOI (for reference, not in candidates)
            unassisted_aois: List of unassisted AOI indices to calculate distances for
            session: Session state containing attention history
            
        Returns:
            Dict mapping AOI index to temporal distance [0.0, 1.0]
        """
        attention_history = session.aoi_attention_history
        
        # If no attention history, all AOIs get distance 1.0
        if not attention_history:
            return {aoi_idx: 1.0 for aoi_idx in unassisted_aois}
        
        # Get attention times for candidate AOIs
        attention_times = {}
        for aoi_idx in unassisted_aois:
            if aoi_idx in attention_history:
                attention_times[aoi_idx] = attention_history[aoi_idx]
            else:
                attention_times[aoi_idx] = None  # Never focused
        
        # Calculate temporal distances
        temporal_distances = {}
        
        # Never focused AOIs get distance 1.0
        never_focused = [aoi for aoi, time in attention_times.items() if time is None]
        for aoi in never_focused:
            temporal_distances[aoi] = 1.0
        
        # Among focused AOIs, calculate relative temporal distances
        focused_aois = [(aoi, time) for aoi, time in attention_times.items() if time is not None]
        
        if focused_aois:
            # Sort by attention time (most recent first)
            focused_aois.sort(key=lambda x: x[1], reverse=True)
            
            most_recent_time = focused_aois[0][1]
            oldest_time = focused_aois[-1][1]
            
            if most_recent_time == oldest_time:
                # All focused at same time (shouldn't happen but handle it)
                for aoi, _ in focused_aois:
                    temporal_distances[aoi] = 0.0
            else:
                # Calculate proportional distances: most recent = 0.0, oldest = 1.0
                time_range = most_recent_time - oldest_time
                for aoi, attention_time in focused_aois:
                    relative_time = (most_recent_time - attention_time) / time_range
                    temporal_distances[aoi] = min(relative_time, 1.0)
        
        return temporal_distances

    def _track_complete_temporal_distances(self, session: SessionState, prediction: Optional[Dict]):
        """Track temporal distances for ALL AOIs at each HMM segment"""
        if not prediction:
            return
        
        # Get prediction data from either 'prediction' key or direct keys
        predicted_state = prediction.get('state')
        raw_metrics = prediction.get('raw_metrics', {})
        dominant_aoi = raw_metrics.get('dominant_aoi', 0)
        segment_end_time = prediction.get('segment_end_time')
        focused_state = prediction.get('focused_state')
        
        if not dominant_aoi or dominant_aoi <= 0:
            return  # No valid dominant AOI
        
        # Get all AOI indices from segmented data
        all_aoi_indices = self._get_all_aoi_indices(session.image_filename, session.activity)
        if not all_aoi_indices:
            return
        
        # Calculate temporal distances for ALL AOIs
        temporal_distances = {}
        for aoi_idx in all_aoi_indices:
            temporal_distances[aoi_idx] = self._calculate_single_aoi_temporal_distance(
                aoi_idx, dominant_aoi, session
            )
        
        # Create temporal distance record
        temporal_record = {
            "timestamp": segment_end_time if segment_end_time else time.time(),
            "hmm_state": predicted_state,
            "gazed_aoi": dominant_aoi,
            "temporal_distances": temporal_distances,
            "dominant_aoi": dominant_aoi,
            "segment_duration": 0.5,
            "focused_state": focused_state
        }
        
        # Store in session history
        session.hmm_temporal_distance_history.append(temporal_record)


    def _get_all_aoi_indices(self, image_filename: str, activity: str) -> List[int]:
        """Get all AOI indices for an image from distance matrix"""
        try:
            distance_data = self._load_distance_matrix(image_filename, activity)
            if not distance_data or "spatial_distance_matrix" not in distance_data:
                return []
            return list(range(1, len(distance_data["spatial_distance_matrix"]) + 1))
        except Exception as e:
            logger.error(f"Error getting AOI indices: {e}")
            return []

    def _calculate_single_aoi_temporal_distance(self, aoi_idx: int, gazed_aoi: int, session: SessionState) -> float:
        """Calculate normalized temporal distance for a single AOI"""
        attention_history = session.aoi_attention_history
        
        # Currently gazed AOI gets distance 0.0
        if aoi_idx == gazed_aoi:
            return 0.0
        
        # No attention history yet - all AOIs get distance 1.0
        if not attention_history:
            return 1.0
        
        # AOI never focused - distance 1.0
        if aoi_idx not in attention_history:
            return 1.0
        
        # Calculate normalized temporal distance among focused AOIs
        focused_times = list(attention_history.values())
        if len(focused_times) == 1:
            # Only one AOI focused so far - give it distance 0.0
            return 0.0
        
        most_recent_time = max(focused_times)
        oldest_time = min(focused_times)
        time_range = most_recent_time - oldest_time
        
        if time_range == 0:
            return 0.0  # All focused at same time
        
        # Normalize: most recent = 0.0, oldest = 1.0
        aoi_time = attention_history[aoi_idx]
        relative_time = (most_recent_time - aoi_time) / time_range
        
        return min(relative_time, 1.0)

    def _select_closest_unassisted_aoi(
        self, 
        gazed_aoi_index: int, 
        assisted_indices: List[int],
        all_aoi_indices: List[int],
        distance_data: Dict,
        session: SessionState  # NEW: Add session parameter
    ) -> Optional[int]:
        """
        Select unassisted AOI with minimum combined distance from gazed AOI
        Formula: 0.4 * spatial + 0.2 * semantic + 0.4 * temporal
        Excludes the gazed AOI from selection to prevent selecting the same AOI twice
        """
        try:
            spatial_matrix = distance_data["spatial_distance_matrix"]
            semantic_matrix = distance_data["semantic_distance_matrix"]
            
            # Convert AOI index to matrix index (1-based to 0-based)
            gazed_matrix_idx = gazed_aoi_index - 1
            
            # Find unassisted AOIs (excluding the gazed AOI to prevent self-selection)
            unassisted = [idx for idx in all_aoi_indices if idx not in assisted_indices and idx != gazed_aoi_index]
            
            if not unassisted:
                logger.info(f"🛑 No unassisted AOIs available (excluding gazed AOI {gazed_aoi_index})")
                return None
            
            # NEW: Calculate HMM-based temporal distances
            temporal_distances = self._calculate_hmm_temporal_distances(gazed_aoi_index, unassisted, session)
            
            # Calculate combined distances
            min_distance = float('inf')
            closest_aoi = None
            
            for aoi_idx in unassisted:
                matrix_idx = aoi_idx - 1  # Convert to 0-based
                
                spatial_dist = spatial_matrix[gazed_matrix_idx][matrix_idx]
                semantic_dist = semantic_matrix[gazed_matrix_idx][matrix_idx]
                temporal_dist = temporal_distances.get(aoi_idx, 1.0)
                
                # NEW: Updated formula with temporal distance
                combined_dist = 0.4 * spatial_dist + 0.2 * semantic_dist + 0.4 * temporal_dist
                
                if combined_dist < min_distance:
                    min_distance = combined_dist
                    closest_aoi = aoi_idx
            
            logger.info(f"🎯 Selected closest unassisted AOI {closest_aoi} (dist: {min_distance:.4f}, temp: {temporal_distances.get(closest_aoi, 1.0):.2f}) - excluding gazed AOI {gazed_aoi_index}")
            return closest_aoi
            
        except Exception as e:
            logger.error(f"Error selecting closest AOI: {e}")
            return None
    
    async def start_tracking(
        self, 
        image_filename: str, 
        client_id: str, 
        activity: str = 'storytelling', 
        sequence_step: Optional[int] = None,
        condition: str = 'eye_assistance',  # NEW: Assistance condition
        child_name: str = 'Guest',  # NEW: Child's name
        child_age: Optional[str] = None,  # NEW: Child's age
        language: str = 'de'  # Language (German only)
    ) -> Dict[str, Any]:
        """Start gaze tracking for an image with activity context"""
        async with self._lock:
            session = self.sessions.get(image_filename)

            # Create if missing
            if not session:
                session = SessionState(
                    image_filename=image_filename,
                    current_state=GazeState.IDLE,
                    gaze_buffer=[],
                )
                self.sessions[image_filename] = session

            # Clear this session's previous_stories so the image we are starting has fresh continuity
            session.previous_stories.clear()

            # Update context every start, and issue a fresh token
            session.activity = activity
            session.client_id = client_id
            session.sequence_step = sequence_step
            session.condition = condition
            session.child_name = child_name
            session.child_age = child_age
            session.language = language  # NEW: Store language
            session.start_time = time.time()
            session.session_token = str(uuid4())
            mode_str = f" (sequence step {sequence_step})" if sequence_step else ""
            logger.info(f"📊 Started gaze collection for {condition}/{activity}/{image_filename}{mode_str} [child: {child_name}] token={session.session_token}")
            # Clear any pending/queued guidance to avoid bleed
            if hasattr(self, '_pending_guidance_requests'):
                self._pending_guidance_requests = []
            self._guidance_queue.clear()
            
            # CRITICAL: Reset ALL other sessions' is_actively_reading flags (only ONE session active at a time)
            for img, sess in self.sessions.items():
                if img != image_filename:
                    sess.is_actively_reading = False
            
            # Mark THIS session as actively reading for gaze data collection
            session.is_actively_reading = True
            
            # CRITICAL: Set starting index in hardware buffer to avoid capturing old data
            if self._eye_tracking_service and self._eye_tracking_service.gaze_buffer:
                session.last_processed_gaze_index = len(self._eye_tracking_service.gaze_buffer)
                logger.info(f"📍 Gaze tracking starts from buffer index {session.last_processed_gaze_index}")
            
            logger.info(f"👁️ Gaze data collection enabled for {image_filename} (others deactivated)")
                
            # Load AOI definitions for this image with activity
            if self._aoi_service:
                aoi_loaded = self._aoi_service.load_aoi_definitions(image_filename, session.activity)
                if aoi_loaded:
                    logger.info(f"🎯 AOI definitions loaded for {image_filename}")
                else:
                    logger.warning(f"⚠️ No AOI definitions found for {image_filename}")
                
                # Unfreeze AOI updates when starting tracking
                self._aoi_service.unfreeze_updates()
            
            # Initialize HMM processor for eye_assistance condition
            if condition == 'eye_assistance':
                success = self._hmm_service.initialize_processor(image_filename, activity)
                if not success:
                    logger.error(f"❌ Failed to initialize HMM for {image_filename}")
                # HMM processor initialized
                logger.info(f"🧠 HMM processor initialized for {image_filename}")
                
            # Check if already tracking
            if session.current_state == GazeState.TRACKING:
                # Already tracking
                return {
                    "success": True,
                    "state": session.current_state.value,
                    "message": "Already tracking"
                }
            
            # Transition to tracking
            if await self._transition_state(session, GazeState.TRACKING):
                # CRITICAL: Start eye tracker data stream
                if self._eye_tracking_service:
                    try:
                        start_success = self._eye_tracking_service.start_tracking()
                        if start_success:
                            logger.info(f"👁️ Eye tracker data stream started (buffer active)")
                        else:
                            logger.warning(f"⚠️ Failed to start eye tracker stream")
                    except Exception as e:
                        logger.error(f"❌ Error starting eye tracker stream: {e}")
                
                # Start fixation processing
                if self._fixation_processor:
                    await self._fixation_processor.start_processing(
                        self._eye_tracking_service, 
                        self
                    )
                
                # Started tracking
                return {
                    "success": True,
                    "state": session.current_state.value,
                    "message": "Tracking started"
                }
            else:
                return {
                    "success": False,
                    "state": session.current_state.value,
                    "message": f"Cannot start tracking from {session.current_state.value}"
                }
    
    async def stop_tracking(self, image_filename: str) -> Dict[str, Any]:
        """Stop gaze tracking for an image"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"success": False, "message": "No active session"}
                
            # Cancel any active generation task
            if session.generation_task and not session.generation_task.done():
                session.generation_task.cancel()
            
            # CRITICAL: Stop gaze data collection immediately
            session.is_actively_reading = False
                
            # NEW: Save gaze data before stopping
            if self._gaze_data_service and session.gaze_buffer:
                try:
                    end_time = time.time()
                    result = self._gaze_data_service.save_gaze_session(
                        samples=session.gaze_buffer,
                        child_name=session.child_name,
                        condition=session.condition,
                        activity=session.activity,
                        image_name=session.image_filename,
                        start_time=session.start_time,
                        end_time=end_time,
                        sequence_step=session.sequence_step
                    )
                    if result.get("success"):
                        # Gaze data saved
                        pass
                    else:
                        logger.error(f"❌ Failed to save gaze data: {result.get('error')}")
                except Exception as e:
                    logger.error(f"❌ Error saving gaze data: {e}")
            
            # NEW: Save HMM states before stopping (eye_assistance only)
            if session.condition == 'eye_assistance' and self._hmm_service:
                try:
                    from services.hmm_state_logger import get_hmm_state_logger
                    hmm_logger = get_hmm_state_logger()
                    
                    # Get focused/unfocused states from HMM processor
                    focused_state = None
                    unfocused_state = None
                    if image_filename in self._hmm_service.processors:
                        processor = self._hmm_service.processors[image_filename]
                        focused_state = processor.focused_state
                        unfocused_state = processor.unfocused_state
                    
                    result = hmm_logger.save_session(
                        image_filename=image_filename,
                        sequence_step=session.sequence_step,
                        focused_state=focused_state,
                        unfocused_state=unfocused_state
                    )
                    if result.get("success"):
                        logger.info(f"📊 HMM states saved: {result.get('segments_logged')} segments")
                    else:
                        logger.error(f"❌ Failed to save HMM states: {result.get('error')}")
                except Exception as e:
                    logger.error(f"❌ Error saving HMM states: {e}")
            
            # Transition to idle
            if await self._transition_state(session, GazeState.IDLE):
                # Stop fixation processing
                if self._fixation_processor:
                    await self._fixation_processor.stop_processing()
                
                # CRITICAL: Stop eye tracker data stream
                if self._eye_tracking_service:
                    try:
                        stop_success = self._eye_tracking_service.stop_tracking()
                        if stop_success:
                            logger.info(f"👁️ Eye tracker data stream stopped")
                        else:
                            logger.warning(f"⚠️ Failed to stop eye tracker stream")
                    except Exception as e:
                        logger.error(f"❌ Error stopping eye tracker stream: {e}")
                
                # Clear request queue and guidance queue
                session.request_queue.clear()
                session.active_request = None
                
                # Clear guidance queue to prevent stale guidance
                queue_size = len(self._guidance_queue)
                if queue_size > 0:
                    self._guidance_queue.clear()
                    logger.info(f"🧹 Cleared {queue_size} items from guidance queue")
                
                # NEW: Save AOI data with HMM temporal distance tracking
                if self._aoi_service:
                    self._aoi_service._save_aoi_data(session)
                    logger.info(f"💾 Saved temporal distance data: {len(session.hmm_temporal_distance_history)} segments")
                
                # Reset attention history
                session.aoi_attention_history.clear()
                session.last_focused_aoi = None
                session.last_focused_timestamp = None
                session.hmm_temporal_distance_history.clear()  # NEW: Also clear temporal history
                
                logger.info(f"🛑 Stopped tracking for {image_filename}")
                return {
                    "success": True,
                    "state": session.current_state.value,
                    "message": "Tracking stopped"
                }
            else:
                return {
                    "success": False,
                    "state": session.current_state.value,
                    "message": f"Cannot stop tracking from {session.current_state.value}"
                }
    
    async def start_reading_session(self, image_filename: str, client_id: str) -> Dict[str, Any]:
        """Start active reading session (fullscreen mode)"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"success": False, "message": "No active session"}
            
            # Reset ALL other sessions' is_actively_reading flags
            for img, sess in self.sessions.items():
                if img != image_filename:
                    sess.is_actively_reading = False
            
            # Mark THIS session as actively reading
            session.is_actively_reading = True
            session.last_update = datetime.now()
            
            logger.info(f"📖 Started reading session for {image_filename} (reset others)")
            
            # Reset AOI data for fresh start
            if self._aoi_service:
                self._aoi_service.reset_all_aoi_data()
                logger.info(f"🔄 Reset AOI data for new reading session: {image_filename}")
            
            # Reset assisted AOI tracking for new reading session
            session.assisted_aoi_indices = []
            logger.info(f"🔄 Reset assisted AOI tracking for new reading session: {image_filename}")
            
            # NEW: Re-enable HMM processing for new reading session
            if self._hmm_service and session.condition == 'eye_assistance':
                # CRITICAL: Initialize HMM processor if not already done
                if image_filename not in self._hmm_service.processors:
                    logger.info(f"🔍 HMM processor not found, initializing for {image_filename}")
                    success = self._hmm_service.initialize_processor(image_filename, session.activity)
                    if not success:
                        logger.error(f"❌ Failed to initialize HMM for {image_filename}")
                    else:
                        logger.info(f"✅ HMM processor initialized for {image_filename}")
                else:
                    logger.info(f"🔍 HMM processor already exists for {image_filename}")
                
                self._hmm_service.enable_processing(image_filename)
                logger.info(f"✅ HMM processing enabled for {image_filename}")
            
            logger.info(f"📖 Started reading session for {image_filename}")
            return {
                "success": True,
                "state": session.current_state.value,
                "is_actively_reading": True,
                "message": "Reading session started"
            }
    
    async def stop_reading_session(self, image_filename: str) -> Dict[str, Any]:
        """Stop active reading session (exit fullscreen)"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"success": False, "message": "No active session"}
            
            # Mark as not actively reading
            session.is_actively_reading = False
            session.last_update = datetime.now()
            
            # Clear guidance queue for clean state
            queue_size = len(self._guidance_queue)
            if queue_size > 0:
                self._guidance_queue.clear()
                logger.info(f"🧹 Cleared {queue_size} items from guidance queue on reading session stop")
            
            # Reset guidance flags so AOIs can trigger guidance again next session
            if self._aoi_service:
                self._aoi_service.reset_guidance_flags()
                logger.info(f"🔄 Reset guidance flags for next reading session")
            
            logger.info(f"📖 Stopped reading session for {image_filename}")
            return {
                "success": True,
                "state": session.current_state.value,
                "is_actively_reading": False,
                "message": "Reading session stopped"
            }
    
    async def request_guidance(
        self, 
        image_filename: str, 
        request_type: str, 
        gaze_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Request guidance generation (curiosity)"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                logger.error(f"   ❌ No active session for {image_filename}")
                return {"success": False, "message": "No active session"}
            
            # Check if we can request guidance from current state
            if session.current_state != GazeState.TRACKING:
                logger.warning(f"   ❌ Cannot request guidance from {session.current_state.value}")
                return {
                    "success": False,
                    "state": session.current_state.value,
                    "message": f"Cannot request guidance from {session.current_state.value}"
                }
            
            # HARD GUARDS: Only generate guidance for eye_assistance and active reading
            if session.condition != 'eye_assistance' or not session.is_actively_reading:
                logger.warning(f"   ❌ Guidance disabled: condition={session.condition}, reading={session.is_actively_reading}")
                return {"success": False, "message": "Guidance disabled for this condition/state"}

            # All checks passed, creating guidance request

            # Create guidance request
            request = GuidanceRequest(
                request_id=f"{image_filename}_{request_type}_{datetime.now().timestamp()}",
                request_type=request_type,
                image_filename=image_filename,
                timestamp=datetime.now(),
                gaze_data=gaze_data,
                priority=1,
                session_token=session.session_token,
                sequence_step=session.sequence_step
            )
            
            # Cancel any existing requests and clear queue
            await self._cancel_active_generation(session)
            session.request_queue.clear()
            
            # Add new request to queue
            session.request_queue.append(request)
            session.request_queue.sort(key=lambda r: r.priority, reverse=True)
            
            # Transition to frozen curiosity state
            target_state = GazeState.FROZEN_CURIOSITY
            
            if await self._transition_state(session, target_state):
                # State transition successful
                
                # FREEZE AOI UPDATES when guidance is requested
                if self._aoi_service:
                    self._aoi_service.freeze_updates()
                    # AOI updates frozen
                
                # FREEZE HMM PROCESSING when guidance is requested
                if self._hmm_service:
                    self._hmm_service.freeze_processing(image_filename)
                    # HMM processing frozen
                
                # Start processing the queue
                await self._process_request_queue(session)
                
                logger.info("Requested %s guidance for %s", request_type, image_filename)
                return {
                    "success": True,
                    "state": session.current_state.value,
                    "request_id": request.request_id,
                    "message": f"Guidance request queued: {request_type}"
                }
            else:
                logger.error(f"   ❌ State transition failed!")
                return {
                    "success": False,
                    "state": session.current_state.value,
                    "message": f"Cannot freeze from {session.current_state.value}"
                }
    
    async def stop_assistance_for_image(self, image_filename: str) -> Dict[str, Any]:
        """Stop all assistance for current image - clears queue and blocks new guidance"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"success": False, "message": "No active session"}
            
            # Clear guidance queue
            queue_size = len(self._guidance_queue)
            if queue_size > 0:
                self._guidance_queue.clear()
                logger.info(f"🧹 Cleared {queue_size} queued guidance items")
            
            # Cancel any active generation task
            if session.generation_task and not session.generation_task.done():
                session.generation_task.cancel()
                logger.info(f"🚫 Cancelled active guidance generation")
            
            # Transition back to tracking
            if session.current_state in [GazeState.GUIDANCE_READY, GazeState.GENERATING_GUIDANCE]:
                await self._transition_state(session, GazeState.TRACKING)
            
            # Clear request queue
            session.request_queue.clear()
            session.active_request = None
            
            # NEW: Disable HMM processing to prevent new assistance triggers
            if self._hmm_service and session.condition == 'eye_assistance':
                self._hmm_service.disable_processing(image_filename)
                # HMM processing disabled
            
            # DO NOT unfreeze AOI updates - keep frozen to prevent new guidance
            # AOI updates will resume on next image or when "Got It!" is clicked
            
            logger.info(f"🛑 Stopped all assistance for {image_filename} (AOI stays frozen)")
            
            # Send goodbye message before stopping
            if hasattr(self, '_websocket_manager') and self._websocket_manager:
                # Language-aware goodbye message
                goodbye_message = (
                    "Bis bald!"
                    if session.language == 'de'
                    else "See you soon!"
                )
                # Sending goodbye message
                await self._websocket_manager.broadcast({
                    "type": "guidance_update",
                    "guidance": {
                        "type": "stopped",
                        "message": goodbye_message,
                        "timestamp": datetime.now().isoformat(),
                        "image_filename": session.image_filename  # For frontend validation
                    }
                })
                # Goodbye message sent
            
            return {
                "success": True,
                "state": session.current_state.value,
                "message": "Assistance stopped for current image"
            }
    
    async def dismiss_guidance(self, image_filename: str) -> Dict[str, Any]:
        """Dismiss current guidance and resume tracking"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"success": False, "message": "No active session"}
            
            # Cancel any active generation
            await self._cancel_active_generation(session)
            
            # Clear guidance state
            session.active_request = None
            session.request_queue.clear()
            
            # NEW: Clear incomplete HMM segment buffer after assistance
            if session.hmm_segment_buffer:
                session.hmm_segment_buffer.clear()
                logger.info("🧹 Cleared HMM segment buffer after assistance dismissal")
            
            # Transition back to tracking
            if await self._transition_state(session, GazeState.TRACKING):
                # UNFREEZE AOI UPDATES when guidance is dismissed
                if self._aoi_service:
                    self._aoi_service.unfreeze_updates()
                
                # NEW: UNFREEZE HMM PROCESSING when guidance is dismissed
                if self._hmm_service:
                    self._hmm_service.unfreeze_processing(image_filename)
                    logger.info("🔄 HMM processing unfrozen - tracking resumed")
                
                # NEW: Start 6-segment cooldown from dismissal (6 × 500ms = 3 seconds)
                if image_filename in self._hmm_segment_counter:
                    self._last_hmm_assistance_segment[image_filename] = self._hmm_segment_counter[image_filename]
                    logger.info("⏳ HMM cooldown started: 6 segments (3 seconds)")
                
                # Dismissed guidance
                return {
                    "success": True,
                    "state": session.current_state.value,
                    "message": "Guidance dismissed, tracking resumed"
                }
            else:
                return {
                    "success": False,
                    "state": session.current_state.value,
                    "message": f"Cannot dismiss from {session.current_state.value}"
                }
    
    async def get_session_state(self, image_filename: str) -> Dict[str, Any]:
        """Get current state of a session"""
        async with self._lock:
            session = self.sessions.get(image_filename)
            if not session:
                return {"exists": False}
            
            return {
                "exists": True,
                "state": session.current_state.value,
                "image_filename": session.image_filename,
                "client_id": session.client_id,
                "has_active_request": session.active_request is not None,
                "queue_length": len(session.request_queue),
                "last_update": session.last_update.isoformat()
            }
    
    async def process_websocket_message(
        self, 
        client_id: str, 
        message: Dict[str, Any], 
        websocket_manager
    ) -> Optional[Dict[str, Any]]:
        """Process incoming WebSocket message"""
        # Store websocket_manager reference for later use
        self._websocket_manager = websocket_manager
        
        # Process any pending guidance requests
        await self._process_pending_guidance_requests()
        try:
            message_type = message.get("type")
            image_filename = message.get("image_filename")
            
            if message_type == "start_tracking":
                activity = message.get("activity", "storytelling")  # Always default to storytelling now
                sequence_step = message.get("sequence_step")  # Get sequence_step from message
                condition = message.get("condition", "eye_assistance")  # NEW: Get condition from message
                child_name = message.get("child_name", "Guest")  # NEW: Get child_name from message
                child_age = message.get("child_age")  # NEW: Get child_age from message
                language = message.get("language", "en")  # NEW: Get language from message
                logger.debug("WS start_tracking: client=%s image=%s cond=%s step=%s activity=%s lang=%s", client_id, image_filename, condition, sequence_step, activity, language)
                result = await self.start_tracking(image_filename, client_id, activity, sequence_step, condition, child_name, child_age, language)
                return {"type": "tracking_started", **result}
                
            elif message_type == "stop_tracking":
                logger.debug("WS stop_tracking: client=%s image=%s", client_id, image_filename)
                result = await self.stop_tracking(image_filename)
                return {"type": "tracking_stopped", **result}
            
            elif message_type == "start_reading_session":
                result = await self.start_reading_session(image_filename, client_id)
                return {"type": "reading_session_started", **result}
            
            elif message_type == "stop_reading_session":
                result = await self.stop_reading_session(image_filename)
                return {"type": "reading_session_stopped", **result}
                
            elif message_type == "request_guidance":
                request_type = message.get("request_type")
                gaze_data = message.get("gaze_data")
                result = await self.request_guidance(image_filename, request_type, gaze_data)
                return {"type": "guidance_requested", **result}
                
            elif message_type == "dismiss_guidance":
                result = await self.dismiss_guidance(image_filename)
                return {"type": "guidance_dismissed", **result}
            
            elif message_type == "stop_assistance":
                result = await self.stop_assistance_for_image(image_filename)
                return {"type": "assistance_stopped", **result}
                
            elif message_type == "get_state":
                result = await self.get_session_state(image_filename)
                return {"type": "state_update", **result}

            elif message_type == "sequence_complete":
                await self.clear_all_previous_stories()
                return {"type": "sequence_complete_ack"}
                
            else:
                return {"type": "error", "message": f"Unknown message type: {message_type}"}
                
        except Exception as e:
            logger.error(f"❌ Error processing WebSocket message: {e}")
            return {"type": "error", "message": str(e)}
    
    async def _transition_state(self, session: SessionState, new_state: GazeState) -> bool:
        """Attempt to transition session to new state"""
        current_state = session.current_state
        # State transition: {current_state.value} → {new_state.value}
        
        if new_state in self.VALID_TRANSITIONS.get(current_state, []):
            session.current_state = new_state
            session.last_update = datetime.now()
            # Transition completed successfully
            
            # HMM freeze/unfreeze control based on state
            if new_state in [GazeState.GENERATING_GUIDANCE, GazeState.GUIDANCE_READY, 
                            GazeState.PLAYING_GUIDANCE, GazeState.AWAITING_DISMISSAL]:
                # Freeze HMM processing when assistance is active
                self._hmm_service.freeze_processing(session.image_filename)
                
            elif new_state == GazeState.TRACKING:
                # Unfreeze HMM processing when back to tracking
                self._hmm_service.unfreeze_processing(session.image_filename)
            
            return True
        else:
            logger.warning(f"❌ Invalid state transition: {current_state.value} → {new_state.value}")
            return False
    
    async def _cancel_active_generation(self, session: SessionState):
        """Cancel any active guidance generation task"""
        if session.generation_task and not session.generation_task.done():
            session.generation_task.cancel()
            try:
                await session.generation_task
            except asyncio.CancelledError:
                logger.info("🚫 Cancelled active guidance generation")
    
    async def _process_request_queue(self, session: SessionState):
        """Process the guidance request queue"""
        if not session.request_queue:
            return
            
        # Get highest priority request
        request = session.request_queue[0]
        session.active_request = request
        
        # Transition to generating state
        if await self._transition_state(session, GazeState.GENERATING_GUIDANCE):
            # Start generation task (mock for now)
            session.generation_task = asyncio.create_task(
                self._generate_guidance_mock(session, request)
            )
    
    async def _generate_guidance_mock(self, session: SessionState, request: GuidanceRequest):
        """Generate guidance with 3-stage progressive updates for curiosity"""
        try:
            logger.info(f"🤖 Generating {request.request_type} guidance for {request.image_filename}")
            
            # Generate 3-stage progressive guidance for curiosity
            await self._generate_progressive_curiosity_guidance(session, request)
            return  # Progressive method handles state transitions
                    
        except asyncio.CancelledError:
            logger.info("🚫 Guidance generation cancelled")
            async with self._lock:
                if session.current_state == GazeState.GENERATING_GUIDANCE:
                    await self._transition_state(session, GazeState.TRACKING)
        except Exception as e:
            logger.error(f"❌ Guidance generation error: {e}")
            async with self._lock:
                await self._transition_state(session, GazeState.TRACKING)
    
    async def _generate_progressive_curiosity_guidance(self, session: SessionState, request: GuidanceRequest):
        """Generate curiosity guidance in 3 progressive stages"""
        try:
            aoi_index = request.gaze_data.get("aoi_index")
            aoi_bbox = request.gaze_data.get("aoi_bbox")
            
            # STAGE 1: Immediate "thinking" message
            # Stage 1: Sending 'thinking' message
            
            # NEW: Capture start timestamp when thinking message is sent
            start_timestamp = time.time()
            
            async with self._lock:
                if session.current_state == GazeState.GENERATING_GUIDANCE:
                    await self._transition_state(session, GazeState.GUIDANCE_READY)
                    
                    # Language-aware thinking message
                    thinking_message = (
                        "Aha! Ich sehe, du bist neugierig darauf. Lass mich darüber nachdenken..."
                        if session.language == 'de'
                        else "Aha! I see you are curious about this. Let me think about it..."
                    )
                    
                    thinking_data = {
                        "type": "curiosity",
                        "stage": "thinking",
                        "message": thinking_message,
                        "timestamp": datetime.now().isoformat(),
                        "start_timestamp": start_timestamp,  # NEW: Include Unix timestamp
                        "image_filename": session.image_filename,  # For frontend validation
                        "triggered_aoi": {
                            "index": aoi_index,
                            "bbox": aoi_bbox,
                            "center": request.gaze_data.get("aoi_center")
                        },
                        "sequence_step": session.sequence_step,  # NEW: For end_timestamp tracking
                        "secondary_aoi_index": None  # Will be updated in guidance_update for two-AOI storytelling
                    }
                    
                    if hasattr(self, '_websocket_manager') and self._websocket_manager:
                        await self._websocket_manager.broadcast({
                            "type": "guidance_ready",
                            "guidance": thinking_data
                        })
                        # Stage 1: Thinking message sent
            
            # STAGE 2: Generate LLM analysis in background
            # Stage 2: Generating LLM analysis
            llm_result = await self._generate_llm_curiosity_guidance(session, request, start_timestamp=start_timestamp)
            
            if llm_result.get("has_llm"):
                # Language-aware main content message
                main_message = (
                    "Schaue dir bitte den hervorgehobenen Teil an"
                    if session.language == 'de'
                    else "Take a look at the highlighted part please"
                )
                
                # Send main content stage
                main_stage_data = {
                    "type": "curiosity",
                    "stage": "main_content",
                    "message": main_message,
                    "analysis": llm_result["analysis"],
                    "voice_texts": llm_result["voice_texts"],
                    "main_audio": llm_result["main_audio"],
                    "timestamp": datetime.now().isoformat(),
                    "image_filename": session.image_filename,  # For frontend validation
                    "triggered_aoi": llm_result["triggered_aoi"],
                    "sequence_step": session.sequence_step,  # NEW: For end_timestamp tracking
                    "secondary_aoi_index": llm_result.get("secondary_aoi_index")  # NEW: Include for two-AOI storytelling
                }
                
                if hasattr(self, '_websocket_manager') and self._websocket_manager:
                    await self._websocket_manager.broadcast({
                        "type": "guidance_update",
                        "guidance": main_stage_data
                    })
                    # Stage 2: Main content sent
            
        except Exception as e:
            logger.error(f"❌ Error in progressive curiosity guidance: {e}")
            # Fallback to simple guidance
            async with self._lock:
                await self._transition_state(session, GazeState.TRACKING)
    
    async def _generate_llm_curiosity_guidance(self, session: SessionState, request: GuidanceRequest, start_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Generate LLM-based curiosity guidance for eye-tracking"""
        try:
            aoi_index = request.gaze_data.get("aoi_index")
            aoi_bbox = request.gaze_data.get("aoi_bbox")
            
            # For storytelling, use two-AOI approach with distance-based selection
            if session.activity == 'storytelling':
                # Load distance matrix
                distance_data = self._load_distance_matrix(session.image_filename, session.activity)
                
                if distance_data is None:
                    logger.error("Cannot proceed without distance matrix for storytelling")
                    return {
                        "type": "curiosity",
                        "message": "you are curious!",
                        "timestamp": datetime.now().isoformat(),
                        "triggered_aoi": {
                            "index": aoi_index,
                            "bbox": aoi_bbox,
                            "center": request.gaze_data.get("aoi_center")
                        } if request.gaze_data else None,
                        "has_llm": False,
                        "error": "Distance matrix not found"
                    }
                
                # Get all AOI indices from distance matrix
                all_aoi_indices = list(range(1, len(distance_data["spatial_distance_matrix"]) + 1))
                
                # Select closest unassisted AOI
                secondary_aoi_index = self._select_closest_unassisted_aoi(
                    aoi_index, 
                    session.assisted_aoi_indices,
                    all_aoi_indices,
                    distance_data,
                    session  # NEW: Pass session for HMM attention data
                )
                
                if secondary_aoi_index is None:
                    logger.info("🛑 All AOIs assisted - stopping eye-tracking assistance")
                    return {
                        "type": "curiosity",
                        "message": "you are curious!",
                        "timestamp": datetime.now().isoformat(),
                        "triggered_aoi": {
                            "index": aoi_index,
                            "bbox": aoi_bbox,
                            "center": request.gaze_data.get("aoi_center")
                        } if request.gaze_data else None,
                        "has_llm": False,
                        "error": "All AOIs already assisted"
                    }
                
                # Mark primary AOI as assisted
                session.assisted_aoi_indices.append(aoi_index)
                
                # Process two AOIs
                result = await self._process_eye_tracking_two_aois(
                    session, aoi_index, secondary_aoi_index
                )
                
                if result is None:
                    raise Exception("Two-AOI processing failed")
                
                # Return guidance data for storytelling
                display_message = result["llm_response"].get("child_story")
                
                return {
                    "type": "curiosity",
                    "message": display_message or "you are curious!",
                    "analysis": result["llm_response"],
                    "voice_texts": result["voice_texts"],
                    "main_audio": result["main_audio"],
                    "timestamp": datetime.now().isoformat(),
                    "triggered_aoi": {
                        "index": aoi_index,
                        "bbox": aoi_bbox,
                        "center": request.gaze_data.get("aoi_center")
                    },
                    "secondary_aoi_index": secondary_aoi_index,  # NEW: Include secondary AOI for frontend
                    "has_llm": True
                }
            
        except Exception as e:
            logger.error(f"❌ Eye-Tracking LLM error: {e}")
            # Fallback to simple
            return {
                "type": "curiosity",
                "message": "you are curious!",
                "timestamp": datetime.now().isoformat(),
                "triggered_aoi": {
                    "index": request.gaze_data.get("aoi_index"),
                    "bbox": request.gaze_data.get("aoi_bbox"),
                    "center": request.gaze_data.get("aoi_center")
                } if request.gaze_data else None,
                "has_llm": False,
                "error": str(e)
            }
    
    async def _process_eye_tracking_two_aois(
        self, 
        session: SessionState, 
        primary_aoi_index: int,
        secondary_aoi_index: int
    ) -> Dict:
        """Process two AOIs for eye-tracking storytelling"""
        try:
            from services.eye_tracking_image_cropping import get_eye_tracking_cropping_service
            from services.eye_tracking_llm_service import get_eye_tracking_llm_service
            from services.eye_tracking_tts_service import get_eye_tracking_tts_service
            from services.eye_tracking_cache_service import get_eye_tracking_cache_service
            
            # Get bboxes for both AOIs
            primary_bbox = self._aoi_service.aoi_definitions[primary_aoi_index]['bbox']
            secondary_bbox = self._aoi_service.aoi_definitions[secondary_aoi_index]['bbox']
            
            # Get object lists for both AOIs (if available) - use German objects if language is 'de'
            if session.language == 'de':
                primary_objects = self._aoi_service.aoi_definitions[primary_aoi_index].get('objects_de', [])
                secondary_objects = self._aoi_service.aoi_definitions[secondary_aoi_index].get('objects_de', [])
                # Fallback to English if German not available
                if not primary_objects:
                    primary_objects = self._aoi_service.aoi_definitions[primary_aoi_index].get('objects', [])
                if not secondary_objects:
                    secondary_objects = self._aoi_service.aoi_definitions[secondary_aoi_index].get('objects', [])
            else:
                primary_objects = self._aoi_service.aoi_definitions[primary_aoi_index].get('objects', [])
                secondary_objects = self._aoi_service.aoi_definitions[secondary_aoi_index].get('objects', [])
            
            # Crop two AOIs
            cropping_service = get_eye_tracking_cropping_service()
            aoi1_b64, aoi2_b64, full_b64 = cropping_service.crop_two_aois_from_image(
                session.image_filename,
                session.activity,
                primary_bbox,
                secondary_bbox
            )
            
            if not aoi1_b64 or not aoi2_b64:
                raise Exception("Two-AOI image cropping failed")
            
            # Call LLM with two AOIs (pass object lists, context, and previous stories)
            llm_service = get_eye_tracking_llm_service()
            llm_response = llm_service.analyze_two_aoi_images(
                aoi1_b64, aoi2_b64, full_b64,
                session.activity,
                primary_aoi_index,
                secondary_aoi_index,
                aoi1_objects=primary_objects if primary_objects else None,
                aoi2_objects=secondary_objects if secondary_objects else None,
                child_name=session.child_name,
                child_age=session.child_age,
                language=session.language,  # NEW: Pass language
                image_filename=session.image_filename,  # NEW: For loading context
                previous_stories=session.previous_stories  # NEW: For continuity
            )
            
            # Append response to previous_stories for next call
            if llm_response and isinstance(llm_response, dict):
                # Store the analysis dict (which contains child_story)
                session.previous_stories.append(llm_response)
                logger.info(f"📚 Added story to previous_stories (total: {len(session.previous_stories)})")
            
            # Generate TTS
            voice_texts = llm_service.create_voice_texts(llm_response, session.activity, session.child_name or "little explorer")
            tts_service = get_eye_tracking_tts_service()
            main_tts = tts_service.synthesize_speech(
                voice_texts["main_voice"],
                session.image_filename,
                session.activity,
                primary_aoi_index,
                "main",
                sequence_step=session.sequence_step,
                primary_aoi=primary_aoi_index,
                secondary_aoi=secondary_aoi_index,
                language=session.language  # NEW: Pass language
            )
            
            # Cache response
            cache_service = get_eye_tracking_cache_service()
            cache_service.save_llm_response_two_aois(
                session.image_filename,
                session.activity,
                primary_aoi_index,
                secondary_aoi_index,
                llm_response,
                main_tts.get("audio_url"),
                session.sequence_step,
                language=session.language  # NEW: Pass language
            )
            
            return {
                "aoi_index": primary_aoi_index,
                "main_audio": main_tts,
                "llm_response": llm_response,
                "voice_texts": voice_texts
            }
            
        except Exception as e:
            logger.error(f"Error processing two AOIs: {e}")
            return None
    
    def _schedule_guidance_request(self, fixation_data, guidance_info):
        """Schedule guidance request to run in main event loop"""
        try:
            if hasattr(self, '_websocket_manager') and self._websocket_manager:
                # Store the guidance request for processing
                if not hasattr(self, '_pending_guidance_requests'):
                    self._pending_guidance_requests = []
                
                self._pending_guidance_requests.append({
                    'fixation_data': fixation_data,
                    'guidance_info': guidance_info,
                    'timestamp': time.time()
                })
                
                logger.info(f"📋 Scheduled guidance request for AOI {guidance_info['aoi_index']}")
        except Exception as e:
            logger.error(f"❌ Error scheduling guidance request: {e}")
    
    async def _process_pending_guidance_requests(self):
        """Process any pending guidance requests from fixation callbacks"""
        if not hasattr(self, '_pending_guidance_requests'):
            return
        
        pending = getattr(self, '_pending_guidance_requests', [])
        if not pending:
            return
        
        # Process all pending requests
        for request in pending:
            try:
                fixation_data = request['fixation_data']
                guidance_info = request['guidance_info']
                target_image = request.get('image_filename')
                target_token = request.get('session_token')

                if not target_image or target_image not in self.sessions:
                    continue

                session = self.sessions[target_image]
                # Validate token and condition
                if session.session_token != target_token or session.condition != 'eye_assistance' or not session.is_actively_reading:
                    continue

                gaze_data = {
                    "fixation_duration_ms": guidance_info['total_duration'],
                    "aoi_index": guidance_info['aoi_index'],
                    "aoi_center": guidance_info['center'],
                    "x": fixation_data.x,
                    "y": fixation_data.y,
                    "detection_method": "real_fixation_event"
                }
                
                await self.request_guidance(target_image, "curiosity", gaze_data)
                    
            except Exception as e:
                logger.error(f"❌ Error processing pending guidance request: {e}")
        
        # Clear processed requests
        self._pending_guidance_requests = []
    
    async def _on_fixation_end(self, fixation_event):
        """Callback when a real fixation ends"""
        try:
            
            # Process through AOI system
            if self._aoi_service:
                aoi_result = self._aoi_service.process_fixation_sync(
                    fixation_event.x,
                    fixation_event.y,
                    fixation_event.duration_ms
                )
                
                if aoi_result and aoi_result.get('guidance_triggered'):
                    guidance_info = aoi_result['guidance_triggered']
                    logger.info(f"🎯 Fixation Processor: AOI {guidance_info['aoi_index']} triggered")
                    
                    # Find actively reading session only (current image)
                    active_sessions = [
                        (image_filename, session) for image_filename, session in self.sessions.items()
                        if session.is_actively_reading and session.current_state == GazeState.TRACKING
                    ]
                    
                    logger.info(f"🔍 Fixation Processor: Found {len(active_sessions)} actively reading sessions")
                    
                    for image_filename, session in active_sessions:
                        # CRITICAL: Only generate LLM guidance for eye_assistance condition
                        if session.condition != 'eye_assistance':
                            logger.info(f"⏭️ Fixation Processor: Skipping guidance for {image_filename} (condition: {session.condition}, not eye_assistance)")
                            break  # Exit loop, no guidance needed for other conditions
                        
                        # Fixation Processor: Using session
                        gaze_data = {
                            "fixation_duration_ms": fixation_event.duration_ms,
                            "aoi_index": guidance_info['aoi_index'],
                            "aoi_bbox": guidance_info.get('aoi_bbox'),  # ← ADD BBOX
                            "aoi_center": guidance_info['center'],
                            "x": fixation_event.x,
                            "y": fixation_event.y,
                            "detection_method": "real_fixation_event"
                        }
                        
                        
                        # Add to guidance queue instead of processing immediately
                        self._add_guidance_to_queue(image_filename, "curiosity", gaze_data)
                        break  # Only process first (and only) actively reading session
                        
        except Exception as e:
            logger.error(f"❌ Error processing fixation end: {e}")
    
    def _on_hardware_gaze_sample(self, gaze_point):
        """
        Called directly from hardware callback at 250 Hz.
        Must be thread-safe and synchronous (no async).
        Processes gaze for HMM segment buffering and triggering.
        """
        with self._thread_lock:
            for session in list(self.sessions.values()):
                if (session.is_actively_reading and 
                    session.condition == 'eye_assistance' and
                    session.current_state == GazeState.TRACKING):
                    
                    # Add to HMM segment buffer
                    session.hmm_segment_buffer.append({
                        'timestamp': gaze_point.timestamp,
                        'x': gaze_point.x if gaze_point.x is not None else 0.0,
                        'y': gaze_point.y if gaze_point.y is not None else 0.0,
                        'validity': 1 if gaze_point.validity == 'valid' else 0
                    })
                    
                    # Check if segment complete (EXACTLY 125 samples = 500ms at 250Hz)
                    if len(session.hmm_segment_buffer) == 125:
                        logger.info(f"📦 HMM segment complete: 125 samples collected")
                        self._process_hmm_segment_sync(session)
    
    def _process_hmm_segment_sync(self, session):
        """
        Process complete HMM segment synchronously.
        Called from hardware thread at 250 Hz.
        """
        try:
            # Check if HMM is initialized (warm-start complete)
            if not self._hmm_service.is_initialized(session.image_filename):
                # Still warming up - feed samples to HMM but don't trigger assistance
                logger.info(f"⏳ HMM warm-start: Processing segment for initialization")
                segment_buffer = session.hmm_segment_buffer.copy()
                session.hmm_segment_buffer.clear()
                
                # Feed each sample to HMM for warm-start
                for sample in segment_buffer:
                    self._hmm_service.process_gaze_sample(
                        session.image_filename,
                        sample['timestamp'],
                        sample['x'],
                        sample['y'],
                        sample['validity']
                    )
                return
            
            # Process complete segment
            segment_buffer = session.hmm_segment_buffer.copy()
            session.hmm_segment_buffer.clear()
            
            assistance_trigger = self._hmm_service.process_segment(
                session.image_filename,
                segment_buffer
            )
            
            # Increment segment counter
            if session.image_filename not in self._hmm_segment_counter:
                self._hmm_segment_counter[session.image_filename] = 0
            self._hmm_segment_counter[session.image_filename] += 1
            current_segment = self._hmm_segment_counter[session.image_filename]
            
            # NEW: Update AOI attention tracking even when no assistance triggered
            self._update_aoi_attention_tracking(session, assistance_trigger)
            
            # NEW: Track complete temporal distances for ALL AOIs
            self._track_complete_temporal_distances(session, assistance_trigger)
            
            # Handle assistance trigger
            if assistance_trigger and assistance_trigger.get('triggered'):
                # Check 6-segment cooldown (6 segments × 500ms = 3 seconds)
                COOLDOWN_SEGMENTS = 6
                if session.image_filename in self._last_hmm_assistance_segment:
                    segments_since_last = current_segment - self._last_hmm_assistance_segment[session.image_filename]
                    if segments_since_last < COOLDOWN_SEGMENTS:
                        logger.info(f"⏳ HMM cooldown active: {segments_since_last}/{COOLDOWN_SEGMENTS} segments")
                        return
                
                # Get AOI data
                aoi_index = assistance_trigger['aoi_index']
                aoi_bbox = None
                aoi_center = None
                
                if self._aoi_service and aoi_index is not None:
                    if aoi_index in self._aoi_service.aoi_data:
                        aoi_data = self._aoi_service.aoi_data[aoi_index]
                        aoi_bbox = aoi_data.bbox
                        aoi_center = aoi_data.center
                
                # Schedule assistance in main event loop
                if self._main_loop:
                    asyncio.run_coroutine_threadsafe(
                        self._trigger_hmm_assistance_async(session, assistance_trigger, aoi_bbox, aoi_center),
                        self._main_loop
                    )
                    
                    # Mark this segment as the last assistance segment
                    self._last_hmm_assistance_segment[session.image_filename] = current_segment
                    logger.info(f"✅ HMM assistance scheduled from hardware callback (segment {current_segment})")
                    
        except Exception as e:
            logger.error(f"❌ Error in HMM segment processing: {e}")
    
    def _update_aoi_attention_tracking(self, session: SessionState, prediction: Optional[Dict]):
        """Update AOI attention tracking based on HMM focused state"""
        if not prediction:
            return
        
        predicted_state = prediction.get('state')
        focused_state = prediction.get('focused_state')
        raw_metrics = prediction.get('raw_metrics', {})
        dominant_aoi = raw_metrics.get('dominant_aoi')
        segment_end_time = prediction.get('segment_end_time')
        
        # Only track when user is in focused state AND has a valid dominant AOI
        if (predicted_state == focused_state and 
            dominant_aoi is not None and 
            dominant_aoi > 0 and  # Exclude background AOI
            segment_end_time is not None):
            
            # Update AOI attention history with latest timestamp
            session.aoi_attention_history[dominant_aoi] = segment_end_time
            session.last_focused_aoi = dominant_aoi
            session.last_focused_timestamp = segment_end_time
            
            logger.debug(f"🎯 AOI {dominant_aoi} focused at {segment_end_time:.2f}s")
    
    async def _trigger_hmm_assistance_async(self, session, assistance_trigger, aoi_bbox, aoi_center):
        """Trigger HMM assistance asynchronously from main event loop"""
        try:
            async with self._lock:
                # Verify session still valid and in tracking state
                if (session.image_filename not in self.sessions or
                    session.current_state != GazeState.TRACKING or
                    not session.is_actively_reading):
                    return
                
                aoi_index = assistance_trigger['aoi_index']
                
                # Check if this AOI has already been assisted (storytelling only)
                if session.activity == 'storytelling' and aoi_index in session.assisted_aoi_indices:
                    logger.info(f"🛑 AOI {aoi_index} already assisted for storytelling - skipping")
                    return
                
                # Create guidance request
                request = GuidanceRequest(
                    request_id=f"{session.image_filename}_curiosity_{datetime.now().timestamp()}",
                    request_type="curiosity",
                    image_filename=session.image_filename,
                    timestamp=datetime.now(),
                    gaze_data={
                        "fixation_duration_ms": 500,
                        "aoi_index": aoi_index,
                        "aoi_bbox": aoi_bbox,
                        "aoi_center": aoi_center,
                        "detection_method": "hmm_based"
                    },
                    priority=1,
                    session_token=session.session_token,
                    sequence_step=session.sequence_step
                )
                
                # Cancel existing requests and add new one
                await self._cancel_active_generation(session)
                session.request_queue.clear()
                session.request_queue.append(request)
                
                # Transition state and start guidance
                if await self._transition_state(session, GazeState.FROZEN_CURIOSITY):
                    # Freeze services
                    if self._aoi_service:
                        self._aoi_service.freeze_updates()
                    if self._hmm_service:
                        self._hmm_service.freeze_processing(session.image_filename)
                    
                    # Start guidance generation
                    await self._process_request_queue(session)
                    logger.info(f"🎯 HMM assistance triggered for AOI {aoi_index}")
                    
        except Exception as e:
            logger.error(f"❌ Error triggering HMM assistance: {e}")
    
    async def _guidance_queue_processor(self):
        """Process guidance queue with 2-second intervals"""
        logger.info("📋 Guidance queue processor started")
        
        while True:
            try:
                if self._guidance_queue:
                    # Get next guidance request
                    guidance_request = self._guidance_queue.pop(0)
                    
                    logger.info(f"📋 Processing guidance request: {guidance_request.get('request_id', 'unknown')}")
                    logger.info(f"   📊 Type: {guidance_request.get('request_type', 'unknown')}")
                    logger.info(f"   📊 Image: {guidance_request.get('image_filename', 'unknown')}")
                    logger.info(f"   📊 Gaze data: {guidance_request.get('gaze_data', {})}")
                    
                    # Process the guidance request
                    await self._process_queued_guidance(guidance_request)
                    
                    # Guidance request processed successfully
                    
                    # Wait 2 seconds before next guidance
                    if self._guidance_queue:  # Only wait if more guidance pending
                        logger.info(f"📋 Waiting {self._guidance_interval}s before next guidance ({len(self._guidance_queue)} remaining)")
                        await asyncio.sleep(self._guidance_interval)
                else:
                    # No guidance in queue, check every 100ms
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"   ❌ Error processing guidance request: {e}")
                logger.exception(e)
                await asyncio.sleep(1)  # Wait before retrying
    
    async def _gaze_polling_loop(self):
        """
        Background task to continuously poll eye-tracker and buffer gaze data for gaze.json files.
        HMM processing now happens directly in hardware callback (250 Hz).
        This loop runs at 50 Hz for data collection only.
        """
        logger.info("📡 Gaze polling loop started (50 Hz - for gaze.json data collection)")
        self._gaze_polling_running = True
        
        while self._gaze_polling_running:
            try:
                # Check if we have any active sessions
                if not self.sessions:
                    await asyncio.sleep(0.1)  # No sessions, check every 100ms
                    continue
                
                # Poll eye-tracker for ALL new gaze data (not just last point)
                if self._eye_tracking_service and self._eye_tracking_service.gaze_buffer:
                    # Get the entire hardware buffer
                    hardware_buffer = self._eye_tracking_service.gaze_buffer
                    current_buffer_size = len(hardware_buffer)
                    
                    # Buffer gaze for ALL active sessions (for gaze.json files)
                    async with self._lock:
                        for session_id, session in self.sessions.items():
                            if session.is_actively_reading and session.gaze_buffer is not None:
                                # Get all NEW points since last poll (not just the last one!)
                                # This captures the full 250 Hz data stream
                                start_idx = session.last_processed_gaze_index
                                
                                # Handle buffer wraparound: if the hardware buffer was cleared or reset,
                                # start from the beginning
                                if start_idx >= current_buffer_size:
                                    start_idx = max(0, current_buffer_size - 10)  # Take last 10 points as safety
                                
                                # Extract ALL new points since last poll
                                new_points = hardware_buffer[start_idx:current_buffer_size]
                                
                                # Add ALL new points to session buffer (for gaze.json files)
                                for gaze_point in new_points:
                                    session.gaze_buffer.append({
                                        "t": gaze_point.timestamp,
                                        "x": gaze_point.x if gaze_point.x is not None else 0.0,
                                        "y": gaze_point.y if gaze_point.y is not None else 0.0,
                                        "v": 1 if gaze_point.validity == 'valid' else 0
                                    })
                                
                                # Update the last processed index for this session
                                session.last_processed_gaze_index = current_buffer_size
                                
                                # NOTE: HMM processing removed from here - now happens in hardware callback
                                # This ensures precise 500ms segments (exactly 125 samples at 250 Hz)
                
                # Sleep 20ms (50 Hz polling rate) - captures all 250 Hz points from buffer
                await asyncio.sleep(self._gaze_poll_interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Gaze polling loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in gaze polling loop: {e}")
                await asyncio.sleep(0.1)  # Wait before retrying
        
        logger.info("📡 Gaze polling loop stopped")
    
    async def _process_queued_guidance(self, guidance_request):
        """Process a single guidance request from the queue"""
        try:
            image_filename = guidance_request['image_filename']
            guidance_type = guidance_request['guidance_type']
            gaze_data = guidance_request['gaze_data']
            
            # Find active session
            session = self.sessions.get(image_filename)
            if not session:
                logger.warning(f"⚠️ Cannot process guidance - no session for {image_filename}")
                return
            
            # Allow guidance processing in TRACKING or GUIDANCE_READY states AND actively reading
            if session.current_state not in [GazeState.TRACKING, GazeState.GUIDANCE_READY]:
                logger.warning(f"⚠️ Cannot process guidance - session in {session.current_state.value} state")
                return
            
            if not session.is_actively_reading:
                logger.warning(f"⚠️ Cannot process guidance - user not actively reading")
                return
            
            # HARD GUARDS: Only for eye_assistance and matching token
            req_token = guidance_request.get('session_token')
            if session.condition != 'eye_assistance' or session.session_token != req_token:
                logger.debug("Discarding queued guidance (condition/token mismatch) for %s", image_filename)
                return

            # Process guidance normally
            await self.request_guidance(image_filename, guidance_type, gaze_data)
            
        except Exception as e:
            logger.error(f"❌ Error processing queued guidance: {e}")
    
    def _add_guidance_to_queue(self, image_filename: str, guidance_type: str, gaze_data: Dict):
        """Add guidance request to queue instead of processing immediately"""
        session = self.sessions.get(image_filename)
        guidance_request = {
            'image_filename': image_filename,
            'guidance_type': guidance_type,
            'gaze_data': gaze_data,
            'timestamp': time.time(),
            'aoi_index': gaze_data.get('aoi_index', 'unknown'),
            'session_token': session.session_token if session else None,
            'sequence_step': session.sequence_step if session else None
        }
        
        self._guidance_queue.append(guidance_request)
        logger.info(f"📋 Added guidance to queue: AOI {gaze_data.get('aoi_index', 'unknown')} (queue size: {len(self._guidance_queue)})")
