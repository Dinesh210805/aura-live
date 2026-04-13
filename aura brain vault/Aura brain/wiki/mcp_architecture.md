---
last_verified: 2026-04-09
source_files: []
status: current
---

# AURA — MCP Architecture & Open-Source Strategy

> Strategic planning document. Not tied to a source file — this captures architectural
> decisions made in advisory sessions, not code that exists yet.

---

## What We Are Building

AURA is being extended from a hackathon voice assistant into a **multi-input, open-source Android
automation platform** that any AI agent (Claude Code, GitHub Copilot, Codex, Cursor, or a human
voice from the phone) can control.

The core insight: **AURA's value is not which LLM it uses — it's the Set-of-Marks perception
pipeline.** YOLO detects UI elements, labels them A1/A2/A3, and any agent picks by label.
No agent ever guesses pixel coordinates. That is the architectural moat.

---

## The Two-Way Pipeline

```
INPUTS (multiple sources, all converge)
────────────────────────────────────────────────────────────────
┌─────────────────┐   ┌──────────────────┐   ┌───────────────┐
│  Android Phone  │   │  Claude Code /   │   │  Any Agent    │
│  🎤 Voice       │   │  Coding Agents   │   │  (HTTP/MCP)   │
│  /ws/audio      │   │  MCP protocol    │   │  REST API     │
└────────┬────────┘   └────────┬─────────┘   └───────┬───────┘
         │ PCM audio            │ text                 │ text
         ▼                      ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│                    AURA INPUT GATEWAY                         │
│                                                               │
│  Voice  → STT (Groq Whisper) → text + source="voice"        │
│  MCP    → no STT needed      → text + source="mcp"          │
│  HTTP   → no STT needed      → text + source="api"          │
│                                                               │
│  All paths produce: { command, source, client_id }           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    AURA CORE PIPELINE                         │
│                                                               │
│  Commander → Planner → Coordinator → Actor → Verifier        │
│  (same pipeline regardless of source)                        │
│                                                               │
│  Gestures → WebSocket /ws/device → Android App               │
└──────────────────────────┬───────────────────────────────────┘
                           │ task result + screenshots
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    RESULT ROUTER + EVENT BUS                  │
│                                                               │
│  source="voice" → TTS → /ws/audio → phone speaks result     │
│  source="mcp"   → MCP tool return → agent reads it          │
│  source="api"   → HTTP response  → agent reads it           │
│                                                               │
│  ALL sources → event broadcast → every subscriber sees it    │
└──────────────────────────────────────────────────────────────┘
```

**Key property**: The Android device is a shared execution target. Every brain controls
the same device. Results are routed back to whoever asked, but broadcast to all observers.

---

## Dual Brain Architecture

The AI provider depends on the input path. This is intentional — not a limitation.

### Voice Path — Groq as Brain

```
Phone mic → Groq Whisper STT → Groq Llama (reasoning) → Groq VLM (SoM selection)
```

- Latency target: < 2 seconds end-to-end
- Claude Code is not running on the user's phone — no other option
- Groq at 560-750 tps is fast enough for voice UX
- Keep existing pipeline unchanged

### MCP Path — Claude as Brain (preferred)

```
Claude Code → perceive_screen() → Claude sees screenshot + SoM labels
           → Claude reasons, picks element by label
           → execute_gesture() → device
           → perceive_screen() again → Claude verifies
```

- Claude replaces Commander, Planner, Coordinator, VisualLocator, Verifier reasoning
- Your SoM pipeline still runs (CV detection → labels) — Claude picks from labels
- No Groq/Gemini API costs for reasoning layer on this path
- Claude handles retries and replanning through conversation naturally

### HTTP/API Path — Black Box

```
External agent → POST /api/v1/execute → AURA runs Groq/Gemini internally → JSON result
```

- Groq/Gemini handle reasoning (as today)
- External agent uses its own AI to interpret the result
- Works for any agent that can make HTTP calls

---

## AI Provider Matrix

| Input source       | Reasoning AI        | Execution AI         | Who pays               |
|--------------------|---------------------|----------------------|------------------------|
| Voice (phone)      | Groq/Gemini         | Groq/Gemini          | You (your API keys)    |
| Claude Code — MCP  | Claude (Anthropic)  | None (deterministic) | User's Claude sub      |
| Other agent (HTTP) | That agent's LLM    | Groq/Gemini          | That agent + your keys |

---

## MCP Tool Surface (Two Styles)

Both styles are exposed simultaneously. Agents choose which fits their task.

### Style A — Black Box (universal compatibility)

```python
@server.tool()
async def execute_android_task(utterance: str) -> dict:
    """
    Full AURA pipeline. Groq/Gemini handle all reasoning internally.
    Works with any agent — no vision capability required.
    Returns: { success, response_text, steps_taken, final_screenshot }
    """
    return await run_aura_task(utterance)
```

Works with: Claude Code, GitHub Copilot, Cursor, Codex, Windsurf, any HTTP client.

### Style B — Granular Tools (Agent-Piloted Mode)

```python
@server.tool()
async def perceive_screen() -> dict:
    """
    Returns: screenshot (base64), UI accessibility tree (JSON),
    CV-detected elements with SoM labels (A1, A2, ... labels).
    No AI inside — Claude reasons about what it sees.
    """

@server.tool()
async def execute_gesture(gesture_type: str, target: str, params: dict) -> dict:
    """
    Sends gesture over WebSocket to Android device. No AI inside.
    gesture_type: "tap" | "swipe" | "type" | "scroll"
    target: SoM label (e.g. "A3") or accessibility description
    """

@server.tool()
async def validate_action(gesture_type: str, target: str) -> dict:
    """
    Rule-based OPA policy check. No AI inside.
    Returns: { allowed: bool, reason: str }
    """

@server.tool()
async def watch_device_events(timeout_seconds: int = 30) -> list[dict]:
    """
    Subscribe to all device events for N seconds.
    Returns list of events regardless of who triggered them (voice, MCP, API).
    Useful for Claude to observe what's happening.
    """
```

Works best with: Claude Code (native vision), GPT-4o agents, Gemini agents.

---

## Event Bus — The Collaborative Layer

Every action taken on the device (regardless of source) is broadcast to all subscribers.

```
Scenario: Developer uses Claude Code to test. Phone is connected.

1. Claude Code calls execute_gesture("tap", "A3")
2. Device screen changes
3. Phone user sees it happen live — no action required
4. Claude Code gets result
5. Phone app also receives broadcast event

Reverse:
1. User speaks "go back to home screen" on phone
2. AURA executes
3. Claude Code (if monitoring via watch_device_events) observes:
   { triggered_by: "voice", command: "go back to home screen" }
4. Claude adjusts its test plan accordingly
```

This creates a genuine human+AI collaborative control loop.

### Implementation sketch

```python
# services/event_bus.py — new service
class AuraEventBus:
    async def publish(self, event: dict): ...
    def subscribe(self, client_id: str) -> asyncio.Queue: ...

# TaskState — one new field
command_source: str   # "voice" | "mcp" | "api"
client_id: str        # route response back to correct connection

# After run_aura_task() — route result
async def route_result(state, result):
    await event_bus.publish({ ... })          # broadcast always
    if state.command_source == "voice":
        await tts_service.speak(...)          # phone hears it
    elif state.command_source == "mcp":
        return result                         # MCP tool return
```

### Task queue — one device, multiple senders

```python
# Only one task runs at a time
class TaskQueue:
    async def submit(self, task: dict) -> TaskResult:
        await self._queue.put(task)
        async with self._lock:
            return await run_aura_task(await self._queue.get())
```

Voice commands from the phone get priority (configurable).

---

## Agent Compatibility

MCP is an open protocol — not Claude-exclusive.

| Agent                | MCP Support | Style A works | Style B works        |
|----------------------|-------------|---------------|----------------------|
| Claude Code          | Native      | Yes           | Yes (best — vision)  |
| GitHub Copilot       | Yes (2025)  | Yes           | Depends on model     |
| Cursor               | Yes         | Yes           | Depends on model     |
| Windsurf (Codeium)   | Yes         | Yes           | Depends on model     |
| Continue.dev         | Yes         | Yes           | Depends on model     |
| OpenAI Codex         | Yes (2025)  | Yes           | If GPT-4o is backend |
| Custom (LangChain)   | Via library | Yes           | If vision-capable    |
| Any HTTP client      | REST API    | Yes           | No                   |

Style B (granular) requires the calling agent to be multimodal (can reason about screenshots).
Style A (black box) works with every agent regardless of vision capability.

---

## What Stays vs What Gets Added

### Keep unchanged

- WebSocket device communication layer (`/ws/device`, `/ws/audio`)
- CV detection / YOLOv8 SoM labeling pipeline
- UI tree parser
- OPA policy engine (rule-based safety)
- Gesture execution logic
- Entire voice path (Groq STT/LLM/VLM)

### Add

- `aura_mcp_server.py` — MCP server exposing Style A + Style B tools
- `services/event_bus.py` — shared broadcast layer
- `services/task_queue.py` — single-device serialization with priority
- `source` + `client_id` fields on `TaskState`
- Result router in `aura_graph/graph.py`
- `api/execute.py` — REST fallback endpoint

### Remove (from MCP path only — keep for voice path)

- Groq/Gemini reasoning calls are bypassed when source="mcp" and Style B is used
- STT call is skipped entirely (text command arrives directly)

---

## Build Phases

### Phase 1 — MCP Granular Tools (2-3 days)

Primary deliverable. Four tools: `perceive_screen`, `execute_gesture`, `validate_action`,
`watch_device_events`. Zero changes to the voice pipeline. This is the open-source demo.

**The demo that gets stars:**
```
Developer types in Claude Code:
"test the login flow on my connected device, 
 use testuser@email.com / password123,
 tell me if anything breaks"

Claude perceives screen → sees SoM labels → types credentials → taps login
→ perceives again → "Login succeeded. Home screen visible. No errors."
Phone showed every step live.
```

### Phase 2 — Event Broadcast Layer (1 day)

Event bus + result router. All clients observe all actions. Phone shows Claude's work live.

### Phase 3 — Black Box Tool + REST API (few hours)

`execute_android_task()` wrapper + `/api/v1/execute` HTTP endpoint.
Compatibility for non-Claude agents and CI pipelines.

### Phase 4 — Open Source Packaging

- `setup.sh` — one-command install
- `quickstart.md` — connect phone → run this → say this → see this
- 30-second demo GIF
- README refactored from hackathon framing to tool framing

---

## Open Source Positioning

```
"AURA — Voice + Agent-Controlled Android Automation"

Control your Android device from:
  ✓ Your voice (phone microphone)
  ✓ Claude Code   — full granular control + vision
  ✓ GitHub Copilot — one-shot task execution
  ✓ Cursor         — integrated device testing
  ✓ Codex          — automated mobile QA
  ✓ Any HTTP client — REST API fallback

Powered by Set-of-Marks perception — agents never guess coordinates.
```

---

## Decisions Made in This Planning

| # | Decision | Rationale |
|---|----------|-----------|
| M1 | Keep Groq for voice path | Latency-sensitive; Claude unavailable on phone |
| M2 | Agent-Piloted Mode for MCP path (Style B) | Any vision-capable agent (Claude, GPT-4o, Gemini) can drive AURA granularly |
| M3 | Expose both MCP styles | Style A for compatibility; Style B for power |
| M4 | Event bus broadcast to all clients | Enables collaborative human+AI control loop |
| M5 | Single task queue, voice priority | One device can only run one task at a time |
| M6 | REST fallback alongside MCP | Reaches agents without MCP support |
| M7 | Build Phase 1 (MCP tools) first | Fastest path to real users; voice already works |
| M8 | SoM pipeline unchanged | It's the moat — LLM changes around it, not through it |
