---
last_verified: 2026-04-08
source_files: [config/settings.py]
status: current
---

# Configuration

**File:** `config/settings.py` (498 lines)  
**Class:** `Settings` (Pydantic BaseSettings)

---

## Rule

> Never read `os.environ` directly. Always use `from config.settings import settings`.

All environment variables flow through a single Pydantic `Settings` class. This ensures type validation, default enforcement, and a single source of truth.

---

## Required Fields (no defaults — will raise at startup if missing)

| Field | Type | Purpose |
|-------|------|---------|
| `groq_api_key` | `str` | Groq LLM + VLM + PromptGuard |
| `gemini_api_key` | `str` | Gemini LLM + VLM fallback |

---

## LLM / VLM Provider Settings

| Field | Default | Notes |
|-------|---------|-------|
| `default_llm_provider` | `"groq"` | Primary LLM provider |
| `default_vlm_provider` | `"groq"` | **⚠️ Must change to `"gemini"` for hackathon** |
| `default_vlm_model` | — | Primary VLM model string |
| `fallback_vlm_model` | — | VLM fallback model string |
| `nvidia_api_key` | `None` | Optional NVIDIA NIM |
| `openrouter_api_key` | `None` | Optional OpenRouter |

---

## TTS / STT Settings

| Field | Default | Notes |
|-------|---------|-------|
| `android_tts_enabled` | `True` | Use Android device for TTS instead of Edge-TTS |
| `default_tts_provider` | `"android"` | "android" or "edge" |

---

## Graph / Task Execution Settings

| Field | Default | Notes |
|-------|---------|-------|
| `graph_recursion_limit` | `100` | Formula: 4 nodes/step × 10 steps × 2.5x retry buffer |
| `graph_timeout_seconds` | `120.0` | Hard wall-clock timeout per task |
| `step_history_window` | `6` | How many steps coordinator keeps in active context |
| `vlm_timeout_seconds` | `30` | ThreadPoolExecutor timeout for VLM selection (G6 fix) |

---

## GCP / Cloud Settings

| Field | Default | Notes |
|-------|---------|-------|
| `google_api_key` | `None` | GCP auth (prefers over `gemini_api_key` for GCS) |
| `google_cloud_project` | `None` | Required for GCS log uploads |
| `gcs_logs_enabled` | `False` | Enable GCS HTML execution log uploads |
| `gemini_live_enabled` | `False` | Enable `/ws/live` Gemini Live bidi endpoint |

---

## Android / ADB Settings

| Field | Default | Notes |
|-------|---------|-------|
| `android_device_id` | `None` | ADB device target (empty = use first connected) |
| `adb_path` | `"adb"` | Path to ADB binary |

---

## `.env.example` Mapping

All required fields must be present in `.env`. The example file documents every variable. Key reminder: change `DEFAULT_VLM_PROVIDER=groq` → `DEFAULT_VLM_PROVIDER=gemini` in both `.env.example` and `config/settings.py` default value before hackathon submission.

---

## Integration
- `AppModule` (`di/app_module.py`) creates the `Settings` singleton and injects it into all services
- `main.py` reads `settings.port` (via `$PORT` env var for Cloud Run) to bind uvicorn
- `Dockerfile` sets `$PORT` via Cloud Run environment
