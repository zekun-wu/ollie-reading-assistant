"""
Area of Interest (AOI) Service for EyeReadDemo v7
Handles AOI mapping, fixation tracking, and data persistence
"""
import json
import os
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class AOIData:
    """AOI tracking data"""
    aoi_index: int
    fixation_duration: float  # Total accumulated fixation time in ms
    fixation_count: int       # Number of separate fixations
    revisits: int            # Number of times returned to this AOI
    last_fixation_time: Optional[float] = None
    guidance_issued: bool = False  # Prevent duplicate guidance
    bbox: List[int] = None    # [x1, y1, x2, y2]
    center: List[int] = None  # [x, y]
    area: int = 0

@dataclass
class FixationEvent:
    """Individual fixation event for logging"""
    timestamp: float
    aoi_index: int
    duration_ms: float
    x_coordinate: float
    y_coordinate: float
    is_new_fixation: bool
    cumulative_duration: float

class AOIService:
    """
    Manages Area of Interest tracking and data persistence
    Integrates with eye tracking to map gaze to semantic regions
    """
    
    def __init__(self):
        self.current_image: Optional[str] = None
        self.current_activity: Optional[str] = None  # Track current activity
        self.aoi_definitions: Dict[int, Dict] = {}
        self.aoi_data: Dict[int, AOIData] = {}
        self.image_width: int = 1500
        self.image_height: int = 959
        
        # Tracking state
        self.is_frozen = False
        self.last_aoi_index: Optional[int] = None
        self.current_fixation_start: Optional[float] = None
        
        # Base directories - activity-aware like ManualAssistanceService
        # Will be set based on user_number from session profile
        self.gaze_base_dir = None
        self.labels_base_dir = Path("../segmented_pictures")
    
    def reset(self):
        """Reset cached values for new session (called when user_number changes)"""
        self.gaze_base_dir = None
        logger.info("🔄 AOI Service reset for new session")
    
    def _get_user_number(self) -> Optional[int]:
        """Get user number from session profile service"""
        try:
            from services.session_profile_service import get_session_profile_service
            profile_service = get_session_profile_service()
            return profile_service.get_user_number()
        except Exception as e:
            logger.warning(f"⚠️ Could not get user_number from session profile: {e}")
            return None
    
    def _get_gaze_base_dir(self) -> Path:
        """Get or initialize gaze_base_dir based on user_number"""
        if self.gaze_base_dir is not None:
            return self.gaze_base_dir
        
        user_number = self._get_user_number()
        backend_dir = Path(__file__).parent.parent.parent
        
        if user_number:
            # Use record/{user_number}/gaze_data/ structure
            self.gaze_base_dir = backend_dir / "record" / str(user_number) / "gaze_data"
            logger.debug("Using user-based gaze_data directory: %s", self.gaze_base_dir)
        else:
            # Fallback to old structure for backward compatibility
            self.gaze_base_dir = backend_dir / "gaze"
            logger.warning("⚠️ No user_number found, using fallback gaze/ directory")
        
        return self.gaze_base_dir
        
    def load_aoi_definitions(self, image_filename: str, activity: str = 'storytelling') -> bool:
        """Load AOI definitions from activity-specific labels file"""
        try:
            self.current_image = image_filename
            self.current_activity = activity
            image_name = Path(image_filename).stem  # Remove .jpg extension
            
            # Activity-specific labels directory (like ManualAssistanceService)
            labels_file = self.labels_base_dir / activity / f"{image_name}_labels.json"
            
            if not labels_file.exists():
                logger.error(f"❌ AOI labels file not found: {labels_file}")
                return False
            
            with open(labels_file, 'r') as f:
                labels_data = json.load(f)
            
            self.image_width = labels_data.get('width', 1500)
            self.image_height = labels_data.get('height', 959)
            
            # Load AOI definitions
            self.aoi_definitions = {}
            for obj in labels_data.get('objects', []):
                aoi_index = obj['index']
                self.aoi_definitions[aoi_index] = {
                    'bbox': obj['bbox'],  # [x1, y1, x2, y2]
                    'center': obj['center'],  # [x, y]
                    'area': obj['area'],
                    'objects': obj.get('objects', []),  # List of object names (English)
                    'objects_de': obj.get('objects_de', [])  # List of object names (German)
                }
            
            logger.info(f"✅ Loaded {len(self.aoi_definitions)} AOIs for {activity}/{image_name} ({self.image_width}x{self.image_height})")
            
            # Initialize or load existing AOI data
            self._load_or_initialize_aoi_data(image_name)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading AOI definitions: {e}")
            return False
    
    def _load_or_initialize_aoi_data(self, image_name: str):
        """Load existing AOI data or initialize new tracking"""
        # Use activity-specific directory
        if not self.current_activity:
            self.current_activity = 'storytelling'  # Default fallback
        
        gaze_base_dir = self._get_gaze_base_dir()
        activity_dir = gaze_base_dir / self.current_activity
        activity_dir.mkdir(parents=True, exist_ok=True)
        aoi_file = activity_dir / f"{image_name}_aois.json"
        
        if aoi_file.exists():
            try:
                with open(aoi_file, 'r') as f:
                    saved_data = json.load(f)
                
                # Load existing AOI data
                self.aoi_data = {}
                for aoi_index_str, data in saved_data.get('aois', {}).items():
                    aoi_index = int(aoi_index_str)
                    self.aoi_data[aoi_index] = AOIData(
                        aoi_index=aoi_index,
                        fixation_duration=data.get('fixation_duration', 0),
                        fixation_count=data.get('fixation_count', 0),
                        revisits=data.get('revisits', 0),
                        last_fixation_time=data.get('last_fixation_time'),
                        guidance_issued=data.get('guidance_issued', False),
                        bbox=self.aoi_definitions[aoi_index]['bbox'],
                        center=self.aoi_definitions[aoi_index]['center'],
                        area=self.aoi_definitions[aoi_index]['area']
                    )
                
                logger.debug(f"📂 Loaded existing AOI data for {image_name}")
                
            except Exception as e:
                logger.error(f"❌ Error loading existing AOI data: {e}")
                self._initialize_fresh_aoi_data()
        else:
            self._initialize_fresh_aoi_data()
    
    def _initialize_fresh_aoi_data(self):
        """Initialize fresh AOI tracking data"""
        self.aoi_data = {}
        for aoi_index, definition in self.aoi_definitions.items():
            self.aoi_data[aoi_index] = AOIData(
                aoi_index=aoi_index,
                fixation_duration=0,
                fixation_count=0,
                revisits=0,
                guidance_issued=False,
                bbox=definition['bbox'],
                center=definition['center'],
                area=definition['area']
            )
        
        logger.debug(f"🆕 Initialized fresh AOI data for {len(self.aoi_data)} AOIs")
    
    def get_aoi_at_position(self, x: float, y: float) -> Optional[int]:
        """Get AOI index at normalized gaze position (0-1 coordinates)"""
        # Convert normalized coordinates (0-1) directly to image pixels
        pixel_x = x * self.image_width   # 0-1 → 0-1500
        pixel_y = y * self.image_height  # 0-1 → 0-959
        
        # Check which AOI contains this point
        for aoi_index, definition in self.aoi_definitions.items():
            bbox = definition['bbox']  # [x1, y1, x2, y2]
            
            if (bbox[0] <= pixel_x <= bbox[2] and 
                bbox[1] <= pixel_y <= bbox[3]):
                return aoi_index
        return None  # No AOI at this position
    
    def process_fixation(self, x: float, y: float, duration_ms: float) -> Optional[Dict]:
        """Process a fixation event and update AOI data"""
        
        if self.is_frozen:
            logger.debug("🧊 AOI processing frozen - guidance active")
            return None
        
        current_time = time.time()
        aoi_index = self.get_aoi_at_position(x, y)
        
        if aoi_index is None:
            # Fixation outside any AOI
            self.last_aoi_index = None
            self.current_fixation_start = None
            return None
        
        # Get or create AOI data
        if aoi_index not in self.aoi_data:
            logger.warning(f"⚠️ AOI {aoi_index} not in data, skipping")
            return None
        
        aoi_data = self.aoi_data[aoi_index]
        
        # Check if this is a new fixation or continuation
        is_new_fixation = False
        if self.last_aoi_index != aoi_index:
            # New AOI - this is a new fixation
            is_new_fixation = True
            aoi_data.fixation_count += 1
            
            # Count revisits (returning to previously visited AOI)
            if aoi_data.last_fixation_time is not None:
                aoi_data.revisits += 1
            
            self.current_fixation_start = current_time
            logger.debug(f"👁️ New fixation on AOI {aoi_index}")
        
        # Update cumulative duration
        aoi_data.fixation_duration += duration_ms
        aoi_data.last_fixation_time = current_time
        
        # Log less frequently to reduce spam
        if aoi_data.fixation_duration % 2000 < duration_ms:  # Every 2 seconds
            logger.debug(f"📊 AOI {aoi_index}: {aoi_data.fixation_duration:.0f}ms")
        
        # Create fixation event
        fixation_event = FixationEvent(
            timestamp=current_time,
            aoi_index=aoi_index,
            duration_ms=duration_ms,
            x_coordinate=x,
            y_coordinate=y,
            is_new_fixation=is_new_fixation,
            cumulative_duration=aoi_data.fixation_duration
        )
        
        # Note: 4-second threshold removed - HMM handles assistance triggering
        guidance_triggered = None
        
        self.last_aoi_index = aoi_index
        
        # Save updated data
        self._save_aoi_data()
        
        return {
            'fixation_event': asdict(fixation_event),
            'aoi_data': asdict(aoi_data),
            'guidance_triggered': guidance_triggered
        }
    
    def process_fixation_sync(self, x: float, y: float, duration_ms: float) -> Optional[Dict]:
        """Synchronous version of process_fixation for thread-safe calling"""
        if self.is_frozen:
            logger.debug("🧊 AOI processing frozen - guidance active")
            return None
        
        current_time = time.time()
        aoi_index = self.get_aoi_at_position(x, y)
        
        if aoi_index is None:
            return None
        
        if aoi_index not in self.aoi_data:
            logger.warning(f"⚠️ AOI {aoi_index} not in data, skipping")
            return None
        
        aoi_data = self.aoi_data[aoi_index]
        
        # This is a complete fixation event - add the full duration
        is_new_fixation = self.last_aoi_index != aoi_index
        if is_new_fixation:
            aoi_data.fixation_count += 1
            if aoi_data.last_fixation_time is not None:
                aoi_data.revisits += 1
            logger.debug(f"👁️ New fixation on AOI {aoi_index}: {duration_ms:.0f}ms")
        
        # Add the complete fixation duration
        aoi_data.fixation_duration += duration_ms
        aoi_data.last_fixation_time = current_time
        
        logger.debug(f"📊 AOI {aoi_index}: {aoi_data.fixation_duration:.0f}ms")
        
        # Note: 4-second threshold removed - HMM handles assistance triggering
        guidance_triggered = None
        
        self.last_aoi_index = aoi_index
        
        # Save updated data
        self._save_aoi_data()
        
        return {
            'aoi_index': aoi_index,
            'aoi_data': asdict(aoi_data),
            'guidance_triggered': guidance_triggered
        }
    
    def freeze_updates(self):
        """Freeze AOI data updates (when guidance is active)"""
        self.is_frozen = True
        logger.info("🧊 AOI updates FROZEN - guidance active")
    
    def unfreeze_updates(self):
        """Unfreeze AOI data updates (when guidance dismissed)"""
        self.is_frozen = False
        logger.info("🔄 AOI updates UNFROZEN - tracking resumed")
    
    def _save_aoi_data(self, session: Optional['SessionState'] = None):
        """Save AOI data with complete HMM temporal distance tracking"""
        if not self.current_image or not self.current_activity:
            return
        
        try:
            # Activity-specific gaze directory (like ManualAssistanceService)
            gaze_base_dir = self._get_gaze_base_dir()
            activity_dir = gaze_base_dir / self.current_activity
            activity_dir.mkdir(parents=True, exist_ok=True)
            
            image_name = Path(self.current_image).stem
            aoi_file = activity_dir / f"{image_name}_aois.json"
            
            logger.debug(f"💾 Saving AOI data to: {aoi_file.absolute()}")
            
            # Get temporal distance history if session provided
            temporal_history = []
            if session:
                temporal_history = getattr(session, 'hmm_temporal_distance_history', [])
            
            # Convert AOI data to JSON format
            aois_json = {
                'image_filename': self.current_image,
                'image_width': self.image_width,
                'image_height': self.image_height,
                'last_updated': time.time(),
                
                # NEW: Complete HMM temporal distance tracking
                'hmm_temporal_distance_history': temporal_history,
                
                'aois': {
                    str(aoi_index): {
                        'aoi_index': data.aoi_index,
                        'fixation_duration': data.fixation_duration,
                        'fixation_count': data.fixation_count,
                        'revisits': data.revisits,
                        'last_fixation_time': data.last_fixation_time,
                        'guidance_issued': data.guidance_issued,
                        'bbox': data.bbox,
                        'center': data.center,
                        'area': data.area
                    }
                    for aoi_index, data in self.aoi_data.items()
                }
            }
            
            with open(aoi_file, 'w') as f:
                json.dump(aois_json, f, indent=2)
            
            logger.debug(f"💾 Saved AOI data with {len(temporal_history)} temporal records to {aoi_file}")
            
        except Exception as e:
            logger.error(f"❌ Error saving AOI data: {e}")
    
    def get_aoi_summary(self) -> Dict[str, Any]:
        """Get summary of current AOI tracking"""
        if not self.aoi_data:
            return {"total_aois": 0, "active_aois": 0}
        
        active_aois = [data for data in self.aoi_data.values() if data.fixation_duration > 0]
        guidance_issued_count = sum(1 for data in self.aoi_data.values() if data.guidance_issued)
        
        return {
            "total_aois": len(self.aoi_data),
            "active_aois": len(active_aois),
            "guidance_issued_count": guidance_issued_count,
            "is_frozen": self.is_frozen,
            "current_image": self.current_image,
            "top_aois": sorted(
                [{"index": data.aoi_index, "duration": data.fixation_duration, "count": data.fixation_count}
                 for data in active_aois],
                key=lambda x: x["duration"],
                reverse=True
            )[:5]
        }
    
    def reset_guidance_flags(self):
        """Reset guidance issued flags for testing"""
        for data in self.aoi_data.values():
            data.guidance_issued = False
        self._save_aoi_data()
        logger.info("🔄 Reset all guidance flags for testing")
    
    def reset_all_aoi_data(self):
        """Reset all AOI data for fresh testing"""
        for data in self.aoi_data.values():
            data.fixation_duration = 0
            data.fixation_count = 0
            data.revisits = 0
            data.guidance_issued = False
            data.last_fixation_time = None
        self._save_aoi_data()
        logger.info("🔄 Reset ALL AOI data for fresh testing")

# Global instance
_aoi_service: Optional[AOIService] = None

def get_aoi_service() -> AOIService:
    """Get the global AOI service instance"""
    global _aoi_service
    if _aoi_service is None:
        _aoi_service = AOIService()
    return _aoi_service
