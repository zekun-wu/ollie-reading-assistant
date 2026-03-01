# Sequence Builder - Comprehensive Impact Analysis

## Executive Summary

Implementing a flexible sequence builder that allows **mixed conditions** (switching between base, assistance, and eye_assistance) within a single session will require **significant architectural changes** but is **feasible** with the current codebase.

**Risk Level: MEDIUM-HIGH**
- Time tracking: ✅ Ready (no changes needed)
- Book components: ⚠️ Need modifications  
- State management: ⚠️ Needs refactoring
- Eye-tracking: ❌ Major impact - connection management
- Manual assistance: ⚠️ Session cleanup needed
- WebSocket: ⚠️ Needs to persist across conditions

---

## 1. Current Architecture Analysis

### 1.1 App Flow (App_Official.js)
```
Selection → Intro → Reading (ONE condition for entire session)
              ↓         ↓
        userConfig   Routes to ONE component:
        {             - BaselineBook (base)
          assistance,  - AssistanceBook (assistance)  
          eyeTracking, - PictureBookReader (eye_assistance)
          activity
        }
```

**Key Issue:** `userConfig` is **static** for entire session. Changing condition mid-session not supported.

### 1.2 Component Independence
Each book component currently:
- ✅ Manages its own image navigation (prev/next buttons)
- ✅ Has its own fullscreen logic
- ✅ Tracks time independently
- ❌ No concept of "locked to single image"
- ❌ No "onComplete" callback for external control

### 1.3 Resource Management

| Resource | Initialization | Lifecycle | Switching Impact |
|----------|---------------|-----------|------------------|
| **Eye Tracking** | Once on app mount | Stays connected | ⚠️ HIGH - Expensive to reconnect |
| **WebSocket** | Once per clientId | Stays open | ⚠️ MEDIUM - Should stay open |
| **Manual Assistance** | Per image session | Cleanup on unmount | ⚠️ MEDIUM - Needs explicit cleanup |
| **Time Tracking** | Per image/condition | Auto start/stop | ✅ LOW - Already works |
| **Gaze State** | Per image | Managed by backend | ⚠️ MEDIUM - Backend session switching |

---

## 2. Detailed Impact by Component

### 2.1 ⚠️ App_Official.js - MAJOR REFACTOR

**Current Problems:**
```javascript
// Problem 1: Static userConfig
const [userConfig, setUserConfig] = useState(null);
// Used to determine ONE condition for entire session

// Problem 2: Conditional hook initialization
const shouldUseEyeTracking = userConfig?.assistance && userConfig?.eyeTracking;
// Eye-tracking only initialized IF condition needs it

// Problem 3: Single image filename
const currentImageFilename = userConfig ? 
  `${currentStep === 'reading' ? '1' : 'test'}.${userConfig.activity === 'storytelling' ? 'png' : 'jpg'}` : 
  'test.jpg';
// Hardcoded to '1.jpg' or '1.png'
```

**Required Changes:**
1. **New state management:**
   ```javascript
   const [sequence, setSequence] = useState(null);  // Array of steps
   const [currentStepIndex, setCurrentStepIndex] = useState(0);
   ```

2. **Always initialize eye-tracking** (even if not initially needed):
   ```javascript
   // OLD: const shouldUseEyeTracking = userConfig?.assistance && userConfig?.eyeTracking;
   // NEW: Always initialize, connect only when needed
   const eyeTracking = useEyeTracking();
   const websocket = useWebSocket('ws://localhost:8001/ws', clientId);
   ```

3. **Dynamic image filename:**
   ```javascript
   const currentItem = sequence?.[currentStepIndex];
   const currentImageFilename = currentItem?.image || 'test.jpg';
   ```

**Impact Level: 🔴 HIGH** - Core app flow restructure

---

### 2.2 ⚠️ BaselineBook.js - MODERATE CHANGES

**Current State:**
- Manages own navigation: `currentImageIndex` state
- Lists all images for activity
- Previous/Next buttons

**Required Changes:**
```javascript
const BaselineBook = ({ 
  activity, 
  childName, 
  onBackToModeSelect,
  // NEW PROPS:
  lockedToSingleImage = false,  // Sequence mode flag
  imageFilename = null,          // Override specific image
  onComplete = null              // Callback when done
}) => {
  
  // Conditional navigation
  const currentImageFile = lockedToSingleImage && imageFilename 
    ? imageFilename 
    : availableImages[currentImageIndex];
  
  // Conditional button rendering
  {!lockedToSingleImage && (
    <button onClick={goToPreviousImage}>← Previous</button>
  )}
  
  {lockedToSingleImage && onComplete && (
    <button onClick={onComplete}>Next Step →</button>
  )}
}
```

**Breaking Changes:**
- Need to hide prev/next buttons in sequence mode
- Time tracking already works (imageFilename changes)

**Impact Level: 🟡 MEDIUM** - Conditional rendering logic

---

### 2.3 ⚠️ AssistanceBook.js - MODERATE CHANGES + CLEANUP

**Current State:**
- Uses `useManualAssistance()` hook
- Has automatic image switching logic
- Manual assistance session per image

**Required Changes:**
Same as BaselineBook PLUS:

```javascript
// NEW: Cleanup manual assistance when switching away
useEffect(() => {
  return () => {
    if (lockedToSingleImage && manualAssistance.isActive) {
      console.log('🧹 Cleaning up manual assistance session');
      manualAssistance.stopSession();
    }
  };
}, [lockedToSingleImage, manualAssistance]);
```

**Critical Issue:**
Manual assistance has **backend session state** (`session_key`). Must properly cleanup:
```javascript
// Backend: services/manual_assistance_service.py
self.sessions[session_key] = session  // Stored in memory
```

**Impact Level: 🟡 MEDIUM** - Cleanup logic + same as BaselineBook

---

### 2.4 ⚠️ PictureBookReader.js - MODERATE CHANGES + EYE-TRACKING

**Current State:**
- Most complex component
- Manages eye-tracking connection
- Has fullscreen enter/exit logic with eye-tracking start/stop
- WebSocket communication for gaze state

**Required Changes:**
Same as BaselineBook PLUS:

```javascript
// Problem: Currently connects eye-tracker on enterFullscreen
const enterFullscreen = async () => {
  // ...
  const connected = await eyeTracking.connect();
  const trackingStarted = await eyeTracking.startTracking();
  await eyeTracking.setImageContext(currentImageFile);
  gaze.startTracking(activity, currentImageFile);
};
```

**NEW BEHAVIOR NEEDED:**
```javascript
// Eye-tracking should STAY CONNECTED across sequence
// Only switch image context, not reconnect

useEffect(() => {
  if (isFullscreen && lockedToSingleImage) {
    // Switch image context only
    if (eyeTracking.isConnected && eyeTracking.isTracking) {
      eyeTracking.setImageContext(imageFilename);
      gaze.startTracking(activity, imageFilename);
    } else {
      // Initial connection (once)
      setupEyeTracking();
    }
  }
}, [imageFilename, isFullscreen]);
```

**Critical Issue:**
Eye-tracking connection is **expensive** (~2-3 seconds). Should NOT disconnect/reconnect between sequence steps.

**Impact Level: 🔴 HIGH** - Eye-tracking lifecycle management

---

### 2.5 ⚠️ useEyeTracking.js - CONNECTION MANAGEMENT

**Current Behavior:**
- Connection opened explicitly by component
- No concept of "stay connected"
- `stopTracking()` doesn't disconnect, but no guarantee connection persists

**Required Enhancement:**
```javascript
// Add connection pooling/persistence
const [persistConnection, setPersistConnection] = useState(false);

const startTracking = useCallback(async (persistMode = false) => {
  setPersistConnection(persistMode);
  // ... existing logic
}, []);

const stopTracking = useCallback(async () => {
  if (persistConnection) {
    // Don't disconnect, just pause tracking
    await fetch(`${API_BASE}/pause`, { method: 'POST' });
  } else {
    // Full stop
    await fetch(`${API_BASE}/stop`, { method: 'POST' });
  }
}, [persistConnection]);
```

**Impact Level: 🟡 MEDIUM** - New "persist mode" flag

---

### 2.6 ⚠️ useManualAssistance.js - SESSION CLEANUP

**Current Behavior:**
- Creates session on `startAssistanceSession(image, activity)`
- Session stored in backend with key: `{activity}_{image_filename}`
- No automatic cleanup

**Required Enhancement:**
```javascript
// Add explicit cleanup method
const forceCleanup = async () => {
  if (sessionKey) {
    try {
      await fetch(`${API_BASE}/stop/${sessionKey}`, {
        method: 'POST'
      });
      console.log('🧹 Manual assistance session cleaned up');
    } catch (err) {
      console.error('Error cleaning up session:', err);
    }
    setSessionKey(null);
    setIsActive(false);
  }
};

return {
  // ... existing
  forceCleanup  // NEW
};
```

**Backend Impact:**
```python
# backend/src/services/manual_assistance_service.py
# Currently: Sessions accumulate in memory
self.sessions: Dict[str, ManualAssistanceSession] = {}

# Need: Explicit cleanup endpoint
def cleanup_session(self, session_key: str):
    if session_key in self.sessions:
        del self.sessions[session_key]
        logger.info(f"🧹 Cleaned up session: {session_key}")
```

**Impact Level: 🟡 MEDIUM** - Cleanup methods + backend endpoint

---

### 2.7 ✅ useTimeTracking.js - NO CHANGES NEEDED

**Current Behavior:**
- Already tracks per `(image, activity, condition, child_name)`
- Auto starts/stops on image change
- Handles cleanup properly

**Why It Works:**
```javascript
useEffect(() => {
  // Auto-starts new session when any param changes
  const initSession = async () => {
    if (isTrackingRef.current) {
      await endSession();  // End previous
    }
    if (imageFilename && activity && assistanceCondition) {
      await startSession();  // Start new
    }
  };
  initSession();
}, [imageFilename, activity, assistanceCondition, childName]);
```

**Sequence Behavior:**
- Step 1: `eye_assistance/question/1.jpg` → Session 1
- Step 2: `base/question/2.jpg` → Session 1 ends, Session 2 starts
- Step 3: `assistance/storytelling/1.png` → Session 2 ends, Session 3 starts

✅ **Perfect!** No changes needed.

**Impact Level: ✅ NONE**

---

### 2.8 ⚠️ Backend State Manager - SESSION SWITCHING

**Current Behavior:**
```python
# backend/src/core/state_manager.py
class GazeStateManager:
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}  # Key: image_filename
```

**Issue:**
Sessions keyed by `image_filename` only. 

**Example Problem:**
```
Sequence:
1. eye_assistance/question/1.jpg  → backend session: "1.jpg"
2. base/question/2.jpg             → backend session: "2.jpg" 
3. eye_assistance/question/3.jpg  → backend session: "3.jpg"
4. Back to step 1                  → backend session: "1.jpg" (REUSES old session!)
```

**Potential Solution:**
Either:
- A) Clear sessions on condition switch
- B) Key sessions by `(image, condition)` tuple
- C) Use `stop_tracking` / `start_tracking` to reset session

**Current Best: Option C** - Already supported:
```javascript
// Frontend
gaze.stopTracking();  // Clears backend session
gaze.startTracking(activity, newImage);  // Creates new session
```

**Impact Level: 🟡 MEDIUM** - Ensure proper stop/start between sequence steps

---

### 2.9 ⚠️ WebSocket Connection - PERSISTENCE

**Current Behavior:**
```javascript
// App_Official.js
const websocket = useWebSocket(
  'ws://localhost:8001/ws', 
  shouldUseEyeTracking ? clientId : null  // Only connects if eye-tracking needed
);
```

**Issue:**
WebSocket only created for eye-tracking condition. In sequence mode, might need it mid-sequence.

**Required Change:**
```javascript
// NEW: Always create WebSocket in sequence mode
const needsWebSocket = sequenceMode || shouldUseEyeTracking;
const websocket = useWebSocket(
  'ws://localhost:8001/ws',
  needsWebSocket ? clientId : null
);
```

**Backend Impact:**
None - backend already handles persistent WebSocket connections. Just need to keep it open.

**Impact Level: 🟡 LOW-MEDIUM** - Change initialization condition

---

## 3. New Components Needed

### 3.1 SequenceBuilder.js
**Purpose:** UI to build custom sequences

**State:**
```javascript
const [sequence, setSequence] = useState([]);
const [currentEdit, setCurrentEdit] = useState({
  condition: 'base',
  activity: 'question', 
  image: '1.jpg'
});
```

**Key Functions:**
- `addToSequence()` - Add step
- `removeFromSequence(index)` - Remove step
- `reorderSequence(fromIndex, toIndex)` - Drag & drop
- `loadPreset(presetName)` - Load preset
- `saveAsPreset(name)` - Save preset

**Impact:** ✅ New component, no existing code affected

---

### 3.2 SequenceReader.js
**Purpose:** Orchestrator that renders appropriate component per step

**State:**
```javascript
const [currentStepIndex, setCurrentStepIndex] = useState(0);
const [completedSteps, setCompletedSteps] = useState([]);
const [resources, setResources] = useState({
  eyeTrackingConnected: false,
  websocketOpen: false
});
```

**Key Logic:**
```javascript
const renderCurrentComponent = () => {
  const step = sequence[currentStepIndex];
  
  // Determine if resources need initialization
  const needsEyeTracking = step.condition === 'eye_assistance';
  const needsManualAssistance = step.condition === 'assistance';
  
  // Ensure resources ready before rendering
  if (needsEyeTracking && !resources.eyeTrackingConnected) {
    return <div>Connecting eye tracker...</div>;
  }
  
  // Render appropriate component
  switch (step.condition) {
    case 'base':
      return <BaselineBook 
        imageFilename={step.image}
        activity={step.activity}
        childName={childName}
        lockedToSingleImage={true}
        onComplete={handleStepComplete}
      />;
    // ... etc
  }
};
```

**Critical:** Manages resource lifecycle across components

**Impact:** ✅ New component, orchestrates existing components

---

## 4. Breaking Changes Summary

### 4.1 Props Changes

**BaselineBook.js:**
```diff
+ lockedToSingleImage?: boolean
+ imageFilename?: string
+ onComplete?: () => void
```

**AssistanceBook.js:**
```diff
+ lockedToSingleImage?: boolean
+ imageFilename?: string
+ onComplete?: () => void
```

**PictureBookReader.js:**
```diff
+ lockedToSingleImage?: boolean
- imageFilename = '1.jpg'  (already has this)
+ onComplete?: () => void
```

### 4.2 Hook Signatures

**useEyeTracking:**
```diff
+ startTracking(persistMode?: boolean)
+ setPersistConnection(persist: boolean)
```

**useManualAssistance:**
```diff
+ forceCleanup(): Promise<void>
```

### 4.3 Backend Endpoints

**New:**
- `POST /api/eye-tracking/pause` - Pause tracking without disconnect
- `POST /api/manual-assistance/cleanup/{session_key}` - Force cleanup

**Modified:**
None (existing endpoints sufficient)

---

## 5. Risk Assessment

### 5.1 High Risk Areas

| Area | Risk | Mitigation |
|------|------|------------|
| **Eye-tracking connection** | 🔴 HIGH | Add connection pooling, persist across steps |
| **Manual assistance cleanup** | 🟡 MEDIUM | Add explicit cleanup, test thoroughly |
| **State transitions** | 🟡 MEDIUM | Proper stop/start between steps |
| **Component unmount timing** | 🟡 MEDIUM | Use cleanup functions in useEffect |

### 5.2 Low Risk Areas

| Area | Risk | Reason |
|------|------|--------|
| **Time tracking** | ✅ LOW | Already designed for flexibility |
| **Image loading** | ✅ LOW | Simple path changes |
| **UI rendering** | ✅ LOW | Conditional rendering straightforward |

---

## 6. Migration Strategy

### Phase 1: Prepare Components (Non-breaking)
1. Add new props to all three book components (with defaults)
2. Add conditional rendering for locked mode
3. Test existing functionality still works

### Phase 2: Resource Management
1. Add connection persistence to useEyeTracking
2. Add cleanup to useManualAssistance
3. Add backend cleanup endpoint
4. Test resource cleanup

### Phase 3: Build Sequence Components
1. Create SequenceBuilder.js
2. Create SequenceReader.js
3. Test with simple sequences

### Phase 4: Integrate into App
1. Modify App_Official.js flow
2. Add sequence step to app flow
3. Test full sequence execution

### Phase 5: Thorough Testing
1. Test each condition individually in sequence
2. Test rapid switching
3. Test resource cleanup
4. Test time tracking accuracy

---

## 7. Testing Requirements

### 7.1 Unit Tests
- [ ] BaselineBook locked mode
- [ ] AssistanceBook locked mode
- [ ] PictureBookReader locked mode
- [ ] SequenceBuilder add/remove/reorder
- [ ] useEyeTracking persist mode

### 7.2 Integration Tests
- [ ] Sequence: base → assistance → base
- [ ] Sequence: eye → base → eye (connection persistence)
- [ ] Sequence: assistance → eye → assistance (session cleanup)
- [ ] Time tracking across mixed sequence
- [ ] Resource cleanup on sequence abort

### 7.3 User Scenarios
- [ ] Complete full mixed sequence
- [ ] Exit mid-sequence
- [ ] Refresh page during sequence
- [ ] Back button during sequence

---

## 8. Estimated Effort

| Task | Complexity | Time Estimate |
|------|-----------|---------------|
| Component props modification | Low | 2-3 hours |
| Resource management | Medium | 4-6 hours |
| SequenceBuilder UI | Medium | 6-8 hours |
| SequenceReader orchestrator | High | 8-10 hours |
| App integration | Medium | 4-6 hours |
| Testing & debugging | High | 10-15 hours |
| **Total** | | **34-48 hours** |

---

## 9. Recommendations

### 9.1 Immediate Actions
1. ✅ Start with **Phase 1** - Add new props (non-breaking)
2. ⚠️ Test existing functionality thoroughly after each phase
3. ✅ Create feature branch for sequence builder work

### 9.2 Architecture Decisions
1. **Eye-tracking:** Implement connection pooling (don't disconnect between steps)
2. **Manual assistance:** Add explicit cleanup methods
3. **State management:** Use stop/start pattern for backend session resets
4. **WebSocket:** Keep open throughout sequence mode

### 9.3 Future Enhancements
- Sequence preset library
- Sequence validation (ensure images exist)
- Progress persistence (resume sequences)
- Analytics dashboard for sequences

---

## 10. Conclusion

**Feasibility: ✅ YES - But requires significant work**

The time tracking system is already flexible and ready. The main challenges are:
1. 🔴 Eye-tracking connection management
2. 🟡 Component lifecycle and cleanup
3. 🟡 State management across conditions

With proper resource management and cleanup logic, the sequence builder is **achievable** without major architectural rewrites. The existing components are well-structured and can be adapted with the proposed props.

**Recommended Approach:** Incremental implementation with thorough testing at each phase.


