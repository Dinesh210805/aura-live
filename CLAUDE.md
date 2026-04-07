

## Wiki Brain

All persistent, living knowledge about Aura lives in the wiki.
Wiki location: `aura brain vault/Aura brain/wiki/`

### ALWAYS start every session by:
1. Reading `aura brain vault/Aura brain/wiki/index.md`
2. Reading pages relevant to the current task

### Wiki structure
- `wiki/overview.md`              → big picture and data flow
- `wiki/agents/`                  → each of the 9 agents documented
- `wiki/aura_graph/`              → LangGraph orchestration deep dive
- `wiki/perception/`              → perception pipeline details
- `wiki/api/`                     → routes, handlers, WebSocket endpoints
- `wiki/services/`                → LLM, VLM, TTS, STT, safety services
- `wiki/backlog.md`               → P1-P3 items from self-reflection
- `wiki/decisions.md`             → why things were built the way they were
- `wiki/index.md`                 → table of contents
- `wiki/log.md`                   → history of all changes

### After EVERY task — without being asked:
Run the wiki-update skill. Update relevant pages. Append to log.md.
# CLAUDE.md
---

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

---

## Known Gaps & Fix Status

Identified 2026-03-25. Priority tiers: **P0** = critical correctness, **P1** = reliability, **P2** = observability, **P3** = nice-to-have.

### P0 — Critical (fix immediately)

| # | Gap | Location | Status |
|---|-----|----------|--------|
| G1 | **HITL never called** — coordinator falls through `ask_user`/`stuck` to actor (gesture executor), which tries to execute them as real gestures → crash or no-op | `agents/coordinator.py:559` | ✅ Fixed |
| G2 | **History grows unboundedly** — `step_memory` list in coordinator has no cap; very long tasks overflow LLM context window | `agents/coordinator.py` | ✅ Fixed |
| G3 | **No structured error taxonomy** — all failures map to string status codes; no per-error-type recovery strategies | `utils/error_types.py` (missing) | ✅ Fixed |
| G4 | **No per-task token budget cap** — `TokenTracker` singleton has no budget enforcement; runaway tasks consume unlimited tokens | `utils/token_tracker.py` | ✅ Fixed |

### P1 — Reliability

| # | Gap | Location | Status |
|---|-----|----------|--------|
| G5 | **Retry ladder not per-subgoal** — `replan_count` was a task-level global; each new subgoal now resets it to 0 | `agents/coordinator.py` | ✅ Fixed |
| G6 | **VLM timeout not surfaced** — `_try_cv_vlm` now runs `select_with_fallback` in a `ThreadPoolExecutor` with `vlm_timeout_seconds` (default 30 s) | `perception/perception_pipeline.py` | ✅ Fixed |
| G7 | **No barge-in on HITL wait** — `HITLService.register_voice_answer()` resolves pending question; websocket router checks HITL before task dispatch | `services/hitl_service.py`, `api_handlers/websocket_router.py` | ✅ Fixed |
| G8 | **`execute_aura_task_from_text` fires without graph init guard** — ADK `FunctionTool` can be called before `set_compiled_graph()` runs; raises cryptic `AttributeError` | `adk_agent.py` | ✅ Fixed (prior session) |

### P2 — Observability

| # | Gap | Location | Status |
|---|-----|----------|--------|
| G9 | **Token tracker resets on restart** — in-memory singleton; no persistence for cross-session budget analysis | `utils/token_tracker.py` | ✅ Fixed |
| G10 | **No per-phase timing metrics** — phases have no start/end timestamps; can't diagnose slow phases post-mortem | `aura_graph/agent_state.py` | ✅ Fixed |
| G11 | **Commander never logs token usage** — only coordinator/reactive calls go through token tracker | `agents/commander.py` | ✅ Fixed |

### P3 — Nice-to-Have

| # | Gap | Location | Status |
|---|-----|----------|--------|
| G12 | **`executed_steps` in TaskState grows unboundedly** — capped at 50 via custom `cap_executed_steps` LangGraph reducer | `aura_graph/state.py` | ✅ Fixed |
| G13 | **No A/B prompt version tracking** — `PROMPT_VERSIONS` dict logged via `PROMPT_VERSIONS` command-logger event in `run_aura_task()` | `aura_graph/graph.py` | ✅ Fixed |
| G14 | **VLM CoT preamble not in VISION_REASONING_PROMPT** — added ①②③④ think-before-output block matching `ELEMENT_SELECTION_PROMPT` style | `prompts/reasoning.py` | ✅ Fixed |
| G15 | **`PromptMode.MINIMAL` unused** — verifier's `semantic_verify` now uses `build_aura_agent_prompt(mode=PromptMode.MINIMAL)` as system prompt; `LLMService.run()` now accepts `system_prompt` param | `agents/verifier_agent.py`, `services/llm.py` | ✅ Fixed |

---

## Self-Reflection Improvement Backlog

Identified 2026-03-29. P0 items already fixed. P1–P3 pending.

### P0 — Done (2026-03-29)

| # | Fix | Location |
|---|-----|----------|
| R0a | **Lesson bucketing too coarse** — `_goal_key()` now appends app name so "play_media__spotify" and "play_media__youtube" are separate lesson pools | `services/reflexion_service.py` |
| R0b | **Lessons only written on full abort** — now also writes on task success when `replan_count > 0`, capturing recovery paths for future attempts | `agents/coordinator.py` |

### P1 — Structured RSG diagnosis field

**What:** Add a `__diagnosis__` JSON field to the RSG output schema alongside the existing `__prev_step_ok__` flag.

**Why:** The model currently outputs a boolean (`__prev_step_ok__`) and a freeform string (`__prev_step_issue__`). A structured diagnosis is more reliably parsed and more useful as context for the next step.

**Schema to add to `prompts/reactive_step.py`:**
```json
"__diagnosis__": {
  "what_happened": "Tapped Search bar but target was not in search results",
  "dead_end": "Search bar is not the right path for this target",
  "try_instead": "Navigate to Library tab"
}
```

**Wiring in `agents/coordinator.py`:** After reading `__prev_step_issue__`, also extract `__diagnosis__` from `next_step.parameters` and:
1. Log it via `_cmd_logger.log_agent_decision("STEP_DIAGNOSIS", ...)`
2. Pass it as a `prev_diagnosis` kwarg into the next RSG call so the model builds on its own reasoning

### P2 — Persistent app knowledge store

**What:** New `services/app_knowledge.py` — a `AppKnowledgeStore` class that stores *structural* facts about app layouts learned during successful task executions.

**Why:** The reflexion service captures task-level failure lessons (ephemeral, task-specific). App layout facts are different — they're stable across sessions. "Spotify Liked Songs is under Library tab" is always true; discovering it once should benefit all future tasks, not just future failures.

**Interface:**
```python
class AppKnowledgeStore:
    async def record_successful_path(self, app: str, goal_type: str, path: list[str]) -> None:
        """Called on task success. e.g. record("spotify", "liked_songs", ["Library tab", "Liked Songs"])"""

    async def get_app_hints(self, app: str, goal_type: str) -> str:
        """Returns formatted hint string for RSG prompt injection."""
```

**Storage:** JSON files at `data/app_knowledge/{app}.json`, keyed by goal_type. Written only on **successful** task completion (success reinforcement — never on failure, so only verified paths accumulate).

**Wiring:** Inject `app_hints` into RSG prompt as the highest-priority context block, before reflexion lessons. Detect app from `goal.original_utterance` using the same `_APP_NAMES` list in `ReflexionService`.

### P3 — Post-phase reflection summary

**What:** After each skeleton phase completes in the coordinator, run a lightweight LLM call (~100 tokens) that summarizes what the agent just learned about the screen/app during that phase.

**Why:** Cross-phase context is currently carried only by `__agent_memory__` (VLM-chosen freeform). The phase boundary is a natural checkpoint where the model can consolidate: "Phase 1 established that the Search bar leads to a dead end; Phase 2 should go via Library instead."

**Where:** In `agents/coordinator.py`, at the `PHASE_COMPLETE` log event (around line 1530), add a non-blocking background call to generate and store a `phase_summary` string. Pass this forward as `agent_memory` seed for the next phase's RSG calls.
