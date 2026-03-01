# Sequence Mode Cache Implementation Status

## Overview
This document tracks the implementation of a separate file structure for sequence mode, keeping standalone mode unchanged.

**Goal**: Files saved/loaded in sequence mode use `backend/mixed/` with sequence-specific naming conventions, while standalone mode continues using existing cache structures.

---

## ✅ COMPLETED: Backend Infrastructure (Phases 1-5)

### Phase 1: Core Infrastructure
- ✅ **Created `SequenceCacheService`** (`backend/src/services/sequence_cache_service.py`)
  - Manages `backend/mixed/` directory structure
  - Provides path generation for all sequence mode files
  - Naming convention: `{seq}_{act}_{img}_{aoi}_{type}.{ext}`
  - Special handling for `time.json` and intro audio

### Phase 2: Time Tracking Integration
- ✅ **Updated `TimeTrackingService`** (`backend/src/services/time_tracking_service.py`)
  - Added `sequence_step` parameter to `start_session()`
  - Routes to `SequenceCacheService` when `sequence_step` is provided
  - Added `enable_sequence_mode()` and `disable_sequence_mode()` methods

### Phase 3: Manual Assistance Cache
- ✅ **Updated `AssistanceCacheService`** (`backend/src/services/assistance_cache_service.py`)
  - Added `sequence_step` parameter to `save_chatgpt_response()`
  - Added `sequence_step` parameter to `load_cached_response()`
  - Routes to `SequenceCacheService` when `sequence_step` is provided
  - Added sequence mode enable/disable methods

### Phase 4: Eye-Tracking Cache
- ✅ **Updated `EyeTrackingCacheService`** (`backend/src/services/eye_tracking_cache_service.py`)
  - Added `sequence_step` parameter to `save_llm_response()`
  - Routes to `SequenceCacheService` when `sequence_step` is provided
  - Added sequence mode enable/disable methods

### Phase 5: Audio Generation
- ✅ **Updated `AzureTTSService`** (`backend/src/services/azure_tts_service.py`)
  - Added `sequence_step` parameter to `synthesize_speech()`
  - Special intro audio handling for both modes
  - Routes to `SequenceCacheService` for sequence mode audio
  - Added sequence mode enable/disable methods

- ✅ **Updated `EyeTrackingTTSService`** (`backend/src/services/eye_tracking_tts_service.py`)
  - Added `sequence_step` parameter to `synthesize_speech()`
  - Routes to `SequenceCacheService` when `sequence_step` is provided
  - Added sequence mode enable/disable methods

---

## 🟡 PARTIAL: API Layer (Phase 6)

### Completed
- ✅ **Updated `time_tracking_routes.py`**
  - Added `sequence_step` parameter to `/start` endpoint
  - Passes `sequence_step` to `TimeTrackingService`

- ✅ **Updated `manual_assistance_routes.py`**
  - Added `sequence_step` parameter to `/tts/waiting` endpoint
  - Passes `sequence_step` to `AzureTTSService`

- ✅ **Updated `manual_assistance_service.py`**
  - Updated `ManualAssistanceSession` dataclass with `sequence_step` field
  - Updated TTS calls in `select_random_aoi()` to pass `sequence_step`
  - Updated cache save call to pass `sequence_step`

### Remaining Issues
⚠️ **Data structure mismatch in `manual_assistance_service.py`**:
- Line 89-95: `start_assistance_session()` creates session with old attributes (`used_aois`, `is_active`, `assistance_count`)
- These don't match the updated dataclass (needs `available_aois`, `used_aoi_indices`, `completed`)
- Line 141: References `session.is_active` which doesn't exist in updated dataclass

**Required Fix**:
```python
def start_assistance_session(self, image_filename: str, activity: str, sequence_step: Optional[int] = None) -> Dict[str, Any]:
    """Start a new manual assistance session"""
    try:
        session_key = f"{activity}_{image_filename}"
        
        # Load AOIs first
        image_name = Path(image_filename).stem
        labels_file = self.labels_base_dir / activity / f"{image_name}_labels.json"
        
        if not labels_file.exists():
            return {"success": False, "error": f"No AOI definitions found"}
        
        with open(labels_file, 'r') as f:
            labels_data = json.load(f)
        
        # Build available AOIs list
        available_aois = []
        for obj in labels_data.get('objects', []):
            aoi = ManualAOI(
                index=obj['index'],
                bbox=obj['bbox'],
                center=obj['center'],
                area=obj['area']
            )
            available_aois.append(aoi)
        
        # Create new session with correct structure
        session = ManualAssistanceSession(
            image_filename=image_filename,
            activity=activity,
            available_aois=available_aois,
            used_aoi_indices=[],
            current_aoi=None,
            completed=False,
            sequence_step=sequence_step  # NEW
        )
        
        self.sessions[session_key] = session
        
        logger.info(f"🤖 Started manual assistance session: {session_key}")
        
        return {
            "success": True,
            "session_key": session_key,
            "message": "Manual assistance session started"
        }
```

### API Routes Needing Updates
- ❌ `/api/manual-assistance/start/{image_filename}` - needs `sequence_step` parameter
- ❌ Eye-tracking routes if they use caching/TTS
- ❌ Guidance routes if they trigger LLM/audio generation

---

## ❌ NOT STARTED: Frontend (Phase 6)

### Required Changes

#### 1. `SequenceReader.js`
**Current**: Passes step config to child components
**Needed**: Extract and pass sequence metadata to all API calls
```javascript
// In SequenceReader.js - handleStepComplete
const handleStepComplete = async () => {
  // Extract sequence metadata
  const currentConfig = sequence[currentStepIndex];
  const sequenceStep = currentStepIndex + 1; // 1-based indexing
  const activity = currentConfig.activity;
  const imageName = currentConfig.image;
  const condition = currentConfig.condition;
  
  // Pass to next step (or through context/props)
  // All child components need access to sequenceStep
};
```

#### 2. `BaselineBook.js`, `AssistanceBook.js`, `PictureBookReader.js`
**All need**: Accept `sequenceStep` prop and pass to API calls

**Example for BaselineBook**:
```javascript
// Add prop
const BaselineBook = ({ activity, imageName, sequenceStep = null, ... }) => {
  
  // Update time tracking API call
  const response = await fetch('/api/time-tracking/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      image_filename: imageName,
      activity: activity,
      assistance_condition: 'base',
      child_name: 'Guest',
      sequence_step: sequenceStep  // NEW
    })
  });
};
```

**Similar updates needed for**:
- AssistanceBook: `/api/manual-assistance/start` + `/api/manual-assistance/tts/waiting`
- PictureBookReader: Eye-tracking assistance endpoints

#### 3. `IntroPage.js`
**Needed**: Pass `sequenceStep` to audio generation if intro is part of sequence
```javascript
// When generating intro audio in sequence mode
const response = await fetch('/api/manual-assistance/tts/waiting', {
  method: 'POST',
  body: new URLSearchParams({
    text: introText,
    image_name: 'intro',
    activity: 'question', // or from sequence config
    sequence_step: sequenceStep // NEW
  })
});
```

#### 4. Sequence Context/State Management
**Option A**: Add sequence metadata to each step config
```javascript
// In SequenceBuilder or SequenceReader
const enrichedSequence = sequence.map((step, index) => ({
  ...step,
  sequenceStep: index + 1,
  isSequenceMode: true
}));
```

**Option B**: Create a React context for sequence mode
```javascript
// SequenceContext.js
export const SequenceContext = React.createContext({
  isSequenceMode: false,
  currentStep: null
});

// Usage in child components
const { isSequenceMode, currentStep } = useContext(SequenceContext);
```

---

## 🔧 BACKEND: Sequence Mode Activation

### Current Issue
Services need to be told when to use `SequenceCacheService`. Two approaches:

#### Option A: Enable globally when sequence starts
```python
# In a sequence initialization endpoint or main.py
from services.sequence_cache_service import get_sequence_cache_service
from services.time_tracking_service import get_time_tracking_service
from services.assistance_cache_service import get_assistance_cache_service
# ... import all services

def enable_sequence_mode():
    """Enable sequence mode for all services"""
    seq_cache = get_sequence_cache_service()
    
    get_time_tracking_service().enable_sequence_mode(seq_cache)
    get_assistance_cache_service().enable_sequence_mode(seq_cache)
    get_eye_tracking_cache_service().enable_sequence_mode(seq_cache)
    get_azure_tts_service().enable_sequence_mode(seq_cache)
    get_eye_tracking_tts_service().enable_sequence_mode(seq_cache)
```

#### Option B: Services automatically detect from `sequence_step` (Current Implementation)
Services check if `sequence_step` is provided in each call. **This is the current approach** - no global toggle needed.

---

## 📋 File Structure Summary

### Sequence Mode (`backend/mixed/`)
```
mixed/
├── intro_audio/
│   ├── intro_greeting.wav
│   └── intro_welcome.wav
└── {step}/                          # e.g., 1/, 2/, 3/
    ├── time.json                    # Only this step's time data
    ├── {seq}_{act}_{img}_{aoi}_asst.json          # Manual assistance cache
    ├── {seq}_{act}_{img}_{aoi}_eye_asst.json      # Eye-tracking cache
    ├── {seq}_{act}_{img}_{aoi}_main.wav           # Main audio
    ├── {seq}_{act}_{img}_{aoi}_explore.wav        # Exploratory audio
    └── {seq}_{act}_{img}_waiting.wav              # Waiting audio (no AOI)
```

### Standalone Mode (Unchanged)
```
time_cache/
  ├── base_time_cache/{activity}/{img}.json
  ├── assistance_time_cache/{activity}/{img}.json
  └── eye_assistance_time_cache/{activity}/{img}.json

assistance_cache/{activity}/
  └── {img}_asst_aoi_{aoi}.json

eye_assistance_cache/{activity}/
  └── {img}_eye_asst_aoi_{aoi}.json

audio_cache/{activity}/
  ├── intro/intro_{type}.wav
  ├── {img}_waiting.wav
  ├── {img}_main_aoi_{aoi}.wav
  └── {img}_explore_aoi_{aoi}.wav

eye_audio_cache/{activity}/
  ├── {img}_eye_waiting.wav
  ├── {img}_eye_main_aoi_{aoi}.wav
  └── {img}_eye_explore_aoi_{aoi}.wav
```

---

## 🎯 Next Steps (Priority Order)

### 1. Fix Backend Data Structure Mismatch
- [ ] Update `manual_assistance_service.py::start_assistance_session()` (see code above)
- [ ] Update `select_random_aoi()` to use `session.completed` instead of `session.is_active`
- [ ] Add `sequence_step` parameter to `start_assistance_session()`
- [ ] Update API route `/api/manual-assistance/start` to accept and pass `sequence_step`

### 2. Frontend API Integration
- [ ] Add `sequenceStep` prop to `BaselineBook`, `AssistanceBook`, `PictureBookReader`
- [ ] Update all `/api/time-tracking/start` calls to include `sequence_step`
- [ ] Update all `/api/manual-assistance/*` calls to include `sequence_step`
- [ ] Update eye-tracking API calls if applicable

### 3. Sequence Metadata Propagation
- [ ] Modify `SequenceReader` to extract and pass `sequenceStep` to child components
- [ ] Ensure `IntroPage` receives `sequenceStep` when shown after sequence building
- [ ] Consider using React Context for cleaner state management

### 4. Testing
- [ ] Test standalone mode (should work exactly as before)
- [ ] Test sequence mode with all three conditions
- [ ] Verify file paths are correct in `backend/mixed/`
- [ ] Verify `time.json` only contains single-step data
- [ ] Verify intro audio shared vs per-step audio

---

## ⚠️ Important Notes

1. **Standalone mode is UNCHANGED**: All existing cache paths remain identical
2. **Sequence mode is OPT-IN**: Only activated when `sequence_step` parameter is provided
3. **Backward compatible**: Existing code works without modifications if not using sequences
4. **Per-step time tracking**: Each `time.json` in `mixed/{step}/` only tracks that step's viewing time
5. **Intro audio**: Stored in `mixed/intro_audio/` for sequence mode, `audio_cache/intro/` for standalone

---

## 🔍 Verification Checklist

### Backend
- [ ] All services accept optional `sequence_step` parameter
- [ ] Services route to `SequenceCacheService` when `sequence_step` provided
- [ ] Standalone paths unchanged when `sequence_step` is `None`
- [ ] API routes pass `sequence_step` from frontend to services

### Frontend
- [ ] All reading components receive `sequenceStep` prop
- [ ] All API calls include `sequence_step` in request body
- [ ] Sequence flow correctly extracts and passes step number
- [ ] Standalone flow works without `sequenceStep` (defaults to `null`)

### File System
- [ ] `backend/mixed/` directory created
- [ ] Sequence files follow naming convention
- [ ] Standalone cache directories unchanged
- [ ] No cross-contamination between modes

---

**Status**: Backend infrastructure complete, API layer partial, frontend not started  
**Blocker**: Data structure mismatch in `manual_assistance_service.py`  
**Next Action**: Fix service initialization, then complete frontend integration
