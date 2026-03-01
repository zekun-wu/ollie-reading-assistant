"""
Fixation Processor - Converts continuous gaze data into discrete fixation events
Uses the working API gaze data to detect real fixations
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

@dataclass
class FixationEvent:
    """A completed fixation event"""
    start_time: float
    end_time: float
    duration_ms: float
    x: float  # Average position
    y: float  # Average position
    gaze_points: int  # Number of gaze points in fixation

class FixationProcessor:
    """
    Processes continuous gaze data into discrete fixation events
    Uses spatial and temporal clustering to detect real fixations
    """
    
    def __init__(self):
        self.fixation_threshold_distance = 50  # 50 pixels on 1920x1200 screen
        self.fixation_threshold_duration = 100   # 100ms minimum
        self.current_fixation = None
        self.current_gaze_points = []
        self.last_gaze_time = None
        
        # Callbacks
        self.on_fixation_end: Optional[Callable] = None
        
        # Processing state
        self.is_running = False
        self._processing_task = None
        
    def set_fixation_callback(self, callback: Callable):
        """Set callback for when fixations end"""
        self.on_fixation_end = callback
    
    async def start_processing(self, eye_tracking_service, state_manager):
        """Start processing gaze data into fixations"""
        if self.is_running:
            return
            
        self.is_running = True
        self._eye_tracking_service = eye_tracking_service
        self._state_manager = state_manager
        
        # Start the processing loop
        self._processing_task = asyncio.create_task(self._processing_loop())
        logger.info("🔄 Started fixation processing")
    
    async def stop_processing(self):
        """Stop fixation processing"""
        self.is_running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        # Reset state
        self.current_fixation = None
        self.current_gaze_points = []
        
        logger.info("🛑 Stopped fixation processing")
    
    async def _processing_loop(self):
        """Main processing loop - runs every 100ms to detect fixations"""
        try:
            while self.is_running:
                await asyncio.sleep(0.1)  # 100ms processing interval
                
                current_gaze = self._eye_tracking_service.get_current_gaze_position()
                current_time = time.time()
                
                
                if current_gaze and current_gaze.get('x') is not None and current_gaze.get('y') is not None:
                    await self._process_gaze_point(
                        current_gaze['x'], 
                        current_gaze['y'], 
                        current_time
                    )
                    
        except asyncio.CancelledError:
            logger.info("🔄 Fixation processing loop cancelled")
        except Exception as e:
            logger.error(f"❌ Error in fixation processing loop: {e}")
    
    async def _process_gaze_point(self, x: float, y: float, timestamp: float):
        """Process a single gaze point"""
        self.last_gaze_time = timestamp
        
        if self.current_fixation is None:
            # Start new fixation
            self.current_fixation = {
                'start_time': timestamp,
                'x_sum': x,
                'y_sum': y,
                'point_count': 1,
                'start_x': x,
                'start_y': y
            }
            self.current_gaze_points = [(x, y, timestamp)]
            return
        
        # Check if this point continues the current fixation
        avg_x = self.current_fixation['x_sum'] / self.current_fixation['point_count']
        avg_y = self.current_fixation['y_sum'] / self.current_fixation['point_count']
        
        try:
            # Convert normalized coordinates to screen pixels for distance calculation
            screen_width = 1920
            screen_height = 1200
            pixel_distance = math.sqrt(
                ((x - avg_x) * screen_width) ** 2 + 
                ((y - avg_y) * screen_height) ** 2
            )
            
            
        except Exception as distance_error:
            logger.error(f"❌ FIXATION: Distance calculation error: {distance_error}")
            logger.error(f"   x={x}, y={y}, avg_x={avg_x}, avg_y={avg_y}")
            return
        
        if pixel_distance <= self.fixation_threshold_distance:
            # Continue current fixation
            self.current_fixation['x_sum'] += x
            self.current_fixation['y_sum'] += y
            self.current_fixation['point_count'] += 1
            self.current_gaze_points.append((x, y, timestamp))
            
            # Note: 4-second threshold removed - HMM handles assistance triggering
            
        else:
            # End current fixation and start new one
            await self._end_current_fixation(timestamp)
            
            # Start new fixation
            self.current_fixation = {
                'start_time': timestamp,
                'x_sum': x,
                'y_sum': y,
                'point_count': 1,
                'start_x': x,
                'start_y': y
            }
            self.current_gaze_points = [(x, y, timestamp)]
    
    async def _end_current_fixation(self, end_time: float):
        """End the current fixation and trigger callback if long enough"""
        if self.current_fixation is None:
            return
            
        duration_ms = (end_time - self.current_fixation['start_time']) * 1000
        
        if duration_ms >= self.fixation_threshold_duration:
            # Calculate average position
            avg_x = self.current_fixation['x_sum'] / self.current_fixation['point_count']
            avg_y = self.current_fixation['y_sum'] / self.current_fixation['point_count']
            
            fixation_event = FixationEvent(
                start_time=self.current_fixation['start_time'],
                end_time=end_time,
                duration_ms=duration_ms,
                x=avg_x,
                y=avg_y,
                gaze_points=self.current_fixation['point_count']
            )
            
            # Trigger callback
            if self.on_fixation_end:
                try:
                    await self.on_fixation_end(fixation_event)
                except Exception as e:
                    logger.error(f"❌ Error in fixation callback: {e}")
        
        self.current_fixation = None
        self.current_gaze_points = []

# Global instance
_fixation_processor: Optional[FixationProcessor] = None

def get_fixation_processor() -> FixationProcessor:
    """Get the global fixation processor instance"""
    global _fixation_processor
    if _fixation_processor is None:
        _fixation_processor = FixationProcessor()
    return _fixation_processor
