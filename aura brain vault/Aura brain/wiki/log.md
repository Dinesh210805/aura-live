---
last_verified: 2026-04-13
source_files: []
status: current
---

# AURA Wiki — Change Log

---

## 2026-04-13 — MCP Startup Fix: Logger Header Template KeyError

**Session**: Fix Aura MCP process crash on startup (`KeyError: 'color'`)  
**Branch**: feature/mcp-server  
**Author**: GitHub Copilot (GPT-5.3-Codex)

### Problem
Aura MCP started successfully, then crashed during logger bootstrap in `MCPBrainLogger.__init__` because `_HTML_HEADER.format(...)` tried to resolve a non-existent `color` format key from CSS template text.

### Fix Applied
- **File modified**: `aura_mcp_server.py`
- In `_HTML_HEADER`, replaced CSS placeholders that looked like Python format fields:
	- `.entry` `border-left:4px solid {color};` → fixed color `#4fc3f7`
	- `.level` `color:{color};` → fixed color `#4fc3f7`

### Verification
- Import smoke test passed: `import aura_mcp_server` no longer raises `KeyError: 'color'`.
- MCP logger initializes and writes session files as expected.

### Notes
- The `pydub` ffmpeg warning remains non-fatal and unrelated to the startup crash.

## 2026-04-13 — MCP Complete Toolset: 30 Tools (Perception + All Gestures)

**Session**: Expand MCP from 10 tools to 30 — full professional toolset  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Problem Solved
The MCP server had a single `execute_gesture()` catch-all for all gestures, no raw screenshot tool,
no raw UI tree tool, and no annotated screenshot. AI agents need distinct tools per gesture for
clean chain-of-thought — a `tap()` call is semantically clearer than `execute_gesture(gesture_type="tap", ...)`.

### New Tools Added (`aura_mcp_server.py`)

**Perception (3 new tools)**
- `get_screenshot()` — raw PNG screenshot, no perception pipeline, calls `GET /accessibility/screenshot`
- `get_ui_tree()` — full unfiltered accessibility tree with resourceId/hierarchy, calls `GET /device/ui-tree`
- `get_annotated_screenshot()` — auto-grabs screenshot then runs OmniParser for bounding-box annotations

**Gestures (14 new dedicated tools)**
- `tap(target, x, y)`, `long_press(target, x, y, duration_ms)`, `double_tap(target, x, y)`
- `type_text(text, auto_submit)`
- `scroll_up/down/left/right(amount)` — directional scrolls
- `scroll_to(x1, y1, x2, y2, duration_ms)` — coordinate-precise scroll
- `swipe(x1, y1, x2, y2, duration_ms)` — free-form swipe

**System buttons (6 new tools)**
- `press_back()`, `press_home()`, `press_enter()`
- `open_recent_apps()`
- `volume_up()`, `volume_down()`, `mute()`

**Private helper added**
- `_call_gesture()` — shared helper deduplicating actor.execute + event_bus.publish + error handling

### New Endpoint Added (`api_handlers/device_router.py`)
- `GET /device/ui-tree` — live request to Android via UITreeService.request_ui_tree(); returns full
  element tree. Handles validation_failed case (DRM/game apps that block accessibility). Added `import uuid`.

### Known Limitation
- `double_tap` bypasses ActorAgent (routes via HTTP `/accessibility/execute-gesture` directly)
  because `GestureType.DOUBLE_TAP` is declared in the enum but not dispatched in
  `gesture_executor._execute_single_action()` — tracked as a bug for a future fix.

---

## 2026-04-13 — MCP Device Disconnect Notification + Android Resilient Connection

**Session**: Wire device-disconnect signals into MCP tools; fix Android connection reliability  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Problem Solved
When Claude-as-brain was running a multi-step MCP task sequence and the Android device
WebSocket disconnected mid-task, `perceive_screen()` raised a raw Python `ValueError`
(not a structured dict). Claude received an unstructured exception string with no way
to know whether to retry, wait, or abort. Similarly, `watch_device_events()` never
emitted `device_disconnected` events because MCP runs in a separate process from FastAPI.

### MCP Changes (`aura_mcp_server.py`)

- **NEW tool `get_device_status()`** — HTTP `GET /device/status` to FastAPI (authoritative). Returns `{connected, device_name, screen_width, screen_height, has_screenshot, ui_elements_available}`. Call this before starting any multi-step sequence or after any `device_disconnected` error.

- **`perceive_screen()` — structured error returns** — wrapped `controller.request_perception()` in try/except. Any `ValueError` / exception matching "no device" / "not connected" keywords now returns `{"error": "device_disconnected", "connected": false, "message": "..."}` instead of raising. Other errors return `{"error": "perception_failed", ...}`.

- **`execute_gesture()` — structured error returns** — wrapped `actor.execute()` in try/except. Also catches `success=False` with disconnect-flavored error strings from the actor layer.

- **`watch_device_events()` — status polling** — now polls `GET /device/status` every 5 s alongside the in-process event queue. Detects `True→False` and `False→True` transitions and emits synthetic `device_disconnected` / `device_reconnected` events into the returned list. Fixes the cross-process gap where FastAPI's event bus never reached the MCP process.

- **`_is_device_disconnect_error(exc)`** — shared helper that checks exception message for disconnect keywords.
- **`_device_disconnected_response(tool, detail)`** — shared helper that builds the canonical `{"error": "device_disconnected", ...}` dict.
- **`_poll_device_status_once()`** — internal async helper for the watch loop.

### Android Connection Architecture (`UI/` module)

- **NEW `ConnectionManager.kt`** — `@Singleton` OkHttp-based persistent WebSocket manager with exponential backoff (1 s → 2 s → 4 s → 30 s max), 20 s PING/PONG heartbeat, silence-detection at 32 s, unlimited Channel queue (drains on reconnect). Exposes `ConnectionState` sealed class with 5 variants.

- **`AssistantForegroundService.kt`** — wired `ConnectionManager` via Hilt `@Inject`; starts on `startOverlay()` (after overlay permission); registers `SharedPreferences` listener for URL changes; stops in `onDestroy()`.

- **`BackendCommunicator.kt`** — timeouts increased to 15 s connect / 60 s read-write (was 10 s/15 s) to handle large UI trees and screenshots. `retryOnConnectionFailure = true`.

- **`AppModule.kt`** — fixed DI bug where `provideAssistantRepository` was passing 2 args to a 3-arg constructor (`connectionManager` was missing).

- **`AssistantRepositoryImpl.kt`** — exposes `connectionState: StateFlow<ConnectionState>` from `ConnectionManager` so UI can observe connection health.

---

## 2026-04-10 — MCP Phase 5: Brain-Mode Tool Expansion + web_search Bug Fix

**Session**: Add `lookup_app`, `launch_app`, `omniparser_detect`, `web_search` MCP tools; add `MCPBrainLogger`; add tap-before-type; fix `web_search` call signature  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created

- `api_handlers/perception_api.py` (NEW) — FastAPI router for OmniParser REST access. `POST /perception/omniparser-detect` takes `screenshot_b64` (optional; uses last screenshot if absent). Accesses `PerceptionController._pipeline._detector` singleton, falls back to fresh `OmniParserDetector()`. Returns `OmniParserResponse(elements_detected, detections, annotated_image_b64)`.

### Files Modified

- `api_handlers/real_accessibility_api.py` (MODIFIED) — Added `LaunchAppRequest` Pydantic model and `POST /launch-app` endpoint. Calls `real_accessibility_service.launch_app_via_intent(package_name)` which sends `{"type": "launch_app", ...}` via Android WebSocket. Distinct from gesture execution path.

- `main.py` (MODIFIED) — Registered `perception_router` at `/perception` prefix so `POST /perception/omniparser-detect` is reachable by MCP.

- `aura_mcp_server.py` (MODIFIED — major rewrite) — Added `MCPBrainLogger` class (session-scoped HTML dark-theme log + plain-text + terminal log, matching CommandLogger style). Added 4 new MCP tools:
  - `lookup_app(app_name)` — resolves human name → package via `AppInventoryManager` (file-based, safe in MCP process)
  - `launch_app(package_name)` — calls `POST /accessibility/launch-app` for intent-based launch
  - `omniparser_detect(screenshot_b64)` — calls `POST /perception/omniparser-detect`; returns SoM-labelled elements
  - `web_search(query)` — wraps `WebSearchService.search()`; returns Tavily synthesized answer string
  Added tap-before-type logic inside `execute_gesture`: when `focus_x`/`focus_y` present in params for a `type` action, auto-sends tap first then waits 300 ms.

- `wiki/mcp_build_plan.md` (MODIFIED) — Added Phase 5 section with all 6 tasks (5.1–5.6). Updated summary table with Phase 5 rows.

### Bug Fixed

**`web_search` tool — wrong `WebSearchService.search()` call signature**

The tool was calling `svc.search(query, max_results=...)` and treating the return value as a dict with `results`/`answer` keys. The actual signature is:

```python
async def search(self, query: str, topic: str = "general") -> str
```

It returns a pre-synthesized `str` answer. Fixed: now calls `answer = await svc.search(query)` and returns `answer` directly in the `answer` field; `results` list is always empty.

### Why

Voice-controlled Android automation benefits greatly from package-level app launching (faster than UI nav), device inventory lookup (avoiding hardcoded package names), on-demand visual parsing (web-view or dynamic UIs), and web search (unfamiliar app layouts). The MCPBrainLogger gives the same structured observability as the AURA HTML logs for MCP-side orchestration.

---

## 2026-04-10 — Duplicate Route Cleanup + Execution Log Surfacing

**Session**: Remove duplicate accessibility API router registration; surface HTML log path in /api/v1/execute response  
**Branch**: feature/mcp-server

### Files Modified

- `main.py` (MODIFIED)
  - Removed duplicate `app.include_router(accessibility_router, prefix=f"{API_PREFIX}/accessibility")` — the Android-facing `/accessibility/*` registration is kept; the redundant versioned copy is gone.

- `aura_graph/graph.py` (MODIFIED)
  - `_finalize_and_upload()` now stores `result["local_log_path"]` with the path to the HTML log file, alongside the existing GCS `log_url`.

- `api/execute.py` (MODIFIED)
  - `ExecuteResponse` gains `log_path: Optional[str]` field.
  - `execute_task()` now returns `log_path=result.get("local_log_path")` so callers see exactly which HTML log file was written for their execution.

### Why

Every `/api/v1/execute` call already triggered HTML log generation via `_finalize_and_upload`; the local path was just never propagated back to the caller. Now it is.

---

## 2026-04-10 — MCP Bootstrap Fix + Smoke Validation

**Session**: Fix MCP startup import failure, validate MCP module/server startup, and run granular tool smoke tests  
**Branch**: feature/mcp-server  
**Author**: GitHub Copilot (GPT-5.3-Codex)

### Files Modified

- `config/settings.py` (MODIFIED)
	- Added backward-compatible module export for `settings` via a **lazy proxy** backed by `get_settings()`.
	- This restores compatibility for imports like `from config.settings import settings` (used by `aura_mcp_server.py`) without eager import-time settings initialization.
- `wiki/services/config.md` (MODIFIED)
	- Updated `last_verified` to `2026-04-10`.
	- Documented lazy `settings` proxy behavior.

### Validation Performed

- MCP import smoke: `python -c "import aura_mcp_server; print('MCP_IMPORT_OK')"` → **PASS**
- Settings compatibility smoke: `settings.mcp_server_name == get_settings().mcp_server_name` → **PASS**
- MCP process startup smoke: `python aura_mcp_server.py` boots without import-time crash → **PASS**
- Tool-level smoke script:
	- `validate_action('open_app', 'Spotify')` returned allowed
	- `execute_gesture('open_app', 'Spotify')` and `perceive_screen()` returned device-not-connected in that standalone MCP process context

### Important Note

The current MCP process and the FastAPI process do not share in-memory `real_accessibility_service` state; running `aura_mcp_server.py` standalone can report device-not-connected even when another process has device state. This is an architecture/runtime integration concern, not a bootstrap import failure.

---

## 2026-04-10 — MCP Phase 4 Complete (Open Source Packaging)

**Session**: Implement Phase 4 MCP — quickstart.md, setup.sh, README MCP section  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created / Modified

- `quickstart.md` (NEW) — 8-step setup guide: prerequisites, clone+install, API keys, device connection, companion app, backend startup, voice command demo, Claude Code MCP config. Includes MCP tools table and troubleshooting.
- `setup.sh` (NEW) — One-command setup: `pip install`, `cp -n .env.example .env`, prints next steps.
- `README.md` (MODIFIED) — Added `## MCP Integration` section (MCP server startup, `~/.claude.json` config snippet, 5-tool table, Style A/B explanation, agent compatibility table for Claude Code / Copilot / Cursor / Windsurf / REST). Added `POST /api/v1/execute` to REST API table. Added MCP Integration to Table of Contents.
- `wiki/mcp_build_plan.md` (MODIFIED) — Tasks 4.1, 4.2, 4.3 status → DONE. Phase 4 checklist checked. Summary table updated.

### All MCP Phases Status

- Phase 1: DONE (perceive_screen, execute_gesture, validate_action, watch_device_events, MCP settings)
- Phase 2: DONE (event_bus, DeviceEvent pub/sub, watch_device_events real impl, TaskState fields)
- Phase 3: DONE (execute_android_task, POST /api/v1/execute, 15 tests)
- Phase 4: DONE (quickstart.md, setup.sh, README MCP section)

---

## 2026-04-10 — MCP Phase 3 Complete

**Session**: Implement Phase 3 MCP — `execute_android_task()` black-box tool + `POST /api/v1/execute` REST fallback  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created / Modified

- `aura_mcp_server.py` (MODIFIED — Task 3.1) — Added `_mcp_graph` singleton + `_get_mcp_graph()` lazy compiler (calls `compile_aura_graph(MemorySaver())` on first invocation). Added `execute_android_task(utterance)` MCP tool: calls `execute_aura_task_from_text`, maps result, publishes `task_executed` DeviceEvent.
- `api/execute.py` (NEW — Task 3.2) — REST fallback endpoint. `POST /api/v1/execute` with `ExecuteRequest(command, source)` → `ExecuteResponse(success, response_text, steps_taken, error)`. Reads `graph_app` from `request.app.state`.
- `main.py` (MODIFIED — Task 3.2) — Added `execute` to `from api import ...` line; registered `execute.router` with `prefix=API_PREFIX, tags=["Execute"]`.
- `tests/test_execute_endpoint.py` (NEW) — 15 unit tests for result-mapping logic; all passing. Tests logic inline (no FastAPI import — same constraint as test_event_bus.py avoiding `mcp` package).
- `wiki/mcp_build_plan.md` (MODIFIED) — Tasks 3.1 + 3.2 status → DONE with completion notes. Phase 3 checklist all checked.

### Critical Interface Correction

Build plan documented `run_aura_task(utterance)` as Phase 3 entry point — **that signature does not exist**.  
Real entry point: `execute_aura_task_from_text(app, text_input, thread_id, track_workflow)` — same as `adk_agent.py`.

### Tasks completed

3.1 `execute_android_task()` MCP tool | 3.2 `api/execute.py` REST endpoint + `main.py` registration

### Remaining: Phase 4

Open-source packaging: `quickstart.md`, `setup.sh`, README `## Google Cloud Architecture` section.

---

## 2026-04-10 — MCP Phase 2 Complete

**Session**: Implement Phase 2 MCP — event bus, gesture publishing, real watch_device_events, TaskState fields  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created / Modified

- `services/event_bus.py` (NEW — Task 2.1) — `AuraEventBus` async pub/sub using `dict[str, asyncio.Queue]` fan-out. `DeviceEvent` dataclass. `get_event_bus()` module singleton. `subscriber_count` property.
- `aura_mcp_server.py` (MODIFIED — Tasks 2.2 + 2.3) — `execute_gesture()` now publishes `DeviceEvent` after every gesture. `watch_device_events()` stub replaced with real `asyncio.wait_for` deadline loop; `finally: bus.unsubscribe()` prevents orphaned queues.
- `aura_graph/state.py` (MODIFIED — Task 2.4) — Added `command_source: Optional[str]` and `client_id: Optional[str]` to `TaskState` TypedDict, after `web_search_result`.
- `wiki/mcp_build_plan.md` (MODIFIED) — Tasks 2.1–2.4 status → DONE, completion notes filled in. Phase 2 checklist all checked.

### Tasks completed

2.1 `services/event_bus.py` | 2.2 gesture publish in `execute_gesture` | 2.3 real `watch_device_events` | 2.4 `TaskState` fields

### Next session: Phase 2 tests + Phase 3

Write `tests/test_event_bus.py` covering: publish/subscribe, multiple subscribers fan-out, timeout behavior, unsubscribe cleanup. Then Phase 3: `execute_android_task()` black-box MCP tool + REST fallback endpoint.

---

## 2026-04-10 — MCP Phase 1 Complete

**Session**: Implement Phase 1 MCP server — all 4 tools + settings + tests  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created / Modified

- `aura_mcp_server.py` (NEW) — Full MCP server with 4 tools: `perceive_screen`, `execute_gesture`, `validate_action`, `watch_device_events`. Lazy singletons `_actor`/`_policy` via helper fns. Module docstring with startup/config docs.
- `config/settings.py` (MODIFIED) — Added `mcp_enabled: bool` and `mcp_server_name: str` Pydantic fields.
- `.env.example` (MODIFIED) — Added MCP section with `MCP_ENABLED=true` and `MCP_SERVER_NAME=aura`.
- `tests/test_mcp_tools.py` (NEW) — 7 unit tests covering all 4 tools with mocked dependencies.
- `wiki/mcp_build_plan.md` (MODIFIED) — Tasks 1.0–1.8 status → DONE, completion notes filled in.

### Interface Correction (critical — update build plan interface contracts)

Build plan documented `PolicyEngine.check(action_type, target, context={})`.  
**Real interface**: `PolicyEngine.evaluate(ActionContext(action_type=..., target=...)) → PolicyDecision`  
`PolicyDecision` has `.allowed`, `.reason`, `.requires_confirmation` (not just `.allowed`/`.reason`).  
The plan's `check()` method does not exist. Future sessions must read `services/policy_engine.py` before calling PolicyEngine.

### Tasks completed

1.0 Pre-done (mcp==1.27.0 already in requirements.txt) | 1.1 aura_mcp_server.py created | 1.2 perceive_screen() | 1.3 execute_gesture() | 1.4 validate_action() | 1.5 watch_device_events() stub | 1.6 settings + .env.example | 1.7 startup docs | 1.8 tests

### Next session: Phase 2

Start at **Task 2.1**: Create `services/event_bus.py` (`AuraEventBus` class, `DeviceEvent` dataclass, pub/sub pattern). Then wire events from `execute_gesture` (Task 2.2), implement real `watch_device_events` (Task 2.3), and add `command_source`/`client_id` to `TaskState` (Task 2.4).

---

## 2026-04-09 — Agent Count Correction (9 → 8)

**Session**: Agent audit — removed phantom "9th agent" from all documentation  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### What changed

- `CLAUDE.md` — Corrected all 4 occurrences of "9 agents" to "8 agents". Removed `visual_locator.py` from the agent list. Added note clarifying `VLMSelector` is a perception component, not an agent.
- `wiki/agents/overview.md` — Changed heading to "The 8 Agents". Removed `VisualLocator` (#9) from table. Removed `→ VisualLocator` from interaction map. Updated Per-Agent Pages to link to `../perception/vlm_selector.md` instead.
- `wiki/agents/visual_locator.md` — **Deleted**. Content was about `perception/vlm_selector.py`, not an agent.
- `wiki/perception/vlm_selector.md` — **Created**. Proper home for VLMSelector docs (SelectionResult, selection prompt, SoM rationale, fallback chain).
- `wiki/index.md` — Removed `agents/visual_locator.md` pointer. Added `perception/vlm_selector.md` under Perception Pipeline section.
- `wiki/mcp_build_plan.md` — Updated Critical Invariant #6 from "9 agents" to "8 agents".

### Root cause
`agents/visual_locator.py` never existed. The actual implementation is `perception/vlm_selector.py` (VLMSelector), a perception pipeline component called internally by `PerceiverAgent`. This phantom #9 was introduced when the wiki was first generated and propagated to CLAUDE.md.

### Confirmed agent list (8 total, all in `agents/`)
`CommanderAgent`, `PlannerAgent`, `Coordinator`, `PerceiverAgent`, `ActorAgent`, `ResponderAgent`, `ValidatorAgent`, `VerifierAgent`

---

## 2026-04-09 — MCP Build Plan Created

**Session**: Strategic planning + solid build plan for MCP server  
**Branch**: feature/mcp-server  
**Author**: Claude Code (Sonnet 4.6)

### Files Created / Updated
- `wiki/mcp_build_plan.md` (NEW) — Complete task-by-task build plan for MCP server. 18 tasks across 4 phases. Includes session resumption protocol, real interface contracts from `perception_controller.py` and `actor_agent.py`, pre-empted failure modes, and per-task completion checklists.
- `wiki/index.md` — Added pointer to `mcp_build_plan.md` under MCP section
- `CLAUDE.md` — Added "Active Development: MCP Server" section pointing to build plan so all future sessions find it at session start

### Decisions
- Build plan is the single source of truth; sessions update task statuses in-place
- Interface contracts embedded in plan to prevent re-deriving from source on every session
- `watch_device_events()` ships as stub in Phase 1; real implementation waits for Phase 2 event bus

---

## 2026-04-07 — Initial Wiki Generation

**Session**: Full codebase read and wiki brain build  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### Pages Created
- `index.md` — Table of contents with all wiki pages
- `overview.md` — System overview, request lifecycle, tri-provider architecture
- `decisions.md` — Architectural decisions and rationale
- `log.md` — This file
- `aura_graph/graph.md` — LangGraph assembly and entry points
- `aura_graph/state.md` — TaskState TypedDict and reducers
- `aura_graph/edges.md` — Conditional routing and retry ladder
- `aura_graph/nodes.md` — Node implementations
- `agents/overview.md` — 9 agents overview and interaction map
- `agents/coordinator.md` — Main coordination loop
- `agents/perceiver.md` — Screen perception
- `agents/actor.md` — Zero-LLM gesture execution
- `agents/commander.md` — Intent parsing
- `agents/planner.md` — Goal decomposition
- `agents/responder.md` — Response generation
- `agents/validator.md` — Rule-based validation
- `agents/verifier.md` — Post-action verification
- `agents/visual_locator.md` — Set-of-Marks VLM selection
- `perception/pipeline.md` — Three-layer perception pipeline
- `services/llm.md` — LLM tri-provider service
- `services/vlm.md` — VLM service and SoM pipeline
- `services/safety.md` — Prompt Guard 2 and OPA engine
- `services/reflexion.md` — Verbal RL lesson system
- `services/hitl.md` — Human-in-the-Loop service
- `services/config.md` — Settings and configuration
- `api/routes.md` — All HTTP and WebSocket routes
- `api/handlers.md` — WebSocket handler details
- `adk.md` — ADK agent, Gemini Live, GCS uploader
- `backlog.md` — P1–P3 improvement backlog

### Key Facts Discovered
- `agents/visual_locator.py` does not exist at that path — VLM selection is in `perception/vlm_selector.py`
- `DEFAULT_VLM_PROVIDER` defaults to `"groq"` in settings (not `"gemini"` as required for hackathon submission)
- `AuraQueryEngine` (`query_engine` in main.py) is a secondary streaming path — falls back to `execute_aura_task_from_streaming()` when disabled
- Thinking-content filter in `adk_streaming_server.py` strips chain-of-thought headers from Gemini 2.5 transcripts
- GCS upload uses `asyncio.get_event_loop().run_in_executor()` pattern (sync SDK wrapped async)

---

## 2026-04-08 — Mid-Task Web Search Tool

**Session**: Expose web_search as RSG-callable mid-task tool  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

**New capability**: The RSG can now emit `action_type: "web_search"` during task execution. The coordinator intercepts it, calls `WebSearchService.search(target)`, and injects the result into `running_screen_context` for the next RSG call. No gesture is executed.

**Files modified**:
- `config/gesture_tools.py` — Added `"web_search"` to `GESTURE_REGISTRY` with `needs_target=False`, `needs_coords=False`, `needs_perception=False`. Auto-appears in RSG's AVAILABLE ACTIONS block via `get_rsg_actions_prompt()`.
- `aura_graph/state.py` — Added `web_search_result: Optional[str]` field to `TaskState`.
- `agents/coordinator.py` — Added dispatch interception for `action_type == "web_search"` between the HITL block and ActorAgent. Handles timeout (8 s), service unavailable, and exceptions gracefully.
- `tests/test_web_search_tool.py` — 20 new tests: registry flags, RSG prompt inclusion, no-target set membership, TaskState field existence, coordinator dispatch (happy path, actor not called, result injection, context preservation, timeout, unavailable).

### Why
Previously `web_search` was only usable as a full-task intent (graph-level routing in `edges.py`). Compound tasks like "find a pizza place and open it in Maps" required web context mid-execution — the agent had no way to look up information once the task had started. This change adds that capability.

### Key architectural point
Result flows through `running_screen_context` (same mechanism as HITL answers), not as a new prompt injection path. This keeps the RSG's information surface consistent — web facts appear as "things observed about the current situation" rather than a special external data field.

### Distinction from planning-time `_web_hints`
`_web_hints` is a silent Tavily call during planning (search_for_guide). The new `web_search` action is RSG-driven, mid-task, and user/agent-visible via step_memory.

---

## 2026-04-08 — Gemini Live Latency Patch

**Session**: Investigate and reduce `/ws/live` transcript/response delays (reported ~52s)  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

- `adk_streaming_server.py`
	- Retuned server VAD to lower turn-end latency:
		- `prefix_padding_ms`: `350 -> 160`
		- `silence_duration_ms`: `1200 -> 650`
		- enabled high start/end sensitivity when available.
	- Added explicit client end-of-turn bridging:
		- on `{"type":"end_turn"}` now attempts `live_queue.send_audio_stream_end()` first,
		- falls back to `live_queue.send_activity_end()` when supported.
	- Added per-turn latency instrumentation logs for:
		- first inbound audio,
		- first input transcription,
		- first model audio,
		- turn complete,
		- derived end-to-end deltas.
	- Added guard to ignore `end_turn` when no active turn exists.
	- Hardened metrics reset to avoid clobbering a newly started turn during async flush.

- `UI/app/src/main/java/com/aura/aura_ui/voice/GeminiLiveController.kt`
	- Disabled periodic `ui_tree` sends in Gemini Live streaming loop to reduce WS payload and serialization overhead.
	- Removed now-unused `UI_TREE_INTERVAL_MS` and `captureAndSendUiTree()` code.

- `README.md`
	- Updated Gemini Live VAD docs to match runtime settings.

### Why

The prior pipeline relied mostly on server VAD closure and sent redundant context payloads. In practice this can delay turn finalization and transcript visibility. Explicit end-turn bridging plus lighter upstream traffic and tighter VAD settings reduces avoidable buffering/wait.

---

## 2026-04-08 — Karpathy Wiki Alignment (Frontmatter + Operations)

**Session**: Implement Karpathy LLM Wiki pattern for AURA brain  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

**New: `CLAUDE.md` — Three wiki operations section**
Added formal definitions for three wiki operations after the Wiki structure section:
- **Query** (before coding): check `last_verified`, run `git log --since=`, update stale pages first
- **Ingest** (after code changes): find pages by `source_files`, update content, bump `last_verified`
- **Lint** (health check): ORPHAN/STALE/UNLISTED/MISSING_FRONTMATTER report
Also added wiki page schema block (YAML frontmatter format).

**New: `scripts/wiki_lint.py`**
Python script implementing the Lint operation. Detects:
- ORPHAN: source file no longer exists on disk
- STALE: source file modified after `last_verified` (git log based, mtime fallback)
- UNLISTED: page not referenced in `wiki/index.md`
- MISSING_FRONTMATTER: page lacks the YAML header block
Flags: `--fix-dates` bumps stale `last_verified` to today. Meta pages (index.md, log.md, etc.) exempt from source_files requirement.

**New: `.claude/skills/wiki-lint.md`**
Claude skill file giving step-by-step instructions for running lint and acting on each issue type.

**All 28 wiki pages — YAML frontmatter added**
Every wiki page now has a frontmatter block:
```yaml
---
last_verified: 2026-04-08
source_files: [path/to/source.py]
status: current
---
```
Pages covered: all meta pages (index, log, overview, decisions, backlog, adk), all 10 agent pages, all 4 aura_graph pages, perception/pipeline, 6 services pages, 2 api pages.

### Why
The wiki existed but had no freshness metadata — no way to know at session start whether a page was trustworthy or stale. The Karpathy pattern adds `last_verified` + `git log` checks so Claude can verify wiki accuracy in seconds instead of re-reading source files from scratch. This saves tokens and prevents acting on stale documentation.

---

## 2026-04-09 — MCP Architecture & Open-Source Strategy Planning

**Session**: Advisory Q&A on how to scale AURA for public open-source release  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

**New wiki page: `wiki/mcp_architecture.md`**
Full planning document covering the strategic pivot from hackathon demo to open-source
Android automation platform with multi-agent MCP support.

**`wiki/index.md`** — added MCP & Open-Source Strategy section pointing to new page.

### Decisions documented (M1–M8)

| # | Decision |
|---|----------|
| M1 | Keep Groq/Gemini for voice path — latency-sensitive, Claude unavailable on phone |
| M2 | Claude as brain for MCP path (Style B granular tools) — best reasoner, no extra cost |
| M3 | Expose both MCP styles simultaneously — Style A for universal compat, Style B for power |
| M4 | Event bus broadcasts all actions to all subscribers — collaborative human+AI loop |
| M5 | Single task queue, voice commands get priority — one device, one task at a time |
| M6 | REST fallback alongside MCP — reaches agents without MCP protocol support |
| M7 | Build Phase 1 (MCP granular tools) first — voice already works, MCP is the new value |
| M8 | SoM perception pipeline unchanged — it's the architectural moat, LLMs change around it |

### Architecture summary

Two input paths converge on one execution pipeline:
- **Voice path** (phone → /ws/audio): Groq handles all reasoning. Target < 2s latency.
- **MCP path** (Claude Code / agents): Claude handles all reasoning via granular tools.
  Your server becomes a pure device bridge. Zero Groq costs for this path.
- **HTTP path** (other agents): Groq handles execution, calling agent handles outer reasoning.

Commands are NOT sent via ADB — they go over WebSocket to the Android companion app (/ws/device).

### Key insight recorded

AURA's moat is the Set-of-Marks pipeline (YOLO detection → element labels → agent picks label).
This makes any LLM reliable at UI selection because it never predicts raw coordinates.
The MCP architecture leaves this pipeline intact and unchanged regardless of which brain is used.

### Build phases

1. MCP granular tools (perceive_screen, execute_gesture, validate_action, watch_device_events)
2. Event broadcast layer (shared event bus, result router)
3. Black box tool + REST fallback (execute_android_task, /api/v1/execute)
4. Open-source packaging (setup.sh, quickstart.md, demo GIF, README refactor)
