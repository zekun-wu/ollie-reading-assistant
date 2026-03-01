"""
HMM-based Eye Tracking Assistance Service
Replaces rule-based 4-second threshold with HMM cognitive state detection
"""
import sys
import os
import time
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

# Add the backend directory to Python path for model imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

try:
    from model.realtime_hmm_pipeline import RealtimeGazeProcessor
except ImportError as e:
    print(f"❌ Failed to import RealtimeGazeProcessor: {e}")
    RealtimeGazeProcessor = None

logger = logging.getLogger(__name__)

class HMMAssistanceService:
    """
    HMM-based assistance service that replaces 4-second threshold detection
    with cognitive state prediction using gaze metrics.
    """
    
    def __init__(self):
        self.processors = {}  # image_filename -> RealtimeGazeProcessor
        self.last_assistance_time = {}  # Track last assistance per image
        self.assistance_cooldown = 3.0  # 3 seconds cooldown
        self.is_frozen = {}  # Track frozen state per image
        self.freeze_timestamp = {}  # Track when freezing started
        self.unfreeze_timestamp = {}  # Track when unfreezing happened
        self.sample_counters = {}  # NEW: Track samples processed per image
        
        # HMM Assistance Service initialized
    
    def initialize_processor(self, image_filename: str, activity: str) -> bool:
        """Initialize HMM processor for specific image"""
        try:
            if RealtimeGazeProcessor is None:
                logger.error("❌ RealtimeGazeProcessor not available")
                return False
                
            # Construct labels path
            image_name = image_filename.split('.')[0]  # Remove extension
            labels_path = f"../segmented_pictures/{activity}/{image_name}_labels.json"
            
            # Check if labels file exists
            if not os.path.exists(labels_path):
                logger.error(f"❌ Labels file not found: {labels_path}")
                return False
            
            # Create processor
            processor = RealtimeGazeProcessor(
                labels_path=labels_path,
                image_filename=image_filename,
                activity=activity,
                window_ms=500.0,
                warm_start_segments=10,  # 5 seconds warm start
                maxdist=35,
                mindur=50
            )
            
            self.processors[image_filename] = processor
            self.is_frozen[image_filename] = False  # Initialize as not frozen
            logger.info(f"✅ HMM processor initialized for {image_filename} ({activity})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize HMM processor: {e}")
            return False
    
    def freeze_processing(self, image_filename: str):
        """Freeze HMM processing for specific image (when assistance starts)"""
        if image_filename in self.is_frozen:
            self.is_frozen[image_filename] = True
            self.freeze_timestamp[image_filename] = time.time()
            logger.info(f"🧊 HMM processing FROZEN for {image_filename} - assistance active")
        
        # Mark assistance as active for logging
        if image_filename in self.processors:
            self.processors[image_filename]._assistance_active = True
    
    def unfreeze_processing(self, image_filename: str):
        """Unfreeze HMM processing for specific image (when assistance ends)"""
        if image_filename in self.is_frozen:
            self.is_frozen[image_filename] = False
            self.unfreeze_timestamp[image_filename] = time.time()
            # HMM processing unfrozen
        
        # Mark assistance as no longer active for logging
        if image_filename in self.processors:
            self.processors[image_filename]._assistance_active = False
    
    def disable_processing(self, image_filename: str):
        """Disable HMM processing for specific image (when assistance is stopped)"""
        if not hasattr(self, 'disabled_processors'):
            self.disabled_processors = set()
        
        self.disabled_processors.add(image_filename)
            # HMM processing disabled
        
        # Mark assistance as stopped for logging
        if image_filename in self.processors:
            self.processors[image_filename]._assistance_stopped = True
            self.processors[image_filename]._assistance_active = False

    def enable_processing(self, image_filename: str):
        """Re-enable HMM processing for specific image"""
        if hasattr(self, 'disabled_processors') and image_filename in self.disabled_processors:
            self.disabled_processors.remove(image_filename)
            # HMM processing re-enabled
    
    def is_initialized(self, image_filename: str) -> bool:
        """Check if HMM processor has completed warm-start initialization"""
        if image_filename not in self.processors:
            return False
        
        processor = self.processors[image_filename]
        return processor.initialization_complete
    
    def process_gaze_sample(self, image_filename: str, timestamp: float, 
                           x_norm: float, y_norm: float, validity: int) -> Optional[Dict]:
        """Process gaze sample and return assistance trigger if needed"""
        
        # Track sample count
        if image_filename not in self.sample_counters:
            self.sample_counters[image_filename] = 0
        self.sample_counters[image_filename] += 1
        
        # Check if processing is frozen for this image
        if image_filename in self.is_frozen and self.is_frozen[image_filename]:
            return None
        
        # NEW: Check if processing is disabled (assistance stopped by user)
        if hasattr(self, 'disabled_processors') and image_filename in self.disabled_processors:
            return None
            
        if image_filename not in self.processors:
            return None
        
        # Remove sample counter logging - not needed for assistance timing
            
        processor = self.processors[image_filename]
        
        # Add sample to HMM pipeline
        prediction = processor.add_sample(timestamp, x_norm, y_norm, validity)
        
        if prediction is None:
            return None
        
        # Extract prediction data
        raw_metrics = prediction.get('raw_metrics', {})
        predicted_state = prediction.get('state', -1)
        state_probs = prediction.get('state_probs', [0, 0])
        dominant_aoi = raw_metrics.get('dominant_aoi', 0)
        focused_state = prediction.get('focused_state', None)
        
        # Check if HMM predicts the dynamically determined focused state
        if focused_state is None:
            # Batch EM not yet complete, skip
            return None
            
        if predicted_state == focused_state:
            # Only trigger on non-background AOIs (index > 0)
            if dominant_aoi is None or dominant_aoi <= 0:
                return None
            
            # Cooldown logic moved to state manager
            
            logger.info(f"🎯 ASSISTANCE TRIGGERED! AOI={dominant_aoi}, Seg={prediction.get('segment_index', 0)}, "
                       f"Confidence={state_probs[predicted_state]:.3f}")
            
            return {
                'triggered': True,
                'aoi_index': dominant_aoi,
                'prediction': prediction,
                'method': 'hmm_based'
            }
        
        return None
    
    def process_segment(self, image_filename: str, segment_buffer: List[Dict]) -> Optional[Dict]:
        """
        Process entire 500ms segment of gaze data at once.
        
        Args:
            image_filename: Image being viewed
            segment_buffer: List of gaze samples for this 500ms segment
                Each sample: {'timestamp', 'x', 'y', 'validity'}
        
        Returns:
            Trigger dictionary if assistance should be triggered, None otherwise
        """
        # Check if processing is frozen
        if image_filename in self.is_frozen and self.is_frozen[image_filename]:
            return None
        
        # Check if processing is disabled
        if hasattr(self, 'disabled_processors') and image_filename in self.disabled_processors:
            return None
        
        if image_filename not in self.processors:
            return None
        
        processor = self.processors[image_filename]
        
        # NEW: Block assistance during warm-start phase
        if not processor.initialization_complete:
            # Still in warm-start, don't trigger assistance
            return None
        
        # Process the complete segment directly (bypass add_sample loop)
        prediction = processor.process_complete_segment(segment_buffer)
        
        if prediction is None:
            logger.warning(f"⚠️ No prediction returned from segment processing")
            return None
        
        # Extract prediction data
        raw_metrics = prediction.get('raw_metrics', {})
        predicted_state = prediction.get('state', -1)
        state_probs = prediction.get('state_probs', [0, 0])
        dominant_aoi = raw_metrics.get('dominant_aoi', 0)
        focused_state = prediction.get('focused_state', None)
        segment_index = prediction.get('segment_index', 0)
        
        # NEW: Extract hybrid decision
        is_focused = prediction.get('is_focused', False)
        decision_method = prediction.get('decision_method', 'unknown')
        
        # Debug: Log every 5th segment to track hybrid decision
        if segment_index % 5 == 0:
            logger.info(f"📊 HMM Seg {segment_index}: AOI={dominant_aoi}, "
                       f"is_focused={is_focused}, method={decision_method}")
        
        if focused_state is None:
            return None
        
        # Always return prediction data, not just when assistance is triggered
        segment_end_time = prediction.get('segment_end_time')
        result = {
            'triggered': False,
            'state': predicted_state,
            'raw_metrics': raw_metrics,
            'focused_state': focused_state,
            'segment_end_time': segment_end_time,
            'prediction': prediction,
            'aoi_index': dominant_aoi if dominant_aoi and dominant_aoi > 0 else None,
            'is_focused': is_focused,  # NEW: Hybrid decision
            'decision_method': decision_method  # NEW: Decision method
        }
        
        # Check if assistance should be triggered using hybrid decision
        if is_focused:
            if dominant_aoi is None or dominant_aoi <= 0:
                return result  # Return prediction but no assistance
            
            logger.info(f"🎯 ASSISTANCE TRIGGERED! AOI={dominant_aoi}, Seg={segment_index}, "
                       f"method={decision_method}")
            
            result['triggered'] = True
            result['aoi_index'] = dominant_aoi
            result['method'] = 'hmm_hybrid'
        
        return result  # Always return result, not None
    
    def get_status(self, image_filename: str) -> Dict[str, Any]:
        """Get HMM status for specific image"""
        if image_filename not in self.processors:
            return {'error': 'Processor not initialized'}
        
        processor = self.processors[image_filename]
        status = processor.get_status()
        
        return {
            'initialization_complete': status['initialization_complete'],
            'segment_index': status['segment_index'],
            'predictions_made': status['predictions_made'],
            'is_frozen': self.is_frozen.get(image_filename, False),
            'last_assistance_time': self.last_assistance_time.get(image_filename, None)
        }
    
    def cleanup(self, image_filename: str):
        """Clean up processor for specific image"""
        if image_filename in self.processors:
            del self.processors[image_filename]
        if image_filename in self.is_frozen:
            del self.is_frozen[image_filename]
        if image_filename in self.last_assistance_time:
            del self.last_assistance_time[image_filename]
        if image_filename in self.freeze_timestamp:
            del self.freeze_timestamp[image_filename]
        if image_filename in self.unfreeze_timestamp:
            del self.unfreeze_timestamp[image_filename]
        
        logger.info(f"🧹 Cleaned up HMM processor for {image_filename}")

# Global instance
_hmm_service: Optional[HMMAssistanceService] = None

def get_hmm_assistance_service() -> HMMAssistanceService:
    """Get the global HMM assistance service instance"""
    global _hmm_service
    if _hmm_service is None:
        _hmm_service = HMMAssistanceService()
    return _hmm_service
