---
last_verified: 2026-04-08
source_files: [main.py, aura_graph/graph.py, agents/coordinator.py]
status: current
---

# AURA — System Overview

## What AURA Does

AURA is a production-grade **Android UI automation system** controlled via voice. A user speaks a command ("Open Spotify and play my liked songs") and AURA:

1. Transcribes the audio (Groq Whisper)
2. Classifies and parses the intent
3. Safety-screens the command (Llama Prompt Guard 2)
4. Captures a screenshot and parses the UI tree from the connected Android device
5. Plans a sequence of steps (LangGraph state machine + 9 agents)
6. Executes gestures on the device (tap, swipe, type, scroll)
7. Verifies success after each action
8. Responds in natural language (Edge-TTS or Android on-device TTS)

---

## Request Lifecycle (Full Path)

```
Voice audio (PCM 16kHz mono int16)
    │
    ▼ WebSocket /ws/audio
api_handlers/websocket_router.py  ←  ConversationManager (5-turn context)
    │
    ▼ STT
services/stt.py  ←  Groq Whisper Large v3 Turbo
    │ transcript
    ▼
utils/fuzzy_classifier.py  ←  tier: conversational / simple / medium / complex
    │
    ▼ safety screen
services/prompt_guard.py  ←  Llama Prompt Guard 2 (fail-safe: allow on error)
    │
    ▼ task dispatch
aura_graph/graph.py → run_aura_task()
    │
    ▼ LangGraph StateGraph (8 nodes)
┌─────────────────────────────────────────────────────────────────┐
│  route_from_start                                               │
│       │                                                         │
│  stt → parse_intent → should_continue_after_intent_parsing      │
│                              │                                  │
│           ┌──────────────────┼──────────────────┐              │
│       web_search          coordinator       conversational      │
│                              │                                  │
│              ┌───────────────┴───────────────┐                  │
│          perception                        error_handler        │
│              │ should_continue_after_perception                 │
│          coordinator                                            │
│    (perceive→decide→act→verify loop, retry ladder)              │
│              │                                                  │
│           speak ← responder_agent                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼ TTS
services/tts.py  ←  Android on-device TTS (WebSocket) OR Edge-TTS
    │
    ▼ Result JSON back to Android app
```

---

## Android Connection

The Android companion app (`UI/`) connects over WebSocket channels:

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `ws://host:8000/ws/audio` | Voice audio upload + task result responses | **Do not change** |
| `ws://host:8000/ws/device` | Device control commands, UI tree pushes | **Do not change** |
| `ws://host:8000/ws/live` | Gemini Live bidi audio+vision | Gated: `GEMINI_LIVE_ENABLED=true` |

The server sends TTS back over `/ws/audio` as `{"type": "tts_response", "text": "...", "voice": "..."}` and the Android app synthesizes speech locally via `AuraTTSManager` — this is the low-latency path (`android_tts_enabled=true`).

---

## Tri-Provider Architecture

All AI calls go through unified service wrappers in `services/`. No direct SDK calls elsewhere.

### LLM (`services/llm.py`) — Groq primary, Gemini/NVIDIA fallback
| Role | Model | Provider |
|------|-------|---------|
| Intent parsing (fast) | Llama 3.1 8B Instant | Groq (560 tps) |
| Planning / reasoning | Llama 4 Maverick 17B (128 MoE experts) | Groq |
| Response generation | Llama 3.3 70B | Groq |
| Fallback (all above) | Gemini 2.5 Flash | Gemini |

### VLM (`services/vlm.py`) — Groq primary, Gemini fallback
| Role | Model | Provider |
|------|-------|---------|
| UI analysis / vision | Llama 4 Scout 17B | Groq (750 tps) |
| Set-of-Marks selection | Same → Gemini 2.5 Flash | Groq → Gemini |

### STT / TTS
- **STT**: Groq Whisper Large v3 Turbo (faster than v3)
- **TTS**: Android on-device TTS (default, ~0ms latency) or Edge-TTS server-side (~1.4s)

---

## The 9 Agents (Single-Responsibility)

| Agent | File | Role |
|-------|------|------|
| `Perceiver` | `agents/perceiver_agent.py` | Wraps PerceptionController, returns ScreenState |
| `Commander` | `agents/commander.py` | Parses intent (rule-based first, LLM fallback) |
| `Planner` | `agents/planner_agent.py` | Decomposes goal into skeleton phases |
| `Coordinator` | `agents/coordinator.py` | Main perceive→decide→act→verify loop |
| `Actor` | `agents/actor_agent.py` | Executes gestures — zero LLM calls |
| `Responder` | `agents/responder.py` | Generates natural language responses |
| `Validator` | `agents/validator.py` | Rule-based pre-execution validation (no LLM) |
| `Verifier` | `agents/verifier_agent.py` | Post-action verification |
| `VisualLocator` | `perception/vlm_selector.py` | SoM VLM selection from CV candidates |

---

## Critical Invariants

1. **VLM never returns pixel coordinates** — only selects among numbered SoM (Set-of-Marks) elements
2. **5-stage retry ladder** runs per-subgoal: `SAME_ACTION → ALTERNATE_SELECTOR → SCROLL_AND_RETRY → VISION_FALLBACK → ABORT`
3. **Every gesture** passes through OPA policy check in `gesture_executor.py`
4. **All new actions** must be registered in `config/action_types.py` ACTION_REGISTRY
5. **All service functions** must be `async def`
6. **All API keys** through `config/settings.py` (Pydantic Settings) — never raw `os.environ`
7. **9 agents stay single-responsibility** — no merging or scope creep

---

## Key Config Flags

| Variable | Default | Effect |
|----------|---------|--------|
| `DEFAULT_VLM_PROVIDER` | `"groq"` | Should be `"gemini"` for hackathon |
| `GEMINI_LIVE_ENABLED` | `false` | Enables `/ws/live` endpoint |
| `GCS_LOGS_ENABLED` | `false` | Enables Cloud Storage log uploads |
| `ANDROID_TTS_ENABLED` | `true` | On-device TTS vs server-side Edge-TTS |
| `GRAPH_TIMEOUT_SECONDS` | `120` | Hard timeout on `run_aura_task()` |

---

## Deployment

```bash
# Local development
python main.py
# → http://0.0.0.0:8000 | docs: /docs | health: GET /health

# Docker / Cloud Run
docker build -t aura-live .
docker run -p 8080:8080 --env-file .env aura-live
```
