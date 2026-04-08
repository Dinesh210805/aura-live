---
last_verified: 2026-04-08
source_files: [adk_agent.py, adk_streaming_server.py, gcs_log_uploader.py]
status: current
---

# Google Cloud / ADK Layer

Hackathon additions connecting AURA to Google Cloud infrastructure.

---

## ADK Agent (`adk_agent.py`, 184 lines)

### Structure

```python
# Module-level state
_compiled_graph: Optional[Any] = None

def set_compiled_graph(app) -> None:
    """Called from main.py lifespan before any tool invocation."""
    global _compiled_graph
    _compiled_graph = app

def _get_graph():
    """Guards against premature tool invocation."""
    if _compiled_graph is None:
        raise RuntimeError("Graph not initialized. Call set_compiled_graph() first.")
    return _compiled_graph
```

### The FunctionTool

```python
async def execute_aura_task(command: str, session_id: str = "adk-session") -> dict:
    """Execute any Android UI automation command via voice or text."""
    graph = _get_graph()
    result = await execute_aura_task_from_text(command, graph, session_id)
    return {"success": result.success, "response": result.response, "steps": result.steps_taken}
```

Wrapped as `aura_tool = FunctionTool(execute_aura_task)`.

### The Root Agent

```python
root_agent = Agent(
    name="AURA",
    model="gemini-2.5-flash",
    description="Autonomous Android UI automation agent controlled by voice or text",
    instruction="...",  # Full system instructions
    tools=[aura_tool]
)
```

### Import Guard
Full ADK import is wrapped in `try/except ImportError`. If the `google-adk` package is not installed, `aura_tool = None` and `root_agent = None` — server still starts without ADK functionality.

### Lazy Graph Init (G8 Fix)
Previously, `execute_aura_task` could be called before `set_compiled_graph()` ran (during server startup race), causing a cryptic `AttributeError`. The `_get_graph()` guard now raises a clear `RuntimeError` with an actionable message. `set_compiled_graph()` is called in `main.py` within the `lifespan` context manager, guaranteed to run before any requests are served.

---

## Gemini Live Bidi (`adk_streaming_server.py`)

### Endpoint
`ws://localhost:8000/ws/live` — gated behind `GEMINI_LIVE_ENABLED=true`

### Features
- **Full VAD config** via `RealtimeInputConfig` — server-side voice activity detection
- **Transcript accumulation** — partial transcripts merged until end-of-turn detected
- **Barge-in support** — user can interrupt AURA's response
- **Explicit end-turn bridging** — `/ws/live` now maps client `end_turn` to ADK queue end signals when available (`send_audio_stream_end` or `send_activity_end`) to avoid waiting on delayed VAD closure
- **Latency telemetry** — per-turn metrics logged (`audio_first`, `input_transcription`, `first_model_audio`, `turn_complete`) for pinpointing wait-time sources
- **Reduced upstream overhead** — Android live client no longer sends `ui_tree` frames in Gemini Live mode because backend intentionally ignores them
- Forwards transcribed commands to `execute_aura_task_from_text()` same as audio WebSocket

### Activation
```bash
# In .env:
GEMINI_LIVE_ENABLED=true
```

---

## GCS Log Uploader (`gcs_log_uploader.py`, 119 lines)

### Purpose
After each task, uploads the HTML execution log (with screenshot timeline, step-by-step decisions, token usage) to Google Cloud Storage. Returns a public URL stored in `TaskState.log_url`.

### Interface

```python
def upload_log_to_gcs(log_path: str, session_id: str) -> Optional[str]
async def upload_log_to_gcs_async(log_path: str, session_id: str) -> Optional[str]
```

`upload_log_to_gcs_async` wraps the sync version in `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop.

### Blob Path
```
logs/{safe_session_id}.html
```
Made public via `blob.make_public()`. Returns the public URL.

### Non-Fatal Design
All failures return `None` and log a warning. GCS unavailability never blocks task execution:
- `gcs_logs_enabled = False` → skip silently
- `_GCS_AVAILABLE = False` (google-cloud-storage not installed) → skip
- Log file doesn't exist → skip
- `google_cloud_project` not set → skip
- Any GCS API error → log warning, return `None`

### Auth Priority
Prefers `GOOGLE_API_KEY` over `GEMINI_API_KEY` for GCS authentication (GCP service account credentials take precedence over Gemini API key).

---

## Demo Dashboard (`api/demo.py`)

### Endpoint: `GET /demo`
Judging dashboard with:
- Live device screenshot (2-second auto-refresh)
- Server health status
- Recent command history
- GCS log links for completed tasks
- Architecture diagram (inline SVG or image)

---

## Hackathon Phase Status

| Item | Status |
|------|--------|
| ADK `root_agent` | ✅ Done |
| Gemini Live bidi `/ws/live` | ✅ Done |
| GCS log uploader | ✅ Done |
| Demo dashboard | ✅ Done |
| `default_vlm_provider` → `"gemini"` | ⚠️ Must change in settings.py + .env.example |
| Android `BuildConfig` for WebSocket URL | ❌ Not done |
| `README.md` GCP architecture section | ❌ Not done |
| Vertex AI as second GCP service | ❌ Not done (optional) |
