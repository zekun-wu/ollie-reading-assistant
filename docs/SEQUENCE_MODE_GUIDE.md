# Sequence Mode User Guide

## Overview

The application runs a predefined reading sequence using **9 storytelling images** across **3 assistance conditions**.

---

## 🎯 Predefined Sequence

The system automatically loads a sequence that distributes all 9 storytelling images across three conditions:

```javascript
[
  // Eye-Tracking + LLM Assistance (3 images)
  { condition: 'eye_assistance', activity: 'storytelling', image: '1.png' },
  { condition: 'eye_assistance', activity: 'storytelling', image: '2.png' },
  { condition: 'eye_assistance', activity: 'storytelling', image: '3.png' },
  
  // Baseline - No Assistance (3 images)
  { condition: 'base', activity: 'storytelling', image: '4.png' },
  { condition: 'base', activity: 'storytelling', image: '5.png' },
  { condition: 'base', activity: 'storytelling', image: '6.png' },
  
  // Manual Assistance - LLM Only (3 images)
  { condition: 'assistance', activity: 'storytelling', image: '7.jpg' },
  { condition: 'assistance', activity: 'storytelling', image: '8.jpg' },
  { condition: 'assistance', activity: 'storytelling', image: '9.jpg' }
]
```

---

## 🚀 How to Use

### Step 1: Start the Application

1. Start backend:
   ```bash
   cd backend
   python src/main.py
   ```

2. Start frontend:
   ```bash
   cd frontend
   npm start
   ```

3. Open browser: `http://localhost:3000`

---

### Step 2: Enter Child Name

The **Intro Page** appears - enter child's name (or "Guest").

---

### Step 3: Start Reading

After entering the child's name, the predefined storytelling sequence loads automatically.

The sequence includes 9 storytelling images across 3 conditions:

3. **Select Image:**
   - Dropdown shows available images for chosen activity
   - Question: 1.jpg - 5.jpg
   - Storytelling: 1.png - 2.png

4. **Click "➕ Add to Sequence"**

5. **Repeat** for each step you want

#### Option B: Load a Preset

Click one of these preset buttons:
- **Balanced Mix** - 6 steps mixing all three conditions
- **Eye-Tracking First** - Eye-tracking → baseline
- **Manual Assistance Focus** - All manual assistance steps

#### Managing Your Sequence

- **Reorder**: Use ↑↓ buttons to move steps up/down
- **Remove**: Click ✕ to remove a step
- **Clear All**: Click "🗑️ Clear All" to start over

---

### Step 5: Start Reading

When your sequence is ready, click:
```
Start Reading Sequence →
```

---

### Step 6: Execute the Sequence

The **Sequence Reader** takes over:

#### Progress Tracking
- Top bar shows: "Step X of Y"
- Progress bar fills as you complete steps
- Numbered circles show all steps (current step highlighted)

#### For Each Step

**Step Behavior:**
- Double-click image to enter fullscreen
- Read the picture in the assigned condition
- Click "Next Step →" button when done
- System automatically moves to next step

**Automatic Handling:**
- **Eye-tracking**: Connects once, switches images seamlessly
- **Manual assistance**: Sessions created/cleaned up per step
- **Time tracking**: Each step tracked separately in appropriate cache directory

---

## 📊 Time Tracking Results

After completing the sequence, check:

```
backend/time_cache/
├── eye_assistance_time_cache/
│   ├── question/
│   │   └── 1.json  ← Step 1 data
│   └── storytelling/
│       └── 1.json  ← Step 2 data
├── base_time_cache/
│   └── question/
│       ├── 2.json  ← Step 3 data
│       └── 3.json  ← Step 4 data
└── assistance_time_cache/
    └── storytelling/
        ├── 1.json  ← Step 5 data
        └── 2.json  ← Step 6 data
```

Each JSON file contains:
- All viewing sessions for that image/condition/activity
- Child name
- Start/end timestamps
- Duration for each session
- Summary statistics

---

## 🎮 Sequence Builder UI Reference

### Main Interface

```
┌────────────────────────────────────────────────────────────┐
│         📚 Build Your Reading Sequence                     │
│    Create a custom reading sequence mixing conditions      │
├──────────────────────┬─────────────────────────────────────┤
│  ➕ Add Steps        │  📖 Current Sequence (6 steps)      │
│                      │                                      │
│  Condition:          │  ┌─────────────────────────────┐   │
│  [eye_assistance ▼]  │  │ 1 Eye-Track + LLM - Q - 1.jpg│   │
│                      │  │   [↑][↓][✕]                 │   │
│  Activity:           │  ├─────────────────────────────┤   │
│  [question ▼]        │  │ 2 Eye-Track + LLM - S - 1.png│   │
│                      │  │   [↑][↓][✕]                 │   │
│  Image:              │  ├─────────────────────────────┤   │
│  [1.jpg ▼]           │  │ 3 Baseline - Q - 2.jpg      │   │
│                      │  │   [↑][↓][✕]                 │   │
│  [➕ Add to Sequence]│  ├─────────────────────────────┤   │
│                      │  │ 4 Baseline - Q - 3.jpg      │   │
│  📋 Or Load Preset:  │  │   [↑][↓][✕]                 │   │
│  [Balanced Mix]      │  ├─────────────────────────────┤   │
│  [Eye-Track First]   │  │ 5 Manual LLM - S - 1.png    │   │
│  [Manual Focus]      │  │   [↑][↓][✕]                 │   │
│                      │  ├─────────────────────────────┤   │
│                      │  │ 6 Manual LLM - S - 2.png    │   │
│                      │  │   [↑][↓][✕]                 │   │
│                      │  └─────────────────────────────┘   │
│                      │            [🗑️ Clear All]          │
└──────────────────────┴─────────────────────────────────────┘
          [← Back]                 [Start Reading Sequence →]
```

### Execution Interface

```
┌────────────────────────────────────────────────────────────┐
│  Reading Sequence Progress        Step 3 of 6              │
│  [████████████░░░░░░░░░░░░░░░░░░░░░░░░] 50%              │
│  [1✓] [2✓] [3●] [4] [5] [6]                              │
└────────────────────────────────────────────────────────────┘
│                                                            │
│              [Picture being displayed]                     │
│                                                            │
│         Sequence Mode: 2.jpg                              │
│                                                            │
│                    [Next Step →]                           │
└────────────────────────────────────────────────────────────┘
```

---

## 💡 Tips & Best Practices

### Sequence Design

1. **Eye-tracking steps first** - Connect hardware once at the start
2. **Group by condition** - Minimize switching for smoother experience
3. **Vary activities** - Mix question and storytelling for engagement
4. **Consider fatigue** - Shorter sequences for younger children

### Recommended Sequences

**Short Test (3 steps):**
```
1. eye_assistance/question/1.jpg
2. base/question/2.jpg
3. assistance/storytelling/1.png
```

**Balanced Research (6 steps):**
```
1. eye_assistance/question/1.jpg
2. eye_assistance/storytelling/1.png
3. base/question/2.jpg
4. base/question/3.jpg
5. assistance/storytelling/1.png
6. assistance/question/4.jpg
```

**Full Coverage (9 steps):**
```
1. eye_assistance/question/1.jpg
2. eye_assistance/question/2.jpg
3. eye_assistance/storytelling/1.png
4. base/question/3.jpg
5. base/storytelling/2.png
6. base/question/4.jpg
7. assistance/question/5.jpg
8. assistance/storytelling/1.png
9. assistance/storytelling/2.png
```

---

## 🔧 Troubleshooting

### Eye-Tracking Not Working in Sequence

**Problem:** Eye tracker fails during sequence execution

**Solution:**
- The system tries to connect when first needed
- If it fails, you'll see an error screen
- Click "← Back to Sequence Builder" and try again
- Ensure Tobii hardware is connected before starting sequence

### Time Tracking Missing Sessions

**Problem:** Some sessions not recorded

**Solution:**
- Fixed! Sessions now properly end before new ones start
- Each image change creates a new session
- Check `backend/time_cache/` for all JSON files

### Manual Assistance Session Conflicts

**Problem:** Manual assistance not starting in sequence

**Solution:**
- `forceCleanup()` now properly cleans up previous sessions
- Backend allows session reuse
- Each step gets fresh session

---

## 📈 Data Analysis

After running sequences, you can analyze:

### Per-Image Analysis
```javascript
// backend/time_cache/{condition}_time_cache/{activity}/{image}.json
{
  "child_name": "Alice",
  "viewing_sessions": [
    { "session_id": "...", "duration_seconds": 45.2 },
    { "session_id": "...", "duration_seconds": 62.5 }  // If returned to same image
  ],
  "summary": {
    "total_sessions": 2,
    "total_duration_seconds": 107.7,
    "average_session_duration": 53.85
  }
}
```

### Research Questions Answered
- ✅ How long did children spend per condition?
- ✅ Which images held attention longer?
- ✅ Did assistance condition affect viewing time?
- ✅ How many times did children return to images?
- ✅ What's the average viewing time per condition?

---

## 🔗 Architecture Benefits

### Flexibility
- ✅ Any combination of conditions, activities, images
- ✅ Easy to add new conditions in future
- ✅ Reusable components (book components unchanged for traditional mode)

### Efficiency
- ✅ Eye-tracking connects **once** for entire sequence
- ✅ WebSocket stays open throughout
- ✅ Time tracking automatic and accurate
- ✅ Proper cleanup between steps

### Usability
- ✅ Visual sequence builder with drag-to-reorder
- ✅ Preset sequences for quick start
- ✅ Progress tracking during execution
- ✅ Can still use traditional single-condition mode

---

## 🎓 Next Steps

### For Researchers
1. Design sequences for your study
2. Save preset sequences in code
3. Run participants through sequences
4. Analyze time tracking data

### For Developers
1. Add more preset sequences
2. Add sequence validation (ensure images exist)
3. Add save/load sequence to file
4. Add analytics dashboard

---

## ✅ Verification Checklist

Before running a study, verify:

- [ ] Backend running: `http://localhost:8001/health`
- [ ] Frontend running: `http://localhost:3000`
- [ ] Eye tracker connected (if using eye-tracking steps)
- [ ] All images exist in `backend/pictures/`
- [ ] Time tracking directories created in `backend/time_cache/`
- [ ] Sequence tested end-to-end once

---

## 📞 Support

If you encounter issues:
1. Check browser console (F12) for errors
2. Check backend logs for error messages
3. Verify `docs/SEQUENCE_BUILDER_IMPACT_ANALYSIS.md` for architecture details
4. Test individual components in traditional mode first

---

**Implementation Status: ✅ COMPLETE**

All features implemented and tested. No linter errors. Ready for use!












