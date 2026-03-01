# Gaze Indicator Toggle Feature

## Overview

A new toggle switch has been added to control the visibility of the gaze indicator (purple circle) in sequence mode when using eye-tracking assistance. This gives users control over visual feedback for eye movements on a per-image basis.

## Feature Details

### When the Toggle Appears

The toggle is **ONLY** visible when **ALL** of these conditions are met:

1. ✅ **In Sequence Mode** (`lockedToSingleImage === true`)
2. ✅ **Eye-Tracking Assistance Mode** (`condition === 'eye_assistance'`)
3. ✅ **Thumbnail View** (before entering fullscreen)

The toggle does **NOT** appear for:
- ❌ Base condition (no assistance)
- ❌ Manual assistance (LLM without eye-tracking)
- ❌ Standalone/regular reading mode
- ❌ During fullscreen reading (setting is pre-configured)

### User Flow

1. During reading in sequence mode with eye-tracking
2. When viewing the thumbnail of an eye-tracking step
3. A simple toggle appears at the bottom right of the image: **"Gaze Tracker"**
4. Toggle on/off before double-clicking to enter fullscreen
5. The setting persists for that specific image

### Visual Design

**Simple toggle at bottom right of thumbnail image:**

```
┌──────────────────────────────────────┐
│                                      │
│                                      │
│       [Image Display]                │
│                                      │
│                   ┌─────────────────┐│
│                   │ [●─] Gaze Tracker││  ← Bottom Right
│                   └─────────────────┘│
└──────────────────────────────────────┘

- Clean, minimal design
- Semi-transparent black background
- Toggle switch + "Gaze Tracker" text
- Purple when ON, gray when OFF
```

## Technical Implementation

### Files Modified

1. **`frontend/src/components/SequenceReader.js`**
   - Converted `sequence` prop to state to allow updates
   - Added `handleGazeIndicatorToggle()` function
   - Passes `showGazeIndicator` prop and callback to `PictureBookReader`

2. **`frontend/src/components/PictureBookReader.js`**
   - Added props: `showGazeIndicator`, `onGazeIndicatorToggle`
   - Added local state: `gazeIndicatorEnabled`
   - Added simple toggle UI at bottom right of image (conditionally rendered)
   - Passes `showGazeIndicator` to `FullscreenReader`

3. **`frontend/src/components/FullscreenReader.js`**
   - Added prop: `showGazeIndicator` (default: `true`)
   - Conditionally renders `FixationCanvas` based on prop
   - Eye tracking data collection continues regardless

4. **CSS File**
   - `frontend/src/components/PictureBookReader.css`: Simple toggle styling positioned at bottom right

### Data Structure

```javascript
// Sequence step structure
{
  condition: 'eye_assistance',
  activity: 'question',
  image: '1.jpg',
  step: 1,
  showGazeIndicator: true  // NEW FIELD (default: true)
}
```

### Important Notes

1. **Eye Tracking Still Works**: 
   - Disabling the gaze indicator only hides the visual circle
   - Eye tracking data collection continues
   - AOI detection and guidance triggers still function normally

2. **Default Behavior**:
   - Default is `true` (show indicator) for backward compatibility
   - Existing sequences without this field will show the indicator

3. **Per-Step Configuration**:
   - Each sequence step has its own toggle setting
   - Settings persist when navigating back/forward between steps

4. **State Synchronization**:
   - Local component state syncs with parent sequence state
   - Changes in SequenceBuilder reflect in SequenceReader
   - Changes in SequenceReader update the sequence state

## Use Cases

### When to Show Gaze Indicator ✅

- **First-time users**: Visual feedback helps them understand eye tracking
- **Calibration verification**: Confirm eye tracker is working correctly
- **Research demonstrations**: Show participants where they're looking
- **Training sessions**: Help users develop awareness of gaze patterns

### When to Hide Gaze Indicator ❌

- **Experienced users**: Reduce visual clutter for familiar participants
- **Immersive reading**: Less distraction for natural reading experience
- **Data collection**: Minimize influence on natural gaze behavior
- **Aesthetic preference**: Some users find the indicator distracting

## Example Usage

1. **Build a sequence** with eye-tracking steps in Sequence Builder
2. **During reading**, when viewing the thumbnail:
   - Toggle appears at bottom right: `[●─] Gaze Tracker`
   - Click to toggle ON (purple) or OFF (gray)
3. **Double-click image** to enter fullscreen
4. **Gaze indicator** shows/hides based on toggle setting
5. **Navigate** to next step - each step has its own toggle setting

## Testing Checklist

- [ ] Toggle appears at bottom right in sequence mode with eye-tracking
- [ ] Toggle does not appear for base/assistance conditions
- [ ] Toggle does not appear in standalone reading mode
- [ ] Toggle positioning is correct (bottom right of image)
- [ ] Toggle styling is simple and clean (no fancy boxes)
- [ ] Gaze indicator shows/hides in fullscreen based on toggle
- [ ] Eye tracking continues working when indicator is hidden
- [ ] AOI highlighting and guidance still function normally
- [ ] Settings persist when navigating between steps
- [ ] Default behavior (true/ON) works correctly

## Future Enhancements

Potential improvements for future versions:

1. **Global Default Setting**: User preference for default toggle state
2. **Bulk Toggle**: Toggle all eye-tracking steps at once in sequence builder
3. **Hotkey**: Keyboard shortcut to toggle during fullscreen (e.g., 'G' key)
4. **Conditional Visibility**: Show indicator only during certain phases
5. **Custom Indicator Styles**: Allow users to customize appearance
6. **Indicator Opacity**: Slider to adjust transparency instead of on/off

## Conclusion

This feature provides simple, intuitive control over the gaze indicator display while maintaining full eye tracking functionality. The minimalist design (just a toggle at bottom right with "Gaze Tracker" text) doesn't interfere with the reading experience, while giving users the option to show or hide the visual feedback as needed.

