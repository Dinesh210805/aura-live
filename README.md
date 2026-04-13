<p align="center">
  <img src="https://img.shields.io/badge/AURA-Autonomous%20User--Responsive%20Agent-blueviolet?style=for-the-badge&logo=android&logoColor=white" alt="AURA Badge"/>
</p>

<h1 align="center">AURA — Autonomous User-Responsive Agent</h1>

<p align="center">
  <strong>A voice-controlled, multi-agent AI system that sees, understands, plans, and acts on your Android device in real-time.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/LangGraph-0.3.27+-FF6F00?style=flat-square&logo=langchain&logoColor=white" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Groq-Llama%204-F55036?style=flat-square&logo=meta&logoColor=white" alt="Groq"/>
  <img src="https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?style=flat-square&logo=google&logoColor=white" alt="Gemini"/>
  <img src="https://img.shields.io/badge/Google%20ADK-root__agent-34A853?style=flat-square&logo=google&logoColor=white" alt="Google ADK"/>
  <img src="https://img.shields.io/badge/OPA-Rego%20Policies-7D9AAA?style=flat-square&logo=openpolicyagent&logoColor=white" alt="OPA"/>
  <img src="https://img.shields.io/badge/YOLOv8-UI%20Detection-00FFFF?style=flat-square&logo=yolo&logoColor=black" alt="YOLOv8"/>
  <img src="https://img.shields.io/badge/Edge--TTS-Voice-0078D4?style=flat-square&logo=microsoft&logoColor=white" alt="Edge-TTS"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Agents-9%20Specialized-purple?style=flat-square" alt="9 Agents"/>
  <img src="https://img.shields.io/badge/Gemini%20Live-Bidi%20Audio%2BVision-4285F4?style=flat-square&logo=google" alt="Gemini Live"/>
  <img src="https://img.shields.io/badge/Cloud%20Run-Deployed-4285F4?style=flat-square&logo=googlecloud" alt="Cloud Run"/>
  <img src="https://img.shields.io/badge/GCS-Execution%20Logs-orange?style=flat-square&logo=googlecloud" alt="GCS"/>
</p>

---

## What is AURA?

AURA is a production-grade Android UI automation backend. A user speaks a natural language command — AURA captures the screen, parses the UI tree, plans a series of atomic actions, executes gestures on the real device via Android Accessibility API, and speaks a natural response back.

**Example**: *"Open Spotify and play my liked songs"*
→ AURA opens the app, locates the Liked Songs button visually, taps it, starts playback, and says *"Done — your liked songs are playing."*

Built as a submission to the **Gemini Live Agent Challenge**, AURA integrates Google ADK, Gemini Live bidirectional audio+vision, and Cloud Run deployment.

---

## Table of Contents

- [Architecture](#architecture)
- [The 9 Agents](#the-9-agents)
- [LangGraph Orchestration](#langgraph-orchestration)
- [Tri-Provider Model Architecture](#tri-provider-model-architecture)
- [Perception Pipeline](#perception-pipeline)
- [Reactive Step Generator](#reactive-step-generator)
- [Google Cloud Integration](#google-cloud-architecture)
- [Android Companion App](#android-companion-app)
- [WebSocket Endpoints](#websocket-endpoints)
- [REST API](#rest-api)
- [MCP Integration](#mcp-integration)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Cloud Run Deployment](#cloud-run-deployment)
- [Safety & Policies](#safety--policies)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER SPEAKS COMMAND                          │
│              (Android companion app, mic button)                    │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ WebSocket  /ws/live  or  /ws/audio
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI  +  LangGraph                           │
│                                                                     │
│  Audio → [STT: Groq Whisper] → transcript                           │
│                ↓                                                    │
│  [Commander Agent] → IntentObject (action, target, confidence)      │
│                ↓                                                    │
│  [Safety: Llama Prompt Guard 2 86M]                                 │
│                ↓                                                    │
│  Smart Router ─────────────────────────────────────────────────┐   │
│     NO_UI actions → Coordinator (skip perception)              │   │
│     Complex/multi-step → Coordinator                           │   │
│     UI actions → Perception → Coordinator                      │   │
│                                                                 │   │
│  ┌──────────────────────────────────────────────────────────┐  │   │
│  │              COORDINATOR  (perceive→decide→act→verify)   │  │   │
│  │                                                          │  │   │
│  │  ┌─────────┐   ┌─────────┐   ┌───────┐   ┌──────────┐  │  │   │
│  │  │Perceiver│ → │ Planner │ → │ Actor │ → │Verifier  │  │  │   │
│  │  │UI+Vision│   │ Phases  │   │ Zero- │   │Post-state│  │  │   │
│  │  │  SoM    │   │Reactive │   │  LLM  │   │ capture  │  │  │   │
│  │  └─────────┘   └─────────┘   └───────┘   └──────────┘  │  │   │
│  │       ↑                           │                      │  │   │
│  │       └────── 5-step Retry ───────┘                      │  │   │
│  │               Ladder + Replan                            │  │   │
│  └──────────────────────────────────────────────────────────┘  │   │
│                ↓                                                 │   │
│  [Responder Agent] → natural language reply                     │   │
│                ↓                                                    │
│  [TTS: Edge-TTS en-US-AriaNeural] → WAV audio                      │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
              Android device executes gesture
              via Accessibility API (no root)
```

**Request lifecycle**:
1. Audio arrives over WebSocket → STT transcription via Groq Whisper Large v3 Turbo
2. Intent parsed by `CommanderAgent` (rule-based + LLM fallback)
3. Safety screened by Llama Prompt Guard 2 86M
4. Smart routing based on action type and complexity
5. Coordinator drives 9 agents through the perceive→decide→act→verify loop
6. Gesture executed via Android Accessibility API after OPA Rego policy check
7. Response spoken via Edge-TTS (Microsoft, no API key required)

---

## The 9 Agents

All agents are single-responsibility — located in `agents/`.

| Agent | File | Responsibility |
|---|---|---|
| **Commander** | `commander.py` | Parses voice transcript → structured `IntentObject` using rule-based classifier (fast) with LLM fallback |
| **Planner** | `planner_agent.py` | Decomposes goal into skeleton phases + ordered atomic `Subgoal` list (max 12 words each) |
| **Perceiver** | `perceiver_agent.py` | Captures screenshot + UI tree → `ScreenState` with Set-of-Marks annotations; never returns raw pixel coordinates |
| **Actor** | `actor_agent.py` | Zero-LLM deterministic gesture executor (tap, type, scroll, swipe, open_app, etc.) |
| **Responder** | `responder.py` | Generates natural TTS-ready conversational responses via LLM; strips markdown for clean speech |
| **Verifier** | `verifier_agent.py` | Waits for UI to settle post-gesture, captures post-action state, detects error dialogs |
| **Validator** | `validator.py` | Fast rule-based intent validation — no LLM calls, zero latency |
| **ScreenVLM** | `visual_locator.py` | Tri-layer visual perception: UI tree → YOLOv8 CV → VLM selection from numbered Set-of-Marks elements |
| **Coordinator** | `coordinator.py` | Orchestrates all 8 agents through perceive→decide→act→verify with 5-step retry ladder and adaptive replanning |

### Critical Invariant

> **The VLM never returns raw pixel coordinates.** It only selects among numbered Set-of-Marks elements detected by YOLOv8. This invariant must never be broken.

---

## LangGraph Orchestration

**File**: `aura_graph/graph.py`

The graph is a `StateGraph(TaskState)` with 15 nodes, compiled via `compile_aura_graph()` at server startup.

```
__start__
    │
    ├─ audio → [stt] → [parse_intent]
    └─ text/streaming → [parse_intent]
                            │
            ┌───────────────┼───────────────────┐
            │               │                   │
        [coordinator]  [perception]→[coordinator]  [speak]
            │                                   │
            └───────────────────────────────────┘
                            │
                         [speak] → END
```

**Conditional routing** (edges.py):
- `NO_UI` actions (open_app, scroll, system) → coordinator directly (skip perception)
- Multi-step commands (contains "and", "then") → coordinator
- Conversational intents → speak directly
- UI actions → perception → coordinator
- Low confidence / general_interaction → coordinator for full planning

**Retry loop** (within coordinator):
```
perceive → decide → act → verify
    ↑                          │
    └── 5-step retry ladder ───┘
         1. SAME_ACTION          (retry exact)
         2. ALTERNATE_SELECTOR   (different element)
         3. SCROLL_AND_RETRY     (scroll to find)
         4. VISION_FALLBACK      (VLM coordinate mode)
         5. ABORT → replan (max 3 replans before giving up)
```

**State** (`aura_graph/state.py`): `TaskState` TypedDict with ~40 fields, custom LangGraph reducers:
- `error_message` — accumulates (joins multiple errors with `;`)
- `status` — last-writer-wins
- `current_step` — takes maximum value (concurrent-safe)
- `end_time` — first-writer-wins (preserves actual completion time)

---

## Tri-Provider Model Architecture

AURA uses a tri-provider strategy: **Groq** (primary, speed), **Gemini** (fallback, quality), **NVIDIA NIM** (optional, scale).

### LLM Models

| Task | Provider | Model | Notes |
|---|---|---|---|
| Intent parsing | Groq | `llama-3.1-8b-instant` | 560 T/s, <300 tokens |
| Low-confidence intent | Groq | `llama-3.3-70b-versatile` | fallback |
| Planning / reasoning | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | 16 experts |
| Planning fallback | Gemini | `gemini-2.5-flash` | |
| Response generation | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | |
| Intent classification | OpenRouter | `z-ai/glm-4.5-air:free` | free tier |
| Intent classif. fallback | OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` | |
| Intent classif. fallback 2 | Groq | `llama-3.3-70b-versatile` | |
| Safety screening | Groq | `meta-llama/llama-prompt-guard-2-86m` | specialized |
| ADK root agent | Google ADK | `gemini-2.5-flash` | |
| Gemini Live bidi | Google | `gemini-2.0-flash-live-001` | |

### VLM Models

| Task | Provider | Model |
|---|---|---|
| UI analysis / screen understanding | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Visual element selection (SoM) | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` |
| VLM fallback | Gemini | `gemini-2.5-flash` |

### STT / TTS

| Service | Provider | Model / Voice |
|---|---|---|
| Speech-to-Text | Groq | `whisper-large-v3-turbo` (16 kHz PCM mono) |
| Text-to-Speech | Edge-TTS (Microsoft) | `en-US-AriaNeural` (default, no API key) |
| Gemini Live voice | Google | `Charon` (configurable) |

---

## Perception Pipeline

**Files**: `services/perception_controller.py`, `perception/omniparser_detector.py`, `perception/vlm_selector.py`

Three-layer hybrid — each layer only runs if the previous is insufficient:

```
Layer 1: Android Accessibility UI Tree
  → Package name, activity, all interactive elements
  → Fast (~50 ms), but misses visual-only elements

Layer 2: YOLOv8 OmniParser (CV Detection)
  → Detects clickable elements in screenshot
  → Draws numbered Set-of-Marks boxes on image
  → Pixel-accurate without returning coordinates

Layer 3: VLM Selection (ScreenVLM)
  → Receives annotated screenshot with numbered elements
  → Returns index of target element (never raw coordinates)
  → Falls back to Gemini 2.5 Flash if Groq fails
```

**Perception modalities** (configurable via `DEFAULT_PERCEPTION_MODALITY`):
- `hybrid` — UI tree + vision (default, most reliable)
- `ui_tree` — fast path for settings-style apps
- `vision` — screenshot-only for canvas/WebView apps
- `auto` — controller selects based on app type

**Caching**: Screenshots cached for 2 s (configurable), invalidated after 1 gesture.

---

## Reactive Step Generator

**File**: `services/reactive_step_generator.py`

Instead of committing to a full upfront plan (which breaks when screens deviate), AURA generates **one concrete action at a time** grounded in the live screen.

```python
async def generate_next_step(
    goal,           # what user wants to accomplish
    screen_context, # current screen description
    step_history,   # what was done so far
    screenshot_b64, # actual screenshot bytes
    ui_hints,       # UI tree labels
) -> Subgoal:       # ONE next action
```

The planner creates **skeleton phases** (e.g., "Open Spotify", "Navigate to Liked Songs", "Start Playback"). For each phase, the reactive generator asks a VLM: *"given the current screen and this phase goal, what is the single next UI action?"* — grounding every decision in real screen state.

---

## Google Cloud Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Google Cloud                          │
│                                                         │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │   Cloud Run      │    │   Cloud Storage           │  │
│  │  aura-backend    │───▶│  aura-execution-logs/     │  │
│  │  (this server)   │    │  logs/{task_id}.html      │  │
│  └────────┬─────────┘    └───────────────────────────┘  │
│           │                                             │
│  ┌────────▼─────────┐                                   │
│  │   Google ADK     │                                   │
│  │  root_agent      │                                   │
│  │  gemini-2.5-flash│                                   │
│  │  + FunctionTool  │                                   │
│  │  execute_aura_   │                                   │
│  │    task()        │                                   │
│  └────────┬─────────┘                                   │
│           │                                             │
│  ┌────────▼─────────┐                                   │
│  │   Gemini Live    │                                   │
│  │  /ws/live        │                                   │
│  │  gemini-2.0-     │                                   │
│  │  flash-live-001  │                                   │
│  │  Bidi audio+vis  │                                   │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

### ADK Root Agent (`adk_agent.py`)

```python
root_agent = Agent(
    name="AURA",
    model="gemini-2.5-flash",
    tools=[aura_tool],   # FunctionTool wrapping execute_aura_task_from_text()
)
```

Lazy initialization — `set_compiled_graph(app)` must be called from `main.py` lifespan before any tool invocation. The tool returns `success`, `response`, `steps_taken`, and `execution_log_url`.

### Gemini Live Bidirectional Streaming (`adk_streaming_server.py`)

Enabled when `GEMINI_LIVE_ENABLED=true`. Registers `/ws/live` in `main.py`.

**Features**:
- Full Voice Activity Detection (`prefix_padding_ms=160`, `silence_duration_ms=650`, high start/end sensitivity)
- Barge-in support (`START_OF_ACTIVITY_INTERRUPTS`)
- Thinking content filter — strips `**Bold**` reasoning headers from model output
- Transcript accumulation across sub-turns until `turn_complete`
- Non-blocking live request queue (audio + screenshot frames)

**Message protocol** (Android ↔ server):

| Direction | Type | Payload |
|---|---|---|
| Android → Server | `audio_chunk` | PCM 16 kHz mono int16, base64 |
| Android → Server | `screenshot` | JPEG base64 |
| Android → Server | `text_command` | plain text fallback |
| Server → Android | `audio_response` | PCM 24 kHz mono int16, base64 |
| Server → Android | `transcript` | incremental + final text |
| Server → Android | `task_progress` | `"executing"` or `"idle"` |

### GCS Execution Logs (`gcs_log_uploader.py`)

After every task, the HTML execution log is uploaded to Cloud Storage:

```python
log_url = await upload_log_to_gcs_async(log_path, task_id)
# → gs://aura-execution-logs/logs/{task_id}.html (public URL)
```

Non-fatal: failures are logged as warnings only. Disabled by default (`GCS_LOGS_ENABLED=false`).

### Cloud Run Deployment

```bash
gcloud run deploy aura-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --set-secrets="GOOGLE_API_KEY=...,GROQ_API_KEY=...,GEMINI_API_KEY=..."
```

The server reads `$PORT` from Cloud Run automatically via Pydantic Settings. YOLOv8 is pre-warmed at Docker build time to eliminate cold-start latency.

---

## Android Companion App

Located in `UI/`. Kotlin + Jetpack Compose.

### GeminiLiveController (`voice/GeminiLiveController.kt`)

Handles continuous voice capture and WebSocket communication:

```kotlin
companion object {
    const val SAMPLE_RATE = 16000           // 16 kHz
    const val AUDIO_FORMAT = PCM_16BIT      // int16 mono
    const val CHUNK_MS = 100                // 100 ms chunks
    const val SCREENSHOT_INTERVAL_MS = 3000 // every 3 s
    const val UI_TREE_INTERVAL_MS = 5000    // every 5 s
    const val PING_INTERVAL_MS = 25_000     // keepalive
}
```

- Continuous listen mode — no push-to-talk button required
- Audio chunks encoded as base64 and sent as WebSocket frames
- Screenshots and UI tree sent on independent timers
- Auto-silence detection after 8 s of post-response inactivity

### ConversationViewModel (`conversation/ConversationViewModel.kt`)

Manages conversation state as `StateFlow`:
- `ConversationState` — current phase, session ID, connection status
- `List<ConversationMessage>` — full message history
- `List<AgentOutput>` — per-agent status updates (for debug overlay)

---

## WebSocket Endpoints

| Endpoint | Direction | Purpose | Notes |
|---|---|---|---|
| `ws://host/ws/audio` | Bidi | Legacy voice command streaming | Android app dependency — path must not change |
| `ws://host/ws/device` | Bidi | Device screenshot + UI tree polling | Android app dependency — path must not change |
| `ws://host/ws/live` | Bidi | Gemini Live bidi audio+vision | Requires `GEMINI_LIVE_ENABLED=true` |
| `ws://host/api/v1/tasks/ws` | Server→Client | Live task event streaming | For demo dashboard |

---

## REST API

| Endpoint | Method | Description |
|---|---|---|
| `GET /health` | GET | Health check (legacy) |
| `GET /api/v1/health` | GET | Health check (versioned) |
| `POST /api/v1/graph/execute` | POST | Execute task from text |
| `POST /api/v1/execute` | POST | Natural-language command (REST fallback for non-MCP agents) |
| `GET /api/v1/device/screenshot` | GET | Live screenshot |
| `GET /demo` | GET | Judge dashboard (live screenshot, recent commands, GCS log links) |
| `GET /docs` | GET | OpenAPI docs (development only) |

---

## MCP Integration

AURA exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server for any AI coding agent to control an Android device directly.

### Start the MCP Server

```bash
python aura_mcp_server.py
```

### Configure Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "aura": {
      "command": "python",
      "args": ["/absolute/path/to/aura-live/aura_mcp_server.py"],
      "env": {}
    }
  }
}
```

### MCP Tools

| Tool | Style | Description |
|---|---|---|
| `execute_android_task(utterance)` | Black-box | Run any natural-language command through the full AURA pipeline |
| `perceive_screen()` | Granular | Capture screenshot + SoM-labeled UI elements |
| `execute_gesture(type, target, params)` | Granular | Tap, swipe, type, scroll on a specific element |
| `validate_action(type, target)` | Granular | Check OPA safety policy before executing |
| `watch_device_events(timeout)` | Streaming | Subscribe to gesture/task/screenshot events |

**Style A** (black-box) — one tool, full pipeline. Use with any agent that supports MCP.  
**Style B** (granular) — Claude sees the screen, reasons, picks elements by SoM label. Best with vision-capable models.

### Agent Compatibility

| Agent | MCP Support | Style A | Style B |
|---|---|---|---|
| **Claude Code** | Native | Yes | Yes (best — native vision) |
| **GitHub Copilot** | Yes (2025) | Yes | Model-dependent |
| **Cursor** | Yes | Yes | Model-dependent |
| **Windsurf** | Yes | Yes | Model-dependent |
| **Any HTTP client** | Via REST | `POST /api/v1/execute` | — |

See [quickstart.md](quickstart.md) for the full setup walkthrough.

---

## Installation

### Prerequisites

- Python 3.11+
- Android device with USB debugging + Accessibility Service enabled
- `adb` in PATH
- Groq API key (required), Gemini API key (required), others optional

### Setup

```bash
git clone <repo>
cd aura-live

# Install dependencies (note: filename has a space)
pip install -r "requirements copy.txt"

# Copy and fill in your API keys
cp .env.example .env
```

---

## Configuration

All settings flow through `config/settings.py` (Pydantic `BaseSettings`). Never read `os.environ` directly.

Create a `.env` file:

```env
# ── Required ──────────────────────────────────────
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
GOOGLE_API_KEY=AIza...          # same key, needed by google-genai SDK

# ── Providers (defaults shown) ────────────────────
DEFAULT_LLM_PROVIDER=groq
DEFAULT_VLM_PROVIDER=groq
DEFAULT_STT_PROVIDER=groq
DEFAULT_TTS_PROVIDER=edge-tts
PLANNING_PROVIDER=groq

# ── Models (defaults shown) ───────────────────────
DEFAULT_LLM_MODEL=llama-3.1-8b-instant
DEFAULT_VLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
PLANNING_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
DEFAULT_STT_MODEL=whisper-large-v3-turbo
DEFAULT_TTS_MODEL=en-US-AriaNeural

# ── Perception ────────────────────────────────────
DEFAULT_PERCEPTION_MODALITY=hybrid   # ui_tree | hybrid | vision | auto
PERCEPTION_CACHE_ENABLED=true
PERCEPTION_CACHE_TTL=2.0

# ── Google Cloud (for Gemini Live + GCS logs) ─────
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_REGION=us-central1
GCS_LOGS_BUCKET=aura-execution-logs
GCS_LOGS_ENABLED=false           # set true to upload HTML logs
GEMINI_LIVE_ENABLED=false        # set true to enable /ws/live
GEMINI_LIVE_MODEL=gemini-2.0-flash-live-001
GEMINI_LIVE_VOICE=Charon         # Aoede | Charon | Fenrir | Kore | Puck | ...

# ── Optional providers ────────────────────────────
NVIDIA_API_KEY=...
OPENROUTER_API_KEY=...

# ── LangGraph limits ──────────────────────────────
GRAPH_RECURSION_LIMIT=100
GRAPH_TIMEOUT_SECONDS=120.0

# ── Server ────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=DEBUG
RELOAD=true

# ── Security ──────────────────────────────────────
REQUIRE_API_KEY=true
DEVICE_API_KEY=your-secret-key
```

---

## Running

```bash
# Start the server
python main.py
# → http://0.0.0.0:8000
# → Docs: http://localhost:8000/docs
# → Health: GET http://localhost:8000/health
# → Demo dashboard: http://localhost:8000/demo
```

### Utility scripts

```bash
python scripts/test_commander_live.py      # test intent parsing live
python scripts/test_sensitive_blocking.py  # test OPA policy blocking
python scripts/view_ui_tree.py             # inspect device UI tree
python scripts/dead_code_scanner.py        # scan for unused code
```

### Tests

```bash
pytest tests/
pytest tests/test_foo.py::test_bar         # single test
```

---

## Cloud Run Deployment

```bash
# Build + deploy from source
gcloud run deploy aura-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --set-secrets="GOOGLE_API_KEY=projects/.../secrets/GOOGLE_API_KEY/versions/latest,GROQ_API_KEY=...,GEMINI_API_KEY=..."

# Verify
curl https://aura-backend-xxx-uc.a.run.app/health
```

The `Dockerfile` pre-warms YOLOv8 at build time so the first real VLM call has no model-load latency. The server reads `$PORT` automatically from Cloud Run's injected environment variable.

---

## Safety & Policies

**Dual-layer safety**:

1. **Llama Prompt Guard 2 86M** (`services/prompt_guard.py`) — screens every voice input before intent parsing. Blocks jailbreaks, prompt injections, and harmful commands. Fail-safe: allows on API error.

2. **OPA Rego Policies** (`policies/`, `services/policy_engine.py`) — gates every single gesture execution. Policies check:
   - Action type (send message, make purchase, delete data require confirmation)
   - Device state (locked screen, accessibility disabled)
   - Target app context

Both layers are fail-safe (allow on error) so transient API failures don't block legitimate commands.

---

## Critical Invariants

1. **VLM never returns pixel coordinates** — only selects from numbered SoM elements
2. **5-stage retry ladder** runs before any replanning
3. **Every gesture** passes through OPA policy check in `gesture_executor.py`
4. **All new actions** must be registered in `config/action_types.py` ACTION_REGISTRY
5. **All service functions** must be `async def`
6. **All API keys** go through `config/settings.py` — never `os.environ` directly
7. **9 agents stay single-responsibility** — no merging or scope creep
8. **`/ws/audio` and `/ws/device`** paths must not change (Android app dependency)

---

## Project Structure

```
aura-live/
├── main.py                          # FastAPI app + lifespan
├── adk_agent.py                     # Google ADK root_agent (gemini-2.5-flash)
├── adk_streaming_server.py          # Gemini Live /ws/live handler
├── gcs_log_uploader.py              # Cloud Storage HTML log upload
├── Dockerfile                       # Cloud Run deployment
├── requirements copy.txt            # Python dependencies
│
├── agents/                          # The 9 single-responsibility agents
│   ├── commander.py                 # Intent parsing
│   ├── planner_agent.py             # Goal decomposition
│   ├── perceiver_agent.py           # Screen capture + SoM
│   ├── coordinator.py               # Multi-agent orchestrator
│   ├── actor_agent.py               # Zero-LLM gesture execution
│   ├── responder.py                 # Natural language responses
│   ├── validator.py                 # Rule-based validation
│   ├── verifier_agent.py            # Post-action verification
│   └── visual_locator.py            # ScreenVLM (SoM selection)
│
├── aura_graph/                      # LangGraph state machine
│   ├── graph.py                     # Graph assembly + entry points
│   ├── state.py                     # TaskState TypedDict (~40 fields)
│   ├── edges.py                     # Conditional routing functions
│   ├── core_nodes.py                # Node implementations
│   └── nodes/                       # Specialized nodes
│       ├── perception_node.py
│       ├── coordinator_node.py
│       ├── validate_outcome_node.py
│       ├── retry_router_node.py
│       ├── decompose_goal_node.py
│       └── next_subgoal_node.py
│
├── config/
│   ├── settings.py                  # Pydantic Settings (all env vars)
│   └── action_types.py              # ACTION_REGISTRY
│
├── services/
│   ├── perception_controller.py     # Tri-layer perception orchestration
│   ├── reactive_step_generator.py   # Per-screen action generation
│   ├── gesture_executor.py          # Gesture execution + strategy selection
│   ├── llm.py                       # Unified LLM interface (Groq/Gemini/NVIDIA)
│   ├── vlm.py                       # Unified VLM interface
│   ├── stt.py                       # Groq Whisper STT
│   ├── tts.py                       # Edge-TTS (Microsoft)
│   ├── prompt_guard.py              # Llama Prompt Guard 2 safety screening
│   ├── policy_engine.py             # OPA Rego policy gateway
│   └── command_logger.py            # HTML execution log builder
│
├── perception/
│   ├── perception_pipeline.py       # YOLOv8 + SoM pipeline
│   ├── omniparser_detector.py       # YOLOv8 UI element detection
│   └── vlm_selector.py              # VLM-based element selection
│
├── api/
│   ├── demo.py                      # /demo judge dashboard
│   ├── graph.py                     # /api/v1/graph/execute
│   ├── health.py                    # /health endpoints
│   └── tasks.py                     # /api/v1/tasks/ws streaming
│
├── api_handlers/
│   └── websocket_router.py          # /ws/audio and /ws/device handlers
│
├── policies/                        # OPA Rego policy files
├── prompts/                         # LLM prompt templates
└── UI/                              # Android companion app (Kotlin)
    └── app/src/main/java/com/aura/aura_ui/
        ├── conversation/ConversationViewModel.kt
        └── voice/GeminiLiveController.kt
```

---

## License

MIT — see `LICENSE`.

---

<p align="center">
  Built for the <strong>Gemini Live Agent Challenge</strong> · Powered by Google ADK, Gemini Live, Groq, LangGraph, and Android Accessibility API
</p>
