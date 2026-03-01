"""
HMM State Logger - Logs HMM predictions and features to JSON
Tracks all segments from warm-start (batch EM) through online prediction (online EM)
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class HMMStateLogger:
    """
    Logs HMM state predictions and features to JSON file.
    Tracks all segments from warm-start through online prediction.
    """
    
    def __init__(self):
        self.sessions: Dict[str, List[Dict]] = {}  # image_filename -> list of segment records
        
    def start_session(self, image_filename: str):
        """Start tracking HMM states for an image"""
        # Only create new session if one doesn't exist
        if image_filename not in self.sessions:
            self.sessions[image_filename] = []
            logger.info(f"📊 Started HMM state logging for {image_filename}")
        else:
            logger.info(f"📊 Continuing HMM state logging for {image_filename} ({len(self.sessions[image_filename])} segments so far)")
    
    def log_segment(self, 
                   image_filename: str,
                   segment_index: int,
                   rms_deviation: float,
                   fixation_count: int,
                   dwell_ratio: float,
                   predicted_state: int,
                   confidence: float,
                   dominant_aoi: Optional[int],
                   is_warmstart: bool,
                   assistance_active: bool = False,
                   assistance_stopped: bool = False):
        """
        Log a single segment's features and prediction.
        
        Args:
            image_filename: Image being viewed
            segment_index: Segment number (0-indexed)
            rms_deviation: RMS deviation feature
            fixation_count: Number of fixations
            dwell_ratio: Dwell ratio on top AOI
            predicted_state: HMM predicted state (0 or 1)
            confidence: Prediction confidence
            dominant_aoi: Most-looked AOI index
            is_warmstart: True if batch EM, False if online EM
            assistance_active: True if assistance is currently being given
            assistance_stopped: True if assistance was stopped (pressed 's')
        """
        if image_filename not in self.sessions:
            self.start_session(image_filename)
        
        record = {
            "segment_index": segment_index,
            "rms_deviation": round(rms_deviation, 4),
            "fixation_count": fixation_count,
            "dwell_ratio": round(dwell_ratio, 4),
            "predicted_state": predicted_state,
            "confidence": round(confidence, 4),
            "dominant_aoi": dominant_aoi,
            "inference_method": "batch_em" if is_warmstart else "online_em",
            "assistance_active": assistance_active,
            "assistance_stopped": assistance_stopped
        }
        
        self.sessions[image_filename].append(record)
    
    def save_session(self, 
                    image_filename: str,
                    sequence_step: Optional[int] = None,
                    focused_state: Optional[int] = None,
                    unfocused_state: Optional[int] = None) -> Dict[str, Any]:
        """
        Save HMM state log to JSON file.
        
        Args:
            image_filename: Image being viewed
            sequence_step: Sequence step number (for file path)
            focused_state: Which state was determined to be focused
            unfocused_state: Which state was determined to be unfocused
            
        Returns:
            Result dictionary with success status and file path
        """
        logger.info(f"🔍 Attempting to save HMM states for {image_filename}")
        logger.info(f"🔍 Available sessions: {list(self.sessions.keys())}")
        logger.info(f"🔍 Session data exists: {image_filename in self.sessions}")
        
        if image_filename not in self.sessions:
            return {"success": False, "error": "No session data"}
        
        records = self.sessions[image_filename]
        if not records:
            return {"success": False, "error": "No segments logged"}
        
        try:
            # Determine file path
            if sequence_step is not None:
                # Sequence mode: save to record/{user_number}/mixed/{step}/hmm_states.json
                from services.sequence_cache_service import get_sequence_cache_service
                cache_service = get_sequence_cache_service()
                step_dir = cache_service.get_sequence_step_dir(sequence_step)
                file_path = step_dir / "hmm_states.json"
            else:
                # Standalone mode: save to hmm_states/{image_name}.json
                base_dir = Path(__file__).parent.parent.parent / "hmm_states"
                base_dir.mkdir(parents=True, exist_ok=True)
                image_base = Path(image_filename).stem
                file_path = base_dir / f"{image_base}.json"
            
            # Prepare data
            data = {
                "image_filename": image_filename,
                "timestamp": datetime.now().isoformat(),
                "total_segments": len(records),
                "warmstart_segments": sum(1 for r in records if r["inference_method"] == "batch_em"),
                "online_segments": sum(1 for r in records if r["inference_method"] == "online_em"),
                "focused_state": focused_state,
                "unfocused_state": unfocused_state,
                "segments": records
            }
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"💾 Saved HMM states to {file_path} ({len(records)} segments)")
            
            return {
                "success": True,
                "file_path": str(file_path),
                "segments_logged": len(records)
            }
            
        except Exception as e:
            logger.error(f"❌ Error saving HMM states: {e}")
            return {"success": False, "error": str(e)}
    
    def clear_session(self, image_filename: str):
        """Clear session data for an image"""
        if image_filename in self.sessions:
            del self.sessions[image_filename]

# Singleton instance
_hmm_state_logger = None

def get_hmm_state_logger() -> HMMStateLogger:
    """Get singleton HMM state logger instance"""
    global _hmm_state_logger
    if _hmm_state_logger is None:
        _hmm_state_logger = HMMStateLogger()
    return _hmm_state_logger
