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

These endpoints must not change signature or path — the Android companion app (`UI/`) depends on them.

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

## Gemini Live Hackathon — Mandatory Tasks

Three requirements for eligibility (none yet complete):
1. **Gemini as primary VLM** — swap `DEFAULT_VLM_PROVIDER` to `"gemini"` in `services/vlm.py` and `config/settings.py`
2. **Google ADK agent wrapper** — create `adk_agent.py` wrapping `run_aura_task()` as an ADK FunctionTool with a `gemini-2.5-flash` root agent
3. **Cloud Run deployment** — create `Dockerfile` (expose `$PORT`, pre-warm YOLOv8 weights)

Phase 2 additions (scoring, not eligibility): `adk_streaming_server.py` (Gemini Live bidirectional audio+vision), `gcs_log_uploader.py` (Cloud Storage).
