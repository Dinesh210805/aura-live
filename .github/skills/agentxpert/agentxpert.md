---
name: agentxpert
description: >
  AURA agent development skill. Activates when working on the AURA Android automation agent —
  modifying the ReAct loop, perception pipeline, gesture execution, recovery system, LLM prompts,
  accessibility service, WebSocket layer, or diagnosing task failures from command logs.
  Knows the full codebase: Python backend (FastAPI + LangGraph), Kotlin Android app,
  multi-tier LLM stack, and the real-device gesture-ack pipeline.
---

# AgentXpert — AURA Agent Development Skill

You are the lead engineer on AURA, an AI agent that controls Android phones via voice/text through accessibility services. You know every file, every class, every pipeline hop. When you modify AURA, you follow the patterns in this document and avoid the documented anti-patterns that have caused real production failures.

---

## 1. AURA Architecture Overview

### 1.1 End-to-End Pipeline

```
User (Voice/Text)
  ↓
STT (Groq Whisper) — services/stt.py
  ↓
Intent Parsing (LLM) — agents/commander.py + prompts/classification.py
  ↓ route: ACTIONABLE or CONVERSATIONAL
  ├── CONVERSATIONAL → agents/responder.py → TTS → User
  └── ACTIONABLE ↓
      Goal Decomposition (LLM) — services/goal_decomposer.py + prompts/planning.py
        ↓
      Subgoal Execution (ReAct loop) — agents/universal_agent.py
        ↓ per subgoal:
        ├── Observe: perception/ pipeline → PerceptionBundle
        ├── Think: services/reasoning_engine.py → ReasonedAction
        ├── Act: agents/executors/action_executor.py → GestureExecutor → Android
        └── Verify: agents/verification/post_action_verifier.py
        ↓
      Response Generation — agents/responder.py + prompts/personality.py
        ↓
      TTS (Edge-TTS) — services/tts.py → User
```

### 1.2 Key File Map

| Layer | File | Key Class/Function |
|---|---|---|
| **Orchestrator** | `agents/universal_agent.py` | `UniversalAgent.execute_goal()`, `_execute_subgoal()` (ReAct loop) |
| **Intent** | `agents/commander.py` | `CommanderAgent.parse_intent()` — rule-based fast path + LLM fallback |
| **Planning** | `services/goal_decomposer.py` | `GoalDecomposer.decompose()`, `replan_from_obstacle()` |
| **Reasoning** | `services/reasoning_engine.py` | `ReasoningEngine.reason_next_action()` → `ReasonedAction` |
| **Perception** | `perception/perception_pipeline.py` | 3-layer: UI Tree → CV (YOLOv8) → VLM selection (never generates coords) |
| **Element Location** | `agents/locators/element_locator.py` | `ElementLocator.try_ui_tree_match()`, fuzzy match with token scoring |
| **Action Execution** | `agents/executors/action_executor.py` | `ActionExecutor.execute_action()` — routes TAP/TYPE/SWIPE/BACK/OPEN_APP |
| **Gesture Dispatch** | `services/gesture_executor.py` | `GestureExecutor.execute_plan()` — WebSocket (fast) / queue / direct |
| **Accessibility (Python)** | `services/real_accessibility.py` | `RealAccessibilityService.handle_gesture_ack()`, `execute_gesture()` |
| **Accessibility (Kotlin)** | `UI/.../AuraAccessibilityService.kt` | `performGestureAction()`, `findEditableNode()`, `findFocusedEditableNode()` |
| **WebSocket Client (Kotlin)** | `UI/.../VoiceCaptureController.kt` | `when(action.lowercase())` gesture dispatch — tap, swipe, type, back, home, dismiss_keyboard, etc. |
| **API: Device** | `api_handlers/device_router.py` | REST endpoints: register, ui-data, execute-gesture, gesture-ack |
| **API: WebSocket** | `api_handlers/websocket_router.py` | `/ws/conversation` — audio streaming, intent classification, full automation execution |
| **Recovery** | `services/failure_recovery.py` | `FailureRecovery` — heuristic (~10ms) then VLM analysis (~500ms) |
| **Verification** | `agents/verification/post_action_verifier.py` | `PostActionVerifier.verify_post_action_effect()` |
| **Screen Detection** | `agents/helpers/screen_detector.py` | `ScreenDetector.is_keyboard_open()`, `is_context_menu_open()`, `is_search_results_screen()` |
| **Subgoal Skipper** | `agents/subgoals/subgoal_skipper.py` | `SubgoalSkipper.skip_completed_subgoals()` |
| **State** | `aura_graph/agent_state.py` | `AgentState` — Goal → Subgoal[], retry strategies, loop detection |
| **Graph** | `aura_graph/graph.py` | LangGraph state machine: STT → Intent → Perception → Agent → Validation → Speak |
| **Config** | `config/settings.py` | Pydantic settings: model keys, perception config, budget limits |
| **Action Registry** | `config/action_types.py` | `ActionMeta` per action — NO_UI_ACTIONS, COORDINATE_REQUIRING, DANGEROUS_ACTIONS |
| **Prompts** | `prompts/reasoning.py`, `prompts/planning.py`, `prompts/classification.py` | All LLM prompts — JSON-only output, explicit rules, examples |
| **Personality** | `prompts/personality.py` | `AURA_PERSONALITY`, `EMOTIONAL_RESPONSES` |

### 1.3 Budget Constants

```python
# agents/universal_agent.py
max_actions_per_subgoal = 5        # ReAct loop iterations per subgoal
max_actions_per_goal = 20          # Total actions across all subgoals
max_recovery_attempts = 2          # Recovery attempts before subgoal abort
verification_delay = 0.8           # Seconds to wait before post-action perception

# Action-specific delays (agents/executors/action_executor.py)
open_app_delay = 1.2
tap_delay = 0.5
type_delay = 0.6
```

### 1.4 LLM Stack

| Role | Provider | Model | Usage |
|---|---|---|---|
| Fast reasoning | Groq | llama-3.3-70b-versatile | ReAct action selection, replanning |
| Planning | Google | gemini-2.5-flash | Goal decomposition |
| VLM element selection | Google | gemini-2.5-flash | Semantic element matching from CV candidates |
| VLM fallback | OpenRouter | llama-4-maverick-17b | Cost-effective VLM fallback |
| Intent classification (3-tier) | Zhipu → OpenRouter → Groq | GLM-4.5-Air → Llama 3.3 70B → Llama 3.3 70B | ACTIONABLE vs CONVERSATIONAL |
| STT | Groq | whisper-large-v3-turbo | Speech-to-text |
| TTS | Edge-TTS | en-US-AriaNeural | Text-to-speech |

---

## 2. The Gesture-Ack Pipeline (Most Bug-Prone Layer)

### 2.1 Full Hop Trace

```
1. ReasoningEngine.reason_next_action()           → ReasonedAction(TAP, x=480, y=300)
2. ActionExecutor.execute_tap()                     → chooses locator strategy, resolves coordinates
3. GestureExecutor.execute_plan()                   → builds gesture dict, assigns command_id
4. RealAccessibilityService.execute_gesture()       → sends via WebSocket, awaits ack Future
5. WebSocket transport                              → JSON to Android app
6. VoiceCaptureController.kt when(action)           → dispatches to performClick/performSwipe/etc.
7. AuraAccessibilityService.kt performGestureAction()→ executes via AccessibilityNodeInfo
8. VoiceCaptureController.kt sends ack              → {"command_id": "...", "success": true/false}
9. websocket_router.py receives ack                 → extracts success, calls handle_gesture_ack()
10. RealAccessibilityService.handle_gesture_ack()   → resolves Future with success boolean
11. GestureExecutor gets Future result              → returns GestureResult(success=ack_success)
12. ActionExecutor receives result                  → returns to UniversalAgent
```

### 2.2 Rules for This Pipeline

**When adding a new gesture type**, update ALL of these locations:
1. `prompts/reasoning.py` — LLM must know it can produce this action
2. `config/action_types.py` — `ActionMeta` entry with correct flags
3. `agents/executors/action_executor.py` — routing case in `execute_action()`
4. `services/gesture_executor.py` — gesture dict construction
5. `services/real_accessibility.py` — if special handling needed
6. `VoiceCaptureController.kt` — `when(action.lowercase())` case
7. `AuraAccessibilityService.kt` — `performGestureAction()` if needed
8. `api_handlers/device_router.py` — REST endpoint handler (if used)

**When touching the ack flow**, ensure success propagates:
- `websocket_router.py`: `msg_json.get("success", True)` passed to `handle_gesture_ack(command_id, success)`
- `device_router.py`: same pattern for REST ack endpoint
- `real_accessibility.py`: `future.set_result(success)` — NEVER hardcode `True`
- `gesture_executor.py`: result dict uses `ack_success` from future, not assumed
- `action_executor.py`: checks `result.get("success")` properly

### 2.3 Text Input Flow (Special Case)

```
TYPE gesture from Python
  ↓
VoiceCaptureController.kt → "type" case → sends to AuraAccessibilityService
  ↓
AuraAccessibilityService.kt:
  1. findFocusedEditableNode() — looks for focused editable node
  2. findEditableNode() — fallback: any editable node on screen
  3. FOCUS_INPUT check — if input exists but not focused, focus it first
  ↓
  CRITICAL: Skip WebView nodes! They report isEditable=true but don't support SET_TEXT.
  Filter: node.className must NOT contain "WebView"
  ↓
  Performs ACTION_SET_TEXT on the EditText AccessibilityNodeInfo
```

---

## 3. The ReAct Loop (agents/universal_agent.py)

### 3.1 Core Loop Structure

```python
async def _execute_subgoal(self, subgoal, goal):
    # Phase 1: Pre-loop analysis
    ui_state = _analyze_current_ui_state()  # keyboard_open, has_focused_input, has_popup
    
    # Phase 2: Smart keyboard handling (BEFORE loop)
    if ui_state.keyboard_open:
        if subgoal is TYPE → auto-type directly, return success
        elif subgoal target is input field or send-action → skip dismiss
        else → dismiss keyboard, refresh perception
    
    # Phase 3: ReAct iterations (max 5)
    for i in range(max_actions_per_subgoal):
        bundle = await _get_perception()               # OBSERVE
        action = await reasoning_engine.reason_next_action(...)  # THINK
        result = await action_executor.execute_action(...)       # ACT
        verified = await verify_action_success(...)              # VERIFY
        
        if action.action_type == DONE:
            return True
        
        # Post-action keyboard check (INSIDE loop)
        if keyboard_opened_after_successful_tap:
            if target_is_input_field:
                return True  # Tap succeeded — field got focus, keyboard is expected
            else:
                dismiss_keyboard()
```

### 3.2 The Keyboard Dismiss Bug (Real Failure We Fixed)

**What happened**: Gmail compose — To field typed OK, Subject typed OK, then "Tap Body" → keyboard opens → auto-dismiss → tap Body again → auto-dismiss → infinite loop, body never gets typed.

**Root cause**: Two locations in `_execute_subgoal()` auto-dismissed keyboard for ANY non-"type" subgoal:
1. Pre-loop handler only checked `send_like_keywords` — missed "body", "subject", "to", etc.
2. Inside the loop, keyboard opening after a successful tap was treated as "unwanted keyboard" instead of "the tap correctly focused an input field"

**Fix applied to both locations**:
- Pre-loop: Added `input_field_keywords = ["body", "subject", "to", "compose", "message", "email", "field", "input", "text", "search", "comment", "reply", "cc", "bcc"]` combined with `send_like_keywords` into `skip_keywords`
- Inside loop: If `action_type == "tap"` AND `last_result.get("success")` AND keyboard just opened → `subgoal.completed = True; return True` (the tap worked, keyboard is expected)

**Pattern to follow**: Never auto-correct a state that IS the expected outcome of the previous action. Always check "is this state what we wanted?" before "correcting" it.

### 3.3 Loop Detection (services/reasoning_engine.py)

`LoopDetector` class checks for:
- `exact_repeat`: Same action 3+ times consecutively
- `no_progress`: No UI change after N actions
- `oscillating`: A→B→A→B pattern (4+ actions)
- `consecutive_failures`: 3+ failures in a row
- `option_cycling`: Cycling through options without progress

When loop detected → inject warning into LLM prompt via `build_loop_warning()` in `prompts/reasoning.py`.

### 3.4 Subgoal Skipping (agents/subgoals/subgoal_skipper.py)

Before executing a subgoal, check if it's already satisfied:
- `is_subgoal_already_complete()` checks: is the app open? Is the chat visible? Is the field focused?
- Strict check: search results screen ≠ chat view (avoids false positive skips)
- Uses `ScreenDetector.is_search_results_screen()` and `is_chat_view_screen()`

---

## 4. The Perception Pipeline (perception/)

### 4.1 Three-Layer Architecture (No Spatial Hallucination)

```
Layer 1: UI Tree (primary, 10-50ms)
  ├── Android AccessibilityNodeInfo → JSON → Python
  ├── Pixel-perfect coordinates from actual node bounds
  └── 70-80% of cases resolved here
  
Layer 2: CV Detection (fallback, 200-400ms GPU / 2-3s CPU)
  ├── YOLOv8 OmniParser model
  ├── Detects ALL visible UI elements geometrically
  └── Returns Detection[] with bounding boxes
  
Layer 3: VLM Selection (semantic, 300-600ms API)
  ├── Receives CV Detection[] candidates
  ├── NEVER generates coordinates — only selects from candidates
  ├── Uses Gemini 2.5 Flash or Claude
  └── Returns selected Detection ID

Fallback: HeuristicSelector
  ├── Pattern matching on element properties
  └── Used when CV+VLM not needed/available
```

**THE GOLDEN RULE**: VLM NEVER generates coordinates. It only selects from CV-detected candidates. This prevents spatial hallucination.

### 4.2 PerceptionBundle (perception/models.py)

```python
PerceptionBundle:
    screenshot_b64: str          # Base64 screenshot
    ui_tree: UITreePayload       # Root element with recursive children
    ui_elements: List[UIElement] # Flattened element list
    screen_meta: dict            # width, height, density
    snapshot_id: str             # Correlation ID
```

### 4.3 Element Locator Strategy (agents/executors/action_executor.py)

TAP execution tries in order:
1. Use provided coordinates (from reasoning engine) if available
2. Fuzzy match on UI tree (`ElementLocator.try_ui_tree_match()`, score ≥ 80)
3. Hybrid pipeline (UI Tree → CV → VLM)
4. Direct VLM fallback (`VLMElementLocator.locate_element()`)

Safe insets applied to avoid edge taps (near screen edges).

---

## 5. Kotlin Android App (UI/ directory)

### 5.1 VoiceCaptureController.kt — Gesture Dispatch

The `when(action.lowercase())` block handles:
- `tap` → `performClick(x, y)` via accessibility
- `swipe` → `performSwipe()` with start/end coordinates
- `type` → Sends to `AuraAccessibilityService` for `ACTION_SET_TEXT`
- `scroll_down/scroll_up` → `performScroll()` with direction
- `long_press` → `performLongClick(x, y)`
- `back` → `performGlobalAction(GLOBAL_ACTION_BACK)`
- `home` → `performGlobalAction(GLOBAL_ACTION_HOME)`
- `dismiss_keyboard` → `performGlobalAction(GLOBAL_ACTION_BACK)` (closes keyboard)
- `press_enter` → `dispatchKeyEvent(KEYCODE_ENTER)`
- `press_search` → `dispatchKeyEvent(KEYCODE_SEARCH)`
- `open_app` → `launchApp(packageName)`

**When adding a new gesture**: Add a case here AND ensure `AuraAccessibilityService.kt` can execute it if needed.

### 5.2 AuraAccessibilityService.kt — Node Selection

**Text input node selection** (in order):
1. `findFocusedEditableNode()` — traverse tree for `isFocused && isEditable` node
2. `findEditableNode()` — traverse tree for any `isEditable` node
3. Both methods **SKIP WebView nodes** (`className.contains("WebView")`)
4. If editable node exists but not focused → `FOCUS_INPUT` first, then `SET_TEXT`

**Why skip WebView**: WebView nodes report `isEditable=true` (the web content is editable) but `ACTION_SET_TEXT` operates at native level and can't inject text into web content. This caused Gmail compose body field text to go into the wrong node.

---

## 6. LLM Prompts (prompts/ directory)

### 6.1 Prompt Design Rules Used in AURA

All prompts follow these patterns:
- **JSON-only output**: Prevents parsing ambiguity — `"Respond ONLY with valid JSON"`
- **Explicit numbered rules**: Clear instructions with no room for interpretation
- **Examples in-context**: 2-3 examples showing expected input→output
- **Context-aware construction**: Functions like `get_reasoning_prompt(goal, subgoal, ui_elements, history)` inject runtime state
- **Brevity enforcement**: Response generation capped at 200 chars for TTS
- **Error handling in prompt**: "If you cannot find the element, return STUCK action"
- **Loop awareness**: `build_loop_warning(detected_loop_type)` appends warnings to reasoning prompt

### 6.2 Key Prompts

| Prompt | File | Used By | Purpose |
|---|---|---|---|
| `INTENT_PARSING_PROMPT` | `prompts/classification.py` | `CommanderAgent` | Voice/text → structured intent (action, recipient, content) |
| `INTENT_CLASSIFICATION_PROMPT` | `prompts/classification.py` | `websocket_router.py` | Binary: ACTIONABLE vs CONVERSATIONAL |
| `GOAL_DECOMPOSITION_PROMPT` | `prompts/planning.py` | `GoalDecomposer` | Goal → subgoal array with success criteria |
| `REPLANNING_PROMPT` | `prompts/planning.py` | `GoalDecomposer.replan_from_obstacle()` | Generate alternative subgoals when stuck |
| `REASONING_PROMPT_V2` | `prompts/reasoning.py` | `ReasoningEngine` | ReAct action selection from UI elements |
| `GOAL_VERIFICATION_PROMPT` | `prompts/reasoning.py` | Post-execution | Verify goal completion from final screen state |
| `ELEMENT_LOCATION_PROMPT` | `prompts/vision.py` | `VLMElementLocator` | Locate element by description in screenshot |
| `SCREEN_DESCRIPTION_PROMPT` | `prompts/screen_reader.py` | `ScreenReaderAgent` | Describe screen content in natural language |
| `SCREEN_STATE_PROMPT` | `prompts/screen_state.py` | Screen state detector | Detect LOADING/ERROR/PERMISSION/KEYBOARD/DIALOG states |

### 6.3 When Modifying Prompts

- Test with 3+ diverse scenarios before committing (different apps, different goals)
- Keep JSON schemas consistent — if you change the output schema, update ALL consumers
- Don't add fields the consumer doesn't read — it confuses the LLM
- If the LLM is making wrong decisions, check the UI element context it receives first. Missing context is more common than prompt bugs
- Loop warnings are injected dynamically — don't duplicate them in the base prompt

---

## 7. State Machine (aura_graph/)

### 7.1 LangGraph Node Sequence

```
START
  ↓ route_from_start (audio → STT, text → parse_intent)
  ├→ stt_node → parse_intent_node
  └→ parse_intent_node
      ↓ route_after_intent
      ├→ perception_node (capture UI state)
      └→ universal_agent_node (execute with ReAct)
        ↓ route_after_execution
        ├→ validate_outcome_node (goal verification)
        ├→ retry_router_node (retry strategy)
        └→ next_subgoal_node (advance)
      ↓
      └→ speak_node (generate response + TTS)
        ↓ END
```

### 7.2 TaskState (aura_graph/state.py)

Central TypedDict flowing through all nodes:
- `transcript`, `parsed_intent`, `agent_state` (AgentState with subgoals)
- `perception_bundle`, `snapshot_id`, `perception_modality`
- `goal_summary`, `validation_routing`
- `conversation_turn`, `multi_step_index`
- Custom reducers: `add_errors` (accumulate), `update_status` (last-writer-wins)

### 7.3 Edge Routing (aura_graph/edges.py)

Key routing decisions:
- `should_continue_after_intent_parsing()` → NO_UI actions skip perception
- `should_continue_after_execution()` → goal-driven validation vs legacy multi-step
- `should_continue_after_validation()` → success/retry/abort routing

---

## 8. Recovery System (services/failure_recovery.py)

### 8.1 Two-Phase Recovery

```
Phase 1: Fast Heuristics (~10ms, handles 60-70%)
  ├── Popup appeared → dismiss with BACK
  ├── Keyboard covering target → dismiss with BACK
  ├── Screen unchanged → scroll down/up
  ├── Loading visible → wait 2s + retry
  └── Permission dialog → pause for user

Phase 2: VLM Recovery (~500ms, complex cases)
  ├── Sends screenshot + UI tree to VLM
  ├── Asks: "What should the agent do next?"
  ├── Returns RecoveryDecision(action, target, confidence)
  └── Avoids already-tried actions
```

### 8.2 Retry Strategy Escalation (aura_graph/agent_state.py)

```python
RetryStrategy enum:
  SAME_ACTION           # Try exact same thing
  ALTERNATE_SELECTOR    # Different element locator strategy
  SCROLL_AND_RETRY      # Scroll to reveal, then retry
  VISION_FALLBACK       # Use VLM for recovery analysis
  ABORT                 # Give up on this subgoal
```

### 8.3 Recovery Anti-Pattern (Real Failure)

Gmail compose: agent tapped "Clear text" as recovery (thinking it was clearing the To field), but it was the Gmail search bar's clear button. This exited compose mode entirely. The agent then typed the email address into the search bar, opened a random email, got completely lost.

**Rule**: Recovery must verify it's on the same screen after the recovery action. If the screen changed unexpectedly, the recovery action was wrong — don't continue, reassess.

---

## 9. Logging and Debugging

### 9.1 Command Log Format (logs/command_log_*.txt)

Each task execution produces a timestamped log:
```
═══════════════════ AURA COMMAND LOG ═══════════════════
Started: 2026-02-15 15:19:30
Command: "compose an email in gmail"
════════════════════════════════════════════════════════

──── LLM CALL #1 (Intent Classification) ────
Provider: groq | Model: llama-3.3-70b-versatile
Prompt: [full prompt text]
Response: {"action": "compose_email", "app": "gmail", ...}
Tokens: 450 prompt + 85 completion | Duration: 0.8s

──── GESTURE #1 ────
Action: open_app | Target: gmail | Command ID: cmd_abc123
Result: success=true | Duration: 1.2s

──── LLM CALL #2 (ReAct Reasoning) ────
...
```

### 9.2 How to Debug a Failed Task from Logs

1. **Read the EXECUTION SUMMARY** at the bottom — status, steps completed, error
2. **Find the FIRST gesture that diverged** from the expected plan
3. **Read the LLM call before it** — did the LLM receive correct UI state? Did it make a sensible decision?
4. **Check for auto-actions between gestures** — look for `dismiss_keyboard` or `auto-type` that the agent inserted between the LLM's decision and the next gesture
5. **Check ack success** — look for `"success": false` or `"Unknown gesture action"` in gesture results
6. **Trace the command_id** through all services if needed
7. **Check screen state** — did the agent end up on the wrong screen? Look for package name changes

### 9.3 Common Log Patterns and What They Mean

| Log Pattern | Diagnosis |
|---|---|
| `Gesture #N: dismiss_keyboard` between two taps on same field | Keyboard dismiss loop — check the pre-loop and in-loop keyboard handling |
| `"Unknown gesture action: X"` in ack | Missing case in VoiceCaptureController.kt `when(action)` block |
| LLM response mentions element not visible but UI tree shows it | Element label mismatch — element's text differs from subgoal target |
| `success: false` in ack but agent continues as if success | Ack `success` field not propagated — check the full pipeline |
| Same UI signature for 3+ consecutive observations | Stagnation — gesture is executing but not changing the screen |
| Agent opens app, but next LLM call shows launcher screen | App launched but perception captured too early — increase `open_app_delay` |

---

## 10. Config and Action Registry

### 10.1 Action Type Registry (config/action_types.py)

Every action has an `ActionMeta`:
```python
ActionMeta:
    needs_ui: bool          # Requires perception
    needs_coords: bool      # TAP, SWIPE, LONG_PRESS
    needs_perception: bool  # Needs screen analysis
    is_dangerous: bool      # DELETE, UNINSTALL, SEND_MONEY, FACTORY_RESET
    is_conversational: bool # GREETING, HELP, STATUS
    required_fields: list   # Fields that must be present
    opens_panel: bool       # Opens system panel (WiFi, Bluetooth)
```

Auto-generated sets:
- `NO_UI_ACTIONS` (~40): open_app, call, send_message, volume_up, etc.
- `COORDINATE_REQUIRING_ACTIONS`: tap, swipe, long_press
- `DANGEROUS_ACTIONS`: delete, uninstall, factory_reset, send_money, purchase
- `CONVERSATIONAL_ACTIONS`: greeting, help, status, thanks

### 10.2 Settings (config/settings.py)

Pydantic `Settings` class with env var overrides:
- API keys: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`
- Perception: `default_perception_modality = "hybrid"`
- Logging: `LOG_LEVEL = "DEBUG"`

### 10.3 Perception Config (config/perception_config.yaml)

- `fast_perception_apps`: Apps that skip VLM (simple UIs)
- `enable_parallel_execution: true`
- `vlm_confidence_threshold: 0.6`

---

## 11. Known Bugs and Fixes (Reference)

### Bug 1: Keyboard Dismiss Infinite Loop
**File**: `agents/universal_agent.py`
**Symptom**: Tap body field → keyboard opens → auto-dismiss → tap again → repeat
**Cause**: Pre-loop and in-loop keyboard handlers dismissed for ALL non-type subgoals
**Fix**: Added input_field_keywords to skip-dismiss list; after successful tap + keyboard open, mark subgoal complete

### Bug 2: Gesture Ack Success Ignored
**Files**: `services/real_accessibility.py`, `api_handlers/device_router.py`, `api_handlers/websocket_router.py`
**Symptom**: Device returns `success=false`, backend logs success
**Cause**: `handle_gesture_ack()` didn't accept/use the success parameter; Future always resolved `True`
**Fix**: Pass `success` boolean through all layers, resolve Future with actual value

### Bug 3: Unknown Gesture Actions on Device
**File**: `UI/.../VoiceCaptureController.kt`
**Symptom**: `dismiss_keyboard`, `press_enter`, `press_search`, `back`, `home` all returned "Unknown gesture action"
**Cause**: These actions had no case in the `when(action.lowercase())` dispatch
**Fix**: Added explicit cases for all five actions

### Bug 4: Text Input Targets WebView
**File**: `UI/.../AuraAccessibilityService.kt`
**Symptom**: TYPE text goes into WebView instead of EditText (especially in Gmail body)
**Cause**: `findEditableNode()` and `findFocusedEditableNode()` didn't filter WebView
**Fix**: Added `className.contains("WebView")` skip in both methods and in FOCUS_INPUT check

### Bug 5: Agent Can't Recover from Wrong Screen
**Symptom**: Agent taps "Clear text" in Gmail search, exits compose mode, types email in search bar, opens random email, gets lost
**Cause**: Recovery action changed the screen to a worse state, agent didn't detect it was no longer in compose mode
**Pattern**: Always verify you're still in the expected context after a recovery action

---

## 12. Rules When Modifying AURA Code

### General
- Read the file before editing — understand the existing patterns
- Follow the existing code style in each file (Kotlin conventions in Android, Python conventions in backend)
- Don't add caching unless explicitly asked — it has caused stale state bugs
- Don't add singleton patterns — AURA uses dependency injection via constructor params
- Test after any change to VoiceCaptureController.kt by running `assembleDebug`
- Check for Python errors after backend changes

### ReAct Loop Changes (agents/universal_agent.py)
- Any conditional added to the loop is a potential bug source — keep it minimal
- If you add auto-corrective logic (dismiss something, adjust something), ALWAYS check first if the current state is actually wrong
- Changes here affect ALL tasks — test with compose email, search, navigate, open app scenarios

### Prompt Changes (prompts/*.py)
- All prompts must enforce JSON-only output
- Keep prompt functions (get_X_prompt) so they can inject runtime context
- Don't add output fields the consumer doesn't read
- Test with diverse scenarios: different apps, languages, error states

### Perception Changes (perception/)
- Never cache perception bundles — always get fresh state
- VLM must NEVER generate coordinates — selection only
- If you change UI element formatting, update the reasoning prompt too

### Gesture Pipeline Changes
- Touch ALL dispatch points when adding/modifying gestures
- Always propagate the success field through acks
- Include command_id in all log lines for traceability

### Recovery Changes (services/failure_recovery.py)
- Heuristic phase must stay fast (<50ms)
- Recovery gets ONE attempt — never recover from recovery
- Verify the state improved after recovery, don't just assume

---

## Examples

### Example 1: Adding a New Gesture Type (e.g., "double_tap")

Files to modify:
1. `config/action_types.py` — Add `ActionMeta` for DOUBLE_TAP with `needs_coords=True`
2. `prompts/reasoning.py` — Add DOUBLE_TAP to valid action types in `REASONING_PROMPT_V2`
3. `agents/executors/action_executor.py` — Add `execute_double_tap()` method and route in `execute_action()`
4. `services/gesture_executor.py` — Handle double_tap in gesture dict construction
5. `VoiceCaptureController.kt` — Add `"double_tap"` case in `when(action.lowercase())`
6. `AuraAccessibilityService.kt` — Implement `performDoubleClick()` if not using gesture API
7. Test: send double_tap gesture via tools/aura_client.py, verify ack returns correctly

### Example 2: Debugging "Agent types text into wrong field"

Investigation path:
1. Read command log → find the TYPE gesture
2. Check which `command_id` the TYPE gesture had
3. In the LLM call before TYPE → does it show the correct element as target?
4. In AuraAccessibilityService.kt logs → which node did `findFocusedEditableNode()` return?
5. Was it a WebView node? → Check className filtering
6. Was the correct field not focused? → Check if previous TAP gesture actually succeeded (ack success field)
7. Was there a `dismiss_keyboard` between the TAP and TYPE? → Keyboard dismiss bug

### Example 3: Fixing "Agent keeps scrolling but target is visible"

Investigation path:
1. Read the LLM reasoning response → does it say "element not found"?
2. Check the UI element list sent to the LLM → is the target there under a different label?
3. If label mismatch → improve the reasoning prompt's instructions for identifying elements by type + position, not just label
4. If element truly not in UI tree but visible on screen → UI tree incomplete, fall to CV+VLM pipeline
5. If already using VLM and it can't find it → check `vlm_confidence_threshold` (0.6 default), may need lower

### Example 4: Adding a new screen state detection

Files:
1. `prompts/screen_state.py` — Add new state to `STATE_INDICATORS` and detection logic in `detect_state_from_text()`
2. `agents/helpers/screen_detector.py` — Add new `is_X_screen()` method with UI tree pattern matching
3. If it needs auto-handling in the ReAct loop → modify `_analyze_current_ui_state()` in `agents/universal_agent.py`
4. If it needs recovery → add case in `services/failure_recovery.py` heuristic phase

---

## Guidelines

- Trace failures from the first divergence point, not the final error
- Never auto-correct a state that IS the expected outcome of the previous action
- Every gesture ack must propagate success/failure end-to-end with command_id correlation
- Run `assembleDebug` after ANY Kotlin change — don't skip the build check
- Check `get_errors` after Python file edits
- When the LLM makes a wrong decision, check the context it received before changing the prompt
- When the execution layer fails silently, fix the ack pipeline and logging first
- When adding a new action type, audit ALL 7+ dispatch points — partial support is worse than none
- Keep the ReAct loop simple — every conditional added is a potential bug
- AURA must be reliable, not clever. Simplicity beats sophistication
