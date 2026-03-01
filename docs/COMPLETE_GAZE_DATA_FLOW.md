# 🔍 Complete Gaze Data Flow - Every Path Explained

## The Full Picture: From Eye-Tracker Hardware to All Destinations

---

## 🎯 Source: Tobii Eye-Tracker Hardware

```
┌─────────────────────────────────────────┐
│  TOBII EYE-TRACKER HARDWARE             │
│  - Infrared cameras                     │
│  - Samples at 60 Hz                     │
│  - Generates: {x, y, validity, time}    │
└─────────────────────────────────────────┘
```

---

## 📡 Step 1: Hardware → Backend Service

**Where:** `backend/src/services/eye_tracking_service.py`

```python
def _gaze_data_callback(self, gaze_data):
    """Called by Tobii SDK every ~16ms with new gaze data"""
    
    # Extract gaze from Tobii GazeData object
    left_eye_point = gaze_data.left_eye.gaze_point.position_on_display_area
    right_eye_point = gaze_data.right_eye.gaze_point.position_on_display_area
    
    # Average both eyes (or use best eye)
    x = (left_eye_point[0] + right_eye_point[0]) / 2
    y = (left_eye_point[1] + right_eye_point[1]) / 2
    
    # Create GazePoint object
    gaze_point = GazePoint(
        timestamp=time.time(),
        x=x,
        y=y,
        validity='valid'
    )
    
    # Store in SERVICE BUFFER (max 1000 points)
    self.gaze_buffer.append(gaze_point)
    if len(self.gaze_buffer) > self.max_buffer_size:
        self.gaze_buffer.pop(0)  # Remove oldest
```

**Result:** `EyeTrackingService.gaze_buffer` contains latest 1000 gaze points

---

## 🌳 Step 2: From Service Buffer → 3 Different Destinations

The gaze data in `EyeTrackingService.gaze_buffer` is now sent to **THREE separate systems**:

```
                     EyeTrackingService.gaze_buffer
                              [1000 points]
                                   ↓
        ┌──────────────────────────┼──────────────────────────┐
        ↓                          ↓                          ↓
   PATH 1:                    PATH 2:                    PATH 3:
   Frontend                   Fixation                   Session Buffer
   (Visualization)            Processor                  (NEW - for gaze.json)
```

---

## PATH 1: Frontend Visualization (Eye-Assistance Mode Only)

**Route:** `EyeTrackingService` → REST API → Frontend → Screen

### Backend API
```python
# backend/src/api/eye_tracking_routes.py

@router.get("/gaze-data")
async def get_gaze_data(count: int = 10):
    """Frontend polls this endpoint every 25ms"""
    service = get_eye_tracking_service()
    
    # Get latest N points from service buffer
    recent_points = service.get_latest_gaze_data(count)
    
    return {
        "success": True,
        "gaze_data": [
            {
                "timestamp": point.timestamp,
                "x": point.x,
                "y": point.y,
                "validity": point.validity
            }
            for point in recent_points
        ]
    }
```

### Frontend Polling
```javascript
// frontend/src/hooks/useEyeTracking.js

const startGazePolling = () => {
    gazePollingRef.current = setInterval(async () => {
        // Poll every 25ms (40 Hz)
        const response = await fetch('http://localhost:8001/api/eye-tracking/gaze-data?count=5');
        const result = await response.json();
        
        if (result.success && result.gaze_data.length > 0) {
            const latestGaze = result.gaze_data[result.gaze_data.length - 1];
            
            // Update state for visualization
            setCurrentGaze({
                x: latestGaze.x,
                y: latestGaze.y,
                timestamp: latestGaze.timestamp
            });
            
            // Add to history
            setGazeHistory(prev => [...prev, latestGaze].slice(-100));
        }
    }, 25);
};
```

### Frontend Display
```javascript
// frontend/src/components/PictureBookReader.js

// Uses eyeTracking.currentGaze to render cursor on screen
<div className="gaze-cursor" style={{
    left: `${currentGaze.x * 100}%`,
    top: `${currentGaze.y * 100}%`
}} />
```

**Purpose:** Real-time gaze cursor visualization  
**Frequency:** 40 Hz (every 25ms)  
**Storage:** Frontend memory only (last 100 points)  
**NOT saved to files**

---

## PATH 2: Fixation Processor (Eye-Assistance Mode Only)

**Route:** `EyeTrackingService` → FixationProcessor → AOI Detection → LLM Trigger

### Fixation Detection
```python
# backend/src/services/fixation_processor.py

async def _processing_loop(self):
    """Runs every 100ms"""
    while self.is_running:
        await asyncio.sleep(0.1)
        
        # Get current gaze from service
        current_gaze = self._eye_tracking_service.get_current_gaze_position()
        
        if current_gaze:
            await self._process_gaze_point(
                current_gaze['x'],
                current_gaze['y'],
                time.time()
            )

async def _process_gaze_point(self, x, y, timestamp):
    """Detect if this is part of a fixation"""
    
    # Check if close to previous points (spatial clustering)
    if is_near_previous_points(x, y):
        self.current_gaze_points.append((x, y, timestamp))
        
        # Check if fixation duration exceeds threshold
        if duration > 300ms:  # Fixation detected!
            # Trigger callback
            if self.on_fixation_end:
                await self.on_fixation_end(fixation_data)
```

### AOI Checking
```python
# backend/src/services/aoi_service.py

async def check_fixation_on_aoi(self, x, y):
    """Check if fixation is on an AOI"""
    
    for aoi in self.loaded_aois:
        if is_point_in_bbox(x, y, aoi.bbox):
            # AOI fixation detected!
            return aoi
    
    return None
```

### LLM Guidance Trigger
```python
# backend/src/core/state_manager.py (existing eye-assistance system)

async def _on_fixation_end(self, fixation_data):
    """Called when fixation detected"""
    
    # Check if on AOI
    aoi = await self._aoi_service.check_fixation_on_aoi(fixation_data.x, fixation_data.y)
    
    if aoi:
        # Trigger LLM curiosity guidance
        await self.request_guidance(
            image_filename,
            'curiosity',
            gaze_data={'aoi_index': aoi.index}
        )
```

**Purpose:** Automatic LLM guidance based on where child looks  
**Frequency:** Checks every 100ms  
**Storage:** None (real-time only)  
**Active only in:** Eye-assistance mode

---

## PATH 3: Session Buffer → gaze.json (NEW - ALL Modes)

**Route:** `EyeTrackingService` → StateManager Background Loop → Session Buffer → gaze.json

### Background Polling
```python
# backend/src/core/state_manager.py

async def _gaze_polling_loop(self):
    """
    Runs continuously at 250 Hz - matches hardware rate
    Collects gaze for ALL conditions (baseline, assistance, eye_assistance)
    """
    while self._gaze_polling_running:
        
        # 1. Get latest gaze directly from hardware buffer
        latest_gaze_point = self._eye_tracking_service.gaze_buffer[-1]
        # GazePoint object with: timestamp, x, y, validity
        
        # 2. Buffer for EVERY active session
        async with self._lock:
            for session_id, session in self.sessions.items():
                if session.is_actively_reading:  # Only if in fullscreen
                    
                    # Append to session's own buffer
                    session.gaze_buffer.append({
                        "t": latest_gaze_point.timestamp,
                        "x": latest_gaze_point.x if latest_gaze_point.x is not None else 0.0,
                        "y": latest_gaze_point.y if latest_gaze_point.y is not None else 0.0,
                        "v": 1 if latest_gaze_point.validity == 'valid' else 0
                    })
        
        # 3. Sleep 4ms before next poll
        await asyncio.sleep(0.004)  # 250 Hz
```

### When Session Ends
```python
# backend/src/core/state_manager.py

async def stop_tracking(self, image_filename):
    """Called when user exits fullscreen"""
    
    session = self.sessions[image_filename]
    
    # Save gaze data to file
    if self._gaze_data_service and session.gaze_buffer:
        result = self._gaze_data_service.save_gaze_session(
            samples=session.gaze_buffer,  # All collected points
            child_name=session.child_name,
            condition=session.condition,
            activity=session.activity,
            image_name=session.image_filename,
            start_time=session.start_time,
            end_time=time.time(),
            sequence_step=session.sequence_step
        )
        
        logger.info(f"💾 Saved {len(session.gaze_buffer)} points to gaze.json")
    
    # Clean up
    del self.sessions[image_filename]
```

### File Creation
```python
# backend/src/services/gaze_data_service.py

def save_gaze_session(self, samples, ...):
    """Save to gaze.json"""
    
    # Determine path
    if sequence_step:
        path = "backend/mixed/{step}/gaze.json"
    else:
        path = "backend/gaze_data/{condition}_gaze/{activity}/{child}_{img}_gaze.json"
    
    # Build JSON
    data = {
        "samples": samples,  # All the buffered points
        "statistics": {
            "total_samples": len(samples),
            "valid_samples": ...,
            "sampling_rate_hz": len(samples) / duration,
            "duration_ms": (end_time - start_time) * 1000
        }
    }
    
    # Write to disk
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
```

**Purpose:** Research data collection  
**Frequency:** Collects at 60 Hz, saves on session end  
**Storage:** Permanent files (gaze.json)  
**Active in:** ALL modes (baseline, assistance, eye_assistance)

---

## 📊 Summary: Where Does Each Gaze Point Go?

### Single Gaze Point from Hardware

```
Tobii Hardware generates gaze at t=1234567890.123, x=0.512, y=0.334
                                ↓
        EyeTrackingService._gaze_data_callback()
                                ↓
        EyeTrackingService.gaze_buffer (rolling buffer, max 1000)
                                ↓
        ┌───────────────────────┼───────────────────────┐
        ↓                       ↓                       ↓
    
PATH 1:                    PATH 2:                 PATH 3:
Frontend polls             FixationProcessor       StateManager polls
GET /gaze-data            polls service           get_latest_gaze_async()
    ↓                          ↓                       ↓
eyeTracking.gazeHistory   Fixation detection      session.gaze_buffer
    ↓                          ↓                       ↓
Cursor on screen          AOI checking            gaze.json file
(real-time viz)           (LLM triggers)          (permanent storage)
```

---

## 🎯 Key Differences

| Aspect | PATH 1: Frontend | PATH 2: Fixations | PATH 3: Session Buffer |
|--------|------------------|-------------------|------------------------|
| **Purpose** | Visualization | Real-time assistance | Data collection |
| **Frequency** | 40 Hz (25ms poll) | 10 Hz (100ms check) | 250 Hz (4ms poll) |
| **Storage** | Frontend memory (100 pts) | None (real-time) | Backend memory → file |
| **Saved?** | ❌ No | ❌ No | ✅ Yes (gaze.json) |
| **Active When** | Eye-assistance only | Eye-assistance only | **ALL modes** |
| **Data Size** | ~4 KB (100 pts) | N/A | ~400 KB per minute |

---

## 🔄 Complete Timeline Example

**User Action:** Reads image in Baseline mode for 10 seconds

```
0.000s: User enters fullscreen
        → Frontend: useTimeTracking starts
        → Frontend: WebSocket sends start_tracking
        → Backend: StateManager creates session
        → Backend: session.gaze_buffer = []

0.016s: Hardware sends gaze point #1
        → EyeTrackingService.gaze_buffer[0] = {x, y, t}
        → StateManager polls service
        → session.gaze_buffer[0] = {t, x, y, v}

0.032s: Hardware sends gaze point #2
        → EyeTrackingService.gaze_buffer[1] = {x, y, t}
        → StateManager polls service
        → session.gaze_buffer[1] = {t, x, y, v}

... (continues every 16ms)

10.000s: User exits fullscreen
         → Frontend: WebSocket sends stop_tracking
         → Backend: StateManager.stop_tracking()
         → Backend: GazeDataService.save_gaze_session()
         → Disk: backend/gaze_data/baseline_gaze/question/Alice_1_gaze.json
         → File contains: 2500 samples (10s × 250 Hz)
```

---

## ❓ Why Three Separate Paths?

**Different purposes require different handling:**

1. **PATH 1 (Frontend Viz):** 
   - Needs to be real-time smooth
   - Only cares about latest position
   - Doesn't need all points

2. **PATH 2 (Fixations):**
   - Needs to detect patterns
   - Only triggers on sustained looking
   - Doesn't need to save anything

3. **PATH 3 (Research Data):**
   - Needs EVERY point
   - Needs to be saved permanently
   - Works for all modes (not just eye-assistance)

**They're independent but use the same hardware source!**

---

## 🎯 The Answer to Your Question

**"Where exactly do we send gaze data?"**

**Answer:** We don't "send" it anywhere. Instead:

1. **Hardware pushes** gaze to `EyeTrackingService.gaze_buffer`
2. **Three consumers pull** from that buffer:
   - Frontend pulls via REST API (visualization)
   - FixationProcessor pulls via method call (AOI detection)
   - StateManager pulls via method call (data collection)

**Think of it like a water fountain:**
- Water source (hardware) continuously flows into fountain (service buffer)
- Three people (consumers) drink from the fountain whenever they want
- Each person uses the water differently (viz, fixations, files)

**Does this complete picture make sense now?** 💡
