---
last_verified: 2026-04-08
source_files: [aura_graph/graph.py]
status: current
---

# LangGraph — Graph Assembly & Entry Points

**File**: `aura_graph/graph.py`

---

## Overview

`graph.py` is the system's assembly point. It:
1. Initializes all services (LLM, VLM, TTS, STT)
2. Instantiates all 9 agents
3. Assembles the LangGraph `StateGraph`
4. Provides the public entry points used by the WebSocket router

---

## Graph Assembly: `create_aura_graph()`

```python
def create_aura_graph(
    llm_service, vlm_service, tts_service, stt_service,
    commander, responder, validator, coordinator,
    planner, perceiver, actor, verifier
) -> StateGraph
```

Builds the graph structure: adds nodes, sets entry point, adds conditional edges. Returns an uncompiled `StateGraph`.

**Nodes added**:
- `stt` — speech-to-text (wraps `stt_service.transcribe()`)
- `parse_intent` — commander agent intent parsing
- `coordinator` — main execution loop
- `perception` — perceiver agent screen capture
- `speak` — responder agent + TTS delivery
- `error_handler` — error recovery and retry logic
- `web_search` — Tavily web search for conversational queries

**Entry point**: `__start__` → `route_from_start()` (conditional edge)

---

## Graph Compilation: `compile_aura_graph()`

```python
async def compile_aura_graph() -> StateGraph
```

The main startup function. Called once from `main.py` lifespan:

1. Reads settings (`config/settings.py`)
2. Initializes services: `LLMService`, `VLMService`, `TTSService`, `STTService`
3. Creates all 9 agents: `CommanderAgent`, `ResponderAgent`, `ValidatorAgent`, `CoordinatorAgent`, `PlannerAgent`, `PerceiverAgent`, `ActorAgent`, `VerifierAgent`
4. **Wires circular dependency**: `PerceiverAgent.perception_controller = PerceptionController(screen_vlm=perceiver)`
5. Calls `create_aura_graph()` to assemble nodes and edges
6. Compiles with `InMemoryStore` for cross-task memory
7. Registers 7 adapters into `AgentRegistry` (non-fatal if it fails)
8. Calls `set_compiled_graph(app)` for ADK integration

The compiled app is stored globally as `graph_app` in `main.py`.

---

## Entry Points

### `run_aura_task(app, state_input, thread_id)`

The canonical entry point used by the WebSocket router:
- Wraps `app.ainvoke()` with a hard timeout from `settings.graph_timeout_seconds`
- Calls `_finalize_and_upload()` after completion regardless of success/failure
- Returns the final `TaskState` dict

### `execute_aura_task_from_text(app, text_input, thread_id)`

Convenience wrapper for text-only input (used by ADK FunctionTool):
- Builds the initial `TaskState` with `input_type="text"`, `text_input=text_input`
- Calls `run_aura_task()`
- Returns a simplified result dict: `{success, response, steps_taken, execution_log_url}`

### `execute_aura_task_from_streaming(app, text_input, thread_id, ...)`

Used by the WebSocket router fallback path (when `AuraQueryEngine` is disabled):
- Similar to `execute_aura_task_from_text` but accepts additional streaming metadata

---

## `_finalize_and_upload()` Helper

Shared post-task cleanup:
1. Retrieves `CommandLogger` and finalizes the HTML execution log
2. If `GCS_LOGS_ENABLED=true`, uploads the log to Cloud Storage via `gcs_log_uploader`
3. Stores the public URL in `TaskState.log_url`
4. Clears the `CommandLogger` for the next task

---

## PROMPT_VERSIONS Tracking (G13 Fix)

At graph startup, `run_aura_task()` logs a `PROMPT_VERSIONS` event containing a dict of all prompt version hashes. This enables tracking which prompt versions were active for each task run — critical for A/B testing prompt improvements.

---

## LangSmith Integration

When `LANGCHAIN_TRACING_V2=true`, all node invocations are automatically traced to LangSmith. Configure via:
- `LANGCHAIN_API_KEY` — auth key
- `LANGCHAIN_PROJECT` — project name (default: `"aura-agent-visualization"`)
- `LANGCHAIN_PROJECT_ID` — UUID for public trace links
