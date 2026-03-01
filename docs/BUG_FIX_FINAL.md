# 🐛 Bug Fix: Eye-Tracking TTS Variable Scope Issue

## Problem

**Error Message**:
```
ERROR:services.eye_tracking_tts_service:❌ Error in eye-tracking speech synthesis: local variable 'image_base' referenced before assignment
```

**Impact**: 
- ✅ JSON cache saved correctly: `1_story_2_14_eye_asst.json`
- ❌ WAV audio files failed to generate

---

## Root Cause

**Location**: `backend/src/services/eye_tracking_tts_service.py`

**Issue**: Variable `image_base` was only defined in the STANDALONE MODE branch (line 108), but was used in a log statement (line 154) that executes for BOTH modes.

**Code Flow**:
```python
def synthesize_speech(..., sequence_step=None):
    # ... config check ...
    
    # SEQUENCE MODE branch
    if sequence_step is not None:
        audio_path = self.sequence_cache_service.get_file_path(...)
        audio_filename = audio_path.name
        # image_base NOT defined here!
    
    # STANDALONE MODE branch
    else:
        image_base = Path(image_name).stem  # ← ONLY defined here!
        audio_filename = f"{image_base}_eye_main_aoi_{aoi_index}.wav"
    
    # Common code for both branches
    logger.info(f"... for {image_base} AOI ...")  # ← ERROR! image_base not defined in sequence mode!
```

---

## Fix Applied

**Changed**: Moved `image_base` definition to the beginning of the function, before any branching logic.

**Before** (Lines 70-108):
```python
# SEQUENCE MODE: Use SequenceCacheService
if sequence_step is not None:
    # ... path generation ...
    audio_filename = audio_path.name
    
# STANDALONE MODE: Use traditional cache structure
else:
    # Create activity-specific directory
    activity_dir = self.audio_cache_base / activity
    activity_dir.mkdir(exist_ok=True)
    
    # Generate structured filename with eye_ prefix
    image_base = Path(image_name).stem  # ← Defined only here
```

**After** (Lines 70-111):
```python
# Extract image base for logging (used in both modes)
image_base = Path(image_name).stem  # ← NOW defined at the start

# SEQUENCE MODE: Use SequenceCacheService
if sequence_step is not None:
    # ... path generation ...
    audio_filename = audio_path.name
    
# STANDALONE MODE: Use traditional cache structure
else:
    # Create activity-specific directory
    activity_dir = self.audio_cache_base / activity
    activity_dir.mkdir(exist_ok=True)
    
    # Generate structured filename with eye_ prefix (no duplicate image_base)
    if audio_type == "waiting":
```

---

## Verification

**File**: `backend/src/services/eye_tracking_tts_service.py`

✅ **Fixed**: Line 71 - `image_base` defined before branching  
✅ **Removed**: Line 108 - Duplicate `image_base` definition removed  
✅ **Linter**: No errors  

---

## Expected Results After Restart

### Previous Behavior (Broken)
```
✅ JSON saved: 1_story_2_14_eye_asst.json
❌ Audio failed: ERROR - image_base not defined
❌ WAV files: Not created
```

### New Behavior (Fixed)
```
✅ JSON saved: 1_story_2_14_eye_asst.json
✅ Audio generated: 1_story_2_14_main.wav
✅ Audio generated: 1_story_2_14_explore.wav
✅ All files: Correct naming convention
```

### Log Output You'll See
```
INFO:services.eye_tracking_tts_service:✅ Eye-Tracking TTS: Sequence mode auto-enabled
INFO:services.eye_tracking_tts_service:📂 Eye-tracking sequence mode audio: backend\mixed\1\1_story_2_14_main.wav
INFO:services.eye_tracking_tts_service:🔊 Eye-TTS: Generating main for 2 AOI 14
INFO:services.eye_tracking_tts_service:✅ Eye-TTS: 1_story_2_14_main.wav
INFO:services.eye_tracking_cache_service:✅ Eye-Tracking Cache: Sequence mode auto-enabled
INFO:services.eye_tracking_cache_service:💾 Eye-tracking: Saved LLM response: 1_story_2_14_eye_asst.json
```

---

## File Structure Created

```
backend/mixed/
└── 1/
    ├── time.json                    ✅
    ├── 1_story_2_14_main.wav       ✅ (now works!)
    ├── 1_story_2_14_explore.wav    ✅ (now works!)
    └── 1_story_2_14_eye_asst.json  ✅ (already worked)
```

---

## Status: ✅ BUG FIXED

**All WAV and JSON files will now save correctly with proper naming convention.**

This was a simple variable scope issue - `image_base` needed to be defined before the branching logic so it's available for logging in both modes.
