import json
import math
import statistics
import logging
import numpy as np
import sys
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from .online_hmm import OnlineHMM

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger(__name__)


@dataclass
class GazeSample:
    """Represents a single gaze sample"""
    t: float  # timestamp in seconds
    x: float  # pixel x
    y: float  # pixel y
    v: int    # validity
    aoi: int  # assigned AOI indexs


@dataclass
class Fixation:
    """Represents a detected fixation"""
    start_time: float
    end_time: float
    duration: float  # in milliseconds
    x: float  # mean x position
    y: float  # mean y position
    aoi: int  # AOI index


class RealtimeGazeProcessor:
    """
    Real-time gaze processor that buffers samples, segments them into time windows,
    calculates metrics, and predicts cognitive states using an online HMM.
    """
    
    # Hybrid threshold constants for focus detection
    FOCUS_THRESHOLD_HIGH = 0.7  # >= 0.7 = definitely focused
    FOCUS_THRESHOLD_LOW = 0.3   # < 0.3 = definitely unfocused
    
    def __init__(
        self,
        labels_path: str,
        image_filename: str = None,
        activity: str = None,
        window_ms: float = 500.0,
        warm_start_segments: int = 10,
        maxdist: int = 35,
        mindur: int = 50
    ):
        """
        Initialize real-time gaze processor.
        
        Args:
            labels_path: Path to labels JSON file with AOI definitions
            image_filename: Name of the image file (for logging)
            activity: Activity type (for logging)
            window_ms: Segment window size in milliseconds
            warm_start_segments: Number of segments for HMM warm start initialization
            maxdist: Maximum dispersion in pixels for I-DT algorithm
            mindur: Minimum fixation duration in milliseconds
        """
        # Load AOI definitions
        with open(labels_path, 'r') as f:
            self.labels = json.load(f)
        
        self.image_filename = image_filename or "unknown.jpg"
        self.activity = activity or "storytelling"
        self.width = self.labels['width']
        self.height = self.labels['height']
        self.objects = self.labels['objects']
        
        # Processing parameters
        self.window_ms = window_ms
        self.warm_start_segments = warm_start_segments
        self.maxdist = maxdist
        self.mindur = mindur
        
        # State tracking
        self.start_time = None
        self.current_segment_start = None
        self.segment_index = 0
        self.samples_buffer = []  # All samples since start
        self.current_segment_samples = []  # Samples in current segment
        self.segment_metrics = []  # Accumulated metrics for warm start
        
        # HMM model (initialized after warm start)
        self.hmm = None
        self.initialization_complete = False
        self.predictions = []
        
        # NEW: Track which state represents focused behavior (determined after batch EM)
        self.focused_state = None
        self.unfocused_state = None
        
        # Initialize HMM state logger
        try:
            from services.hmm_state_logger import get_hmm_state_logger
            self.hmm_logger = get_hmm_state_logger()
            self.hmm_logger.start_session(self.image_filename)
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize HMM state logger: {e}")
            self.hmm_logger = None
    
    def add_sample(self, timestamp: float, x_norm: float, y_norm: float, validity: int) -> Optional[Dict]:
        """
        Process incoming gaze sample and return prediction if segment is complete.
        
        Args:
            timestamp: Sample timestamp in seconds
            x_norm: Normalized x coordinate (0-1)
            y_norm: Normalized y coordinate (0-1)
            validity: Sample validity (1=valid, 0=invalid)
            
        Returns:
            Dictionary with prediction results if segment completed, None otherwise
        """
        # Initialize start time on first sample
        if self.start_time is None:
            self.start_time = timestamp
            self.current_segment_start = timestamp
        
        # Validate gaze coordinates
        if x_norm is None or y_norm is None:
            logger.warning(f"⚠️ None gaze coordinates: x={x_norm}, y={y_norm}, validity={validity}")
            return None
        
        if not (0 <= x_norm <= 1) or not (0 <= y_norm <= 1):
            # Skip logging out-of-bounds coordinates to reduce noise
            return None
        
        # Convert normalized coordinates to pixels
        x_pixel = x_norm * self.width
        y_pixel = y_norm * self.height
        
        # Assign AOI
        aoi = self._assign_aoi(x_pixel, y_pixel)
        
        # Debug AOI assignment issues (only log when AOI is 0 and we have valid samples)
        if aoi == 0 and validity == 1 and self.initialization_complete:
            logger.debug(f"🔍 Background AOI: pixel=({x_pixel:.1f}, {y_pixel:.1f}), available_AOIs={len(self.objects)}")
        
        # Create sample object
        sample = GazeSample(
            t=timestamp,
            x=x_pixel,
            y=y_pixel,
            v=validity,
            aoi=aoi
        )
        
        # Add to buffers
        self.samples_buffer.append(sample)
        if validity == 1:  # Only valid samples for current segment
            self.current_segment_samples.append(sample)
        
        # Check if segment is complete
        elapsed_ms = (timestamp - self.current_segment_start) * 1000
        if elapsed_ms >= self.window_ms:
            return self._process_segment()
        
        return None
    
    def process_complete_segment(self, segment_samples: List[Dict]) -> Optional[Dict]:
        """
        Process a complete 500ms segment that was already collected.
        Bypasses the internal segment buffering in add_sample().
        
        Args:
            segment_samples: List of dicts with 'timestamp', 'x', 'y', 'validity'
        
        Returns:
            Prediction dict if successful, None otherwise
        """
        if not segment_samples:
            return None
        
        # Convert to GazeSample objects and assign AOIs
        gaze_samples = []
        for sample in segment_samples:
            # Convert normalized coordinates to pixels
            x_pixel = sample['x'] * self.width
            y_pixel = sample['y'] * self.height
            
            # Assign AOI
            aoi = self._assign_aoi(x_pixel, y_pixel)
            
            # Create GazeSample
            gs = GazeSample(
                t=sample['timestamp'],
                x=x_pixel,
                y=y_pixel,
                v=sample['validity'],
                aoi=aoi
            )
            
            if sample['validity'] == 1:  # Only valid samples
                gaze_samples.append(gs)
        
        if not gaze_samples:
            return None
        
        # Set segment boundaries
        self.current_segment_start = gaze_samples[0].t
        self.current_segment_samples = gaze_samples
        
        # Process the segment
        result = self._process_segment()
        
        return result
    
    def _assign_aoi(self, x: float, y: float) -> int:
        """Assign AOI index to a gaze point. Returns 0 (background) if no match."""
        # Check if AOI objects are loaded
        if len(self.objects) == 0:
            if not hasattr(self, '_aoi_warning_shown'):
                logger.error(f"❌ No AOI objects loaded! Check labels file.")
                self._aoi_warning_shown = True
            return 0
        
        for obj in self.objects:
            if self._point_in_bbox(x, y, obj['bbox']):
                return obj['index']
        return 0  # background
    
    def _point_in_bbox(self, x: float, y: float, bbox: List[int]) -> bool:
        """Check if point (x, y) is inside bounding box [x1, y1, x2, y2]"""
        x1, y1, x2, y2 = bbox
        return x1 <= x <= x2 and y1 <= y <= y2
    
    def _process_segment(self) -> Optional[Dict]:
        """
        Process current segment and return prediction.
        Called when 500ms window is complete.
        """
        if not self.current_segment_samples:
            # No valid samples in this segment
            self._reset_segment()
            return None
        
        # Calculate metrics for current segment
        metrics = self._calculate_metrics()
        
        # Add to warm start buffer if still initializing
        if not self.initialization_complete:
            self.segment_metrics.append(metrics)
            
            # Check if we have enough segments for warm start
            if len(self.segment_metrics) >= self.warm_start_segments:
                self._initialize_hmm()
                self.initialization_complete = True
                # HMM warm-start complete
            
            self._reset_segment()
            return None
        
        # Online prediction phase
        prediction = self._predict_with_hmm(metrics)
        self.predictions.append(prediction)
        
        self._reset_segment()
        return prediction
    
    def _calculate_metrics(self) -> Dict:
        """
        Calculate the three gaze metrics for current segment.
        
        Returns:
            Dictionary with rms_deviation, fixation_count, dwell_ratio_top_aoi, dominant_aoi
        """
        segment_start = self.current_segment_start
        segment_end = segment_start + (self.window_ms / 1000.0)
        
        # Get samples in current segment
        segment_samples = [s for s in self.current_segment_samples 
                          if segment_start <= s.t < segment_end]
        
        if not segment_samples:
            # Log why segment is empty (only after initialization)
            if self.initialization_complete:
                # Empty segment - no valid samples
                pass
            return {
                'rms_deviation': 0.0,
                'fixation_count': 0,
                'dwell_ratio_top_aoi': 0.0,
                'dominant_aoi': None
            }
        
        # 1. RMS deviation of consecutive gaze points
        rms_deviation = self._calculate_rms_deviation(segment_samples)
        
        # 2. Fixation count using I-DT algorithm
        fixations = self._detect_fixations_idt(segment_samples)
        fixation_count = len(fixations)
        
        # 3. Dwell ratio on most-looked AOI
        dwell_ratio = self._calculate_dwell_ratio(fixations)
        
        # 4. Track dominant AOI (only if there are fixations)
        dominant_aoi = None
        if fixations:
            aoi_dwell = {}
            for fix in fixations:
                aoi = fix.aoi
                aoi_dwell[aoi] = aoi_dwell.get(aoi, 0) + fix.duration
            if aoi_dwell:
                dominant_aoi = max(aoi_dwell.items(), key=lambda x: x[1])[0]
        
        
        return {
            'rms_deviation': rms_deviation,
            'fixation_count': fixation_count,
            'dwell_ratio_top_aoi': dwell_ratio,
            'dominant_aoi': dominant_aoi
        }
    
    def _calculate_rms_deviation(self, samples: List[GazeSample]) -> float:
        """Calculate RMS deviation from mean position (dispersion around centroid)."""
        if len(samples) < 2:
            return 0.0
        
        # Calculate mean position (centroid)
        mean_x = statistics.mean([s.x for s in samples])
        mean_y = statistics.mean([s.y for s in samples])
        
        # Calculate squared distances from mean
        squared_distances = []
        for sample in samples:
            dx = sample.x - mean_x
            dy = sample.y - mean_y
            squared_distance = dx**2 + dy**2
            squared_distances.append(squared_distance)
        
        # Calculate RMS
        if squared_distances:
            mean_squared_distance = statistics.mean(squared_distances)
            return math.sqrt(mean_squared_distance)
        
        return 0.0
    
    def _detect_fixations_idt(self, samples: List[GazeSample]) -> List[Fixation]:
        """
        Detect fixations using I-DT (dispersion-threshold) algorithm.
        Adapted from analyze_gaze_pygaze.py
        """
        if len(samples) < 2:
            return []
        
        fixations = []
        
        # Convert samples to format for I-DT algorithm
        gaze_data = [[s.t, s.x, s.y] for s in samples]
        
        # I-DT algorithm
        i = 0
        while i < len(gaze_data):
            # Start a potential fixation
            window_start = i
            window_end = i + 1
            
            # Expand window while dispersion is below threshold
            while window_end < len(gaze_data):
                # Get all points in current window
                window_points = gaze_data[window_start:window_end + 1]
                
                # Calculate dispersion (max distance between any two points)
                x_coords = [p[1] for p in window_points]
                y_coords = [p[2] for p in window_points]
                
                dispersion_x = max(x_coords) - min(x_coords)
                dispersion_y = max(y_coords) - min(y_coords)
                dispersion = math.sqrt(dispersion_x**2 + dispersion_y**2)
                
                # If dispersion exceeds threshold, stop expanding
                if dispersion > self.maxdist:
                    break
                
                window_end += 1
            
            # Check if the window duration meets minimum requirement
            if window_end > window_start:
                start_time = gaze_data[window_start][0]
                end_time = gaze_data[window_end - 1][0]
                duration = (end_time - start_time) * 1000  # Convert to ms
                
                if duration >= self.mindur:
                    # Calculate fixation centroid
                    window_samples = samples[window_start:window_end]
                    mean_x = statistics.mean([s.x for s in window_samples])
                    mean_y = statistics.mean([s.y for s in window_samples])
                    
                    # Assign AOI based on most common AOI in fixation
                    aois = [s.aoi for s in window_samples]
                    most_common_aoi = max(set(aois), key=aois.count)
                    
                    fixations.append(Fixation(
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        x=mean_x,
                        y=mean_y,
                        aoi=most_common_aoi
                    ))
            
            # Move to next potential fixation
            i = window_end if window_end > window_start else i + 1
        
        return fixations
    
    def _calculate_dwell_ratio(self, fixations: List[Fixation]) -> float:
        """
        Calculate dwell ratio on most-looked AOI with area normalization and scale-aware Laplace smoothing.
        
        Process:
        1. Calculate raw dwell time per AOI (sum of fixation durations)
        2. Normalize each AOI's dwell time by its area: normalized_dwell = raw_dwell / area
        3. Calculate ratio using normalized values: (max_normalized) / (sum_all_normalized)
        4. Apply scale-aware Laplace smoothing (epsilon calibrated from warm-start data)
        
        This accounts for AOI size - smaller AOIs with same dwell time get higher normalized values.
        """
        if not fixations:
            return 0.0
        
        # Calculate raw dwell time per AOI
        aoi_dwell = {}
        for fix in fixations:
            aoi = fix.aoi
            if aoi == 0:  # Skip background
                continue
            aoi_dwell[aoi] = aoi_dwell.get(aoi, 0) + fix.duration
        
        if not aoi_dwell:
            return 0.0
        
        # Normalize dwell time by AOI area
        normalized_dwell = {}
        for aoi, dwell_time in aoi_dwell.items():
            aoi_area = self._get_aoi_area(aoi)
            if aoi_area > 0:
                normalized_dwell[aoi] = dwell_time / aoi_area
            else:
                logger.warning(f"⚠️ AOI {aoi} has no area defined, skipping normalization")
        
        if not normalized_dwell:
            return 0.0
        
        max_normalized = max(normalized_dwell.values())
        total_normalized = sum(normalized_dwell.values())
        
        # Track total_normalized during warm-start to calibrate epsilon
        if not self.initialization_complete:
            if not hasattr(self, '_warmstart_totals'):
                self._warmstart_totals = []
            self._warmstart_totals.append(total_normalized)
        
        # Use scale-aware epsilon (calibrated during warm-start, or default)
        if hasattr(self, '_calibrated_epsilon') and self._calibrated_epsilon is not None:
            epsilon = self._calibrated_epsilon
        else:
            # Default fallback before calibration (very small to not dominate)
            epsilon = 1e-6
        
        # Apply scale-aware Laplace smoothing
        smoothed_ratio = (max_normalized + epsilon) / (total_normalized + 2 * epsilon)
        
        return smoothed_ratio
    
    def _calibrate_epsilon(self):
        """Calibrate epsilon from warm-start data. Call after warm-start completes."""
        if hasattr(self, '_warmstart_totals') and self._warmstart_totals:
            median_total = np.median(self._warmstart_totals)
            # Set epsilon to 1% of median total_normalized
            self._calibrated_epsilon = 0.01 * median_total
            logger.info(f"📏 Calibrated epsilon: {self._calibrated_epsilon:.8f} (median total: {median_total:.8f})")
        else:
            self._calibrated_epsilon = 1e-6
            logger.warning("⚠️ No warm-start data, using default epsilon: 1e-6")
    
    def _get_aoi_area(self, aoi_index: int) -> float:
        """
        Get area in pixels² for a given AOI index.
        
        Args:
            aoi_index: The AOI index to look up
            
        Returns:
            Area in pixels², or 0 if not found
        """
        for obj in self.objects:
            if obj['index'] == aoi_index:
                return obj.get('area', 0)
        return 0
    
    def _initialize_hmm(self):
        """Initialize HMM with warm start using accumulated segments."""
        # Create HMM model with feature names for transformations
        # Using only dwell ratio on top AOI as the single feature
        feature_names = ['dwell_ratio_top_aoi']
        self.hmm = OnlineHMM(
            n_states=2,
            n_features=1,  # Only 1 feature now
            n_components=2,
            learning_rate_emission=0.1,
            learning_rate_transition=0.05,
            learning_rate_mixture=0.05,
            feature_names=feature_names
        )
        
        # Run warm start initialization
        self.hmm.warm_start_initialization(
            self.segment_metrics,
            warm_start_segments=len(self.segment_metrics),
            em_iterations=10
        )
        
        # Calibrate epsilon for scale-aware Laplace smoothing
        self._calibrate_epsilon()
        
        # NEW: Analyze which state is "focused"
        try:
            self._analyze_learned_states()
        except Exception as e:
            logger.error(f"❌ HMM state analysis failed: {e}")
            # Set default states if analysis fails
            self.focused_state = 0
            self.unfocused_state = 1
            logger.warning("⚠️ Using default states: 0=focused, 1=unfocused")
        
        # Log all warm-start segments retroactively
        if self.hmm_logger:
            try:
                for idx, metrics in enumerate(self.segment_metrics):
                    # Get state prediction for this segment using batch EM results
                    # Only using dwell ratio on top AOI
                    features = np.array([
                        metrics['dwell_ratio_top_aoi']
                    ])
                    normalized_features = self.hmm.normalizer.normalize(features)
                    
                    # Use forward algorithm to get state probabilities
                    alpha_t = self.hmm._forward_step(normalized_features)
                    predicted_state = int(np.argmax(alpha_t))
                    confidence = float(alpha_t[predicted_state])
                    
                    self.hmm_logger.log_segment(
                        image_filename=self.image_filename,
                        segment_index=idx,
                        rms_deviation=metrics['rms_deviation'],
                        fixation_count=metrics['fixation_count'],
                        dwell_ratio=metrics['dwell_ratio_top_aoi'],
                        predicted_state=predicted_state,
                        confidence=confidence,
                        dominant_aoi=metrics.get('dominant_aoi'),
                        is_warmstart=True,
                        assistance_active=False,
                        assistance_stopped=False
                    )
                logger.info(f"📊 Logged {len(self.segment_metrics)} warm-start segments retroactively")
            except Exception as e:
                logger.warning(f"⚠️ Failed to log warm-start segments: {e}")
    
    def _predict_with_hmm(self, metrics: Dict) -> Dict:
        """
        Predict cognitive state using hybrid threshold + HMM approach.
        
        Args:
            metrics: Dictionary with rms_deviation, fixation_count, dwell_ratio_top_aoi
            
        Returns:
            Dictionary with prediction results including hybrid focus decision
        """
        # Extract features (only dwell ratio on top AOI)
        features = np.array([
            metrics['dwell_ratio_top_aoi']
        ])
        
        # Normalize features using HMM's normalizer
        normalized_features = self.hmm.normalizer.normalize(features)
        
        # Get prediction from HMM (still needed for parameter updates)
        prediction = self.hmm.fit_online_step(normalized_features)
        predicted_state = prediction['state']
        state_probs = prediction['state_probs']
        
        # NEW: Hybrid decision logic using raw dwell ratio
        raw_dwell_ratio = metrics['dwell_ratio_top_aoi']
        
        # Apply three-tier threshold logic
        if raw_dwell_ratio >= self.FOCUS_THRESHOLD_HIGH:
            # High dwell ratio = definitely focused
            is_focused = True
            decision_method = "threshold_high"
        elif raw_dwell_ratio < self.FOCUS_THRESHOLD_LOW:
            # Low dwell ratio = definitely unfocused
            is_focused = False
            decision_method = "threshold_low"
        else:
            # Medium dwell ratio (0.3-0.7) = use HMM decision
            if predicted_state == self.focused_state:
                is_focused = True
                decision_method = "threshold_medium_hmm_confirm"
            else:
                is_focused = False
                decision_method = "threshold_medium_hmm_reject"
        
        # Log decision every 5th segment for monitoring
        if self.segment_index % 5 == 0:
            logger.info(
                f"📊 Seg {self.segment_index}: dwell={raw_dwell_ratio:.3f}, "
                f"HMM_state={predicted_state}, focused_state={self.focused_state}, "
                f"is_focused={is_focused}, method={decision_method}"
            )
        
        # Log to HMM state logger (assistance state will be set by state manager)
        if self.hmm_logger:
            try:
                is_warmstart = not self.initialization_complete
                self.hmm_logger.log_segment(
                    image_filename=self.image_filename,
                    segment_index=self.segment_index,
                    rms_deviation=metrics['rms_deviation'],
                    fixation_count=metrics['fixation_count'],
                    dwell_ratio=raw_dwell_ratio,
                    predicted_state=predicted_state,
                    confidence=state_probs[predicted_state],
                    dominant_aoi=metrics.get('dominant_aoi'),
                    is_warmstart=is_warmstart,
                    assistance_active=getattr(self, '_assistance_active', False),
                    assistance_stopped=getattr(self, '_assistance_stopped', False)
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to log HMM segment: {e}")
        
        # Add segment information with hybrid decision
        prediction.update({
            'segment_index': self.segment_index,
            'segment_start_time': self.current_segment_start,
            'segment_end_time': self.current_segment_start + (self.window_ms / 1000.0),
            'raw_metrics': metrics,
            'focused_state': self.focused_state,
            'unfocused_state': self.unfocused_state,
            'is_focused': is_focused,  # NEW: Hybrid decision
            'decision_method': decision_method  # NEW: How decision was made
        })
        
        return prediction
    
    def _reset_segment(self):
        """Reset for next segment."""
        self.segment_index += 1
        self.current_segment_start += (self.window_ms / 1000.0)
        self.current_segment_samples = []
    
    def get_current_state(self) -> Optional[Dict]:
        """Get the most recent state prediction."""
        if self.predictions:
            return self.predictions[-1]
        return None
    
    def get_all_predictions(self) -> List[Dict]:
        """Get all predictions made so far."""
        return self.predictions
    
    def get_status(self) -> Dict:
        """Get current processor status."""
        return {
            'initialization_complete': self.initialization_complete,
            'segment_index': self.segment_index,
            'total_samples': len(self.samples_buffer),
            'warm_start_segments': len(self.segment_metrics),
            'predictions_made': len(self.predictions)
        }
    
    def _analyze_learned_states(self):
        """
        Analyze warm-start segments to determine which state is focused.
        Uses HMM state assignments and per-state average dwell ratios.
        State with higher average dwell ratio = FOCUSED (concentrated attention)
        """
        if not self.hmm or not self.segment_metrics:
            logger.error("❌ Cannot analyze states: HMM or metrics missing")
            self.focused_state = 0
            self.unfocused_state = 1
            return self.focused_state, self.unfocused_state
        
        # Get state assignments for each warm-start segment
        state_assignments = []
        for metrics in self.segment_metrics:
            features = np.array([
                metrics['dwell_ratio_top_aoi']
            ])
            normalized = self.hmm.normalizer.normalize(features)
            
            # Get most likely state for this segment
            prediction = self.hmm.fit_online_step(normalized)
            state = prediction['state']
            state_assignments.append(state)
        
        # Calculate average dwell ratio per state
        state_0_dwell_ratios = []
        state_1_dwell_ratios = []
        
        for i, state in enumerate(state_assignments):
            dwell_ratio = self.segment_metrics[i]['dwell_ratio_top_aoi']
            if state == 0:
                state_0_dwell_ratios.append(dwell_ratio)
            else:
                state_1_dwell_ratios.append(dwell_ratio)
        
        # State with higher average dwell ratio = FOCUSED (concentrated attention)
        avg_state_0 = np.mean(state_0_dwell_ratios) if state_0_dwell_ratios else 0
        avg_state_1 = np.mean(state_1_dwell_ratios) if state_1_dwell_ratios else 0
        
        if avg_state_0 > avg_state_1:
            self.focused_state = 0
            self.unfocused_state = 1
        else:
            self.focused_state = 1
            self.unfocused_state = 0
        
        logger.info(f"🎯 Focused state determined: {self.focused_state}")
        logger.info(f"   State 0 avg dwell ratio: {avg_state_0:.3f} ({len(state_0_dwell_ratios)} segments)")
        logger.info(f"   State 1 avg dwell ratio: {avg_state_1:.3f} ({len(state_1_dwell_ratios)} segments)")
        
        return self.focused_state, self.unfocused_state

