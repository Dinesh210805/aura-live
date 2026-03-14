# Chapter 4: System Requirements and Implementation

---

## 4.1 Hardware Requirements

The AURA server performs local inference for the OmniParser YOLOv8 model and the Prompt Guard safety classifier, and maintains persistent WebSocket connections to the Android device, so it requires a GPU-equipped machine. The Android client has moderate minimum requirements since all language model inference is offloaded to cloud providers.

### Server (Primary Deployment)

- **Processor:** AMD Ryzen 9 5950X — 16 cores / 32 threads, 3.4 GHz base clock (4.9 GHz boost). A modern multi-core CPU is required to handle concurrent WebSocket connections, async FastAPI request handling, and background inference threads simultaneously.
- **Memory (RAM):** 64 GB DDR4. Large RAM headroom is required to keep the compiled LangGraph state machine, all agent instances, the OmniParser model, and the Prompt Guard classifier resident in memory across the server's lifetime without paging.
- **GPU:** NVIDIA GeForce RTX 3090 with 24 GB VRAM. The GPU is used exclusively for the OmniParser YOLOv8 inference (Layer 2 perception) and the Llama Prompt Guard 2 86M safety classifier. All primary LLM and VLM inference is handled by cloud providers. A minimum of 8 GB VRAM is recommended; 16+ GB VRAM is preferred for stable batch OmniParser inference.
- **Storage:** NVMe SSD with sustained read speeds exceeding 3000 MB/s. Fast storage is critical because the OmniParser model weights (~180 MB) and Prompt Guard weights (~86 M parameters) are loaded into GPU memory at server startup. Slow storage causes perceptible cold-start latency on first boot.
- **Operating System:** Ubuntu 22.04 LTS (primary deployment). Windows 11 with WSL2 is supported for development.
- **Network:** Local Area Network (Ethernet or Wi-Fi) connectivity to the Android device is required. The server binds to port 8000 and communicates with the companion app over the same LAN. A stable internet connection is required for Groq, OpenRouter, and Google Gemini API calls.

### Android Test Device (Evaluation Hardware)

- **Device:** OnePlus CPH2661 — Android 16 (API Level 36).
- **Display:** 6.7-inch AMOLED, 1080 × 2412 pixels.
- **RAM:** 8 GB.
- **ADB over TCP:** Enabled on port 5555 for gesture injection from the server.
- **Required permissions:** Accessibility Service, MediaProjection (screen capture), microphone access, and network access for WebSocket communication.

### Minimum Android Client Requirements

- **OS:** Android 10 (API Level 29) or higher. Android 10 introduced the mandatory Settings panel architecture for system toggles, which the PolicyEngine is designed around.
- **RAM:** 4 GB minimum, 6 GB recommended to keep the companion Accessibility Service resident in the background.
- **Display:** Any resolution — the perception pipeline normalises all screenshots to 640 × 640 before YOLOv8 inference.
- **Microphone and speaker:** Required for voice command input and spoken TTS feedback.
- **Connectivity:** Wi-Fi or 4G/5G with stable low-latency connection to the server LAN.

---

## 4.2 Software Requirements

### Operating System

- **Server:** Ubuntu 22.04 LTS (recommended) or Windows 11 with WSL2. The Uvicorn ASGI server, ADB command-line tools, and PyTorch GPU bindings are fully supported on both platforms.
- **Mobile:** Android 10 (API Level 29) or higher with Accessibility Services enabled and MediaProjection API available. The evaluation device ran Android 16 (API Level 36).

### Programming Languages

- **Python 3.11** — All backend logic: FastAPI server, LangGraph state machine, eight specialist agents, perception pipeline, gesture executor, policy engine, and model service clients.
- **Kotlin** — Android companion application (`com.aura.aura_ui`): Accessibility Service implementation, MediaProjection screenshot capture, WebSocket client, TTS audio playback, and GestureController dispatch.

### Backend Frameworks and Libraries

- **FastAPI 0.104.1 + Uvicorn 0.24.0** — Asynchronous REST API and WebSocket server. Handles all `/api/v1` endpoints with a single-worker configuration to ensure in-memory state consistency across the compiled LangGraph graph.
- **LangGraph ≥ 0.3.27 + LangChain ≥ 0.3.0** — Agent orchestration framework. LangGraph compiles the 15-node directed state machine at server startup. LangChain provides the message formatting and provider abstraction used by `LLMService` and `VLMService`.
- **Ultralytics YOLOv8 ≥ 8.0.0** — Object detection engine for the OmniParser Layer 2 perception path. Runs on the server GPU to detect UI elements in screenshots where the Android Accessibility Tree is absent or incomplete.
- **OpenCV ≥ 4.8.0 + NumPy ≥ 1.24.0** — Image preprocessing, bounding box drawing, and Set-of-Marks alphabetic label overlay generation for the annotated screenshots passed to the vision-language model.
- **Pydantic v2 2.5.3** — Request and response model validation, settings management via `BaseSettings`, and immutable `IntentObject` and `TaskState` bundle definitions.
- **Edge-TTS ≥ 6.1.0** — Microsoft Neural Voices text-to-speech synthesis using the `en-US-AriaNeural` voice. Synthesises spoken feedback audio and delivers it over WebSocket to the companion application.
- **pydub 0.25.1 + SpeechRecognition 3.10.0** — MP3-to-WAV audio format conversion and audio buffer format validation for the voice pipeline.
- **regopy ≥ 0.4.0** — Pure-Python Open Policy Agent (OPA) / Rego policy evaluation engine used by the `PolicyEngine` to evaluate safety rules against action contexts at runtime, without requiring a sidecar OPA server.
- **SlowAPI** — Per-endpoint rate limiting middleware, keyed on the client's remote IP address.
- **httpx 0.25.2 + aiohttp 3.9.1** — Asynchronous HTTP clients for model provider API calls and device communication.
- **python-dotenv 1.0.0** — `.env` file loading for API keys and configuration at startup.
- **HuggingFace Hub ≥ 0.19.0** — OmniParser v2.0 model weight download and caching.
- **LangSmith 0.0.70** — LLM call tracing and debugging. All model invocations are traced when `LANGCHAIN_TRACING_V2=true` is set in the environment.
- **pytest 7.4.3 + pytest-asyncio 0.21.1** — Asynchronous unit and integration test suite.

### Cloud APIs and AI Models

- **Groq Cloud (primary inference provider):**
  - `whisper-large-v3-turbo` — Real-time speech-to-text for voice commands (300–500 ms transcription latency for short utterances).
  - `llama-3.1-8b-instant` — Fast intent classification fallback (~560 tokens/sec on Groq LPU).
  - `meta-llama/llama-4-maverick-17b-128e-instruct` — Goal decomposition and reactive step generation (Llama 4 Maverick with 128 mixture-of-experts routing).
  - `meta-llama/llama-4-scout-17b-16e-instruct` — Primary vision-language model for Set-of-Marks region selection (Llama 4 Scout with 16 experts).
  - `llama-3.3-70b-versatile` — Spoken response generation with emotion-aware tone calibration.
  - `meta-llama/llama-prompt-guard-2-86m` — Prompt injection and jailbreak detection; runs as a pre-processing classifier on every user input before any primary model receives it.

- **OpenRouter (intent classification primary):**
  - `glm-4.5-air:free` — GLM-4.5-Air via OpenRouter's free tier, used as the primary intent classification model for structured `IntentObject` JSON extraction.

- **Google Gemini (universal fallback):**
  - `gemini-2.5-flash` — Universal fallback for all Groq-backed tasks (goal decomposition, vision analysis, response generation, and intent classification). Activates automatically on any Groq API error without user-visible interruption.

- **Microsoft Edge-TTS (text-to-speech):**
  - `en-US-AriaNeural` — Neural voice for spoken feedback synthesis delivered to the companion app.

### Android APIs and Device Integration

- **Android Accessibility Service Framework** — Extracts the complete UI element tree from any foreground application at any point in time, providing element text, content description, class name, bounding rectangle, and interactability flags without requiring developer cooperation.
- **MediaProjection API** — Captures full-resolution pixel buffer screenshots of the current display state for forwarding to the perception pipeline and for VLM analysis.
- **GestureController API (`dispatchGesture()`)** — Injects synthetic touch gestures (tap, swipe, long press, double tap, scroll) into the active screen with coordinate precision from element bounding rectangles.
- **ADB over TCP (port 5555)** — Secondary gesture injection path used by the server for `type`, `key`, and complex input sequences that the GestureController API does not support natively.
- **OkHttp** — HTTP and WebSocket client library in the Kotlin companion app for bidirectional JSON protocol communication with the FastAPI server.
- **Kotlin Coroutines** — Asynchronous execution model for the companion app's audio streaming, screenshot capture, and WebSocket message handling.

### Development Tools

- **VS Code** — Primary IDE for Python backend development, with Pylance, Python Debugger, and REST Client extensions.
- **Android Studio** — Kotlin companion application development, layout editing, Logcat monitoring, and APK build/signing.
- **Android Debug Bridge (ADB)** — Device connection management, APK installation, log capture (`aura_logcat.bat`), and shell command execution during testing.
- **Postman / cURL** — REST API endpoint testing for all `/api/v1` routes.
- **LangSmith** — Real-time tracing dashboard for LLM and VLM invocation chains, token usage monitoring, and latency profiling across agent nodes.
- **GitHub** — Version control and issue tracking for the project codebase.

---

## 4.3 Development Environment Setup

The backend server is initialised by running `main.py` through Uvicorn. At startup the application performs the following sequence in order: the LangGraph state machine is compiled by `compile_aura_graph()`, which instantiates all service objects (`LLMService`, `VLMService`, `STTService`, `TTSService`) and all eight agent objects (`CommanderAgent`, `PlannerAgent`, `PerceiverAgent`, `ActorAgent`, `VerifierAgent`, `ValidatorAgent`, `ResponderAgent`, `Coordinator`), then stores the compiled graph in `app.state.graph_app`. The `RealAccessibilityService` singleton is instantiated and stored in `app.state.accessibility_service`. LangSmith tracing is enabled by injecting the `LANGCHAIN_TRACING_V2=true` environment variable. The OmniParser YOLOv8 weights are loaded into GPU memory in a background daemon thread so that the first computer vision inference request does not experience cold-start model-loading latency. When all startup tasks complete, Uvicorn begins accepting connections on port 8000.

All API keys required by the system — `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, and `LANGCHAIN_API_KEY` — are stored in a `.env` file at the project root and loaded by `python-dotenv` during the settings object construction. The `config/settings.py` module defines a Pydantic `BaseSettings` class that validates all required keys at startup and raises a clear configuration error if any are absent, preventing the server from starting in a partially configured state.

The Android companion application is built and deployed through Android Studio. The app requires a one-time Accessibility Service activation through the device's Settings, and a one-time MediaProjection permission grant through a system dialog on first screenshot capture. The server IP address is configured in the app's settings screen. Once configured, the companion app maintains a persistent WebSocket connection to the server and streams audio and UI tree snapshots on demand.

---

## 4.4 Implementation Overview

The implementation is organised across seven top-level directories and approximately forty source files. The `agents/` directory contains the eight specialist agent modules. The `aura_graph/` directory contains the LangGraph state machine compilation, node definitions, conditional edge functions, and the shared `TaskState` TypedDict. The `services/` directory contains the `LLMService`, `VLMService`, `STTService`, `TTSService`, `GestureExecutor`, `PolicyEngine`, `PromptGuard`, and `PerceptionPipeline` service implementations. The `api/` and `api_handlers/` directories contain the eleven FastAPI router modules. The `config/` directory contains the `Settings` Pydantic model, action type registry, application package registry, model router configuration, and success criteria definitions. The `perception/` directory contains the `OmniParserDetector` YOLOv8 integration and the `HeuristicSelector` fallback.

The server exposes eleven REST and WebSocket routes under the `/api/v1` prefix. The primary task execution route is `POST /api/v1/tasks`, which accepts a JSON body containing the user's command as a text string, injects it into a fresh `TaskState` graph invocation, streams intermediate status events over a Server-Sent Events connection, and returns the final JSON result. The real-time voice path uses `WebSocket /api/v1/ws/audio`, which accepts raw PCM audio chunks, accumulates them until a silence boundary is detected, submits the buffer to STT, and then processes the resulting transcript identically to the text command path. All responses include a `taskId`, `status`, `result`, `feedback` (the spoken response text), and `executionTime` field.

The middleware stack applies security checks before any route handler executes. The `API key authentication middleware` verifies the `X-API-Key` header on every request using `secrets.compare_digest` for timing-safe comparison. The `Request ID middleware` generates a UUID-based `X-Request-ID` header and injects it into the request log context so that every log line for a given request can be correlated by ID. The `SlowAPI rate limiter` enforces per-endpoint request-per-minute limits to prevent runaway automation from any single client. The `CORSMiddleware` permits all origins for development flexibility on the local network.

---

## 4.5 Testing and Evaluation Setup

Functional testing was performed using the `pytest` suite located in the `tests/` directory, covering intent classification accuracy, PolicyEngine rule evaluation, PerceptionPipeline layer selection, and GestureExecutor command serialisation. The `pytest-asyncio` plugin enabled direct testing of all asynchronous agent and service methods without requiring separate event loop management.

End-to-end evaluation was performed manually on the physical OnePlus CPH2661 device across six application categories: Gmail, LinkedIn, Chrome, Android Settings, the Home Screen and App Drawer, and YouTube. Each evaluation scenario was issued as a natural language voice command through the companion application's microphone. The experimenter verified task completion by observing the device screen and confirming that the final application state matched the command's intent. A task was counted as successfully completed only if the entire interaction sequence — from voice input to the correct final screen state — was executed without any manual intervention by the experimenter. Partial completions (where some steps succeeded but the final state was incorrect) were counted as failures in the reported 85 percent completion rate.

API call behaviour during testing was monitored through the LangSmith tracing dashboard, which recorded per-node latency, token consumption, and model fallback events for every command. This tracing data validated the per-step average latency of 2.2 seconds and confirmed that the Groq-to-Gemini fallback path was triggered in fewer than 3 percent of all inference calls during the evaluation period.

---

*End of Chapter 4: System Requirements and Implementation*
