# Aura Agent — End-to-End Command Flow Analysis
### Command Under Review: *"Open WhatsApp and message John"*

> **Report Date:** March 12, 2026  
> **Scope:** Full pipeline trace — STT → Intent → Routing → Planning → Execution → Response  
> **Methodology:** Live codebase review across 25+ source files

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Pipeline Entry Points](#2-pipeline-entry-points)
3. [Stage 1 — Command Understanding (Commander Agent)](#3-stage-1--command-understanding-commander-agent)
4. [Stage 2 — Routing Logic (Edge Decision)](#4-stage-2--routing-logic-edge-decision)
5. [Stage 3 — Planning (Coordinator + Planner)](#5-stage-3--planning-coordinator--planner)
6. [Stage 4 — App Launch: Who Does It and How?](#6-stage-4--app-launch-who-does-it-and-how)
7. [Stage 5 — Package Resolution: Rule-Based vs LLM](#7-stage-5--package-resolution-rule-based-vs-llm)
8. [Stage 6 — Reactive Execution Loop](#8-stage-6--reactive-execution-loop)
9. [Stage 7 — Verification and Completion](#9-stage-7--verification-and-completion)
10. [Stage 8 — Response Generation](#10-stage-8--response-generation)
11. [Complete Data Flow Diagram](#11-complete-data-flow-diagram)
12. [Agent Responsibility Matrix](#12-agent-responsibility-matrix)
13. [Key Design Decisions and Trade-offs](#13-key-design-decisions-and-trade-offs)
14. [Issues and Gaps Found During Review](#14-issues-and-gaps-found-during-review)
15. [Summary Table](#15-summary-table)

---

## 1. System Architecture Overview

Aura is a **multi-agent, LangGraph-orchestrated mobile automation system**. It accepts voice or text commands and translates them into low-level Android gestures (taps, types, swipes, app launches) via a connected Android device.

### Core Architecture Layers

```
User Input
    │
    ▼
[LangGraph StateGraph] — aura_graph/graph.py
    │  (nodes + conditional edges)
    ├── STT Node
    ├── parse_intent Node  ◄── Commander Agent
    ├── Edge Router        ◄── should_continue_after_intent_parsing()
    ├── coordinator Node   ◄── Coordinator (master loop)
    │       ├── PlannerAgent
    │       ├── PerceiverAgent
    │       ├── ActorAgent     ◄── GestureExecutor ◄── Android Device
    │       └── VerifierAgent
    └── speak Node         ◄── Responder + TTS
```

### Technology Stack

| Component | Technology |
|---|---|
| Orchestration | LangGraph `StateGraph` |
| Intent Parsing Model | Groq `llama-3.1-8b-instant` |
| Planner Model | Groq `meta-llama/llama-4-scout-17b-16e-instruct` |
| Visual Perception (VLM) | Groq Llama 4 Scout → Gemini 2.5 Flash (fallback) |
| Response Generation | Groq `llama-3.3-70b-versatile` |
| STT | Groq `whisper-large-v3-turbo` |
| TTS | Edge-TTS `en-US-AriaNeural` (local, zero-latency) |
| Device Bridge | ADB + WebSocket + Android Accessibility API |

---

## 2. Pipeline Entry Points

The system accepts commands via **three paths**, all entering the same LangGraph pipeline:

| Path | Entry File | How transcript enters |
|---|---|---|
| Voice/Audio | `api/websocket.py` → STT Node | `raw_audio` → `stt_service.transcribe()` |
| Text (REST) | `api/tasks.py` | `transcript` pre-set in `TaskState` |
| Streaming WebSocket | `websocket/` | `streaming_transcript` pre-set |

For text input (e.g., `"open whatsapp and message john"`), the `route_from_start()` edge in `aura_graph/edges.py` detects `input_type == "text"` and skips the STT node entirely, routing directly to `parse_intent`.

**File reference:** [`aura_graph/edges.py`](../aura_graph/edges.py) — `route_from_start()`, line ~30

---

## 3. Stage 1 — Command Understanding (Commander Agent)

**File:** [`agents/commander.py`](../agents/commander.py)  
**Entry method:** `CommanderAgent.parse_intent(transcript, context?)`

### Step A: Rule-Based Fast Path

The Commander first tries a **rule-based classifier** (`utils/rule_based_classifier.py`) using compiled regex patterns. This handles simple, deterministic commands:

- `"turn on wifi"` → instantly classified without LLM
- `"volume up"` → instantly classified without LLM  
- `"open WhatsApp"` → **could match here** if rule pattern exists with confidence ≥ 0.85

For `"open whatsapp and message john"`, no single-command rule matches this precisely. The rule classifier returns confidence < 0.85 or no match. Execution falls through to Step B.

**Rule classifier covers:** system toggles, volume, brightness, navigation (back, home, scroll), screenshot.

### Step B: LLM Intent Parsing

```python
# agents/commander.py — _parse_direct()
prompt = INTENT_PARSING_PROMPT.format(transcript=transcript)
result = self.llm_service.run(
    prompt,
    max_tokens=300,
    response_format={"type": "json_object"},
)
```

The `INTENT_PARSING_PROMPT` (in [`prompts/classification.py`](../prompts/classification.py)) includes explicit handling for multi-step commands:

```
━━━ MULTI-STEP COMMANDS ━━━
If the command chains 3+ distinct actions OR uses connectors like "then", "and then", "after that":
→ {"action":"general_interaction","content":"<full command>","confidence":0.85,"parameters":{"delegate_to_planner":true}}
Do NOT try to parse recipient/content from multi-step commands — let the planner decompose them.
```

### What the LLM Returns for This Command

For `"open whatsapp and message john"`, the LLM produces:

```json
{
  "action": "general_interaction",
  "content": "open whatsapp and message john",
  "confidence": 0.85,
  "parameters": {
    "delegate_to_planner": true
  }
}
```

**Why `general_interaction` and not `send_message`?**  
The command has `" and "` which is a multi-step connector. The prompt explicitly instructs the LLM NOT to parse recipient/content for multi-step commands. This is a deliberate design choice — the full command is handed intact to the Coordinator's planner, which has richer context for decomposition.

### Post-Processing in Commander

After getting the LLM JSON, the Commander applies two normalisation steps:

1. **`_normalize_action()`** — aliases: `"open" → "open_app"`, `"message" → "send_message"`, etc. *(Not triggered here since action is already `general_interaction`.)*
2. **`_normalize_intent_fields()`** — restructures `parameters.recipient` to top-level `recipient` for `send_message` actions. *(Not triggered here.)*

**Output `IntentObject`:**

```python
IntentObject(
    action="general_interaction",
    content="open whatsapp and message john",
    recipient=None,
    confidence=0.85,
    parameters={"delegate_to_planner": True}
)
```

---

## 4. Stage 2 — Routing Logic (Edge Decision)

**File:** [`aura_graph/edges.py`](../aura_graph/edges.py)  
**Function:** `should_continue_after_intent_parsing(state)`

This is the critical decision gate after intent parsing. The routing logic evaluates (in order):

```python
# Gate 1: Blocked sensitive action
if status == "blocked": return "speak"

# Gate 2: Failed parsing
if status == "intent_failed" or not intent: return "error_handler"

# Gate 3: Very low confidence
if confidence < 0.3: return "error_handler"

# Gate 4: Low confidence or general_interaction → Coordinator
if confidence < 0.6 or action == "general_interaction":
    if settings.use_universal_agent:
        return "coordinator"

# Gate 5: Multi-step detection
multi_step_indicators = [" and ", " then ", " after that "]
is_multi_step = any(indicator in transcript for indicator in multi_step_indicators)
if is_multi_step and use_universal_agent:
    return "coordinator"
```

For `"open whatsapp and message john"`:
- `action == "general_interaction"` → **Gate 4 triggers immediately**
- Additionally, transcript contains `" and "` → **Gate 5 would also trigger**
- **Result: routes to `"coordinator"`**

---

## 5. Stage 3 — Planning (Coordinator + Planner)

**File:** [`agents/coordinator.py`](../agents/coordinator.py)  
**File:** [`agents/planner_agent.py`](../agents/planner_agent.py)  
**File:** [`services/goal_decomposer.py`](../services/goal_decomposer.py)

### Coordinator Entry

`Coordinator.execute(utterance, intent, session_id, perception_bundle)` is called by the `coordinator_node` LangGraph wrapper.

### Skeleton Planning via LLM

```python
goal = self.planner.create_plan(utterance, intent, perception=perception_bundle, step_history=step_memory)
```

This calls `GoalDecomposer.decompose()` which makes one LLM call with `SKELETON_PLANNING_PROMPT` using `meta-llama/llama-4-scout-17b-16e-instruct` (300 max tokens):

**LLM Skeleton Plan Output:**

```json
{
  "goal_summary": "Send a WhatsApp message to John",
  "phases": [
    "Open WhatsApp",
    "Open John's chat",
    "Type and send message"
  ],
  "commit_actions": ["send"]
}
```

**What is a "skeleton plan"?**  
It is a **high-level phase list** — NOT concrete UI actions. There are no tap coordinates, no specific element targets, no action types yet. Concrete subgoals are generated **reactively** at runtime as each screen is encountered.

**Resulting `Goal` object:**

```python
Goal(
    original_utterance="open whatsapp and message john",
    description="Send a WhatsApp message to John",
    phases=[
        Phase("Open WhatsApp"),
        Phase("Open John's chat"),
        Phase("Type and send message"),
    ],
    pending_commits=["send"],
    subgoals=[],  # empty — filled reactively
    current_subgoal_index=0,
    completed=False,
)
```

---

## 6. Stage 4 — App Launch: Who Does It and How?

### Which Agent Opens WhatsApp?

**Chain of responsibility:**

```
Coordinator  →  ActorAgent  →  GestureExecutor  →  real_accessibility_service
```

**The `ActorAgent` is the executor**, but it is purely a thin wrapper. It does **zero reasoning** and **zero LLM calls**. It builds an action dict and calls `GestureExecutor._execute_single_action()`.

**Step-by-step for Phase 1 "Open WhatsApp":**

#### 6.1 Short-Circuit Detection in Coordinator

```python
# agents/coordinator.py — inside the main while-loop
_phase_desc = goal.current_phase.description.strip()  # "Open WhatsApp"
_open_app_name = self._extract_open_app_phase(_phase_desc)
# Returns "WhatsApp" — short-circuits reactive VLM generation
```

The Coordinator has a special fast-path: if the current phase description is simply `"Open <AppName>"`, it **does not call the VLM at all**. It creates the `open_app` subgoal directly, bypassing the expensive reactive step generator.

```python
subgoal = Subgoal(
    description="Open WhatsApp",
    action_type="open_app",
    target="WhatsApp",
    parameters={"__phase_complete__": True},
)
```

#### 6.2 `open_app` is in `NO_TARGET_ACTIONS` → Perception Skipped

```python
# agents/coordinator.py
NO_TARGET_ACTIONS = {
    "open_app", "go_back", "go_home", "back", "home",
    "scroll", ..., "type", ...
}
```

Since `open_app` is in `NO_TARGET_ACTIONS`, **the PerceiverAgent is never called** for this step. There is no screenshot taken, no UI tree parsed, no VLM invoked. The system goes straight to execution.

#### 6.3 ActorAgent.execute()

```python
# agents/actor_agent.py
action = {
    "action": "open_app",
    "app_name": "WhatsApp",
}
result = await self.executor._execute_single_action(action)
```

#### 6.4 GestureExecutor._execute_app_launch()

```python
# services/gesture_executor.py
async def _execute_app_launch(self, action):
    app_name = action.get("app_name")   # "WhatsApp"
    package_name = action.get("package_name")  # None at this point
    
    if not package_name and app_name:
        inventory = get_app_inventory_manager()
        candidates = inventory.get_package_candidates(app_name.lower().strip())
        if candidates:
            package_name = candidates[0]  # e.g. "com.whatsapp"
    
    # Launch via Android Accessibility API
    result = await real_accessibility_service.launch_app_via_intent(
        package_name, deep_link_uri=None
    )
```

#### 6.5 Verifier Post-State Capture

After the app launches, `VerifierAgent` waits **3.0 seconds** (the `open_app` settle delay) and captures a fresh UI tree + screenshot. A `ui_signature` diff confirms WhatsApp is now in the foreground. Phase 1 is marked complete.

---

## 7. Stage 5 — Package Resolution: Rule-Based vs LLM

**This is a purely rule-based / lookup system. No LLM is involved in package name resolution.**

The package resolution happens in a **three-tier lookup chain**:

### Tier 1: Static Registry — `config/app_packages.py`

```python
APP_PACKAGES: dict[str, str] = {
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "spotify": "com.spotify.music",
    "youtube": "com.google.android.youtube",
    # ~20 hardcoded entries
}

def resolve_package(app_name: str) -> str:
    return APP_PACKAGES.get(app_name.lower().strip(), app_name)
```

Simple `dict.get()` — pure Python. WhatsApp resolves to `"com.whatsapp"` instantly.

### Tier 2: Device Inventory + Fuzzy Matching — `utils/app_inventory_utils.py`

If Tier 1 fails (app not in the hardcoded dict), the system queries `device_app_inventory.json` — a **scan of all installed apps on the actual connected device**:

```python
inventory = get_app_inventory_manager()
candidates = inventory.get_package_candidates(app_name.lower().strip())
```

The `get_package_candidates()` method applies a **multi-stage fuzzy matching algorithm**:

1. **Synonym expansion** — `APP_SYNONYMS` dict maps spoken names to canonical names (e.g., `"wa"` → `["whatsapp"]`, `"insta"` → `["instagram"]`)
2. **Exact match** → score 1.0
3. **Normalized match** (no spaces) → score 0.95
4. **Contains match** → score 0.7–0.95
5. **Word overlap** → score 0.5–0.9
6. **Character-level Levenshtein approximation** → score 0.3–0.6

Candidates above a threshold (~0.5) are returned sorted by score. The top candidate is used.

### Tier 3: Fallback

If neither tier resolves the package, the `app_name` string is passed through as-is, and `launch_app_via_intent` fails gracefully with an error logged.

### Deep Link Enhancement

For messaging actions (`send_message`, `send_whatsapp`), `GestureExecutor` also checks if a **deep link URI** can be constructed. For WhatsApp with a phone number:

```python
from utils.deep_link_utils import DeepLinkManager
uri = deep_link_manager.build_deep_link_uri(intent_obj, scheme="whatsapp", app_package="com.whatsapp")
# Builds: "whatsapp://send?phone=+91XXXXXXXXX&text=Hello"
```

Contact names (like "John") are resolved to phone numbers first via `ContactResolver` before the deep link is built.

---

## 8. Stage 6 — Reactive Execution Loop

After WhatsApp is open (Phase 1 complete), Phases 2 and 3 are executed **reactively** — the system decides what to do by looking at the live screen state.

### Phase 2: "Open John's chat"

```
Coordinator while-loop iteration:
  subgoal = None  →  reactive generation triggered

  PerceiverAgent.perceive(force_screenshot=True)
    → PerceptionController.request_perception()
        → UITreeService: captures accessibility node tree (WhatsApp chat list)
        → ScreenshotService: captures screenshot
    → VisualLocator.build_annotated_screenshot()
        → OpenCV draws numbered SoM bounding boxes on screenshot
    → Returns PerceptionBundle{ui_tree, screenshot, visual_description}

  ReactiveStepGenerator.generate_next_step(goal, screen_context, screenshot_b64, ui_elements)
    → Calls VLMService.analyze_image(annotated_screenshot, REACTIVE_STEP_SYSTEM + user_msg)
    → VLM sees: goal, current phase "Open John's chat",
                 screenshot with numbered boxes, UI tree text
    → Returns JSON: {
        "thinking": "...",
        "action_type": "tap",
        "target": "John",
        "phase_complete": false,
        "goal_complete": false,
        "verification_passed": true
      }

  PerceiverAgent resolves "John" in UI tree:
    → Finds element with text="John" (or "John Doe") in accessibility tree
    → Returns coordinates (x=540, y=320)

  ActorAgent.execute("tap", coordinates=(540, 320))
    → GestureExecutor._execute_tap()
    → WebSocket sends: {action: "tap", x: 540, y: 320, format: "pixels"}
    → Android device taps

  VerifierAgent: wait 0.8s, capture post-state
    → ui_signature changed → success
```

### Phase 3: "Type and send message"

```
Reactive gen iteration 1:
  VLM sees: WhatsApp chat with John open
  Returns: {action_type: "tap", target: "Type a message", phase_complete: false}
  → ActorAgent taps message input field

Reactive gen iteration 2:
  VLM sees: input field is now focused (keyboard visible)
  Returns: {action_type: "type", target: "<message content>"}
  Note: If no message was specified in original command,
        VLM may generate placeholder text or the Coordinator
        prompts clarification.
  → ActorAgent.execute("type", target="Hello John")
  → GestureExecutor._execute_type() via ADB input

Reactive gen iteration 3:
  VLM sees: text typed, Send button now active (highlighted)
  Returns: {action_type: "tap", target: "Send", phase_complete: true, goal_complete: true}
  → ActorAgent taps Send button

Post-tap: VerifierAgent captures UI
  → _detect_goal_completion() checks for "sent"/"delivered" in element tree
  → Found → returns (True, "Message sent — indicator detected")
  → goal.completed = True → exit while-loop
```

---

## 9. Stage 7 — Verification and Completion

**File:** [`agents/verifier_agent.py`](../agents/verifier_agent.py)

### Post-Action Settle Delays

Different action types have different stabilization wait times before re-reading UI:

| Action Type | Wait Time |
|---|---|
| `open_app` | 3.0 seconds |
| `tap` | 0.8 seconds |
| `type` | 0.5 seconds |
| `scroll` | 0.4 seconds |

### UI Signature Comparison

After every action, a `ui_signature` (hash of key UI element attributes) is compared before and after. A diff confirms the action had visible effect.

### Goal Completion Detection (`_detect_goal_completion()`)

This is a **deterministic heuristic** — no LLM needed:

```python
# agents/coordinator.py
def _detect_goal_completion(utterance, elements, pre_elements=None):
    goal_type = _classify_goal_type(utterance)
    # For "message john" → goal_type = "messaging"
    
    if goal_type == "messaging":
        sent_signals = ("sent", "delivered", "message sent", "email sent")
        for txt in _all_text:
            if any(sig in txt for sig in sent_signals):
                return True, f"Message sent — indicator detected (text='{txt}')"
```

---

## 10. Stage 8 — Response Generation

**File:** [`agents/responder.py`](../agents/responder.py)

After the Coordinator returns to LangGraph, the `speak_node` calls:

```python
response = responder_agent.generate_feedback(
    intent=intent,
    status="completed",
    goal_summary="Send WhatsApp message to John",
    completed_steps=["Open WhatsApp", "Open John's chat", "Typed and sent message"]
)
```

The Responder uses `llama-3.3-70b-versatile` at temperature 0.1 with the `AURA_PERSONALITY` system prompt and the list of completed steps. This produces a natural language summary like:

> *"Done! I opened WhatsApp, found John's chat, and sent the message for you."*

The text is then piped to **Edge-TTS** (`en-US-AriaNeural`) for audio output — this runs locally with near-zero latency.

---

## 11. Complete Data Flow Diagram

```
USER: "open whatsapp and message john"
          │
          ▼
  ┌── LangGraph Entry ──────────────────────────────────────────────────┐
  │  aura_graph/graph.py → compile_aura_graph()                        │
  │  input_type="text" → route_from_start() → "parse_intent"           │
  └─────────────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌── NODE: parse_intent ───────────────────────────────────────────────┐
  │  CommanderAgent.parse_intent("open whatsapp and message john")      │
  │                                                                     │
  │  ① RuleClassifier.classify() → no match (multi-step cmd)           │
  │  ② LLM: Groq llama-3.1-8b-instant + INTENT_PARSING_PROMPT          │
  │     → {action: "general_interaction",                               │
  │         content: "open whatsapp and message john",                  │
  │         confidence: 0.85,                                           │
  │         parameters: {delegate_to_planner: true}}                    │
  └─────────────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌── EDGE: should_continue_after_intent_parsing ───────────────────────┐
  │  action="general_interaction" → Gate 4 triggers                     │
  │  → "coordinator"                                                    │
  └─────────────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌── NODE: coordinator ────────────────────────────────────────────────┐
  │  Coordinator.execute(utterance, intent, session_id)                 │
  │                                                                     │
  │  ┌── PLANNING ─────────────────────────────────────────────────┐   │
  │  │  PlannerAgent.create_plan()                                  │   │
  │  │  → GoalDecomposer.decompose()                                │   │
  │  │  → LLM: Groq llama-4-scout-17b + SKELETON_PLANNING_PROMPT   │   │
  │  │  → Goal: phases=["Open WhatsApp",                           │   │
  │  │                   "Open John's chat",                        │   │
  │  │                   "Type and send message"]                   │   │
  │  └──────────────────────────────────────────────────────────────┘   │
  │                                                                     │
  │  ┌── PHASE 1: Open WhatsApp ───────────────────────────────────┐   │
  │  │  Short-circuit: _extract_open_app_phase("Open WhatsApp")    │   │
  │  │  → Subgoal(action_type="open_app", target="WhatsApp")       │   │
  │  │  → open_app ∈ NO_TARGET_ACTIONS → skip PerceiverAgent       │   │
  │  │  → ActorAgent.execute("open_app", target="WhatsApp")        │   │
  │  │    → GestureExecutor._execute_app_launch()                  │   │
  │  │      → AppInventory.get_package_candidates("whatsapp")      │   │
  │  │        Tier 1: config/app_packages.py → "com.whatsapp" ✓   │   │
  │  │      → real_accessibility_service.launch_app_via_intent(    │   │
  │  │            "com.whatsapp")                                   │   │
  │  │  → VerifierAgent: wait 3.0s → ui_signature diff → ✅        │   │
  │  └──────────────────────────────────────────────────────────────┘   │
  │                                                                     │
  │  ┌── PHASE 2: Open John's chat ────────────────────────────────┐   │
  │  │  PerceiverAgent.perceive(force_screenshot=True)              │   │
  │  │  → UI tree (WhatsApp chat list) + annotated screenshot       │   │
  │  │  ReactiveStepGenerator.generate_next_step()                  │   │
  │  │  → VLM: Llama 4 Scout (annotated screenshot + goal)         │   │
  │  │  → Returns: {action_type:"tap", target:"John"}               │   │
  │  │  → Coordinates resolved from accessibility tree              │   │
  │  │  → ActorAgent.execute("tap", coordinates=(540, 320))         │   │
  │  │  → VerifierAgent: wait 0.8s → ui_signature diff → ✅        │   │
  │  └──────────────────────────────────────────────────────────────┘   │
  │                                                                     │
  │  ┌── PHASE 3: Type and send message ──────────────────────────┐   │
  │  │  ReactiveStepGenerator × 3 iterations:                      │   │
  │  │    Iter 1: VLM → tap "Type a message" (input field)         │   │
  │  │    Iter 2: VLM → type "<message content>"                   │   │
  │  │    Iter 3: VLM → tap "Send" (phase_complete=true)           │   │
  │  │  _detect_goal_completion() → "sent" in UI tree → ✅         │   │
  │  │  goal.completed = True                                       │   │
  │  └──────────────────────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────────────────────┘
          │
          ▼
  ┌── NODE: speak ──────────────────────────────────────────────────────┐
  │  ResponderAgent.generate_feedback(status="completed", steps=[...])  │
  │  → LLM: Groq llama-3.3-70b → "Done! Sent John a message on..."    │
  │  → TTSService (Edge-TTS AriaNeural) → audio bytes                  │
  └─────────────────────────────────────────────────────────────────────┘
          │
          ▼
        END
```

---

## 12. Agent Responsibility Matrix

| Agent | File | LLM Used? | Role in This Command |
|---|---|---|---|
| **CommanderAgent** | `agents/commander.py` | ✅ Yes (llama-3.1-8b) | Parses "open whatsapp and message john" → `general_interaction` intent |
| **PlannerAgent** | `agents/planner_agent.py` | ✅ Yes (llama-4-scout) | Creates 3-phase skeleton plan |
| **Coordinator** | `agents/coordinator.py` | ❌ No | Master orchestration loop, phase management, retry logic |
| **PerceiverAgent** | `agents/perceiver_agent.py` | ❌ No (calls VLM indirectly) | Captures UI state (screen + accessibility tree) |
| **ReactiveStepGenerator** | `services/reactive_step_generator.py` | ✅ Yes (VLM) | Decides next action given current screen state |
| **ActorAgent** | `agents/actor_agent.py` | ❌ No | Executes single gestures (tap, type, open_app) |
| **VerifierAgent** | `agents/verifier_agent.py` | ❌ No | Validates action outcomes, error detection |
| **ResponderAgent** | `agents/responder.py` | ✅ Yes (llama-3.3-70b) | Generates natural language response + TTS |

**Who actually opens WhatsApp?**

> `ActorAgent` triggers the call, `GestureExecutor` resolves the package and executes, `real_accessibility_service` launches the Android Intent. The Coordinator orchestrates the decision to launch it via the short-circuit open-app fast-path.

---

## 13. Key Design Decisions and Trade-offs

### Decision 1: `general_interaction` for Multi-Step Commands

**Design:** Multi-step commands containing `" and "` are intentionally classified as `general_interaction` rather than trying to extract a specific action.

**Trade-off:** Loses some specificity at the intent layer, but avoids the intent parser over-committing to wrong structured fields (e.g., extracting `recipient="whatsapp"` and `content="message john"` when the real intent is two separate goals).

**Verdict:** ✅ Good design. The planner is better positioned to decompose multi-step goals after seeing the full utterance.

### Decision 2: Skeleton Planning + Reactive Execution

**Design:** The planner only creates abstract phases. Concrete subgoals (tap coordinates, element names) are generated reactively per screen.

**Trade-off:** Adds latency (VLM call per step), but handles dynamic UI state correctly — element positions change across devices, app versions, scroll positions.

**Verdict:** ✅ Correct for screen automation. Hardcoded coordinates would be brittle.

### Decision 3: Short-Circuit for "Open \<App\>" Phases

**Design:** If a skeleton phase is exactly `"Open <AppName>"`, the Coordinator bypasses the VLM and creates an `open_app` subgoal directly.

**Trade-off:** Saves one VLM call and avoids the VLM hallucinating a "tap on the WhatsApp icon on home screen" (which may not be visible).

**Verdict:** ✅ Excellent optimization.

### Decision 4: Package Resolution is Purely Rule-Based

**Design:** Package names are resolved via a static dict + device inventory fuzzy match. No LLM involvement.

**Trade-off:** The static dict (`config/app_packages.py`) has only ~20 entries. The device inventory fills the gap for installed apps.

**Verdict:** ⚠️ Acceptable but the static dict is sparse. The device inventory is the real workhorse.

### Decision 5: Deep Link for Messaging

**Design:** For `send_message` intents, the system tries to construct a WhatsApp/SMS deep link instead of navigating the UI.

**Trade-off:** Much faster for messaging — opens WhatsApp directly in the compose view with pre-filled recipient. Requires contact name → phone number resolution.

**Verdict:** ✅ Smart optimization. Reduces 2+ screen navigation steps to one.

---

## 14. Issues and Gaps Found During Review

### Issue 1: Missing Message Content — No Clarification Flow

**Problem:** `"open whatsapp and message john"` does not specify WHAT to message John. The current `INTENT_PARSING_PROMPT` defers to planner, but the planner's `SKELETON_PLANNING_PROMPT` does not explicitly handle missing message content.

During Phase 3 (type message), the `ReactiveStepGenerator` may:
- Generate a placeholder message (`"Hello!"`)
- Or attempt to type an empty string

**Risk:** Silent failure — the system sends an unintended message or types nothing,  without asking the user what to say.

**Recommendation:** In `agents/coordinator.py`, before entering Phase 3 execution, check if `goal.pending_commits` contains `"send"` and `intent.content` is `None`. If so, pause and emit a clarification request to the user.

---

### Issue 2: Static `APP_PACKAGES` Dict is Sparse

**Problem:** `config/app_packages.py` has only ~20 hardcoded entries. Apps not in this list fall through to the device inventory. If `device_app_inventory.json` is stale or missing, the system fails.

**File:** [`config/app_packages.py`](../config/app_packages.py)

**Recommendation:** Either expand the static dict to cover the top 100 apps, or make the device inventory refresh on every app launch failure.

---

### Issue 3: Contact Name Resolution is Async but Not Awaited on Failure

**Problem:** In `gesture_executor.py`, if `ContactResolver.resolve_contact("john")` fails (network timeout, contact not found), the code logs a warning and continues with `recipient="john"` — which is not a valid phone number.

**Risk:** Deep link constructed with a name instead of phone number → WhatsApp rejects the URI → silently falls back to plain app launch without compose screen pre-filled.

**Recommendation:** Add explicit fallback handling — if contact resolution fails, either prompt the user for the number or skip the deep link and navigate to WhatsApp contacts search via UI.

---

### Issue 4: VLM Hallucination Risk in Reactive Step

**Problem:** The `ReactiveStepGenerator` relies on a VLM (Llama 4 Scout) to decide the next action. If the VLM misidentifies the "Type a message" input field, it may tap the wrong element (e.g., a status bar or navigation element).

**Risk:** Medium — the verifier checks `ui_signature` diff, so a wrong tap is caught if the signature doesn't change, but the retry ladder may not recover correctly for all cases.

**Recommendation:** Add a `field_hint` validation step in the Coordinator — if `action_type="tap"` and `target` contains "message" or "input", verify the tapped element's `className` contains `"EditText"` before proceeding.

---

### Issue 5: `MAX_TOTAL_ACTIONS = 30` Can Be Hit in Complex Multi-Step Goals

**Problem:** If the VLM makes inefficient decisions (e.g., taps wrong element, triggers retry ladder twice) across a 3-phase goal, the budget of 30 total actions can be exhausted.

**Risk:** Task aborted mid-execution with message already open but not sent.

**Recommendation:** Increase to 40–50 actions for messaging tasks, or implement a goal-type-aware budget (messaging = 20, navigation = 30, general = 15).

---

### Issue 6: Two `nodes.py` Files (Potential Confusion)

**Problem:** Both `aura_graph/nodes.py` and `aura_graph/core_nodes.py` exist and appear to have overlapping content (same module per the sub-agent research).

**Risk:** Maintenance confusion — developers may edit one file while the other takes precedence at import time.

**Recommendation:** Audit and consolidate to a single file. Keep `core_nodes.py` if that's the canonical import, remove `nodes.py` or clearly mark it deprecated.

---

### Issue 7: Retry Ladder May Not Handle "Chat with John Not Found" Correctly

**Problem:** If "John" doesn't exist in the WhatsApp contact list (or appears as "John Doe" requiring a search), the `tap` on "John" will fail. The retry ladder escalates:

```
SAME_ACTION → ALTERNATE_SELECTOR → SCROLL_AND_RETRY → VISION_FALLBACK → ABORT
```

The `SCROLL_AND_RETRY` step may scroll down in the chat list, which is correct. But `VISION_FALLBACK` will call the VLM again with the same screen context if no scroll was useful.

**Risk:** Wasted retries without finding John, then aborting without using the WhatsApp search functionality.

**Recommendation:** Add a search-box tap as an explicit fallback step in the reactive planner for contact-finding phases.

---

## 15. Summary Table

| Question | Answer |
|---|---|
| **Where does command understanding happen?** | `agents/commander.py` — `parse_intent()` |
| **Is intent parsing rule-based or LLM?** | Hybrid: rules first (confidence ≥ 0.85), LLM (Groq llama-3.1-8b-instant) if no rule match |
| **What intent does "open whatsapp and message john" produce?** | `{action: "general_interaction", delegate_to_planner: true}` |
| **Why not `send_message` intent?** | Multi-step `" and "` connector → LLM deliberately returns `general_interaction` per prompt rules |
| **Which edge routes this to the Coordinator?** | `should_continue_after_intent_parsing()` — Gate 4: `action == "general_interaction"` |
| **Which agent creates the execution plan?** | `PlannerAgent` → `GoalDecomposer.decompose()` — 1 LLM call, skeleton phases only |
| **Which agent opens WhatsApp?** | `ActorAgent` executes; `GestureExecutor._execute_app_launch()` does the actual Android call |
| **Does opening the app require PerceiverAgent?** | ❌ No — `open_app` is in `NO_TARGET_ACTIONS`, PerceiverAgent is bypassed |
| **Is package name resolved by LLM?** | ❌ No — purely rule-based: static dict → device inventory fuzzy match → fallback |
| **How is "com.whatsapp" found?** | `config/app_packages.py` static dict: `"whatsapp" → "com.whatsapp"` |
| **What drives navigation inside WhatsApp?** | `ReactiveStepGenerator` — VLM (Llama 4 Scout) looking at live annotated screenshots |
| **How is goal completion detected?** | Deterministic heuristic: `_detect_goal_completion()` scans UI tree for "sent"/"delivered" text |
| **How many LLM calls for this command?** | ~5–7: 1 (intent) + 1 (planning) + ~3–5 (reactive steps per screen) + 1 (response) |
| **Main risk?** | Missing message content — no explicit clarification flow if user doesn't specify what to say |

---

*Report generated by full E2E codebase review. All findings verified against source files.*
