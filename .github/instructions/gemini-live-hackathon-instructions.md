# AURA — GitHub Copilot Agent Instructions

# Gemini Live Agent Challenge — UI Navigator Track

## MISSION BRIEF

You are working on **AURA (Autonomous User-Responsive Agent)** — a production-grade
Android UI automation system. The immediate goal is to make AURA eligible and
competitive for the **Google Gemini Live Agent Challenge** (UI Navigator track).

Submission deadline:  **March 16, 2026 at 5:00 PM PT** .

The three mandatory requirements to become eligible are:

1. Use a Gemini model (currently a fallback — must become primary VLM)
2. Build agents using Google GenAI SDK **or** ADK (currently neither — must add)
3. Host on at least one Google Cloud service (currently local — must deploy)

All changes must leave existing behavior intact. You are wrapping and extending,
not rewriting.

---

## CODEBASE MAP

Understand this structure before touching any file:

```
aura-agent/
├── main.py                          ← FastAPI entry point, lifespan, middleware
├── constants.py                     ← API version, size limits
├── requirements.txt                 ← Python deps — ADD new deps here
│
├── agents/                          ← The 9 specialized agents (DO NOT REWRITE)
│   ├── commander.py                 ← Intent parsing (rule-based + LLM fallback)
│   ├── coordinator.py               ← perceive→decide→act→verify loop
│   ├── perceiver_agent.py           ← Wraps PerceptionController → ScreenState
│   ├── planner_agent.py             ← Goal → skeleton phases
│   ├── actor_agent.py               ← Gesture execution, zero LLM calls
│   ├── verifier_agent.py            ← Post-action verification
│   ├── responder.py                 ← Natural language responses
│   ├── validator.py                 ← Rule-based validation, zero LLM calls
│   └── visual_locator.py            ← ScreenVLM: SoM + YOLOv8 + VLM selection
│
├── aura_graph/                      ← LangGraph state machine (DO NOT REWRITE)
│   ├── graph.py                     ← Graph assembly — exposes run_aura_task()
│   ├── state.py                     ← TaskState TypedDict, 40+ fields
│   ├── edges.py                     ← Conditional routing functions
│   ├── core_nodes.py                ← Node implementations
│   ├── agent_state.py               ← Goal/Subgoal/RetryStrategy models
│   └── nodes/                       ← Specialized nodes
│       ├── perception_node.py
│       ├── coordinator_node.py
│       ├── decompose_goal_node.py
│       ├── validate_outcome_node.py
│       ├── retry_router_node.py
│       └── next_subgoal_node.py
│
├── services/                        ← Core service layer
│   ├── llm.py                       ← Unified LLM interface (Groq/Gemini/NVIDIA)
│   ├── vlm.py                       ← VLM wrapper — PRIMARY CHANGE TARGET
│   ├── stt.py                       ← STT: Groq Whisper — REPLACE with Gemini Live
│   ├── tts.py                       ← TTS: Edge-TTS — REPLACE with Gemini Live
│   ├── perception_controller.py     ← 3-layer perception orchestration
│   ├── reactive_step_generator.py   ← Per-screen step generation
│   ├── goal_decomposer.py           ← Skeleton plan generation
│   ├── gesture_executor.py          ← Gesture dispatch + OPA policy check
│   ├── real_accessibility.py        ← Android device communication
│   ├── policy_engine.py             ← OPA Rego evaluation
│   ├── prompt_guard.py              ← Llama Prompt Guard 2 safety
│   ├── screenshot_service.py        ← Device screenshot capture
│   ├── conversation_manager.py      ← Multi-turn dialogue context
│   ├── command_logger.py            ← HTML execution logs ← EXTEND to upload GCS
│   ├── hitl_service.py              ← Human-in-the-loop
│   ├── task_progress.py             ← Real-time progress broadcast
│   ├── visual_feedback.py           ← Edge glow + ripple animations
│   └── ui_signature.py              ← MD5 UI tree fingerprinting
│
├── perception/                      ← OmniParser pipeline
│   ├── perception_pipeline.py       ← 3-layer orchestration
│   ├── models.py                    ← PerceptionBundle, UITreePayload
│   ├── omniparser_detector.py       ← YOLOv8 detection
│   └── vlm_selector.py              ← VLM element selection
│
├── config/
│   ├── settings.py                  ← Pydantic Settings (all env vars) ← ADD new vars
│   ├── action_types.py              ← ACTION_REGISTRY
│   ├── model_router.py              ← Dynamic model resolution
│   └── success_criteria.py
│
├── api/                             ← REST route definitions
├── api_handlers/                    ← WebSocket handlers
│   └── websocket_router.py          ← Device WS handler ← ADD live session handler
├── policies/                        ← OPA Rego files (safety.rego, apps.rego)
├── prompts/                         ← LLM prompt templates
├── middleware/                      ← rate_limit, request_id, auth
├── models/                          ← Pydantic data models (gestures.py)
├── utils/                           ← logger, ui_element_finder, perf_tracker
└── UI/                              ← Kotlin Android companion app
    └── app/                         ← Android source — UPDATE WebSocket URL here
```

**New files you will create** (do not place them elsewhere):

```
aura-agent/
├── adk_agent.py                     ← ADK root agent + FunctionTool wrapper
├── adk_streaming_server.py          ← Gemini Live API bidi streaming handler
├── gcs_log_uploader.py              ← Cloud Storage log upload utility
├── Dockerfile                       ← Cloud Run deployment
├── .dockerignore
├── cloudbuild.yaml                  ← Optional: Cloud Build CI
└── .env.example                     ← Update with new required vars
```

---

## TASK LIST (ORDERED BY PRIORITY)

Work through tasks in this exact order. Phase 1 makes the project eligible.
Phase 2 improves the score. Phase 3 is aspirational.

---

### PHASE 1 — ELIGIBILITY (Complete These First)

---

#### TASK 1 — Create `adk_agent.py` (ADK Root Agent)

**File:** `adk_agent.py` (project root)

**Purpose:** Wrap the existing LangGraph execution graph as an ADK FunctionTool,
satisfying the "must use Google GenAI SDK or ADK" requirement without rewriting
any existing agent logic.

**What to import from existing code:**

```python
from aura_graph.graph import run_aura_task   # the existing LangGraph entry point
```

**What to build:**
    
```python
# adk_agent.py
import asyncio
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from aura_graph.graph import run_aura_task

async def execute_aura_task(command: str, session_id: str) -> dict:
    """
    Execute a UI navigation task on the connected Android device.
    Invokes the full AURA LangGraph pipeline: perceive → plan → act → verify.

    Args:
        command: Natural language command, e.g. 'Open Spotify and play liked songs'
        session_id: Active device session identifier from the WebSocket connection

    Returns:
        dict with keys: success (bool), response (str), steps_taken (int),
        execution_log_url (str or None)
    """
    result = await run_aura_task(command=command, session_id=session_id)
    return {
        "success": result.get("status") == "completed",
        "response": result.get("feedback_message", ""),
        "steps_taken": len(result.get("executed_steps", [])),
        "execution_log_url": result.get("log_url"),
    }

aura_tool = FunctionTool(func=execute_aura_task)

root_agent = Agent(
    name="AURA",
    model="gemini-2.5-flash",
    description=(
        "AURA — Autonomous User-Responsive Agent. "
        "Controls Android devices via natural language. "
        "Sees the screen, plans actions, and executes precise gestures."
    ),
    instruction="""
    You are AURA, an autonomous Android UI navigation agent.

    When the user gives a command to control their device, call execute_aura_task
    immediately. Do not ask for confirmation unless the action involves sensitive
    data (payment, deletion, messaging).

    After the task completes, summarize what happened in one or two sentences.
    If the task failed, explain what was attempted and suggest an alternative.

    Personality: helpful, concise, slightly playful. Never robotic.
    Always identify yourself as AURA, never claim to be human.
    """,
    tools=[aura_tool],
)
```

**Constraints:**

* Do NOT modify `aura_graph/graph.py` — only import from it.
* The `run_aura_task` signature may differ from what is shown above — inspect
  the actual function signature in `aura_graph/graph.py` before calling it.
* Add `google-adk` and `google-genai` to `requirements.txt`.

---

#### TASK 2 — Swap Gemini to Primary VLM in `services/vlm.py`

**File:** `services/vlm.py`

**Purpose:** Make Gemini 2.5 Flash the PRIMARY vision model for all screenshot
analysis. Currently it is a fallback. This satisfies "must use Gemini multimodal
to interpret screenshots and output executable actions."

**Rules — read before editing:**

* The VLM is called from `perception/vlm_selector.py` and `agents/visual_locator.py`
* The critical safety guarantee must be preserved:  **VLM never returns pixel
  coordinates** , only selects among numbered CV-detected elements. Do not change
  the Set-of-Marks (SoM) flow.
* Keep the existing Groq fallback — demote it, don't remove it.

**What to change:**

Find the provider selection logic (likely a try/except or if/else on
`DEFAULT_VLM_PROVIDER`). Restructure it so Gemini is always attempted first:

```python
# services/vlm.py — restructured provider order

from google import genai
import base64

_genai_client = genai.Client()  # reads GOOGLE_API_KEY from env

async def analyze_screenshot_with_vlm(
    image_b64: str,
    prompt: str,
    fallback_to_groq: bool = True,
) -> str:
    """
    Analyze a device screenshot using Gemini 2.5 Flash (primary).
    Falls back to Groq vision model if Gemini fails or rate-limits.

    The prompt must instruct the model to return a NUMBER only (SoM index),
    never raw pixel coordinates.
    """
    try:
        response = _genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_b64,
                    }
                },
                prompt,
            ],
        )
        return response.text.strip()
    except Exception as gemini_error:
        if not fallback_to_groq:
            raise
        # Existing Groq vision call goes here — do not delete it
        return await _analyze_with_groq_fallback(image_b64, prompt)
```

**Also update** `config/settings.py`:

```python
DEFAULT_VLM_PROVIDER: str = "gemini"    # was "groq"
DEFAULT_VLM_MODEL: str = "gemini-2.5-flash"
```

**Also update** `config/model_router.py` if it has a provider priority list —
ensure `gemini` appears before `groq` for vision tasks.

---

#### TASK 3 — Create `Dockerfile` for Cloud Run

**File:** `Dockerfile` (project root)

**Purpose:** Package the FastAPI backend for deployment to Google Cloud Run.
Cloud Run supports WebSockets natively, which AURA requires for the device
connection on `/ws/device` and voice on `/ws/audio`.

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# OmniParser YOLOv8 weights download on first run — pre-warm here
RUN python -c "from perception.omniparser_detector import OmniParserDetector; OmniParserDetector()" || true

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--ws", "websockets"]
```

**File:** `.dockerignore` (project root)

```
__pycache__/
*.pyc
*.pyo
.env
.env.*
!.env.example
venv/
.venv/
logs/
data/failure_screenshots/
UI/
.git/
*.md
```

**Cloud Run deployment command** (document this in README, do not execute):

```bash
gcloud run deploy aura-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest,GROQ_API_KEY=groq-api-key:latest"
```

**Port note:** `main.py` must respect the `PORT` environment variable.
Check `main.py` and add this if it hardcodes 8000:

```python
import os
port = int(os.environ.get("PORT", 8000))
```

---

#### TASK 4 — Add new env vars to `config/settings.py` and `.env.example`

**File:** `config/settings.py`

Add these fields to the existing Pydantic Settings class (do not replace
the class, only add fields):

```python
# Google Cloud
GOOGLE_API_KEY: str = ""                        # For Gemini GenAI SDK
GOOGLE_CLOUD_PROJECT: str = ""                  # For Vertex AI / Cloud Run
GOOGLE_CLOUD_REGION: str = "us-central1"

# Cloud Storage (execution logs)
GCS_LOGS_BUCKET: str = "aura-execution-logs"
GCS_LOGS_ENABLED: bool = False                  # Enable after bucket created

# ADK
ADK_APP_NAME: str = "AURA"

# Gemini Live (streaming)
GEMINI_LIVE_MODEL: str = "gemini-live-2.5-flash"
GEMINI_LIVE_ENABLED: bool = False               # Disabled until Phase 2
```

**File:** `.env.example` — add the corresponding documented entries:

```env
# Google Cloud (required for competition submission)
GOOGLE_API_KEY=your_google_api_key_from_aistudio
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_REGION=us-central1

# Cloud Storage execution logs (optional, set GCS_LOGS_ENABLED=true to activate)
GCS_LOGS_BUCKET=aura-execution-logs
GCS_LOGS_ENABLED=false

# Gemini Live bidi streaming (optional, Phase 2)
GEMINI_LIVE_ENABLED=false
```

---

### PHASE 2 — SCORING ADVANTAGE

---

#### TASK 5 — Create `adk_streaming_server.py` (Gemini Live bidi audio + vision)

**File:** `adk_streaming_server.py` (project root)

**Purpose:** Replace the current two-hop voice pipeline (Groq Whisper STT →
processing → Edge-TTS TTS) with a single persistent Gemini Live API session.
This gives AURA true bidirectional voice: the user speaks, Gemini hears AND
sees the screen simultaneously, and responds in audio.

This file adds a new WebSocket endpoint `/ws/live` alongside the existing ones.
It does NOT replace `/ws/audio` yet — both coexist until this is stable.

**The ADK streaming pattern:**

```python
# adk_streaming_server.py
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai.types import Blob, Part, Modality
from adk_agent import root_agent
from utils.logger import get_logger

logger = get_logger(__name__)

_session_service = InMemorySessionService()
_runner = Runner(
    agent=root_agent,
    session_service=_session_service,
    app_name="AURA",
)

async def handle_live_websocket(websocket: WebSocket, session_id: str):
    """
    Bidirectional Gemini Live session for a connected Android device.

    Incoming messages from the Android app WebSocket:
      {"type": "audio_chunk", "data": "<base64 PCM>"}
      {"type": "screenshot", "data": "<base64 JPEG>"}
      {"type": "ui_tree", "tree": {}, "packageName": "com.example"}

    Outgoing messages to the Android app:
      {"type": "audio_response", "data": "<base64 PCM>"}
      {"type": "transcript", "text": "Opening Spotify..."}
      {"type": "task_progress", "tasks": [...]}
    """
    await websocket.accept()

    session = await _session_service.create_session(
        app_name="AURA",
        user_id=session_id,
    )

    run_config = RunConfig(
        response_modalities=[Modality.AUDIO],
        streaming_mode=StreamingMode.BIDI,
    )

    live_queue = LiveRequestQueue()

    async def receive_from_device():
        """Read messages from the Android companion app and push to Gemini."""
        try:
            while True:
                raw = await websocket.receive_json()
                msg_type = raw.get("type")

                if msg_type == "audio_chunk":
                    # PCM audio from device microphone
                    audio_bytes = bytes.fromhex(raw["data"]) if isinstance(raw["data"], str) else raw["data"]
                    await live_queue.send_realtime(
                        Part(inline_data=Blob(mime_type="audio/pcm", data=audio_bytes))
                    )

                elif msg_type == "screenshot":
                    # Current device screen — sends vision context to Gemini
                    img_data = raw["data"]  # base64 JPEG
                    if isinstance(img_data, str):
                        import base64
                        img_bytes = base64.b64decode(img_data)
                    else:
                        img_bytes = img_data
                    await live_queue.send_realtime(
                        Part(inline_data=Blob(mime_type="image/jpeg", data=img_bytes))
                    )

        except WebSocketDisconnect:
            live_queue.close()

    async def send_to_device():
        """Relay Gemini Live events back to the Android companion app."""
        async for event in _runner.run_live(
            user_id=session_id,
            session_id=session.id,
            run_config=run_config,
            live_request_queue=live_queue,
        ):
            if event.get_function_calls():
                # Tool calls in flight — send progress update
                await websocket.send_json({
                    "type": "task_progress",
                    "status": "executing",
                })

            audio = getattr(event, "audio", None)
            if audio:
                import base64
                await websocket.send_json({
                    "type": "audio_response",
                    "data": base64.b64encode(audio).decode(),
                })

            text = getattr(event, "text", None)
            if text:
                await websocket.send_json({
                    "type": "transcript",
                    "text": text,
                })

    await asyncio.gather(receive_from_device(), send_to_device())
```

**Wire it into `main.py`:**

```python
from adk_streaming_server import handle_live_websocket

@app.websocket("/ws/live")
async def live_websocket_endpoint(websocket: WebSocket, session_id: str = "default"):
    await handle_live_websocket(websocket, session_id)
```

**Guard with the feature flag** — only register this route if
`settings.GEMINI_LIVE_ENABLED` is True, so it doesn't break the existing
pipeline if ADK is not yet fully configured.

---

#### TASK 6 — Create `gcs_log_uploader.py` (Cloud Storage log upload)

**File:** `gcs_log_uploader.py` (project root)

**Purpose:** After every task completes, upload the HTML execution log (currently
saved to `logs/`) to a Google Cloud Storage bucket and return a public URL.
This lets judges inspect full execution traces without running the code.

```python
# gcs_log_uploader.py
import os
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

def upload_log_to_gcs(log_html: str, session_id: str) -> str | None:
    """
    Upload an HTML execution log to Cloud Storage.

    Args:
        log_html: The full HTML content of the execution log
        session_id: Used as the GCS object name

    Returns:
        Public URL of the uploaded log, or None if upload is disabled/failed
    """
    from config.settings import get_settings
    settings = get_settings()

    if not settings.GCS_LOGS_ENABLED:
        return None

    try:
        from google.cloud import storage
        client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)
        bucket = client.bucket(settings.GCS_LOGS_BUCKET)
        blob_name = f"logs/{session_id}.html"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(log_html, content_type="text/html")
        blob.make_public()
        url = blob.public_url
        logger.info(f"Execution log uploaded: {url}")
        return url
    except Exception as e:
        logger.warning(f"GCS log upload failed (non-fatal): {e}")
        return None
```

**Wire it into `services/command_logger.py`:**

Find the method that finalizes and saves the HTML execution log. After the
local file write, add:

```python
from gcs_log_uploader import upload_log_to_gcs
log_url = upload_log_to_gcs(html_content, session_id)
# Store log_url in TaskState so it can be returned via the API
```

**Add to `requirements.txt`:**

```
google-cloud-storage
```

---

#### TASK 7 — Update Android companion app WebSocket URL

**File:** `UI/app/src/main/java/` — find the file that defines the backend URL.
Look for a constant containing `ws://` or `192.168` or `localhost:8000`.

**What to change:**

```kotlin
// Before (local dev)
private const val BACKEND_WS_URL = "ws://192.168.x.x:8000/ws/device"

// After (Cloud Run)
private const val BACKEND_WS_URL = BuildConfig.BACKEND_WS_URL
```

Add to `UI/app/build.gradle.kts`:

```kotlin
android {
    buildTypes {
        debug {
            buildConfigField("String", "BACKEND_WS_URL",
                "\"ws://10.0.2.2:8000/ws/device\"")  // local emulator
        }
        release {
            buildConfigField("String", "BACKEND_WS_URL",
                "\"wss://aura-backend-XXXX-uc.a.run.app/ws/device\"")  // Cloud Run
        }
    }
}
```

Replace the placeholder `aura-backend-XXXX` with the actual Cloud Run service
URL after deployment (from Task 3).

Also update the `/ws/live` URL for the new Gemini Live endpoint:

```kotlin
private const val BACKEND_LIVE_URL = BuildConfig.BACKEND_LIVE_URL
```

---

#### TASK 8 — Add Vertex AI as second Google Cloud service (optional upgrade)

**File:** `services/vlm.py` (extend Task 2)

**Purpose:** Route Gemini calls through Vertex AI instead of AI Studio. This
proves two distinct GCP services (Cloud Run + Vertex AI) in the architecture
diagram, which strengthens the judging submission.

```python
# In services/vlm.py — alternative client using Vertex AI

import vertexai
from vertexai.generative_models import GenerativeModel, Part as VertexPart, Image

def _get_vertex_model():
    from config.settings import get_settings
    s = get_settings()
    vertexai.init(project=s.GOOGLE_CLOUD_PROJECT, location=s.GOOGLE_CLOUD_REGION)
    return GenerativeModel("gemini-2.5-flash")

async def analyze_screenshot_vertex(image_b64: str, prompt: str) -> str:
    """Gemini 2.5 Flash via Vertex AI (second GCP service for judging proof)."""
    import base64
    model = _get_vertex_model()
    img_bytes = base64.b64decode(image_b64)
    image_part = VertexPart.from_data(img_bytes, mime_type="image/jpeg")
    response = model.generate_content([image_part, prompt])
    return response.text.strip()
```

**Add to `requirements.txt`:**

```
google-cloud-aiplatform
vertexai
```

**Add to `config/settings.py`:**

```python
USE_VERTEX_AI: bool = False   # Set True to route VLM through Vertex AI
```

---

### PHASE 3 — ASPIRATION (Do Last)

---

#### TASK 9 — Add a judging web dashboard (serve from FastAPI)

**File:** `api/demo.py` (new file)

**Purpose:** A minimal HTML page served at `/demo` that shows:

* Live device screenshot (auto-refreshes every 2 seconds)
* Current task status and last 5 commands
* Links to Cloud Storage execution logs
* Architecture diagram image

This gives judges a live view of AURA without needing an Android device.

```python
# api/demo.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/demo", response_class=HTMLResponse)
async def demo_dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>AURA Live Demo</title></head>
    <body>
        <h1>AURA — Autonomous UI Navigator</h1>
        <img id="screen" src="/api/v1/device/screenshot" width="360"
             style="border:1px solid #ccc; border-radius:8px"/>
        <div id="status">Waiting for commands...</div>
        <script>
            setInterval(() => {
                document.getElementById('screen').src =
                    '/api/v1/device/screenshot?t=' + Date.now();
            }, 2000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
```

Register in `main.py`:

```python
from api.demo import router as demo_router
app.include_router(demo_router)
```

---

#### TASK 10 — Add GCP proof documentation to README

**File:** `README.md` — add a new section titled `## Google Cloud Architecture`

Include:

* Architecture diagram showing: Android App → Cloud Run → ADK Agent →
  Gemini 2.5 Flash (Vertex AI) → 9 LangGraph agents → Cloud Storage logs
* Code snippet from `adk_agent.py` showing the ADK agent definition
* Code snippet from `gcs_log_uploader.py` showing Cloud Storage usage
* The Cloud Run deployment command from Task 3

This satisfies the judging FAQ requirement: "proof is a code file in your GitHub
repo that demonstrates use of Google Cloud services."

---

## INVARIANTS — NEVER VIOLATE THESE

These rules apply to every file you touch or create. Violating them will break
the existing working system.

### 1. The SoM coordinate safety guarantee is sacred

VLMs must NEVER return pixel coordinates. The flow is always:

```
YOLOv8 detects elements → assigns numbers → VLM picks a number → number maps to coords
```

If you are modifying anything in `perception/`, `agents/visual_locator.py`, or
`services/vlm.py`, check that no code path allows a VLM to produce `{"x": 540, "y": 1200}`.

### 2. The 9 agents are single-responsibility

* `actor_agent.py` has zero LLM calls. Keep it that way.
* `validator_agent.py` has zero LLM calls. Keep it that way.
* Do not add gesture execution logic to any agent other than `actor_agent.py`.
* Do not add LLM calls to `actor_agent.py` or `validator_agent.py`.

### 3. New actions must go through ACTION_REGISTRY

If adding any new action type, register it in `config/action_types.py`:

```python
"your_action": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True)
```

Never hardcode action types in agent logic.

### 4. The retry ladder is the first resort, not LLM replanning

The 5-stage retry ladder in `coordinator.py` must remain:

```python
RETRY_LADDER = [
    RetryStrategy.SAME_ACTION,
    RetryStrategy.ALTERNATE_SELECTOR,
    RetryStrategy.SCROLL_AND_RETRY,
    RetryStrategy.VISION_FALLBACK,
    RetryStrategy.ABORT,
]
```

Do not add replanning calls inside the retry steps.

### 5. OPA policy check happens before every gesture

`services/gesture_executor.py` calls the policy engine before sending any
gesture to the device. Never bypass this check, even for new gesture types.

### 6. All new API keys go through Pydantic Settings

Never hardcode API keys. Never read `os.environ` directly in service files.
Use `from config.settings import get_settings; s = get_settings()`.

### 7. New Google SDK calls must handle rate limits gracefully

Wrap every `google.genai` and `vertexai` call in try/except and fall back to
the existing Groq-based implementation. The Groq fallback must never be removed,
only demoted.

### 8. The existing WebSocket endpoints must keep working

`/ws/audio` and `/ws/device` must not be modified. New endpoints (`/ws/live`)
are additions, not replacements.

### 9. Async all the way down

All new service-layer functions must be `async def`. AURA runs on an async
event loop — synchronous blocking calls in service functions will freeze it.
For synchronous SDK calls (like some Vertex AI calls), use:

```python
import asyncio
result = await asyncio.get_event_loop().run_in_executor(None, sync_fn, args)
```

---

## TESTING EACH TASK

After completing each task, verify with these checks before moving on:

**Task 1 (ADK agent):**

```bash
python -c "from adk_agent import root_agent; print(root_agent.name)"
# Expected: AURA
```

**Task 2 (Gemini primary VLM):**

```bash
python -c "
from config.settings import get_settings
s = get_settings()
print(s.DEFAULT_VLM_PROVIDER)  # Expected: gemini
print(s.DEFAULT_VLM_MODEL)     # Expected: gemini-2.5-flash
"
```

**Task 3 (Dockerfile):**

```bash
docker build -t aura-backend .
docker run -p 8080:8080 --env-file .env aura-backend
curl http://localhost:8080/health
```

**Task 5 (ADK streaming):**

```bash
python main.py
# New endpoint must appear in startup logs: /ws/live
```

**Task 6 (GCS uploader):**

```bash
python -c "
from gcs_log_uploader import upload_log_to_gcs
# With GCS_LOGS_ENABLED=false it should return None without error
result = upload_log_to_gcs('<html>test</html>', 'test-session')
print(result)  # Expected: None
"
```

---

## COMPETITION SUBMISSION CHECKLIST

Before submitting to Devpost, verify every item:

* [ ] `adk_agent.py` exists and `root_agent` imports without error
* [ ] `google-adk` and `google-genai` are in `requirements.txt`
* [ ] `services/vlm.py` calls `gemini-2.5-flash` as the FIRST provider
* [ ] `config/settings.py` has `DEFAULT_VLM_PROVIDER = "gemini"`
* [ ] `Dockerfile` exists and builds successfully
* [ ] `GOOGLE_API_KEY` is in `.env.example` (not in `.env` — that's gitignored)
* [ ] FastAPI app reads `PORT` from environment (required for Cloud Run)
* [ ] Cloud Run service is deployed and `/health` returns 200
* [ ] Architecture diagram in README shows Gemini + Cloud Run + (Vertex AI or GCS)
* [ ] GitHub repo is public (judges need to read the code)
* [ ] Demo video shows: voice command → screen understanding → gesture → voice response

---

## KEY APIS AND DOCS

When generating code that calls Google APIs, use these exact patterns:

**GenAI SDK (AI Studio):**

```python
from google import genai
client = genai.Client()  # reads GOOGLE_API_KEY
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[image_part, text_prompt]
)
```

**ADK Agent:**

```python
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
```

**ADK Live streaming:**

```python
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai.types import Blob, Part, Modality
```

**Cloud Storage:**

```python
from google.cloud import storage
client = storage.Client(project="your-project")
bucket = client.bucket("bucket-name")
blob = bucket.blob("path/to/file.html")
blob.upload_from_string(content, content_type="text/html")
```

**Vertex AI:**

```python
import vertexai
from vertexai.generative_models import GenerativeModel
vertexai.init(project="your-project", location="us-central1")
model = GenerativeModel("gemini-2.5-flash")
```

---

## CONTEXT FOR THE COMPETITION

**Track:** UI Navigator — Visual UI Understanding & Interaction

**Mandatory tech:** Gemini multimodal for screenshots → executable actions, hosted on Google Cloud

**All projects must:** Use Gemini model + Google GenAI SDK or ADK + one Google Cloud service

**AURA's existing differentiators** (highlight these in the submission writeup):

* 3-layer hybrid perception: UI tree → YOLOv8 CV → VLM selection
* VLM NEVER generates coordinates (SoM safety guarantee)
* 5-stage retry ladder before expensive LLM replanning
* OPA Rego policy engine for action safety
* 9 single-responsibility agents with deterministic coordinator
* Reactive hybrid planning: skeleton phases + per-screen grounding

**Judging criteria axes:**

1. Technical complexity and innovation
2. Effective use of Google technology
3. Real-world impact and practicality
4. Quality of presentation and demo video

---

*Generated for AURA — Gemini Live Agent Challenge submission*
*Deadline: March 16, 2026 @ 5:00 PM PT*
