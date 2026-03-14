# Intelligent Agent Architecture

## The Problem We Solved

**Old approach (dumb step splitting):**
```
"open spotify and play my liked songs"
  ↓ Commander splits into steps
  Step 1: open_app (spotify) ✅
  Step 2: play_song (???) ❌ No idea where liked songs are!
```

**New approach (intelligent reasoning):**
```
"open spotify and play my liked songs"
  ↓ Commander recognizes complex goal
  Intent: open_app with parameters.goal="play_liked_songs"
  ↓ Routes to UniversalAgent
  ↓ UniversalAgent reasons:
    1. App opened ✓
    2. Need to find "Library" tab (VLM locates it)
    3. Tap Library
    4. Find "Liked Songs" (VLM locates it)
    5. Tap Liked Songs
    6. Validate playback started
```

## Key Changes

### 1. Commander: Recognize Complex Goals
**File:** `agents/commander.py`

Instead of splitting into steps, encode the goal in parameters:
- ❌ Old: `{"action": "open_app", "steps": [{"action": "play_song"}]}`
- ✅ New: `{"action": "open_app", "parameters": {"goal": "play_liked_songs"}}`

### 2. Routing: Detect Complex Parameters
**File:** `aura_graph/edges.py`

```python
# Check for complex parameters that indicate reasoning is needed
has_complex_params = any(key in intent_params for key in 
    ["goal", "target_section", "type", "content_type", "visual_reference"])

if has_complex_params:
    # Route to perception → UniversalAgent
    return "perception"
```

### 3. Action Registry: App-Specific Actions
**File:** `config/action_types.py`

Added actions that need intelligent UI reasoning:
- `play_song`: Navigate to music/playlists
- `play_video`: Find and play videos
- `find_content`: Search for specific content
- `navigate_app`: Go to app sections
- `app_action`: Generic app-specific action

### 4. UniversalAgent: The Brain
**Capabilities:**
- **ReasoningEngine**: "To play liked songs, I need Library → Liked Songs"
- **VLMElementLocator**: Uses vision to find "Library" tab, "Liked Songs" text
- **GestureExecutor**: Taps elements via accessibility API
- **Self-validation**: Checks if action worked, retries if needed

## Example Flows

### "Open Spotify and play my liked songs"
```
1. Commander Parse:
   {
     "action": "open_app",
     "recipient": "spotify",
     "parameters": {
       "goal": "play_liked_songs",
       "target_section": "library"
     }
   }

2. Routing Check:
   - Has complex params? YES (goal, target_section)
   - Route to: perception → universal_agent

3. Perception:
   - Capture Spotify UI (screenshot + UI tree)
   - Returns PerceptionBundle

4. UniversalAgent Reasoning:
   - Goal: Play liked songs in Spotify
   - Current UI: Spotify home screen
   - Plan:
     a. Find "Library" tab using VLM
     b. Tap Library
     c. Find "Liked Songs" using VLM
     d. Tap Liked Songs
     e. Validate playback started

5. Execution:
   - Tap Library → verify UI changed
   - Tap Liked Songs → verify playback started
   - ✅ Success
```

### "Find my profile on Instagram"
```
1. Commander Parse:
   {
     "action": "find_content",
     "recipient": "instagram",
     "parameters": {
       "content_type": "profile"
     }
   }

2. Route to UniversalAgent (has content_type param)

3. UniversalAgent:
   - Sees Instagram UI
   - Locates profile icon (bottom right)
   - Taps it
   - ✅ Profile opened
```

## When UniversalAgent is Used

**Triggers:**
1. Action in `COORDINATE_REQUIRING_ACTIONS` (tap, swipe, etc.)
2. Action has complex parameters:
   - `goal`: High-level objective
   - `target_section`: App section to navigate to
   - `type`: Content type (liked_songs, trending, etc.)
   - `content_type`: What to find
   - `visual_reference`: Needs vision to understand

**Settings:**
- `USE_UNIVERSAL_AGENT=true` (default enabled)

## Benefits

✅ **Context-aware**: Knows app layouts (Library tab has liked songs)  
✅ **Visual reasoning**: Uses VLM to actually SEE the UI  
✅ **Adaptive**: Works across different app versions  
✅ **Self-correcting**: Validates actions worked, retries if needed  
✅ **No brittle scripts**: No hardcoded coordinates or element IDs  

## Architecture

```
User: "open spotify and play liked songs"
  ↓
Commander (LLM): Parse intent with goal parameter
  ↓
Route: Complex params? → perception
  ↓
Perception: Capture UI (VLM + accessibility)
  ↓
Route: Has params + use_universal_agent? → universal_agent
  ↓
UniversalAgent:
  ├─ ReasoningEngine: Break goal into steps
  ├─ VLMElementLocator: Find elements visually
  ├─ GestureExecutor: Execute via accessibility API
  └─ Validator: Check if it worked
  ↓
✅ Success: Music playing!
```

## The Power of "Eyes and Hands"

**Eyes (VLM + UI Tree):**
- Screenshot: Visual appearance
- UI tree: Structure, text, bounds
- VLM: Semantic understanding ("Library" means music collection)

**Hands (Accessibility API):**
- Tap elements by coordinates
- Type text into fields
- Scroll, swipe, long-press
- Navigate system UI

**Brain (UniversalAgent):**
- Understands goal: "play liked songs"
- Knows domain: "Spotify has Library → Liked Songs"
- Plans actions: Navigate to Library, find playlist, tap it
- Validates outcome: Check if playback started
- Adapts: If not found, scroll and try again

No more dumb step-by-step scripts. **Real intelligence.**
