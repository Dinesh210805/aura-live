# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AURA (Autonomous User-Responsive Agent)** is a production-grade Android UI automation system controlled via voice. Users speak commands; AURA captures a screenshot, parses the UI tree, plans steps, executes gestures on the Android device, and responds in natural language.

**Active context**: This repo is a submission to the **Gemini Live Agent Challenge** (deadline: March 16, 2026 @ 5:00 PM PT). See `.github/instructions/gemini-live-hackathon-instructions.md` for the full task breakdown and mandatory requirements.

---

## Commands

### Run the server
```bash
python main.py
# Server: http://0.0.0.0:8000  |  Docs: /docs  |  Health: GET /health
```

### Install dependencies
```bash
pip install -r "requirements copy.txt"
```
> Note: The file is literally named `requirements copy.txt` (with a space).

### Run tests
```bash
pytest tests/
pytest tests/test_foo.py::test_bar   # single test
```

### Utility scripts
```bash
python scripts/test_commander_live.py    # live commander agent test
python scripts/test_sensitive_blocking.py
python scripts/view_ui_tree.py
python scripts/dead_code_scanner.py
```

---

## Architecture

### Request lifecycle
1. Voice audio arrives over WebSocket → `api_handlers/websocket_router.py`
2. STT transcription via Groq Whisper (`services/stt.py`)
3. Intent classified by `utils/fuzzy_classifier.py` → complexity tier (conversational / simple / medium / complex)
4. Safety screening via `services/prompt_guard.py` (Llama Prompt Guard 2)
5. Task dispatched to `aura_graph/graph.py` → `run_aura_task()`
6. LangGraph state machine drives 9 agents through perceive→decide→act→verify loop
7. Gesture executed via `services/gesture_executor.py` after OPA policy check
8. Response spoken via `services/tts.py` (Edge-TTS)

### The 9 agents (`agents/`)
Each is single-responsibility — do not merge or expand scope:
- `perceiver_agent.py` — wraps PerceptionController
- `commander.py` — parses intent
- `planner_agent.py` — goal decomposition into skeleton phases
- `coordinator.py` — perceive→decide→act→verify loop
- `actor_agent.py` — gesture execution (zero LLM calls)
- `responder.py` — natural language responses
- `validator.py` — rule-based validation
- `verifier_agent.py` — post-action verification
- `visual_locator.py` — ScreenVLM with Set-of-Marks

### LangGraph orchestration (`aura_graph/`)
- `state.py` — `TaskState` TypedDict (~40 fields), `Goal`/`Subgoal`/`RetryStrategy` models
- `graph.py` — assembles the graph; `run_aura_task()` is the main entry point
- `edges.py` — conditional routing (retry ladder, replanning triggers)
- `core_nodes.py` + `nodes/` — node implementations

### Perception pipeline (`perception/` + `services/perception_controller.py`)
Three-layer hybrid: UI tree → YOLOv8 CV detection (`omniparser_detector.py`) → VLM selection (`vlm_selector.py`). **The VLM selects among numbered CV-detected elements (Set-of-Marks) — it never returns raw pixel coordinates.** This invariant must never be broken.

### Tri-provider LLM/VLM architecture
- LLM: `services/llm.py` — Groq primary, Gemini/NVIDIA fallback
- VLM: `services/vlm.py` — controlled by `DEFAULT_VLM_PROVIDER` / `DEFAULT_VLM_MODEL` in settings
- Intent classifier: `utils/fuzzy_classifier.py` — Groq primary, Gemini 1.5 Flash fallback, rule-based last resort

### Configuration (`config/settings.py`)
All environment variables flow through a single Pydantic `Settings` class. Never read `os.environ` directly — use `from config.settings import settings`. Copy `.env.example` to `.env` to configure locally.

### Safety (`policies/`, `services/policy_engine.py`, `services/prompt_guard.py`)
OPA Rego policies gate every gesture execution. Prompt Guard 2 screens all voice inputs. Both fail-safe (allow on API error).

### WebSocket endpoints
- `ws://localhost:8000/ws/audio` — voice streaming
- `ws://localhost:8000/ws/device` — device control / UI tree responses
- `ws://localhost:8000/api/v1/tasks/ws` — task execution streaming
- `ws://localhost:8000/ws/live` — Gemini Live bidi audio+vision (gated by `GEMINI_LIVE_ENABLED=true`)

`/ws/audio` and `/ws/device` must not change signature or path — the Android companion app (`UI/`) depends on them. `/ws/live` is an addition.

### Google Cloud / ADK layer (Hackathon additions)
- `adk_agent.py` — ADK `root_agent` (gemini-2.5-flash) wrapping `execute_aura_task_from_text()` as a `FunctionTool`. Lazy graph init: call `set_compiled_graph(app)` from `main.py` lifespan before any tool invocation.
- `adk_streaming_server.py` — Gemini Live bidi WebSocket handler for `/ws/live`. Full VAD config (`RealtimeInputConfig`), transcript accumulation, barge-in support. Guarded behind `GEMINI_LIVE_ENABLED`.
- `gcs_log_uploader.py` — uploads HTML execution logs to GCS after each task; returns public URL stored in `TaskState.log_url`. Non-fatal: failures are warnings only.
- `Dockerfile` — Cloud Run deployment. Reads `$PORT` via Pydantic Settings. Pre-warms YOLOv8 at build time.
- `.dockerignore` — excludes `.env`, `logs/`, `UI/`, `.git/`, `venv/`
- `api/demo.py` — `/demo` judging dashboard: live screenshot (2 s refresh), health status, recent commands, GCS log links, architecture diagram.

---

## Critical Invariants

1. **VLM never returns pixel coordinates** — only selects among numbered SoM elements
2. **5-stage retry ladder** (`aura_graph/edges.py`) runs before any replanning
3. **Every gesture** passes through OPA policy check in `gesture_executor.py`
4. **All new actions** must be registered in `config/action_types.py` ACTION_REGISTRY
5. **All service functions** must be `async def`
6. **All API keys** must go through `config/settings.py` (Pydantic Settings), not raw env reads
7. **9 agents stay single-responsibility** — no merging or scope creep

---

## Gemini Live Hackathon — Implementation Status

Deadline: **March 16, 2026 @ 5:00 PM PT**

### Phase 1 — Eligibility

| # | Task | Status |
|---|------|--------|
| 1 | ADK root agent (`adk_agent.py`) | ✅ Done |
| 2 | Gemini as primary VLM (`DEFAULT_VLM_PROVIDER=gemini`) | ⚠️ Partial — `services/vlm.py` supports Gemini first-class, but `settings.py` still defaults to `"groq"` and `.env.example` still sets `DEFAULT_VLM_PROVIDER=groq`. Change both to `"gemini"` to satisfy the checklist. |
| 3 | `Dockerfile` for Cloud Run | ✅ Done |
| 4 | New env vars in `settings.py` + `.env.example` | ✅ Done |

### Phase 2 — Scoring

| # | Task | Status |
|---|------|--------|
| 5 | `adk_streaming_server.py` (Gemini Live bidi) | ✅ Done |
| 6 | `gcs_log_uploader.py` (Cloud Storage) | ✅ Done |
| 7 | Android app WebSocket URL → `BuildConfig` | ❌ Not done — `MainActivity.kt` still hardcodes `192.168.1.41:8000`; `build.gradle.kts` has no `buildConfigField` |
| 8 | Vertex AI as second GCP service (optional) | ❌ Not done |

### Phase 3 — Aspirational

| # | Task | Status |
|---|------|--------|
| 9 | `/demo` judging dashboard (`api/demo.py`) | ✅ Done |
| 10 | README `## Google Cloud Architecture` section | ❌ Not done |

### Remaining checklist items before submission
1. Set `default_vlm_provider = "gemini"` default in `config/settings.py` and `DEFAULT_VLM_PROVIDER=gemini` in `.env.example`
2. Add `## Google Cloud Architecture` section to `README.md` (architecture diagram, `adk_agent.py` snippet, `gcs_log_uploader.py` snippet, Cloud Run deploy command)
3. Deploy to Cloud Run and verify `/health` returns 200
4. (Optional) Android `BuildConfig` for release WebSocket URL (Task 7)
5. Make GitHub repo public before submitting to Devpost
