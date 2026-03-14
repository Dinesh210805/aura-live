<p align="center">
  <img src="https://img.shields.io/badge/AURA-Autonomous%20User--Responsive%20Agent-blueviolet?style=for-the-badge&logo=android&logoColor=white" alt="AURA Badge"/>
</p>

<h1 align="center">AURA — Autonomous User-Responsive Agent</h1>

<p align="center">
  <strong>A voice-controlled, multi-agent AI system that sees, understands, plans, and acts on your Android device.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/LangGraph-0.3.27+-FF6F00?style=flat-square&logo=langchain&logoColor=white" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Groq-Llama%204-F55036?style=flat-square&logo=meta&logoColor=white" alt="Groq"/>
  <img src="https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?style=flat-square&logo=google&logoColor=white" alt="Gemini"/>
  <img src="https://img.shields.io/badge/OPA-Rego%20Policies-7D9AAA?style=flat-square&logo=openpolicyagent&logoColor=white" alt="OPA"/>
  <img src="https://img.shields.io/badge/YOLOv8-UI%20Detection-00FFFF?style=flat-square&logo=yolo&logoColor=black" alt="YOLOv8"/>
  <img src="https://img.shields.io/badge/Edge--TTS-Voice-0078D4?style=flat-square&logo=microsoft&logoColor=white" alt="Edge-TTS"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Agents-9%20Specialized-purple?style=flat-square" alt="Agents"/>
  <img src="https://img.shields.io/badge/LLMs-6%20Models-orange?style=flat-square" alt="Models"/>
  <img src="https://img.shields.io/badge/Perception-3%20Layer%20Hybrid-blue?style=flat-square" alt="Perception"/>
  <img src="https://img.shields.io/badge/Planning-Reactive%20Hybrid-red?style=flat-square" alt="Planning"/>
</p>

---

## Table of Contents

- [What is AURA?](#-what-is-aura)
- [Key Capabilities](#-key-capabilities)
- [System Architecture](#-system-architecture)
- [The 9-Agent System](#-the-9-agent-system)
- [LangGraph State Machine](#-langgraph-state-machine)
- [Tri-Provider Model Architecture](#-tri-provider-model-architecture)
- [Perception Pipeline — OmniParser Hybrid](#-perception-pipeline--omniparser-hybrid)
- [Planning System — Reactive Hybrid Planner](#-planning-system--reactive-hybrid-planner)
- [Coordinator — The Execution Loop](#-coordinator--the-execution-loop)
- [Safety and Guardrails](#-safety-and-guardrails)
- [Android Companion App](#-android-companion-app)
- [WebSocket Communication Protocol](#-websocket-communication-protocol)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Installation and Setup](#-installation-and-setup)
- [Configuration](#-configuration)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

---

## What is AURA?

AURA (**Autonomous User-Responsive Agent**) is a **production-grade AI backend** that turns natural language into real device actions on Android. You speak (or type) a command, and AURA:

1. **Hears** — Transcribes speech via Groq Whisper Large v3 Turbo
2. **Understands** — Classifies intent with rule-based + LLM parsing
3. **Sees** — Captures and analyzes the screen through a 3-layer perception pipeline
4. **Plans** — Decomposes goals into skeleton phases, then generates reactive per-screen steps
5. **Acts** — Executes precise gestures (tap, swipe, type, scroll) on the real device
6. **Verifies** — Checks the outcome, retries with escalating strategies, or replans
7. **Speaks** — Responds with natural, context-aware conversation

AURA is **not a toy demo** — it runs a full perceive-decide-act-verify loop against a real Android device via AccessibilityService and MediaProjection, with safety policies blocking dangerous operations.

### What Makes AURA Different?

| Feature | AURA | Typical AI Agents |
|---|---|---|
| **Perception** | 3-layer hybrid: UI Tree, YOLOv8 CV, VLM selection | Single screenshot + VLM guess |
| **Planning** | Reactive hybrid: skeleton phases + per-screen grounding | Full plan upfront (brittle) |
| **Coordinates** | Always from deterministic sources (UI tree or CV) | VLM generates coordinates (unreliable) |
| **Retry** | 5-stage retry ladder with strategy escalation | Simple retry or fail |
| **Safety** | OPA Rego policies + Prompt Guard 2 + policy engine | Basic keyword filtering |
| **Voice** | Full duplex: STT to processing to TTS | Text-only |

---

## Key Capabilities

- **Voice and Text Commands** — "Open Spotify and play my liked songs", "Send a WhatsApp message to John saying I'll be late"
- **Multi-Step Goal Execution** — Decomposes complex goals into phases, executes each reactively
- **Screen Understanding** — Reads and describes what's on screen, finds any UI element
- **App Launching** — Opens any installed app by name via package resolution with fuzzy matching and 80+ synonym mappings
- **UI Interaction** — Tap, swipe, scroll, long-press, type text with pixel-accurate coordinates
- **Device Control** — Volume, brightness, Wi-Fi, Bluetooth, airplane mode, notifications
- **Smart Navigation** — Back, home, recent apps, settings panels
- **Conversational AI** — Multi-turn dialogue with personality, memory, and emotion detection
- **Human-in-the-Loop** — Pauses for user confirmation on ambiguous or sensitive actions
- **Real-Time Progress** — Live task progress broadcast to the Android companion app

---

## System Architecture

AURA follows a **multi-agent, event-driven architecture** orchestrated by a LangGraph state machine. The system has three main layers:

```
+-------------------------------------------------------------------+
|                        ANDROID DEVICE                              |
|  +------------------------+  +----------------------------------+  |
|  |  Companion App         |  |  AccessibilityService            |  |
|  |  (Kotlin)              |  |  - UI Tree extraction            |  |
|  |  - Audio capture       |  |  - Gesture execution             |  |
|  |  - Screenshot relay    |  |  - Screen change detection       |  |
|  |  - Visual feedback     |  |                                  |  |
|  |  - Progress display    |  |  MediaProjection                 |  |
|  +----------+-------------+  |  - Screenshot capture            |  |
|             | WebSocket       +----------------------------------+  |
+-------------+-----------------------------------------------------+
              | Bidirectional
              v
+-------------------------------------------------------------------+
|                     AURA BACKEND (FastAPI)                          |
|                                                                    |
|  +-----------+  +--------------+  +-----------------------------+  |
|  | WebSocket |  | REST API     |  | Middleware                  |  |
|  | Router    |  | Endpoints    |  | - Rate Limiting             |  |
|  | - Audio   |  | - /health    |  | - Request ID                |  |
|  | - Commands|  | - /tasks     |  | - CORS                      |  |
|  | - Device  |  | - /device    |  | - Trusted Hosts             |  |
|  +-----+-----+  +------+-------+  +-----------------------------+  |
|        |               |                                           |
|  +-----v---------------v-----------------------------------------+|
|  |               LANGGRAPH STATE MACHINE                          ||
|  |                                                                ||
|  |  STT -> Parse Intent -> Perception -> Coordinator -> Speak     ||
|  |                            ^              |                    ||
|  |                            |    +---------v----------+         ||
|  |                            |    |  PERCEIVE -> DECIDE |         ||
|  |                            |    |  -> ACT -> VERIFY   |         ||
|  |                            |    |    (Agent Loop)     |         ||
|  |                            |    +--------------------+         ||
|  +---------------------------------------------------------------|+
|                                                                    |
|  +---------------------------------------------------------------+|
|  |                    SERVICE LAYER                               ||
|  |  LLM - VLM - STT - TTS - Perception - Gesture - Policy       ||
|  +---------------------------------------------------------------+|
+--------------------------------------------------------------------+
              |
              v
+-------------------------------------------------------------------+
|                     AI MODEL PROVIDERS                              |
|  +--------------+  +--------------+  +-------------------+         |
|  |  Groq        |  |  Google      |  |  NVIDIA NIM       |         |
|  |  (Primary)   |  |  Gemini      |  |  (Optional)       |         |
|  |  Llama 4     |  |  (Fallback)  |  |                   |         |
|  |  Whisper     |  |  2.5 Flash   |  |                   |         |
|  +--------------+  +--------------+  +-------------------+         |
+-------------------------------------------------------------------+
```

---

## The 9-Agent System

AURA uses **9 specialized agents**, each with a single responsibility. They don't talk to each other directly — the **Coordinator** orchestrates them through a structured loop.

### Agent Overview

| # | Agent | Role | Uses LLM? | Latency |
|---|---|---|---|---|
| 1 | **CommanderAgent** | Intent parsing (voice/text to structured intent) | Hybrid | 10-200ms |
| 2 | **Coordinator** | Multi-agent orchestration loop | No (orchestrator) | — |
| 3 | **PerceiverAgent** | Screen understanding and element location | Via VLM | 50-600ms |
| 4 | **PlannerAgent** | Goal decomposition and replanning | Yes | 200-500ms |
| 5 | **ActorAgent** | Gesture execution on device | No | 50-200ms |
| 6 | **VerifierAgent** | Post-action outcome validation | Via VLM | 100-400ms |
| 7 | **ResponderAgent** | Natural language response generation | Yes | 200-400ms |
| 8 | **ValidatorAgent** | Rule-based intent validation | No | <5ms |
| 9 | **ScreenVLM** | Unified visual perception (SoM annotation) | Yes | 300-600ms |

### Agent Deep Dive

#### 1. CommanderAgent — `agents/commander.py`

The **entry point** for all user input. Converts raw voice/text into a structured intent object.

**How it works:**
1. **Rule-based classifier runs first** — Pattern matching with confidence scoring (>=0.85 threshold). Zero LLM calls for common commands like "go back", "open settings", "scroll down".
2. **LLM fallback** — If rule-based confidence is below threshold, sends to Groq Llama 3.1 8B for classification.
3. **Action normalization** — Maps synonyms (`press` to `tap`, `swipe up` to `scroll`), resolves visual references ("the blue button" is stored for perception).

**Output format:**
```json
{
  "action": "tap",
  "target": "Play button",
  "parameters": {"visual_reference": "green play button"},
  "confidence": 0.92,
  "raw_transcript": "tap the green play button"
}
```

#### 2. Coordinator — `agents/coordinator.py`

The **brain of execution**. Runs the core `perceive -> decide -> act -> verify` loop for every task.

**Key constants:**
- `MAX_TOTAL_ACTIONS = 30` — Hard limit preventing infinite loops
- `MAX_REPLAN_ATTEMPTS = 3` — Maximum replanning cycles
- `COMMIT_ACTIONS` — Side-effect actions (send, purchase, delete) that need VLM verification

**Execution flow:**
```
for each phase in skeleton_plan:
    while phase not complete:
        1. perceiver.capture_screen()          # Fresh screen state
        2. reactive_gen.next_step(screen)       # ONE concrete action
        3. actor.execute(gesture)               # Run on device
        4. verifier.check_outcome()             # Did it work?
           +-- YES -> advance to next step
           +-- NO  -> retry_ladder.escalate()
                      +-- SAME_ACTION
                      +-- ALTERNATE_SELECTOR
                      +-- SCROLL_AND_RETRY
                      +-- VISION_FALLBACK
                      +-- ABORT -> replan or fail
```

**Features:**
- Pre-action snapshots for accurate before/after comparison
- UI signature tracking for loop detection (same screen state = stuck)
- Step memory accumulation (each step records what happened for context)
- Automatic retry ladder escalation before expensive LLM replanning

#### 3. PerceiverAgent — `agents/perceiver_agent.py`

Wraps the **PerceptionController** to give the Coordinator a clean `ScreenState` object.

**ScreenState contains:**
- `ui_tree` — Parsed accessibility tree with all interactive elements
- `screenshot` — Base64-encoded device screenshot
- `screen_type` — Detected as `native`, `webview`, or `keyboard_open`
- `ui_signature` — MD5 hash of UI tree for change detection
- `vlm_description` — Natural language screen description from VLM (optional)

**Smart behavior:**
- Detects webview screens (Chrome, in-app browsers) and forces VLM analysis since UI tree is unreliable for web content
- Uses combined `describe_and_locate` fast-path when both description and element location are needed
- Caches perception results within a configurable TTL (default: 2 seconds) to avoid redundant captures

#### 4. PlannerAgent — `agents/planner_agent.py`

Generates **skeleton plans** — high-level phase decompositions of a user's goal.

**Example:** "Order a pizza from Domino's"
```
Phase 1: Open the Domino's app
Phase 2: Browse menu and select a pizza
Phase 3: Add to cart and proceed to checkout
Phase 4: Confirm and place the order
```

**Key constraints:**
- `ATOMIC_MAX_WORDS = 12` — Each phase description must be 12 words or less (forces atomic goals)
- Plans include **commit coverage** — ensures user-requested side-effects (send, buy, confirm) appear in at least one phase
- Supports **replanning from obstacles** — when execution hits a wall, the planner generates a new plan from the current screen state

#### 5. ActorAgent — `agents/actor_agent.py`

**Fully deterministic** — the only agent with **zero LLM calls**. Wraps the `GestureExecutor` service.

**Supported gestures:**

| Gesture | Description |
|---|---|
| `tap(x, y)` | Single tap at coordinates |
| `long_press(x, y, duration)` | Hold at coordinates |
| `swipe(x1, y1, x2, y2)` | Swipe between two points |
| `scroll(direction)` | Scroll up/down/left/right |
| `type_text(text)` | Input text into focused field |
| `press_enter()` | IME action (search/send/done) |
| `go_back()` | Android back navigation |
| `go_home()` | Android home button |

**Execution strategies** (selected automatically):
1. **WebSocket** — Instant command via persistent connection (fastest)
2. **Command Queue** — Via polling queue (reliable for unreliable connections)
3. **Direct** — Direct API call (fallback)

Returns an `ActionResult` with `success`, `execution_time`, and `coordinates_used`.

#### 6. VerifierAgent — `agents/verifier_agent.py`

**Post-action quality gate.** Checks whether each gesture actually achieved its intended effect.

**Verification pipeline:**
1. **Stabilization delay** (300ms) — Wait for UI to settle after action
2. **UI signature comparison** — Compare MD5 hash of UI tree before and after
3. **Error screen detection** — Check for "App has stopped", permission dialogs, error toasts
4. **Commit action verification** — For side-effect actions (send, purchase), uses VLM to semantically confirm the outcome
5. **Change polling** — For network-dependent actions, polls up to 4 seconds for UI changes

#### 7. ResponderAgent — `agents/responder.py`

Generates **natural, personality-driven responses** for the user. This is AURA's voice.

**Features:**
- **AURA Personality** — Helpful, concise, slightly playful. Never robotic.
- **Emotion detection** — Adjusts tone based on detected user frustration or confusion
- **Multi-turn grounding** — References conversation history for coherent dialogue
- **Identity guardrails** — Always identifies as "AURA", never claims to be human
- **Screen-aware responses** — Can describe what's visible on screen when asked

**Model:** Groq Llama 3.3 70B (highest quality for user-facing text)

#### 8. ValidatorAgent — `agents/validator.py`

**Pure rule-based validation** — zero LLM calls, runs in <5ms.

**Checks:**
- Required fields present (e.g., `target` for tap actions)
- Action type exists in the `ACTION_REGISTRY`
- Confidence threshold met (configurable)
- Dangerous action detection (routes to confirmation flow)
- Parameter format validation

#### 9. ScreenVLM — `agents/visual_locator.py`

The **visual perception engine**. Builds annotated screenshots with **Set-of-Marks (SoM)** — numbered bounding boxes drawn on UI elements.

**How SoM works:**
1. Capture screenshot from device
2. Run OmniParser (YOLOv8) to detect all UI elements
3. Draw numbered boxes on each detected element
4. Send annotated image to VLM with prompt: "Which numbered element is [target]?"
5. VLM returns the **number**, not coordinates
6. Map number to deterministic bounding box center coordinates

**This is the key safety guarantee:** VLM never generates pixel coordinates. It only classifies among valid, CV-detected options.

---

## LangGraph State Machine

AURA's execution flow is controlled by a **LangGraph `StateGraph`** — a deterministic, observable state machine where nodes are processing steps and edges are conditional routing functions.

### Graph Topology

```
                        +----------+
                        |  START   |
                        +----+-----+
                             |
                  +----------+----------+
                  v          v          v
              +------+  +---------+  +-------+
              | STT  |  |  Parse  |  | Error |
              |      |  | Intent  |  |Handler|
              +--+---+  +----+----+  +-------+
                 |           |
                 +-----+-----+
                       v
                +-----------+
                |  Intent   +---------------------------+
                |  Router   |                           |
                +-----+-----+                           |
                      |                                 |
        +-------------+-------------+                   |
        v             v             v                   v
  +----------+ +----------+ +-----------+        +-----------+
  |Perception| | Parallel | |   Speak   |        | Coordin-  |
  |          | | UI+Valid | |(conversa- |        |   ator    |
  +----+-----+ +----+-----+ |  tional)  |        |           |
       |             |       +-----+-----+        +-----+-----+
       +------+------+             |                    |
              |                    |                    |
              v                    |                    |
       +-----------+               |                    |
       |Coordinator|               |                    |
       | (Agent    |               |                    |
       |  Loop)    |               |                    |
       +-----+-----+              |                    |
              |                    |                    |
              v                    v                    v
           +------+             +------+            +------+
           |Speak |             | END  |            |Speak |
           +--+---+             +------+            +--+---+
              |                                        |
              v                                        v
           +------+                                +------+
           | END  |                                | END  |
           +------+                                +------+
```

### State Object — TaskState

The graph passes a single `TaskState` TypedDict through all nodes. It has **40+ fields** with custom reducers:

```python
class TaskState(TypedDict):
    # Input
    session_id: str
    raw_audio: Optional[bytes]
    transcript: str
    streaming_transcript: str
    input_type: str                    # "audio" | "text" | "streaming"

    # Intent
    intent: Optional[Dict]             # Parsed intent object

    # Perception
    ui_screenshot: Optional[str]       # Base64 screenshot
    ui_elements: List[Dict]            # Parsed UI tree elements
    perception_bundle: Optional[Any]   # Full PerceptionBundle

    # Planning
    plan: Annotated[List, update_plan] # Execution plan with custom reducer
    current_step: int

    # Execution
    executed_steps: Annotated[List, add_step]  # Append-only history
    status: Annotated[str, update_status]      # Custom status reducer

    # Output
    feedback_message: str              # Response to user
    spoken_audio: Optional[bytes]      # TTS audio bytes

    # Error handling
    error_message: Annotated[Optional[str], add_errors]  # Accumulating errors
    retry_count: int

    # ... 20+ more fields for workflow tracking,
    #     conversation context, goal state, etc.
```

**Custom reducers** prevent state conflicts in parallel execution:
- `add_errors` — Concatenates error messages instead of overwriting
- `update_status` — Only updates if new status is "more severe"
- `add_step` — Appends to executed steps list

### Routing Logic — edges.py

Each edge is a Python function that inspects `TaskState` and returns the name of the next node:

**Key routing rules after intent parsing:**
1. **Blocked action** -> `speak` (inform user action is blocked)
2. **Low confidence (<0.3)** -> `error_handler`
3. **Low confidence (<0.6) or ambiguous** -> `coordinator` (full planning)
4. **Multi-step commands** ("open X and do Y") -> `coordinator`
5. **NO_UI actions** (open_app, scroll, toggles) -> `coordinator` (skip perception)
6. **Conversational** ("hello", "help") -> `speak` directly
7. **Screen reading** ("what's on screen") -> `perception` then `speak`
8. **UI actions** requiring coordinates -> `perception` then `coordinator`

### Parallel Execution

The graph supports **fan-out/fan-in parallelism**:

```
Parse Intent -> [Fan-Out] -> UI Analysis   -> [Fan-In] -> Coordinator
                           -> Validation    ->
```

UI analysis and intent validation run concurrently, reducing total latency when both are needed. Controlled by the `enable_parallel_execution` setting.

---

## Tri-Provider Model Architecture

AURA uses a **task-specialized model routing** strategy. Different tasks use different models optimized for that specific workload:

```
+------------------------------------------------------------------+
|                   AURA MODEL ROUTING                              |
+----------------------+-------------------------------------------+
|  TASK                |  MODEL (Provider)                         |
+----------------------+-------------------------------------------+
|  Intent Parsing      |  Llama 3.1 8B Instant (Groq) - 560 T/s   |
|  UI Analysis/Vision  |  Llama 4 Scout 17B (Groq) - 750 T/s      |
|  Planning/Reasoning  |  Llama 4 Maverick 17B 128E (Groq)        |
|  Response Generation |  Llama 3.3 70B Versatile (Groq)           |
|  Speech-to-Text      |  Whisper Large v3 Turbo (Groq)            |
|  Text-to-Speech      |  Edge-TTS (local, no API key)             |
|  Safety Screening    |  Llama Prompt Guard 2 86M                 |
+----------------------+-------------------------------------------+
|  FALLBACK CHAIN      |                                           |
+----------------------+-------------------------------------------+
|  Vision              |  Scout 17B -> Maverick 17B -> Gemini 2.5  |
|  Planning            |  Maverick 17B -> Gemini 2.5 Flash         |
|  Intent (low conf.)  |  Llama 3.1 8B -> Llama 3.3 70B           |
+----------------------+-------------------------------------------+
```

### Why This Design?

- **Llama 3.1 8B** for intent parsing — 560 tokens/sec means sub-200ms classification. Most commands are simple and don't need a 70B model.
- **Llama 4 Scout 17B** for vision — 750 tokens/sec with native multimodal. Sees the screen and identifies elements faster than Gemini.
- **Llama 4 Maverick 17B (128 experts)** for planning — Mixture-of-experts architecture excels at decomposing complex, multi-step goals.
- **Llama 3.3 70B** for responses — User-facing text quality matters. The 70B model produces more natural, contextually-aware responses.
- **Edge-TTS** for speech — Runs locally using Microsoft's Edge voices. No API key, no latency, no cost. Supports 300+ voices.

### Automatic Fallback

Every model call has an automatic fallback chain. If Groq times out or rate-limits:

```python
# services/llm.py — Simplified fallback logic
try:
    response = await groq_client.chat(model="llama-3.1-8b-instant", ...)
except (RateLimitError, TimeoutError):
    response = await gemini_client.generate(model="gemini-2.5-flash", ...)
```

Provider selection is configured via environment variables and can be changed without code modifications.

---

## Perception Pipeline — OmniParser Hybrid

The perception pipeline is AURA's **eyes**. It determines what's on screen and where every element is, using a 3-layer escalation architecture.

### The Three Layers

```
+------------------------------------------------------------+
|                    PERCEPTION REQUEST                       |
|                "Find the search button"                     |
+------------+-----------------------------------------------+
             |
             v
+--------------------------------+
|  LAYER 1: UI TREE              |    Success: 70-80%
|  - Android AccessibilityService|    Latency: 10-50ms
|  - Parse XML element tree      |    Cost: FREE
|  - Match by text/description   |
|  - Pixel-perfect coordinates   |
+----------+--------+------------+
           |        |
        FOUND    NOT FOUND
           |        |
           v        v
        RETURN   +------------------------------+
                 |  LAYER 2: CV DETECTION        |
                 |  - YOLOv8 (OmniParser)        |    Latency: 200-400ms GPU
                 |  - Detect ALL UI elements     |              2-3s CPU
                 |  - Bounding boxes + labels    |
                 |  - Draw numbered SoM overlay  |
                 +----------+--------+-----------+
                            |        |
                         FOUND    CANDIDATES
                            |        |
                            v        v
                         RETURN   +--------------------------+
                                  |  LAYER 3: VLM SELECTION   |
                                  |  - Send annotated image   |
                                  |  - "Which # is target?"   |
                                  |  - Returns NUMBER only    |
                                  |  - Map # to CV coords     |
                                  |  Latency: 300-600ms       |
                                  +----------+---------------+
                                             |
                                          RETURN
```

### The Critical Safety Guarantee

> **VLM NEVER generates coordinates.** It only selects among CV-detected candidates by number.

This eliminates the most common failure mode in AI agents — hallucinated coordinates from vision models. Every pixel coordinate comes from either:
- The Android UI tree (Layer 1) — system-provided, pixel-perfect
- YOLOv8 detection (Layer 2) — geometrically computed bounding boxes

### Perception Bundle

Every perception cycle produces a `PerceptionBundle`:

```python
@dataclass
class PerceptionBundle:
    snapshot_id: str                    # Unique ID for this capture
    modality: PerceptionModality        # UI_TREE | HYBRID | VISION
    ui_tree: Optional[UITreePayload]    # Parsed accessibility tree
    screenshot: Optional[ScreenshotPayload]  # Base64 screenshot
    timestamp: float
    vlm_description: Optional[str]      # Natural language screen description
    element_coordinates: Optional[Dict]  # Located element position
```

### Modality Selection

The system automatically selects the right perception mode:

| App Context | Modality | Reason |
|---|---|---|
| Native Android app | `UI_TREE` | Accessibility tree is reliable |
| WebView / browser | `VISION` | UI tree doesn't capture web content |
| Hybrid (native + web elements) | `HYBRID` | UI tree + VLM for web parts |
| Fast-perception apps (configurable) | `UI_TREE` | Skip screenshot for speed |

---

## Planning System — Reactive Hybrid Planner

AURA's planning is **not a single upfront plan**. It is a two-layer system that combines high-level strategy with per-screen tactical decisions.

### Layer 1: Skeleton Phases — `services/goal_decomposer.py`

The PlannerAgent decomposes a goal into **2-4 abstract phases**:

```
User: "Book an Uber to the airport"

Skeleton Plan:
  Phase 1: Open the Uber app
  Phase 2: Set destination to airport
  Phase 3: Select ride type and confirm booking
```

**Rules enforced by the prompt:**
- Maximum 4 phases (prevents over-planning)
- Each phase must be 12 words or less (atomic constraint)
- Must include a "commit" phase for user-requested side-effects
- Phases are abstract — no specific UI elements referenced

### Layer 2: Reactive Step Generator — `services/reactive_step_generator.py`

For each phase, the **ReactiveStepGenerator** looks at the **live screen** and generates exactly **ONE concrete next action**:

```
Current Phase: "Set destination to airport"
Current Screen: [Uber home screen with "Where to?" search field]

Reactive Step:
  action: "tap"
  target: "Where to? search field"
  reasoning: "The search field is visible, tapping it will open destination input"
```

**The 4-step thinking process** (embedded in the prompt):

1. **OBSERVE** — What is on this screen right now?
2. **ORIENT** — Where am I in the phase? What has already been done?
3. **DECIDE** — What is the single best next action?
4. **OUTPUT** — Structured action with exact target

### Why Reactive Planning?

Traditional AI agents create a full plan upfront:
```
Step 1: Tap "Where to?"
Step 2: Type "airport"
Step 3: Tap first suggestion
Step 4: Tap "Confirm"
```

This is **brittle** — if step 2 shows a different UI than expected, steps 3-4 are invalid.

AURA's approach:
```
Phase: "Set destination to airport"
   See screen -> generate ONE action -> execute -> see new screen -> generate next action
```

Each action is **grounded in the current screen state**, not a predicted future state.

---

## Coordinator — The Execution Loop

The Coordinator (`agents/coordinator.py`) is the runtime engine. Here is the complete execution lifecycle:

### Full Loop Diagram

```
                    +---------------+
                    |   User Goal   |
                    | "Send message |
                    |  to John on   |
                    |  WhatsApp"    |
                    +-------+-------+
                            |
                            v
                    +---------------+
                    |   PLANNER     |
                    |  Skeleton     |
                    |  Decompose    |
                    +-------+-------+
                            |
                  +---------v----------+
                  |  Phase 1: Open     |
                  |  WhatsApp          |
                  +---------+----------+
                            |
          +-----------------v-----------------+
          |         EXECUTION LOOP            |
          |                                   |
          |  +----------+                     |
          |  |PERCEIVER | Capture screen      |
          |  +----+-----+                     |
          |       |                           |
          |       v                           |
          |  +--------------+                 |
          |  |REACTIVE STEP | Generate ONE    |
          |  |  GENERATOR   | concrete action |
          |  +----+---------+                 |
          |       |                           |
          |       v                           |
          |  +----------+                     |
          |  |  ACTOR   | Execute gesture     |
          |  +----+-----+                     |
          |       |                           |
          |       v                           |
          |  +----------+    +------------+   |
          |  | VERIFIER |    |  SUCCESS?  |   |
          |  +----------+    +------+-----+   |
          |                   YES   |  NO     |
          |              +---------++---------+
          |              v                   v|
          |    Advance to next       Retry   |
          |    step or phase         Ladder  |
          |                                   |
          +-----------------------------------+
```

### Retry Ladder

When an action fails, AURA does not immediately give up or replan. It escalates through a **5-stage retry ladder**:

```python
RETRY_LADDER = [
    RetryStrategy.SAME_ACTION,           # 1. Try exact same action again
    RetryStrategy.ALTERNATE_SELECTOR,    # 2. Find element by different selector
    RetryStrategy.SCROLL_AND_RETRY,      # 3. Scroll to find the element
    RetryStrategy.VISION_FALLBACK,       # 4. Use VLM to locate element visually
    RetryStrategy.ABORT,                 # 5. Give up on this subgoal
]
```

Only after all strategies are exhausted does the system request an **LLM replan** (up to `MAX_REPLAN_ATTEMPTS = 3`), which is expensive. The retry ladder handles transient failures cheaply.

### Loop Detection

The Coordinator maintains a **UI signature history** — MD5 hashes of the UI tree after each action. If the same signature repeats too many times, it detects a loop (stuck on the same screen) and triggers an abort.

```python
# services/ui_signature.py
def compute_ui_signature(ui_tree: dict) -> str:
    """MD5 hash of UI tree structure for change detection."""
    # Normalizes tree, removes volatile fields, hashes
    return hashlib.md5(normalized_tree.encode()).hexdigest()
```

### Step Memory

Each completed action is recorded in `StepMemory`:

```python
@dataclass
class StepMemory:
    subgoal_description: str
    action_type: str
    target: Optional[str]
    result: str                    # "success" | "failed"
    screen_type: str               # "native" | "webview" | "keyboard_open"
    screen_before: str             # UI signature pre-action
    screen_after: str              # UI signature post-action
    screen_description: Optional[str]  # VLM description for webview screens
```

This accumulated history is passed to the planner and reactive step generator, giving them context about what has already been tried.

---

## Safety and Guardrails

AURA has **three layers of safety** preventing the agent from performing harmful actions:

### Layer 1: OPA Rego Policies — `policies/safety.rego`

The policy engine evaluates every action against Rego rules before execution:

```rego
# Unconditionally blocked — NEVER executed
blocked_actions := {
    "factory_reset", "wipe_data", "delete_all",
    "format_storage", "root_device", "install_unknown_apk",
    "disable_security", "grant_root",
}

# Requires explicit user confirmation
confirmation_required := {
    "send_money", "transfer", "payment", "delete",
    "uninstall", "clear_data", "remove_account",
}

# Sensitive data pattern detection
sensitive_patterns := [
    "password is", "pin is", "ssn is",
    "credit card number", "cvv is",
]
```

**Evaluation happens in the `GestureExecutor`** — before any gesture is sent to the device, the policy engine checks it:

```python
# services/gesture_executor.py
decision = policy_engine.evaluate(ActionContext(
    action_type=gesture_type,
    target=target_element,
    parameters=params,
))
if decision == PolicyDecision.DENY:
    raise SafetyViolationError(decision.reason)
if decision == PolicyDecision.CONFIRM:
    await hitl_service.request_confirmation(decision.reason)
```

### Layer 2: Prompt Guard — `services/prompt_guard.py`

Uses **Llama Prompt Guard 2 86M** (a specialized small model) to detect:
- **Jailbreak attempts** — Prompts trying to override system instructions
- **Injection attacks** — Malicious content in user transcripts
- **Prompt manipulation** — Attempts to extract system prompts or change behavior

Runs on every user input before intent classification.

### Layer 3: Human-in-the-Loop — `services/hitl_service.py`

For actions in the `confirmation_required` set, AURA **pauses execution** and asks the user:

```
AURA: "You want to send a payment of $50. Should I proceed?"
       [Confirm] [Cancel]
```

**Question types:**
- `CONFIRMATION` — Yes/No for sensitive actions
- `CHOICE` — Select from options when ambiguous
- `TEXT_INPUT` — Request specific information (e.g., "Which John — John Smith or John Doe?")

The Android companion app displays the question and sends the response back via WebSocket.

---

## Android Companion App

The `UI/` directory contains a **Kotlin/Gradle Android app** that runs on the target device.

### Components

| Component | Purpose |
|---|---|
| **AccessibilityService** | Extracts UI trees, executes gestures (tap, swipe, type), monitors screen changes |
| **MediaProjection** | Captures screenshots on demand via screen recording API |
| **WebSocket Client** | Persistent bidirectional connection to AURA backend |
| **Audio Capture** | Records user voice and streams to backend for STT |
| **Visual Feedback** | Apple Intelligence-style edge glow + tap ripple animations |
| **Task Progress UI** | Displays real-time todo-style task progress from backend |

### How It Connects

```
Android App                          AURA Backend
-----------                          ------------
1. Boot and Start
   AccessibilityService
2. Connect WebSocket     -------->   WebSocket Router accepts
3. Stream audio          -------->   STT processes
4. Receive command       <--------   Backend sends gesture
5. Execute gesture
6. Send UI tree          -------->   Perception processes
7. Send screenshot       -------->   VLM analyzes
8. Display progress      <--------   Task progress broadcast
9. Show visual feedback  <--------   Visual feedback commands
```

---

## WebSocket Communication Protocol

AURA uses **two WebSocket endpoints** for device communication:

### 1. Audio WebSocket — `/ws/audio`

Handles voice command streaming:

```
Client -> Server: Binary audio chunks (WAV/opus)
Server -> Client: JSON responses with TTS audio
```

**Flow:**
1. Client streams audio chunks while user speaks
2. Server assembles chunks in `AudioBuffer`
3. On silence detection or explicit stop, triggers STT then full pipeline
4. Returns JSON with `feedback_message` + optional base64 `spoken_audio`

### 2. Device WebSocket — `/ws/device`

Bidirectional device control channel:

```
Server -> Client: Gesture commands (tap, swipe, type, etc.)
Client -> Server: UI tree updates, screenshots, gesture acknowledgments
```

**Message types (Server to Client):**
```json
{"type": "gesture", "action": "tap", "x": 540, "y": 1200}
{"type": "gesture", "action": "swipe", "startX": 540, "startY": 1500, "endX": 540, "endY": 500}
{"type": "gesture", "action": "type", "text": "Hello John"}
{"type": "screenshot_request"}
{"type": "visual_feedback", "effect": "edge_glow", "color": "#4CAF50"}
{"type": "task_progress", "tasks": ["..."]}
```

**Message types (Client to Server):**
```json
{"type": "ui_tree", "tree": {}, "packageName": "com.whatsapp"}
{"type": "screenshot", "data": "base64..."}
{"type": "gesture_ack", "id": "abc123", "success": true}
{"type": "hitl_response", "answer": "confirm"}
```

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check + connected device status |
| `POST` | `/api/v1/tasks/text` | Submit text command for processing |
| `POST` | `/api/v1/tasks/audio` | Submit audio file for processing |
| `GET` | `/api/v1/tasks/{task_id}` | Get task status and result |
| `GET` | `/api/v1/device/status` | Get connected device information |
| `POST` | `/api/v1/device/screenshot` | Request device screenshot |
| `GET` | `/api/v1/device/ui-tree` | Get current UI tree |
| `GET` | `/api/v1/graph/visualization` | Get LangGraph structure as JSON |
| `GET` | `/api/v1/workflow/sessions` | List workflow execution sessions |
| `GET` | `/api/v1/workflow/sessions/{id}` | Get workflow execution details |
| `GET` | `/api/v1/config` | Get current configuration |
| `POST` | `/api/v1/config` | Update configuration dynamically |

### WebSocket Endpoints

| Path | Description |
|---|---|
| `/ws/audio` | Voice command streaming + TTS response |
| `/ws/device` | Bidirectional device control channel |

---

## Project Structure

```
aura-agent/
|
+-- main.py                          # FastAPI app entry point, lifespan, middleware
+-- constants.py                     # API version, prefix, size limits
+-- requirements.txt                 # Python dependencies
|
+-- agents/                          # The 9 specialized agents
|   +-- commander.py                 # Intent parsing (rule-based + LLM)
|   +-- coordinator.py               # Multi-agent orchestration loop
|   +-- perceiver_agent.py           # Screen understanding wrapper
|   +-- planner_agent.py             # Goal decomposition (skeleton plans)
|   +-- actor_agent.py               # Gesture execution (zero LLM)
|   +-- verifier_agent.py            # Post-action verification
|   +-- responder.py                 # Natural language response generation
|   +-- validator.py                 # Rule-based intent validation
|   +-- visual_locator.py            # ScreenVLM — SoM visual perception
|
+-- aura_graph/                      # LangGraph state machine
|   +-- graph.py                     # Graph assembly (nodes + edges)
|   +-- state.py                     # TaskState definition (40+ fields)
|   +-- edges.py                     # Conditional routing logic
|   +-- core_nodes.py                # Node implementations
|   +-- agent_state.py               # Goal/Subgoal/RetryStrategy models
|   +-- nodes/                       # Specialized graph nodes
|       +-- perception_node.py       # Perception Controller integration
|       +-- coordinator_node.py      # Coordinator graph entry point
|       +-- decompose_goal_node.py   # Goal decomposition node
|       +-- validate_outcome_node.py # Post-execution validation
|       +-- retry_router_node.py     # Retry strategy selection
|       +-- next_subgoal_node.py     # Phase advancement
|
+-- config/                          # Configuration
|   +-- settings.py                  # Pydantic Settings (all env vars)
|   +-- action_types.py              # Metadata-driven ACTION_REGISTRY
|   +-- model_router.py              # Dynamic model resolution
|   +-- success_criteria.py          # Post-action validation criteria
|
+-- services/                        # Core service layer
|   +-- llm.py                       # Unified LLM interface (Groq/Gemini/NVIDIA)
|   +-- vlm.py                       # Vision-Language Model wrapper
|   +-- stt.py                       # Speech-to-Text (Groq Whisper)
|   +-- tts.py                       # Text-to-Speech (Edge-TTS)
|   +-- perception_controller.py     # Perception orchestration
|   +-- reactive_step_generator.py   # Layer 2 reactive planner
|   +-- goal_decomposer.py           # Skeleton plan generation
|   +-- gesture_executor.py          # Centralized gesture dispatch
|   +-- real_accessibility.py        # Android device communication
|   +-- policy_engine.py             # OPA Rego policy evaluation
|   +-- prompt_guard.py              # Llama Prompt Guard 2 safety
|   +-- screenshot_service.py        # Device screenshot capture
|   +-- conversation_manager.py      # Multi-turn dialogue context
|   +-- command_logger.py            # HTML execution logs
|   +-- hitl_service.py              # Human-in-the-loop interaction
|   +-- task_progress.py             # Real-time task progress broadcast
|   +-- visual_feedback.py           # Edge glow + ripple animations
|   +-- ui_signature.py              # UI tree fingerprinting
|   +-- vlm_element_locator.py       # VLM-based element location
|   +-- contact_resolver.py          # Name to phone number resolution
|   +-- token_tracker.py             # API usage monitoring
|
+-- perception/                      # OmniParser perception pipeline
|   +-- perception_pipeline.py       # Three-layer orchestration
|   +-- models.py                    # PerceptionBundle, UITreePayload
|   +-- omniparser_detector.py       # YOLOv8 UI element detection
|   +-- vlm_selector.py              # VLM + heuristic element selection
|
+-- prompts/                         # LLM prompt templates
|   +-- classification.py            # Intent parsing prompts
|   +-- skeleton_planning.py         # Phase decomposition prompts
|   +-- reactive_step.py             # Per-screen step prompts
|   +-- personality.py               # AURA personality definition
|   +-- vision.py                    # VLM screen analysis prompts
|   +-- screen_reader.py             # Screen description prompts
|   +-- reasoning.py                 # Complex reasoning prompts
|
+-- policies/                        # OPA Rego policy files
|   +-- safety.rego                  # Blocked actions, confirmations
|   +-- apps.rego                    # App-specific policies
|   +-- rate.rego                    # Rate limiting policies
|
+-- api/                             # API route definitions
|   +-- health.py                    # Health check endpoint
|   +-- tasks.py                     # Task submission endpoints
|   +-- device.py                    # Device control endpoints
|   +-- websocket.py                 # Audio WebSocket handler
|   +-- workflow.py                  # Workflow visualization
|   +-- graph.py                     # Graph structure endpoint
|   +-- config_api.py                # Dynamic configuration
|   +-- sensitive_policy.py          # Sensitive action policy API
|
+-- api_handlers/                    # WebSocket handlers
|   +-- websocket_router.py          # Device WebSocket handler
|   +-- device_router.py             # Device HTTP handlers
|   +-- task_router.py               # Task execution handlers
|
+-- middleware/                      # HTTP middleware
|   +-- rate_limit.py                # slowapi rate limiting
|   +-- request_id.py                # Request ID injection
|   +-- auth.py                      # Authentication middleware
|
+-- models/                          # Pydantic data models
|   +-- gestures.py                  # TapAction, SwipeAction models
|
+-- validators/                      # Input validation
|   +-- config.py                    # Configuration validation
|
+-- exceptions/                      # Error handling
|   +-- handlers.py                  # Global exception handlers
|
+-- utils/                           # Utility functions
|   +-- logger.py                    # Unified logging setup
|   +-- ui_element_finder.py         # UI tree element search
|   +-- app_inventory_utils.py       # App package name resolution
|   +-- perf_tracker.py              # Performance timing
|   +-- token_tracker.py             # Token usage monitoring
|
+-- tools/                           # Development and debug tools
|   +-- aura_client.py               # CLI client for testing
|   +-- agent_monitor.py             # Agent activity monitor
|   +-- get_ui_elements.py           # UI tree inspector
|
+-- scripts/                         # Test and utility scripts
|   +-- test_commander_live.py       # Live commander testing
|   +-- test_sensitive_blocking.py   # Safety policy tests
|   +-- view_ui_tree.py              # UI tree visualization
|
+-- websocket/                       # WebSocket utilities
|   +-- audio_buffer.py              # Audio chunk assembly
|
+-- static/                          # Static web files
|   +-- ui.py                        # Fallback web UI
|
+-- logs/                            # HTML execution logs (auto-generated)
|
+-- UI/                              # Android Companion App (Kotlin/Gradle)
|   +-- app/                         # Android app source
|   +-- build.gradle.kts             # Gradle build configuration
|   +-- settings.gradle.kts          # Gradle settings
|
+-- data/                            # Runtime data
    +-- failure_screenshots/         # Saved failure screenshots for debugging
```

---

## Installation and Setup

### Prerequisites

- **Python 3.11+**
- **Android device** connected via USB/Wi-Fi with **USB debugging** enabled
- **ADB** installed and accessible in PATH
- **Groq API key** (free tier available at [console.groq.com](https://console.groq.com))
- **Google Gemini API key** (free tier available at [aistudio.google.com](https://aistudio.google.com))

### 1. Clone the Repository

```bash
git clone https://github.com/Dinesh210805/Aura_agent.git
cd Aura_agent
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

OmniParser YOLOv8 models are auto-downloaded from HuggingFace on first use (~50MB).

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Required — AI Model Providers
GROQ_API_KEY=gsk_your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Optional — Enhanced intent classification
OPENROUTER_API_KEY=your_openrouter_key_here

# Optional — NVIDIA NIM (additional model provider)
NVIDIA_API_KEY=your_nvidia_key_here

# Optional — LangSmith observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here
LANGCHAIN_PROJECT=aura-agent

# Model Configuration (defaults are optimized, change only if needed)
DEFAULT_LLM_PROVIDER=groq
DEFAULT_VLM_PROVIDER=groq
DEFAULT_STT_PROVIDER=groq
DEFAULT_TTS_PROVIDER=edge-tts
```

See `.env.example` for the full list of configurable variables.

### 5. Connect Android Device

```bash
# Via USB
adb devices

# Via Wi-Fi (same network)
adb connect <device-ip>:5555
```

### 6. Install the Companion App

Build and install the Android app from the `UI/` directory, or use the provided APK:
1. Install the AURA companion app on your Android device
2. Enable **Accessibility Service** for AURA in Android Settings
3. Grant **screen capture permission** when prompted
4. Set the backend URL in the app to your server address

### 7. Start the Server

```bash
python main.py
```

The server starts on `http://0.0.0.0:8000` with:
- REST API at `/api/v1/`
- WebSocket at `/ws/audio` and `/ws/device`
- Health check at `/health`

---

## Configuration

All configuration is managed through **environment variables** loaded via Pydantic Settings. Key settings:

### Model Routing

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_LLM_PROVIDER` | `groq` | Provider for text/intent tasks |
| `DEFAULT_VLM_PROVIDER` | `groq` | Provider for vision tasks |
| `DEFAULT_STT_PROVIDER` | `groq` | Provider for speech-to-text |
| `DEFAULT_TTS_PROVIDER` | `edge-tts` | Provider for text-to-speech |
| `PLANNING_PROVIDER` | `groq` | Provider for planning/reasoning |
| `PLANNING_MODEL` | `llama-4-maverick-17b-128e` | Planning model |
| `DEFAULT_VLM_MODEL` | `llama-4-scout-17b-16e` | Vision model |
| `ENABLE_PROVIDER_FALLBACK` | `true` | Auto-fallback on failure |

### Perception

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_PERCEPTION_MODALITY` | `hybrid` | `ui_tree`, `hybrid`, `vision`, or `auto` |
| `PERCEPTION_CACHE_ENABLED` | `true` | Cache perception results |
| `PERCEPTION_CACHE_TTL` | `2.0` | Cache lifetime in seconds |

### Execution

| Variable | Default | Description |
|---|---|---|
| `USE_UNIVERSAL_AGENT` | `true` | Route through Coordinator |
| `ENABLE_PARALLEL_EXECUTION` | `true` | Parallel graph node execution |
| `MAX_PARALLEL_TASKS` | `3` | Concurrent task limit |

---

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black . && isort .
```

### Testing the Commander

```bash
python scripts/test_commander_live.py
```

### Inspecting UI Trees

```bash
python scripts/view_ui_tree.py
```

### Monitoring Agent Activity

```bash
python tools/agent_monitor.py
```

### CLI Client

```bash
python tools/aura_client.py "open settings and turn on wifi"
```

### Viewing Execution Logs

AURA generates HTML execution logs in the `logs/` directory. Each log shows:
- Every LLM call with input/output
- Every gesture executed with coordinates
- Perception pipeline decisions
- Retry ladder progression
- Timing information

Open any log file in a browser to inspect a full execution trace.

### LangSmith Tracing

When `LANGCHAIN_TRACING_V2=true` is set, all LangGraph executions are traced to [LangSmith](https://smith.langchain.com/) for debugging and monitoring. You can inspect:
- State transitions between graph nodes
- Token usage per model call
- Latency breakdown per node
- Error propagation through the graph

---

## Contributing

Contributions are welcome! Here is how to get started:

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Format code: `black . && isort .`
6. Submit a pull request

### Code Style

- **Formatter:** `black` (line length: 88)
- **Import sorting:** `isort`
- **Type hints:** Required for function parameters and return types
- **Docstrings:** Required for public functions (concise "what", not "how")

### Architecture Guidelines

- **Agents are single-responsibility.** Don't add LLM calls to `ActorAgent`. Don't add gesture execution to `PerceiverAgent`.
- **New actions go in `ACTION_REGISTRY`** (`config/action_types.py`) — add once, all routing updates automatically.
- **Perception coordinates come from deterministic sources only.** Never let a VLM generate pixel coordinates.
- **Retry before replan.** The retry ladder is cheaper than an LLM replan call.
- **Test against a real device.** AURA is designed for real Android interaction, not mocked simulations.

### Adding a New Agent

1. Create `agents/your_agent.py` with a class that has an `async execute()` method
2. Wire it into the Coordinator's loop if it participates in the execution cycle
3. Or add it as a new LangGraph node in `aura_graph/graph.py` if it is a pipeline stage

### Adding a New Action

1. Add the action to `ACTION_REGISTRY` in `config/action_types.py`:
   ```python
   "your_action": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
   ```
2. Handle execution in `services/gesture_executor.py`
3. Add success criteria in `config/success_criteria.py`
4. Add safety rules in `policies/safety.rego` if needed

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | FastAPI 0.104 + Uvicorn | HTTP/WebSocket server |
| **Agent Orchestration** | LangGraph 0.3.27+ | State machine for agent flow |
| **LLM Providers** | Groq, Google Gemini, OpenRouter, NVIDIA NIM | Multi-provider model routing |
| **Computer Vision** | YOLOv8 (Ultralytics) via OmniParser | UI element detection |
| **Speech-to-Text** | Groq Whisper Large v3 Turbo | Voice transcription |
| **Text-to-Speech** | Edge-TTS | Local voice synthesis (300+ voices) |
| **Policy Engine** | OPA Rego via regopy | Safety policy evaluation |
| **Safety Guard** | Llama Prompt Guard 2 86M | Injection/jailbreak detection |
| **Observability** | LangSmith | Execution tracing and monitoring |
| **Device Control** | Android AccessibilityService + MediaProjection | UI automation |
| **Companion App** | Kotlin + Gradle | Android client |

---

## Acknowledgments

| Component | Source |
|---|---|
| Agent Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM Inference | [Groq](https://groq.com/), [Google Gemini](https://deepmind.google/technologies/gemini/), [OpenRouter](https://openrouter.ai/) |
| OmniParser Architecture | [Microsoft OmniParser](https://microsoft.github.io/OmniParser/) |
| CV Detection | [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) |
| API Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Policy Engine | [OPA / Rego](https://www.openpolicyagent.org/) |
| Safety Guard | [Llama Prompt Guard 2](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M) |
| Text-to-Speech | [Edge-TTS](https://github.com/rany2/edge-tts) |

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built with care by the AURA team</strong>
  <br>
  <sub>AURA — Making Android devices truly autonomous, one voice command at a time.</sub>
</p>

<p align="center">
  <a href="https://github.com/Dinesh210805/Aura_agent/issues">Report Bug</a> | <a href="https://github.com/Dinesh210805/Aura_agent/issues">Request Feature</a>
</p>
