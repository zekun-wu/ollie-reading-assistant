# Frontend Integration Guide for Sequence Mode Cache

## Overview
Backend is **100% complete** and tested with no linter errors. This guide provides step-by-step instructions for updating the frontend to pass `sequence_step` to all API calls.

---

## ✅ Backend Status: COMPLETE

All backend services, APIs, and routes are updated to:
- Accept optional `sequence_step` parameter
- Route to sequence cache when `sequence_step` is provided
- Maintain backward compatibility (standalone mode unchanged)

**Files Updated**:
- ✅ `SequenceCacheService` - Core cache management
- ✅ `TimeTrackingService` + API route
- ✅ `AssistanceCacheService` + Manual Assistance API routes
- ✅ `EyeTrackingCacheService`
- ✅ `AzureTTSService` (manual assistance audio)
- ✅ `EyeTrackingTTSService` (eye-tracking audio)
- ✅ `ManualAssistanceService` - Complete refactor ✨

---

## 🎯 Frontend Changes Required

### 1. Update `SequenceReader.js`

**Location**: `frontend/src/components/SequenceReader.js`

**Goal**: Extract sequence step number from current position and pass to child components.

```javascript
// BEFORE
const renderCurrentComponent = () => {
  const currentConfig = sequence[currentStepIndex];
  
  if (currentConfig.condition === 'base') {
    return (
      <BaselineBook
        key={`${currentConfig.activity}_${currentConfig.image}_${currentConfig.condition}`}
        activity={currentConfig.activity}
        imageName={currentConfig.image}
        lockedToSingleImage={true}
        onComplete={handleStepComplete}
        onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
      />
    );
  }
  // ... other conditions
};

// AFTER - Add sequenceStep prop
const renderCurrentComponent = () => {
  const currentConfig = sequence[currentStepIndex];
  const sequenceStep = currentStepIndex + 1; // 1-based indexing for backend
  
  if (currentConfig.condition === 'base') {
    return (
      <BaselineBook
        key={`${currentConfig.activity}_${currentConfig.image}_${currentConfig.condition}`}
        activity={currentConfig.activity}
        imageName={currentConfig.image}
        lockedToSingleImage={true}
        sequenceStep={sequenceStep}  // NEW: Pass sequence step
        onComplete={handleStepComplete}
        onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
      />
    );
  }
  else if (currentConfig.condition === 'assistance') {
    return (
      <AssistanceBook
        key={`${currentConfig.activity}_${currentConfig.image}_${currentConfig.condition}`}
        activity={currentConfig.activity}
        imageName={currentConfig.image}
        lockedToSingleImage={true}
        sequenceStep={sequenceStep}  // NEW: Pass sequence step
        onComplete={handleStepComplete}
        onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
      />
    );
  }
  else if (currentConfig.condition === 'eye_assistance') {
    return (
      <PictureBookReader
        key={`${currentConfig.activity}_${currentConfig.image}_${currentConfig.condition}`}
        activity={currentConfig.activity}
        imageName={currentConfig.image}
        lockedToSingleImage={true}
        sequenceStep={sequenceStep}  // NEW: Pass sequence step
        onComplete={handleStepComplete}
        onPrevious={currentStepIndex > 0 ? handleStepPrevious : null}
        onBackToModeSelect={() => navigate('/')}
      />
    );
  }
};
```

---

### 2. Update `BaselineBook.js`

**Location**: `frontend/src/components/BaselineBook.js`

**Changes**:
1. Add `sequenceStep` prop
2. Pass to time tracking API calls

```javascript
// Add to component props
const BaselineBook = ({
  activity = 'question',
  imageName = '1.jpg',
  lockedToSingleImage = false,
  onComplete = null,
  onPrevious = null,
  sequenceStep = null  // NEW: Add this prop
}) => {

  // Find the time tracking start call (around line 100-150)
  const startTimeTracking = async () => {
    try {
      const formData = new URLSearchParams();
      formData.append('image_filename', imageName);
      formData.append('activity', activity);
      formData.append('assistance_condition', 'base');
      formData.append('child_name', 'Guest');
      
      // NEW: Add sequence_step if in sequence mode
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch('/api/time-tracking/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest of the function
    } catch (error) {
      console.error('Error starting time tracking:', error);
    }
  };
```

---

### 3. Update `AssistanceBook.js`

**Location**: `frontend/src/components/AssistanceBook.js`

**Changes**:
1. Add `sequenceStep` prop
2. Pass to time tracking, manual assistance start, and TTS API calls

```javascript
// Add to component props
const AssistanceBook = ({
  activity = 'question',
  imageName = '1.jpg',
  lockedToSingleImage = false,
  onComplete = null,
  onPrevious = null,
  sequenceStep = null  // NEW: Add this prop
}) => {

  // Update time tracking (same as BaselineBook)
  const startTimeTracking = async () => {
    try {
      const formData = new URLSearchParams();
      formData.append('image_filename', imageName);
      formData.append('activity', activity);
      formData.append('assistance_condition', 'assistance');
      formData.append('child_name', 'Guest');
      
      // NEW: Add sequence_step
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch('/api/time-tracking/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest
    } catch (error) {
      console.error('Error starting time tracking:', error);
    }
  };

  // Update manual assistance start
  const startManualAssistance = async () => {
    try {
      const formData = new URLSearchParams();
      formData.append('activity', activity);
      
      // NEW: Add sequence_step
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch(`/api/manual-assistance/start/${imageName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest
    } catch (error) {
      console.error('Error starting manual assistance:', error);
    }
  };

  // Update waiting TTS generation (if applicable)
  const generateWaitingTTS = async (text) => {
    try {
      const formData = new URLSearchParams();
      formData.append('text', text);
      formData.append('image_name', imageName);
      formData.append('activity', activity);
      
      // NEW: Add sequence_step
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch('/api/manual-assistance/tts/waiting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest
    } catch (error) {
      console.error('Error generating waiting TTS:', error);
    }
  };
```

---

### 4. Update `PictureBookReader.js`

**Location**: `frontend/src/components/PictureBookReader.js`

**Changes**:
1. Add `sequenceStep` prop
2. Pass to time tracking API call
3. Pass to any eye-tracking assistance API calls if applicable

```javascript
// Add to component props
const PictureBookReader = ({
  activity = 'question',
  imageName = '1.jpg',
  lockedToSingleImage = false,
  onComplete = null,
  onPrevious = null,
  onBackToModeSelect = null,
  sequenceStep = null  // NEW: Add this prop
}) => {

  // Update time tracking (same pattern as above)
  const startTimeTracking = async () => {
    try {
      const formData = new URLSearchParams();
      formData.append('image_filename', imageName);
      formData.append('activity', activity);
      formData.append('assistance_condition', 'eye_assistance');
      formData.append('child_name', 'Guest');
      
      // NEW: Add sequence_step
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch('/api/time-tracking/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest
    } catch (error) {
      console.error('Error starting time tracking:', error);
    }
  };

  // If there are eye-tracking TTS or cache calls, update them similarly
  // (Check for any fetch calls to eye-tracking assistance endpoints)
```

---

### 5. Update `IntroPage.js` (If Needed)

**Location**: `frontend/src/components/IntroPage.js`

**Only needed if intro page generates audio in sequence mode**

```javascript
// Add sequenceStep prop if intro is part of sequence
const IntroPage = ({
  onComplete,
  onBack,
  sequenceStep = null  // NEW: If intro is part of sequence
}) => {

  // If generating intro audio
  const generateIntroAudio = async (text) => {
    try {
      const formData = new URLSearchParams();
      formData.append('text', text);
      formData.append('image_name', 'intro');
      formData.append('activity', 'question'); // or from props
      
      // NEW: Add sequence_step if provided
      if (sequenceStep !== null) {
        formData.append('sequence_step', sequenceStep);
      }
      
      const response = await fetch('/api/manual-assistance/tts/waiting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      
      // ... rest
    } catch (error) {
      console.error('Error generating intro audio:', error);
    }
  };
```

**And update in `App_Official.js` where IntroPage is rendered in sequence mode**:

```javascript
// In App_Official.js, when rendering IntroPage after sequence building
{currentStep === 'intro' && useSequenceMode && (
  <IntroPage
    onComplete={handleIntroComplete}
    onBack={handleBackToSequenceBuilder}
    sequenceStep={currentSequenceStepIndex + 1}  // NEW: Pass current step
  />
)}
```

---

## 🔍 Testing Checklist

### Standalone Mode (Should work exactly as before)
- [ ] Baseline reading: Files in `backend/time_cache/base_time_cache/`
- [ ] Manual assistance: Files in `backend/assistance_cache/` and `backend/audio_cache/`
- [ ] Eye-tracking: Files in `backend/eye_assistance_cache/` and `backend/eye_audio_cache/`
- [ ] Intro audio in `backend/audio_cache/intro/`

### Sequence Mode (New paths)
- [ ] Build a 3-step sequence with mixed conditions
- [ ] Start sequence and complete step 1
- [ ] Check `backend/mixed/1/time.json` exists
- [ ] Check audio files in `backend/mixed/1/` follow naming: `1_que_1_2_main.wav`, etc.
- [ ] Check JSON cache files if assistance was used
- [ ] Verify intro audio in `backend/mixed/intro_audio/`
- [ ] Complete all steps and verify separate `time.json` per step

### Verification
```bash
# After running sequence mode, check structure:
ls -la backend/mixed/
ls -la backend/mixed/1/
ls -la backend/mixed/2/
ls -la backend/mixed/intro_audio/

# Standalone should be unchanged:
ls -la backend/time_cache/
ls -la backend/assistance_cache/
ls -la backend/audio_cache/
```

---

## 🚨 Common Issues

### Issue 1: `sequence_step` not reaching backend
**Symptom**: Files still saving to old cache locations
**Fix**: Check browser DevTools Network tab, verify FormData includes `sequence_step`

### Issue 2: Intro audio in wrong location
**Symptom**: Intro audio saves to standalone cache in sequence mode
**Fix**: Ensure `sequenceStep` is passed to IntroPage and its audio generation calls

### Issue 3: Time tracking saves all steps in one file
**Symptom**: `mixed/1/time.json` contains data from multiple steps
**Fix**: Verify each step uses correct `sequence_step` value (1, 2, 3, not 0-based)

---

## 📊 File Naming Reference

### Sequence Mode Files
```
Pattern: {seq}_{act}_{img}_{aoi}_{type}.{ext}

Examples:
- 1_que_1_2_main.wav        → Step 1, question, image 1, AOI 2, main audio
- 1_que_1_2_explore.wav     → Step 1, question, image 1, AOI 2, exploratory audio
- 1_que_1_waiting.wav       → Step 1, question, image 1, waiting audio (no AOI)
- 2_story_2_5_asst.json     → Step 2, storytelling, image 2, AOI 5, assistance cache
- 3_que_3_7_eye_asst.json   → Step 3, question, image 3, AOI 7, eye-tracking cache

Special cases:
- time.json                  → Always just "time.json" in each step folder
- intro_greeting.wav         → In mixed/intro_audio/ directory
- intro_welcome.wav          → In mixed/intro_audio/ directory
```

---

## 🎉 Summary

**What's Done**:
- ✅ All backend services support sequence mode
- ✅ All API routes accept `sequence_step` parameter
- ✅ Backward compatibility maintained
- ✅ No linter errors

**What's Left**:
- 🔲 Add `sequenceStep` prop to 4 frontend components
- 🔲 Update ~10 API fetch calls to include `sequence_step` in FormData
- 🔲 Test both modes

**Estimated Time**: 30-45 minutes of focused frontend work

---

**Need Help?** 
- Backend implementation: See `docs/SEQUENCE_CACHE_IMPLEMENTATION_STATUS.md`
- Questions about file paths: Check `backend/src/services/sequence_cache_service.py`
- API signatures: Check `backend/src/api/*_routes.py` files
