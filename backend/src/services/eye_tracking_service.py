"""
Tobii Eye-Tracking Service for EyeReadDemo v7
Integrates with the new state machine architecture
"""
import asyncio
import logging
import time
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

@dataclass
class GazePoint:
    """Individual gaze data point"""
    timestamp: float
    x: Optional[float]  # Screen coordinates (0-1)
    y: Optional[float]  # Screen coordinates (0-1)
    validity: str  # 'valid', 'invalid', 'unknown'
    device_timestamp: Optional[float] = None

@dataclass
class Fixation:
    """Detected fixation event"""
    start_time: float
    end_time: float
    duration_ms: float
    x: float
    y: float
    gaze_points: List[GazePoint]

class TobiiEyeTrackingService:
    """
    Eye-tracking service that integrates with the state machine
    Handles real Tobii hardware or provides simulation mode
    """
    
    def __init__(self, simulation_mode: bool = False):
        self.simulation_mode = False  # FORCE REAL HARDWARE ONLY
        self.is_connected = False
        self.is_tracking = False
        self.current_image_context = None
        
        # Gaze data storage
        self.gaze_buffer: List[GazePoint] = []
        self.max_buffer_size = 1000
        
        # Fixation detection parameters
        self.fixation_threshold_duration = 100  # ms minimum for fixation
        self.fixation_threshold_distance = 50   # pixels maximum movement
        
        # Current fixation tracking
        self.current_fixation_start = None
        self.current_fixation_points = []
        self.last_gaze_time = None
        
        # Event callbacks
        self._hmm_callback: Optional[Callable] = None  # Direct HMM processing callback
        
        # Threading
        self._tracking_thread = None
        self._stop_tracking = threading.Event()
        self._main_loop = None  # Store reference to main event loop
        
        # Try to import Tobii SDK
        self.tobii_available = self._check_tobii_sdk()
        if not self.tobii_available:
            raise RuntimeError("❌ Tobii SDK required for real hardware mode")

    def _check_tobii_sdk(self) -> bool:
        """Check if Tobii SDK is available"""
        # #region agent log
        import sys
        import json
        _log_path = r"c:\Users\ZekunWu\Desktop\EyeReadDemo-v7\.cursor\debug.log"
        try:
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"hypothesisId": "H3,H4", "location": "eye_tracking_service.py:_check_tobii_sdk", "message": "before tobii_research import", "data": {"sys_executable": sys.executable, "path_len": len(sys.path)}, "timestamp": __import__("time").time(), "sessionId": "debug-session", "runId": "run1"}) + "\n")
        except Exception:
            pass
        # #endregion
        try:
            import tobii_research as tr
            self.tr = tr
            logger.info("✅ Tobii SDK available")
            return True
        except Exception as e:
            # #region agent log
            try:
                with open(_log_path, "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"hypothesisId": "H3,H4", "location": "eye_tracking_service.py:_check_tobii_sdk", "message": "tobii_research import failed", "data": {"exc_type": type(e).__name__, "exc_msg": str(e)}, "timestamp": __import__("time").time(), "sessionId": "debug-session", "runId": "run1"}) + "\n")
            except Exception:
                pass
            # #endregion
            logger.warning("❌ Tobii SDK not found")
            return False

    async def find_and_connect_eyetracker(self) -> bool:
        """Find and connect to a Tobii eye tracker"""
        try:
            if not self.tobii_available:
                return False
                
            # Find eye trackers
            eyetrackers = self.tr.find_all_eyetrackers()
            
            if not eyetrackers:
                logger.error("❌ No eye trackers found")
                return False
            
            # Connect to first available eye tracker
            self.eyetracker = eyetrackers[0]
            logger.info(f"✅ Connected to eye tracker: {self.eyetracker.device_name}")
            logger.info(f"📍 Address: {self.eyetracker.address}")
            logger.info(f"🔄 Sampling rate: {self.eyetracker.get_gaze_output_frequency()}Hz")
            
            self.is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to eye tracker: {e}")
            return False

    def start_tracking(self) -> bool:
        """Start gaze data collection"""
        if self.is_tracking:
            return True
            
        if not self.is_connected:
            logger.error("❌ Eye tracker not connected")
            return False
        
        try:
            self.gaze_buffer.clear()
            self._stop_tracking.clear()
            self.last_gaze_time = time.time()
            
            # Store reference to main event loop for thread-safe callbacks
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("⚠️ No running event loop found")
            
            # Start real Tobii tracking ONLY
            self.eyetracker.subscribe_to(self.tr.EYETRACKER_GAZE_DATA, self._gaze_data_callback)
            logger.info("👁️ Started real eye tracking")
            
            self.is_tracking = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start eye tracking: {e}")
            return False

    def stop_tracking(self) -> bool:
        """Stop gaze data collection"""
        if not self.is_tracking:
            return True
            
        try:
            self._stop_tracking.set()
            
            # Stop real Tobii tracking ONLY
            self.eyetracker.unsubscribe_from(self.tr.EYETRACKER_GAZE_DATA, self._gaze_data_callback)
            logger.info("🛑 Stopped real eye tracking")
            
            self.is_tracking = False
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop eye tracking: {e}")
            return False

    def disconnect(self):
        """Disconnect from eye tracker"""
        if self.is_tracking:
            self.stop_tracking()
        
        self.is_connected = False
        if hasattr(self, 'eyetracker'):
            delattr(self, 'eyetracker')
        
        logger.info("🔌 Disconnected from eye tracker")

    def get_status(self) -> Dict[str, Any]:
        """Get current eye tracker status"""
        status = {
            "connected": self.is_connected,
            "tracking": self.is_tracking,
            "simulation_mode": False,  # Always false now
            "tobii_available": self.tobii_available,
            "buffer_size": len(self.gaze_buffer),
            "current_image": self.current_image_context
        }
        
        if self.is_connected and hasattr(self, 'eyetracker'):
            try:
                status.update({
                    "device_name": self.eyetracker.device_name,
                    "address": self.eyetracker.address,
                    "sampling_rate": self.eyetracker.get_gaze_output_frequency()
                })
            except:
                pass
        
        return status

    def set_image_context(self, image_path: str):
        """Set the current image context for gaze analysis"""
        self.current_image_context = image_path
        logger.info(f"🖼️ Set image context: {image_path}")

    def get_current_gaze_position(self) -> Optional[Dict[str, float]]:
        """Get the most recent valid gaze position - filter stale data"""
        if not self.gaze_buffer:
            return None
        
        current_time = time.time()
        freshness_threshold = 0.2  # 200ms - data older than this is considered stale
        
        # Find the most recent valid AND FRESH gaze point
        for gaze_point in reversed(self.gaze_buffer):
            age_ms = (current_time - gaze_point.timestamp) * 1000
            
            if (gaze_point.validity == 'valid' and 
                gaze_point.x is not None and gaze_point.y is not None and
                str(gaze_point.x) != 'nan' and str(gaze_point.y) != 'nan' and
                age_ms <= (freshness_threshold * 1000)):
                
                return {
                    'x': gaze_point.x,
                    'y': gaze_point.y,
                    'timestamp': gaze_point.timestamp
                }
        
        return None

    def get_latest_gaze_data(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get the latest gaze data points - only return valid ones"""
        if not self.gaze_buffer:
            return []
        
        recent_points = self.gaze_buffer[-count:] if len(self.gaze_buffer) >= count else self.gaze_buffer
        
        # Filter out invalid points at retrieval time
        valid_points = [
            point for point in recent_points
            if (point.validity == 'valid' and 
                point.x is not None and point.y is not None and
                str(point.x) != 'nan' and str(point.y) != 'nan')
        ]
        
        return [
            {
                'timestamp': point.timestamp,
                'x': point.x,
                'y': point.y,
                'validity': point.validity,
                'device_timestamp': point.device_timestamp
            }
            for point in valid_points
        ]

    def set_hmm_callback(self, callback: Callable):
        """Set callback for direct HMM processing (called at 250 Hz)"""
        self._hmm_callback = callback
        logger.info("✅ HMM callback registered for direct gaze processing")
    
    def _schedule_callback(self, callback: Callable, data: Any):
        """Schedule callback safely - use sync callbacks to avoid threading issues"""
        if callback is None:
            return
            
        try:
            # Use synchronous callback approach to avoid asyncio threading issues
            if hasattr(callback, '__self__') and hasattr(callback.__self__, 'process_fixation_sync'):
                # Call the synchronous version if available
                callback.__self__.process_fixation_sync(data)
            else:
                # For now, just log the fixation - we'll process it differently
                logger.info(f"🎯 Fixation detected: {data.duration_ms:.0f}ms at ({data.x:.3f}, {data.y:.3f})")
                
                # Store fixation for processing by the main loop
                if not hasattr(self, '_pending_fixations'):
                    self._pending_fixations = []
                self._pending_fixations.append(data)
                
        except Exception as e:
            logger.error(f"❌ Error in callback: {e}")

    def _gaze_data_callback(self, gaze_data):
        """Process incoming gaze data from Tobii SDK"""
        try:
            # Extract gaze data from Tobii GazeData object
            left_eye_data = gaze_data.left_eye
            right_eye_data = gaze_data.right_eye
            
            # Extract gaze point on display area and validity
            left_eye_point = left_eye_data.gaze_point.position_on_display_area
            right_eye_point = right_eye_data.gaze_point.position_on_display_area
            left_validity = left_eye_data.gaze_point.validity
            right_validity = right_eye_data.gaze_point.validity
            
            # Extract coordinates (normalized 0-1 coordinates)
            # Check validity properly - Tobii uses True/False, not 0/1
            left_valid = left_validity == True
            right_valid = right_validity == True
            
            left_x = left_eye_point[0] if left_valid and left_eye_point[0] is not None else None
            left_y = left_eye_point[1] if left_valid and left_eye_point[1] is not None else None
            right_x = right_eye_point[0] if right_valid and right_eye_point[0] is not None else None
            right_y = right_eye_point[1] if right_valid and right_eye_point[1] is not None else None
            
            # Use average of both eyes if both valid, otherwise use available eye
            if left_valid and right_valid and left_x is not None and right_x is not None:
                # Both eyes valid - use average
                x = (left_x + right_x) / 2
                y = (left_y + right_y) / 2
                validity = 'valid'
            elif left_valid and left_x is not None:
                # Only left eye valid
                x = left_x
                y = left_y
                validity = 'valid'
            elif right_valid and right_x is not None:
                # Only right eye valid
                x = right_x
                y = right_y
                validity = 'valid'
            else:
                # Neither eye valid
                x, y = None, None
                validity = 'invalid'
            
            # ALWAYS ADD TO BUFFER - Don't filter here, filter at retrieval
            gaze_point = GazePoint(
                timestamp=time.time(),
                x=x,
                y=y,
                validity=validity,  # Keep original validity
                device_timestamp=getattr(gaze_data, 'device_time_stamp', None)
            )
            
            self._add_gaze_point(gaze_point)
            
        except Exception as e:
            logger.error(f"❌ Error processing gaze data: {e}")
            logger.error(f"   Gaze data type: {type(gaze_data)}")
            if hasattr(gaze_data, '__dict__'):
                logger.error(f"   Gaze data attributes: {list(vars(gaze_data).keys())}")
            elif isinstance(gaze_data, dict):
                logger.error(f"   Gaze data keys: {list(gaze_data.keys())}")
            else:
                logger.error(f"   Gaze data: {gaze_data}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")


    def _add_gaze_point(self, gaze_point: GazePoint):
        """Add gaze point to buffer - ALWAYS add, filter later"""
        # ALWAYS add to buffer (valid or invalid)
        self.gaze_buffer.append(gaze_point)
        if len(self.gaze_buffer) > self.max_buffer_size:
            self.gaze_buffer.pop(0)
        
        # NEW: Direct HMM processing callback (called at 250 Hz)
        if self._hmm_callback:
            try:
                self._hmm_callback(gaze_point)
            except Exception as e:
                logger.error(f"❌ HMM callback error: {e}")
        
        # Only update last_gaze_time for valid points
        if (gaze_point.validity == 'valid' and 
            gaze_point.x is not None and gaze_point.y is not None and
            str(gaze_point.x) != 'nan' and str(gaze_point.y) != 'nan'):
            self.last_gaze_time = gaze_point.timestamp
            
            # Only check for fixations with valid points
            self._check_for_fixation(gaze_point)

    def _check_for_fixation(self, gaze_point: GazePoint):
        """Check if current gaze forms a fixation"""
        if gaze_point.validity != 'valid':
            return
        
        current_time = gaze_point.timestamp
        
        # If no current fixation, start one
        if self.current_fixation_start is None:
            self.current_fixation_start = current_time
            self.current_fixation_points = [gaze_point]
            return
        
        # Check if gaze point is close enough to continue fixation
        if self._is_within_fixation_threshold(gaze_point):
            self.current_fixation_points.append(gaze_point)
        else:
            # Gaze moved too far, end current fixation
            self._reset_fixation()
            # Start new fixation
            self.current_fixation_start = current_time
            self.current_fixation_points = [gaze_point]

    def _is_within_fixation_threshold(self, gaze_point: GazePoint) -> bool:
        """Check if gaze point is within fixation distance threshold"""
        if not self.current_fixation_points:
            return True
        
        # Use average position of current fixation
        avg_x = sum(p.x for p in self.current_fixation_points) / len(self.current_fixation_points)
        avg_y = sum(p.y for p in self.current_fixation_points) / len(self.current_fixation_points)
        
        # Convert to pixels (assuming 1920x1080 screen)
        screen_width, screen_height = 1920, 1080
        pixel_distance = (
            ((gaze_point.x - avg_x) * screen_width) ** 2 +
            ((gaze_point.y - avg_y) * screen_height) ** 2
        ) ** 0.5
        
        return pixel_distance <= self.fixation_threshold_distance

    def _reset_fixation(self):
        """Reset current fixation tracking"""
        self.current_fixation_start = None
        self.current_fixation_points = []


# Global instance
_eye_tracking_service: Optional[TobiiEyeTrackingService] = None

def get_eye_tracking_service() -> TobiiEyeTrackingService:
    """Get the global eye tracking service instance"""
    global _eye_tracking_service
    if _eye_tracking_service is None:
        _eye_tracking_service = TobiiEyeTrackingService(simulation_mode=False)  # REAL HARDWARE MODE
    return _eye_tracking_service
