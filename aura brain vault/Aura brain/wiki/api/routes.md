# API Routes

All routes registered in `main.py` via FastAPI router includes.

---

## HTTP Endpoints

### Health & System
| Method | Path | Handler | Notes |
|--------|------|---------|-------|
| GET | `/health` | `main.py` | Returns `{"status": "healthy"}` — used by Cloud Run health checks |
| GET | `/docs` | FastAPI auto | Swagger UI |
| GET | `/demo` | `api/demo.py` | Judging dashboard: live screenshot, health, recent commands, GCS log links |

### Task API (`api_handlers/task_router.py`)
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/tasks` | Submit a task by text (JSON body: `{"command": "..."}`) |
| GET | `/api/v1/tasks/{task_id}` | Poll task status |
| GET | `/api/v1/tasks/{task_id}/result` | Get completed task result |

### Device API (`api_handlers/device_router.py`)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/device/screenshot` | Returns current device screenshot (base64 PNG) |
| GET | `/api/v1/device/ui-tree` | Returns current accessibility UI tree JSON |
| POST | `/api/v1/device/gesture` | Execute a single gesture directly (bypass policy check when called directly — use with care) |

### Accessibility API (`api_handlers/real_accessibility_api.py`)
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/accessibility/find` | Find UI element by description |
| GET | `/api/v1/accessibility/apps` | List installed apps |

---

## WebSocket Endpoints

### Voice Audio — `/ws/audio`
**File:** `api_handlers/websocket_router.py`

- Receives raw audio chunks from Android companion app
- STT transcription via Groq Whisper
- PromptGuard screening
- Intent classification → task dispatch
- Streams text responses back
- **Must not change path or message format** — Android app hardcodes this URL

### Device Control — `/ws/device`
**File:** `api_handlers/websocket_router.py` (or dedicated handler)

- Receives UI tree updates pushed from Android accessibility service
- Sends gesture commands to Android device
- **Must not change path** — Android app hardcodes this URL

### Task Streaming — `/api/v1/tasks/ws`
**File:** `api_handlers/task_router.py` or `websocket_router.py`

- Bidirectional task execution streaming
- Client sends: `{"command": "...", "session_id": "..."}`
- Server streams: `{"type": "progress_update", "message": "..."}` events
- Terminal events: `UpdateType.TASK_COMPLETED`, `UpdateType.TASK_FAILED`

### Gemini Live — `/ws/live`
**File:** `adk_streaming_server.py`

- Bidi audio+vision streaming with Gemini Live API
- VAD (Voice Activity Detection) configured via `RealtimeInputConfig`
- Transcript accumulation and barge-in support
- **Gated behind `GEMINI_LIVE_ENABLED=true`** — inactive by default
- Added for hackathon scoring

---

## Message Formats

### Audio WebSocket (client → server)
```json
{"type": "audio_chunk", "data": "<base64 PCM>", "session_id": "..."}
```

### Task Progress (server → client)
```json
{"type": "progress_update", "message": "Tapping Search button...", "step": 3}
```

### Task Complete (server → client)
```json
{"type": "task_completed", "result": "Done. I opened Spotify and started playing liked songs.", "task_id": "..."}
```
