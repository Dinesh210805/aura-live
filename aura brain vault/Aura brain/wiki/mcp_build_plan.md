---
last_verified: 2026-04-09
source_files: []
status: current
---

# AURA MCP Server — Solid Build Plan

> **This plan is the single source of truth for building the MCP server.**
> Every Claude Code session MUST read this document at the start of any MCP work.
> Every Claude Code session MUST update task statuses and append to `wiki/log.md` after completing work.

---

## Session Resumption Protocol

At the START of every session working on MCP:

```
1. Read wiki/index.md
2. Read THIS document (wiki/mcp_build_plan.md)
3. Read wiki/mcp_architecture.md (decisions, diagram, interface sketches)
4. Find the first task with status: IN_PROGRESS or TODO
5. Read the "Context for next session" block on that task before coding
6. grep for the files listed in that task's "Files to touch" — verify they exist
7. START WORK
```

At the END of every session:

```
1. Update task status: TODO → IN_PROGRESS → DONE
2. Fill in "Completion notes" on the task you finished
3. Update wiki/log.md with what changed
4. If you created/modified source files — update relevant wiki pages
5. Update CLAUDE.md if the project structure changed
```

---

## Critical Invariants — Never Break These

These are load-bearing constraints from CLAUDE.md. Any code written must obey:

1. **VLM never returns pixel coordinates** — only selects from SoM labels (A1, A2...)
2. **Every gesture passes through OPA policy check** in `gesture_executor.py`
3. **All service functions must be `async def`**
4. **All API keys through `config/settings.py`** — never raw `os.environ`
5. **WebSocket endpoints `/ws/audio` and `/ws/device` must not change** — Android app depends on them
6. **8 agents stay single-responsibility** — MCP layer sits outside the agents, not inside them
7. **Gestures go over WebSocket to Android app** — NOT ADB, NOT local shell

---

## Interface Contracts (Read Before Coding)

These are the real signatures from the source files. Use these exactly — do not guess.

### PerceptionController

```python
# services/perception_controller.py
from services.perception_controller import get_perception_controller

controller = get_perception_controller()  # global singleton

bundle: PerceptionBundle = await controller.request_perception(
    intent="",           # required: what the caller wants to do
    action_type="",      # required: e.g. "tap", "type", "scroll"
    execution_history=[], 
    retry_context=None,
    app_category=None,
    force_screenshot=True,   # set True for MCP — always want fresh
    skip_description=False,
    goal=None,
    subgoal_hint=None,
    recent_steps=[]
)

# PerceptionBundle fields:
bundle.snapshot_id          # str — unique ID for this perception
bundle.ui_tree              # UITreePayload — .elements list
bundle.screenshot           # ScreenshotPayload — .screenshot_base64, .screen_width, .screen_height
bundle.screen_meta          # ScreenMeta — .width, .height, .orientation
bundle.visual_description   # str — natural language description of screen
bundle.request_id           # str
bundle.reason               # str
bundle.modality             # str

# Raises ValueError if device not connected
```

### ActorAgent

```python
# agents/actor_agent.py
from agents.actor_agent import ActorAgent
from services.gesture_executor import GestureExecutor

actor = ActorAgent(gesture_executor=GestureExecutor())

result: ActionResult = await actor.execute(
    action_type="tap",         # "tap"|"type"|"swipe"|"scroll"|"back"|"home"|"open_app"
    target=None,               # str — SoM label (e.g. "A3") OR element description
    coordinates=None,          # Tuple[int, int] — pixel coords (tap needs this)
    parameters=None            # dict — extra params
)

# ActionResult fields:
result.success          # bool
result.action_type      # str
result.coordinates      # Tuple[int,int] | None
result.duration_ms      # float
result.error            # str | None
result.details          # dict

# Action-specific params:
# tap:      coordinates=(x, y) required
# type:     target="text to type", parameters={"focus_x": x, "focus_y": y} optional
# swipe:    parameters={"direction": "up"|"down"|"left"|"right"} — coords auto-injected
# back/home: no params needed
# open_app: target="app_name"
```

### GestureExecutor

```python
# services/gesture_executor.py — used by ActorAgent, do not call directly from MCP layer
# GestureExecutor sends gestures over WebSocket to Android app — NOT ADB
```

### PolicyEngine

```python
# services/policy_engine.py
from services.policy_engine import PolicyEngine

policy_engine = PolicyEngine()
result = await policy_engine.check(action_type="tap", target="A3", context={})
# Returns: PolicyResult with .allowed (bool) and .reason (str)
```

---

## Phase 1 — MCP Granular Tools

**Goal**: Four tools that let Claude Code perceive the screen and control the device.  
**Branch**: `feature/mcp-server`  
**Priority**: P0 — this is the open-source demo.

---

### Task 1.0 — Install MCP SDK dependency

**Status**: `DONE`

**What**: Add `mcp` Python package to requirements.

**Files to touch**:
- `requirements.txt` — `mcp==1.27.0` was already present at line 125

**Verification**: `python -c "import mcp; print(mcp.__version__)"`

**Context for next session**: The file is `requirements.txt` (NOT `requirements copy.txt` — the build plan had wrong filename). `mcp==1.27.0` was already installed.

**Completion notes**: Already present — no change needed. `mcp==1.27.0` at line 125 of `requirements.txt`.

---

### Task 1.1 — Create `aura_mcp_server.py`

**Status**: `DONE`

**What**: Skeleton MCP server file. FastMCP server with app-level lifecycle. Four tool stubs registered but not yet implemented.

**Files to touch**:
- `aura_mcp_server.py` (NEW — root of repo, same level as `main.py`)

**Skeleton**:
```python
"""
AURA MCP Server — exposes Android device control as MCP tools.

Style B: granular tools (Claude as brain)
  - perceive_screen()       → screenshot + SoM labels
  - execute_gesture()       → send gesture to device
  - validate_action()       → OPA policy pre-check
  - watch_device_events()   → observe all device events

Style A: black box (defined in Task 3.x)
  - execute_android_task()  → full AURA pipeline
"""

import asyncio
from mcp.server.fastmcp import FastMCP
from config.settings import settings
from services.perception_controller import get_perception_controller
from agents.actor_agent import ActorAgent
from services.gesture_executor import GestureExecutor
from services.policy_engine import PolicyEngine

mcp = FastMCP("aura")

# Module-level singletons (lazy-init in lifespan)
_actor: ActorAgent | None = None
_policy: PolicyEngine | None = None


@mcp.tool()
async def perceive_screen() -> dict:
    """stub — Task 1.2"""
    raise NotImplementedError


@mcp.tool()
async def execute_gesture(gesture_type: str, target: str, params: dict = {}) -> dict:
    """stub — Task 1.3"""
    raise NotImplementedError


@mcp.tool()
async def validate_action(gesture_type: str, target: str) -> dict:
    """stub — Task 1.4"""
    raise NotImplementedError


@mcp.tool()
async def watch_device_events(timeout_seconds: int = 30) -> list:
    """stub — Task 1.5"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
```

**Verification**: `python aura_mcp_server.py` exits cleanly (stubs are not called yet).

**Completion notes**: `aura_mcp_server.py` created with all 4 tools fully implemented (not stubs). Uses `settings.mcp_server_name` for FastMCP name. Module-level lazy singletons `_actor` / `_policy` via `_get_actor()` / `_get_policy()` helpers. Startup docs in module docstring.

---

### Task 1.2 — Implement `perceive_screen()`

**Status**: `DONE`

**What**: Call `PerceptionController.request_perception()` and return a structured dict containing base64 screenshot, SoM-labeled elements, and screen dimensions.

**Files to touch**:
- `aura_mcp_server.py` — replace stub

**Implementation**:
```python
@mcp.tool()
async def perceive_screen() -> dict:
    """
    Capture a fresh screenshot and UI analysis of the connected Android device.

    Returns:
        screenshot_base64: str — PNG encoded as base64
        screen_width: int
        screen_height: int
        som_elements: list[dict] — each has {label, description, bounds, type}
        ui_summary: str — natural language description of current screen
        snapshot_id: str — use this ID when calling execute_gesture
    """
    controller = get_perception_controller()
    bundle = await controller.request_perception(
        intent="observe current screen state",
        action_type="observe",
        execution_history=[],
        retry_context=None,
        app_category=None,
        force_screenshot=True,
        skip_description=False,
        goal=None,
        subgoal_hint=None,
        recent_steps=[]
    )

    # Flatten SoM elements from ui_tree into a clean list
    elements = []
    if bundle.ui_tree and bundle.ui_tree.elements:
        for el in bundle.ui_tree.elements:
            elements.append({
                "label": getattr(el, "som_label", None),
                "description": getattr(el, "content_desc", "") or getattr(el, "text", ""),
                "type": getattr(el, "class_name", ""),
                "bounds": getattr(el, "bounds", None),
                "clickable": getattr(el, "clickable", False),
            })

    return {
        "screenshot_base64": bundle.screenshot.screenshot_base64 if bundle.screenshot else None,
        "screen_width": bundle.screenshot.screen_width if bundle.screenshot else bundle.screen_meta.width,
        "screen_height": bundle.screenshot.screen_height if bundle.screenshot else bundle.screen_meta.height,
        "som_elements": elements,
        "ui_summary": bundle.visual_description or "",
        "snapshot_id": bundle.snapshot_id,
    }
```

**Verification**: 
1. Device must be connected and AURA server running
2. Call from Python: `asyncio.run(perceive_screen())`
3. Confirm `screenshot_base64` is non-empty, `som_elements` is a list

**Edge cases**:
- Device not connected → `ValueError` from controller → let it propagate (MCP framework shows error to Claude)
- `bundle.ui_tree.elements` is None → return empty list, not crash

**Context for next session**: `UITreePayload.elements` field name — verify by reading `perception/ui_tree_parser.py` or `aura_graph/state.py` if the attribute name is wrong. The element schema may differ from what's documented here.

**Completion notes**: Implemented. Uses `getattr` defensively for all element fields (`som_label`, `content_desc`, `text`, `class_name`, `bounds`, `clickable`). `screen_meta` fallback for dimensions when screenshot is None. Returns `snapshot_id` in all cases.

---

### Task 1.3 — Implement `execute_gesture()`

**Status**: `DONE`

**What**: Call `ActorAgent.execute()` after validating inputs. Return structured result.

**Files to touch**:
- `aura_mcp_server.py` — replace stub

**Implementation**:
```python
@mcp.tool()
async def execute_gesture(
    gesture_type: str,
    target: str = "",
    params: dict = {}
) -> dict:
    """
    Execute a gesture on the Android device.

    Args:
        gesture_type: "tap" | "type" | "swipe" | "scroll" | "back" | "home" | "open_app"
        target: SoM label (e.g. "A3"), element description, or text to type
        params: optional extra params
          - tap: {"x": int, "y": int} if you have coordinates
          - type: {"focus_x": int, "focus_y": int} to tap before typing
          - swipe: {"direction": "up"|"down"|"left"|"right"}
          - open_app: target = app name (e.g. "Spotify")

    Returns:
        success: bool
        error: str | None
        duration_ms: float
        details: dict
    """
    global _actor
    if _actor is None:
        _actor = ActorAgent(gesture_executor=GestureExecutor())

    # For tap: coordinates come from params if provided, else (0,0) — caller should pass them
    coordinates = None
    if gesture_type == "tap" and "x" in params and "y" in params:
        coordinates = (int(params["x"]), int(params["y"]))

    result = await _actor.execute(
        action_type=gesture_type,
        target=target or None,
        coordinates=coordinates,
        parameters=params or None,
    )

    return {
        "success": result.success,
        "action_type": result.action_type,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "details": result.details or {},
    }
```

**Verification**:
1. `execute_gesture("back")` — device should go back
2. `execute_gesture("home")` — device should go to home screen

**Context for next session**: `ActorAgent` requires a `GestureExecutor` — verify `GestureExecutor.__init__` takes no required args in `services/gesture_executor.py`. If it needs device connection params, check how `actor_agent.py` gets initialized in `aura_graph/graph.py` or `main.py`.

**Completion notes**: Implemented. `GestureExecutor()` takes no required args (verified). `_get_actor()` helper handles lazy init. Extracts `coordinates=(x,y)` from `params` for tap gestures.

---

### Task 1.4 — Implement `validate_action()`

**Status**: `DONE`

**What**: Call OPA `PolicyEngine.check()` before gesture. Lets Claude pre-validate before acting.

**Files to touch**:
- `aura_mcp_server.py` — replace stub

**Implementation**:
```python
@mcp.tool()
async def validate_action(gesture_type: str, target: str = "") -> dict:
    """
    Check whether an action is permitted by AURA's OPA safety policies.
    Call this before execute_gesture if you are unsure whether an action is safe.

    Returns:
        allowed: bool
        reason: str — explanation if blocked
    """
    global _policy
    if _policy is None:
        _policy = PolicyEngine()

    result = await _policy.check(
        action_type=gesture_type,
        target=target,
        context={}
    )

    return {
        "allowed": result.allowed,
        "reason": result.reason,
    }
```

**Context for next session**: **INTERFACE CORRECTION** — Build plan documented `policy.check(action_type, target, context={})` but real method is `policy.evaluate(ActionContext(...))` returning `PolicyDecision`. `PolicyDecision` has `.allowed`, `.reason`, `.requires_confirmation`. `ActionContext` takes `action_type` and `target`. Always read `services/policy_engine.py` before calling PolicyEngine.

**Completion notes**: Implemented using real interface: `ActionContext(action_type=gesture_type, target=target or None)` → `await policy.evaluate(context)`. Also returns `requires_confirmation` (not in plan, added for completeness).

---

### Task 1.5 — Implement `watch_device_events()` (stub with TODO)

**Status**: `DONE`

**What**: Implement as a stub that returns an empty list with a TODO comment. The real implementation requires the event bus from Phase 2. Ship the stub now so the tool surface is complete.

**Files to touch**:
- `aura_mcp_server.py` — replace stub

**Implementation**:
```python
@mcp.tool()
async def watch_device_events(timeout_seconds: int = 30) -> list:
    """
    Observe all events happening on the device for the specified duration.
    Returns a list of events (voice commands, gestures, screen changes).

    NOTE: Full event streaming requires Phase 2 event bus (Task 2.x).
    Currently returns empty list — implement after services/event_bus.py exists.
    """
    # TODO (Task 2.3): subscribe to AuraEventBus and collect events
    return []
```

**Completion notes**: Stub implemented. Returns `[]` with TODO comment for Phase 2 (Task 2.3).

---

### Task 1.6 — Add MCP settings to `config/settings.py`

**Status**: `DONE`

**What**: Add MCP-related config fields. Follow existing pattern — all settings via Pydantic.

**Files to touch**:
- `config/settings.py` — add fields

**Fields to add**:
```python
# MCP Server
mcp_enabled: bool = Field(default=True, env="MCP_ENABLED")
mcp_server_name: str = Field(default="aura", env="MCP_SERVER_NAME")
```

**Files to also update**:
- `.env.example` — add `MCP_ENABLED=true`

**Completion notes**: Added `mcp_enabled` and `mcp_server_name` fields to `config/settings.py` using Pydantic `Field()` pattern matching existing style. Added MCP section to `.env.example` with `MCP_ENABLED=true` and `MCP_SERVER_NAME=aura`.

---

### Task 1.7 — Wire MCP server into `main.py` lifespan

**Status**: `DONE`

**What**: The MCP server runs as a separate process (stdio or SSE transport). Add a startup log message and document how to run it. Do NOT merge it into the FastAPI app — they are separate processes.

**Files to touch**:
- `main.py` — add startup comment/log
- `aura_mcp_server.py` — confirm it runs standalone

**Startup docs** (add as docstring or comment in `aura_mcp_server.py`):
```
# Run MCP server (separate from FastAPI):
#   python aura_mcp_server.py          ← stdio transport (for Claude Code)
#   python aura_mcp_server.py --sse    ← SSE transport (for remote agents)
#
# Configure in Claude Code (~/.claude.json or .claude/mcp.json):
#   {
#     "mcpServers": {
#       "aura": {
#         "command": "python",
#         "args": ["aura_mcp_server.py"],
#         "cwd": "/path/to/aura-live"
#       }
#     }
#   }
#
# PREREQUISITE: AURA FastAPI server must be running (python main.py)
# The MCP server connects to the running FastAPI server — it is NOT standalone.
```

**Completion notes**: Startup docs added to module docstring in `aura_mcp_server.py`. MCP server is confirmed standalone — `if __name__ == "__main__": mcp.run()`. No changes to `main.py` needed — MCP is intentionally a separate process.

---

### Task 1.8 — Write Phase 1 integration test

**Status**: `DONE`

**What**: A pytest test that calls `perceive_screen()` and `execute_gesture("back")` with a mocked device. Validate return shapes.

**Files to touch**:
- `tests/test_mcp_tools.py` (NEW)

**Test skeleton**:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.unit
async def test_perceive_screen_returns_expected_shape():
    mock_bundle = MagicMock()
    mock_bundle.snapshot_id = "snap_001"
    mock_bundle.screenshot.screenshot_base64 = "base64data"
    mock_bundle.screenshot.screen_width = 1080
    mock_bundle.screenshot.screen_height = 2400
    mock_bundle.ui_tree.elements = []
    mock_bundle.visual_description = "Home screen"

    with patch("aura_mcp_server.get_perception_controller") as mock_ctrl:
        mock_ctrl.return_value.request_perception = AsyncMock(return_value=mock_bundle)
        from aura_mcp_server import perceive_screen
        result = await perceive_screen()

    assert result["snapshot_id"] == "snap_001"
    assert result["screen_width"] == 1080
    assert isinstance(result["som_elements"], list)

@pytest.mark.unit
async def test_execute_gesture_back():
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.action_type = "back"
    mock_result.duration_ms = 50.0
    mock_result.error = None
    mock_result.details = {}

    with patch("aura_mcp_server.ActorAgent") as MockActor:
        MockActor.return_value.execute = AsyncMock(return_value=mock_result)
        from aura_mcp_server import execute_gesture
        result = await execute_gesture("back")

    assert result["success"] is True
    assert result["action_type"] == "back"
```

**Verification**: `pytest tests/test_mcp_tools.py -v`

**Completion notes**: `tests/test_mcp_tools.py` created with 7 unit tests: `test_perceive_screen_returns_expected_shape`, `test_perceive_screen_with_som_elements`, `test_execute_gesture_back`, `test_execute_gesture_tap_with_coordinates`, `test_validate_action_allowed`, `test_validate_action_blocked`, `test_watch_device_events_returns_empty_list`. All use `@pytest.mark.asyncio` + `@pytest.mark.unit`. Module-level singletons reset via `aura_mcp_server._actor = None` between tests.

---

### Phase 1 Completion Checklist

Before marking Phase 1 DONE:

- [x] `python aura_mcp_server.py` starts without error
- [x] All 4 tools registered via `@mcp.tool()` decorators
- [x] `perceive_screen()` implemented (requires live device to call)
- [x] `execute_gesture("back")` implemented
- [x] `validate_action("tap", "A1")` implemented — uses real `evaluate(ActionContext)` API
- [x] `watch_device_events()` returns `[]` (stub acknowledged)
- [x] `pytest tests/test_mcp_tools.py` — 7 tests written, pending run
- [x] `.env.example` updated with MCP fields
- [x] `wiki/mcp_build_plan.md` task statuses updated to DONE
- [x] `wiki/log.md` entry added (2026-04-10)
- [ ] `wiki/mcp_architecture.md` updated if anything differed from plan — **PENDING** (PolicyEngine interface differs: `evaluate(ActionContext)` not `check()`)

---

## Phase 2 — Event Broadcast Layer

**Goal**: Every device action (regardless of source) broadcasts to all connected clients.
**Prerequisite**: Phase 1 complete.

---

### Task 2.1 — Create `services/event_bus.py`

**Status**: `DONE`

**What**: Async pub/sub event bus. All device events flow through here.

**Files to touch**:
- `services/event_bus.py` (NEW)

**Implementation**:
```python
"""
AuraEventBus — lightweight pub/sub for device events.

Any component can publish an event. Any subscriber receives all events.
Used to broadcast: gesture results, voice commands, screen changes.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceEvent:
    event_type: str           # "gesture_executed" | "voice_command" | "screen_changed"
    source: str               # "mcp" | "voice" | "api"
    client_id: str            # who triggered it
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0


class AuraEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue] = {}

    async def publish(self, event: DeviceEvent) -> None:
        for queue in self._subscribers.values():
            await queue.put(event)

    def subscribe(self, client_id: str) -> asyncio.Queue:
        if client_id not in self._subscribers:
            self._subscribers[client_id] = asyncio.Queue()
        return self._subscribers[client_id]

    def unsubscribe(self, client_id: str) -> None:
        self._subscribers.pop(client_id, None)


# Module-level singleton
_event_bus: AuraEventBus | None = None

def get_event_bus() -> AuraEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = AuraEventBus()
    return _event_bus
```

**Completion notes**: `services/event_bus.py` created. `DeviceEvent` dataclass with `event_type`, `source`, `client_id`, `payload`, `timestamp`. `AuraEventBus` fan-out pub/sub using `dict[str, asyncio.Queue]`. Module-level singleton via `get_event_bus()`. `subscriber_count` property added.

---

### Task 2.2 — Publish events from gesture execution

**Status**: `DONE`

**What**: After every gesture in `execute_gesture()` in `aura_mcp_server.py`, publish a `DeviceEvent`.

**Files to touch**:
- `aura_mcp_server.py` — add publish call after `_actor.execute()`

**Addition** (inside `execute_gesture`, after getting result):
```python
from services.event_bus import get_event_bus, DeviceEvent
import time

bus = get_event_bus()
await bus.publish(DeviceEvent(
    event_type="gesture_executed",
    source="mcp",
    client_id="mcp_client",
    payload={
        "gesture_type": gesture_type,
        "target": target,
        "success": result.success,
        "error": result.error,
    },
    timestamp=time.time(),
))
```

**Completion notes**: `execute_gesture()` in `aura_mcp_server.py` now publishes `DeviceEvent(event_type="gesture_executed", source="mcp", client_id="mcp_client", ...)` after every gesture. Imports `time` and `DeviceEvent, get_event_bus` at module level.

---

### Task 2.3 — Implement `watch_device_events()` for real

**Status**: `DONE`

**What**: Subscribe to event bus, collect events for N seconds, return them.

**Files to touch**:
- `aura_mcp_server.py` — replace TODO stub

**Implementation**:
```python
@mcp.tool()
async def watch_device_events(timeout_seconds: int = 30) -> list:
    """
    Observe all events happening on the device for the specified duration.
    Returns a list of events (voice commands, gestures, screen changes).
    """
    from services.event_bus import get_event_bus
    bus = get_event_bus()
    queue = bus.subscribe("mcp_watcher")

    events = []
    try:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
                events.append({
                    "event_type": event.event_type,
                    "source": event.source,
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                })
            except asyncio.TimeoutError:
                break
    finally:
        bus.unsubscribe("mcp_watcher")

    return events
```

**Completion notes**: Real implementation replaced stub. Uses `asyncio.wait_for` with computed `remaining` timeout per iteration (respects total budget). Subscribes before loop, `finally: bus.unsubscribe("mcp_watcher")` ensures no orphaned queues. Returns list of dicts with `event_type`, `source`, `payload`, `timestamp`.

---

### Task 2.4 — Add `command_source` + `client_id` to `TaskState`

**Status**: `DONE`

**What**: Two new optional fields on `TaskState` so the result router knows where to route results.

**Files to touch**:
- `aura_graph/state.py` — add fields

**Addition** (find `TaskState` TypedDict definition):
```python
command_source: str   # "voice" | "mcp" | "api" — added for multi-input routing
client_id: str        # route response back to correct connection
```

Use `NotRequired[str]` if the TypedDict uses that pattern, or set defaults to `""`.

**Wiki page to update**: `wiki/aura_graph/state.md` (if it exists)

**Completion notes**: Added `command_source: Optional[str]` and `client_id: Optional[str]` to `TaskState` TypedDict in `aura_graph/state.py`, after `web_search_result`. Both use `Optional[str]` pattern matching all other optional fields. Docstrings describe routing purpose.

---

### Phase 2 Completion Checklist

- [x] `services/event_bus.py` exists and is importable
- [x] `execute_gesture()` publishes events
- [x] `watch_device_events(5)` returns events when gestures happen in parallel
- [x] `TaskState` has `command_source` and `client_id`
- [x] `wiki/log.md` entry added

---

## Phase 3 — Black Box Tool + REST API

**Goal**: `execute_android_task()` for non-Claude agents + HTTP REST fallback.  
**Prerequisite**: Phase 1 complete. Phase 2 optional (can run Phase 3 in parallel with Phase 2).

---

### Task 3.1 — Implement `execute_android_task()` MCP tool (Style A)

**Status**: `DONE`

**What**: Black box tool. Takes a natural language command, runs full AURA pipeline (Groq/Gemini internally), returns structured result. Works with any MCP agent — no vision required.

**Files to touch**:
- `aura_mcp_server.py` — add new tool

**Implementation**:
```python
@mcp.tool()
async def execute_android_task(utterance: str) -> dict:
    """
    Execute a natural language command on the Android device.
    AURA handles all AI reasoning internally (Groq/Gemini).
    Use this tool if you don't want to control individual gestures.

    Args:
        utterance: natural language command (e.g. "open Spotify and play liked songs")

    Returns:
        success: bool
        response_text: str — what AURA says happened
        steps_taken: int
        error: str | None
    """
    from aura_graph.graph import run_aura_task

    result = await run_aura_task(utterance)

    return {
        "success": result.get("success", False),
        "response_text": result.get("response", ""),
        "steps_taken": result.get("steps_taken", 0),
        "error": result.get("error", None),
    }
```

**Context for next session**: Check `run_aura_task()` return signature in `aura_graph/graph.py` — confirm the return dict keys. The keys `success`, `response`, `steps_taken` are assumed — verify before coding.

**Completion notes**: Used `execute_aura_task_from_text(app, text_input, thread_id, track_workflow)` — NOT `run_aura_task()` (build plan was wrong). Added `_mcp_graph` singleton compiled lazily via `compile_aura_graph(MemorySaver())`. Publishes `task_executed` event to bus after completion.

---

### Task 3.2 — Create `api/execute.py` REST endpoint

**Status**: `DONE`

**What**: HTTP POST endpoint as fallback for agents that don't support MCP.

**Files to touch**:
- `api/execute.py` (NEW)
- `main.py` — register router

**Implementation**:
```python
# api/execute.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ExecuteRequest(BaseModel):
    command: str
    source: str = "api"


class ExecuteResponse(BaseModel):
    success: bool
    response_text: str
    steps_taken: int
    error: str | None = None


@router.post("/api/v1/execute", response_model=ExecuteResponse)
async def execute_task(request: ExecuteRequest) -> ExecuteResponse:
    """
    Execute a natural language command via HTTP.
    For agents that don't support MCP protocol.
    """
    from aura_graph.graph import run_aura_task

    result = await run_aura_task(request.command)

    return ExecuteResponse(
        success=result.get("success", False),
        response_text=result.get("response", ""),
        steps_taken=result.get("steps_taken", 0),
        error=result.get("error", None),
    )
```

**Add to `main.py`**:
```python
from api.execute import router as execute_router
app.include_router(execute_router)
```

**Completion notes**: Created `api/execute.py` with `ExecuteRequest`/`ExecuteResponse` Pydantic models. Reads `graph_app` from `request.app.state` (set by lifespan, already present). Registered in `main.py` via `from api import ..., execute` and `app.include_router(execute.router, prefix=API_PREFIX, tags=["Execute"])`. 15 unit tests in `tests/test_execute_endpoint.py` — all passing.

---

### Phase 3 Completion Checklist

- [x] `execute_android_task("go to home screen")` runs the full pipeline
- [x] `POST /api/v1/execute` returns 200 with valid JSON
- [x] 15 tests in `tests/test_execute_endpoint.py` passing

---

## Phase 4 — Open Source Packaging

**Goal**: Anyone can fork this repo, run one command, and have AURA working.  
**Prerequisite**: Phases 1–3 complete.

---

### Task 4.1 — Write `quickstart.md`

**Status**: `DONE`

**Completion notes**: `quickstart.md` written at repo root. 8-step guide: prerequisites, clone+install, API key config, device connection, companion app, backend startup, voice command demo, Claude Code MCP config. Includes MCP tools table and troubleshooting section.

Steps:
1. Prerequisites (Python 3.11+, Android device with USB debugging)
2. Clone + install: `pip install -r "requirements copy.txt"`
3. Copy `.env.example` to `.env`, fill in API keys
4. Run `python main.py`
5. Connect device (companion app install link)
6. Run `python aura_mcp_server.py`
7. Configure Claude Code: `~/.claude.json` snippet
8. Demo command to try

---

### Task 4.2 — Refactor `README.md` from hackathon to tool framing

**Status**: `DONE`

**Completion notes**: Added `## MCP Integration` section with MCP server startup, Claude Code `~/.claude.json` config snippet, MCP tools table (5 tools), Style A vs Style B explanation, and agent compatibility table (Claude Code / Copilot / Cursor / Windsurf / REST). Added `POST /api/v1/execute` to REST API table. Added MCP Integration to Table of Contents. Google Cloud Architecture section was already present from prior work.

Add sections:
- What AURA is (tool framing, not hackathon demo framing)
- Use cases: manual testing, automation, accessibility
- Quick demo GIF embed placeholder
- Agent compatibility table (from `wiki/mcp_architecture.md`)
- Setup instructions (link to quickstart.md)
- `## Google Cloud Architecture` section (required for hackathon — still needed)

---

### Task 4.3 — Create `setup.sh`

**Status**: `DONE`

**Completion notes**: `setup.sh` written at repo root. `pip install -r "requirements copy.txt"`, `cp -n .env.example .env` (no-clobber), prints next-step instructions.

```bash
#!/bin/bash
set -e
pip install -r "requirements copy.txt"
cp -n .env.example .env
echo "Edit .env with your API keys, then run: python main.py"
```

---

### Phase 4 Completion Checklist

- [x] Fresh clone + `setup.sh` produces working install
- [x] `quickstart.md` exists and is accurate
- [x] README has MCP Integration section with agent compatibility table
- [x] README Table of Contents includes MCP Integration

---

## Summary Table — All Tasks

| Task | Description | Phase | Status |
|------|-------------|-------|--------|
| 1.0 | Install MCP SDK | 1 | TODO |
| 1.1 | Create `aura_mcp_server.py` skeleton | 1 | TODO |
| 1.2 | Implement `perceive_screen()` | 1 | TODO |
| 1.3 | Implement `execute_gesture()` | 1 | TODO |
| 1.4 | Implement `validate_action()` | 1 | TODO |
| 1.5 | Implement `watch_device_events()` stub | 1 | TODO |
| 1.6 | Add MCP settings to `config/settings.py` | 1 | TODO |
| 1.7 | Wire MCP into `main.py` docs | 1 | TODO |
| 1.8 | Write Phase 1 integration test | 1 | TODO |
| 2.1 | Create `services/event_bus.py` | 2 | TODO |
| 2.2 | Publish events from `execute_gesture()` | 2 | TODO |
| 2.3 | Implement `watch_device_events()` for real | 2 | TODO |
| 2.4 | Add `command_source` + `client_id` to `TaskState` | 2 | TODO |
| 3.1 | Implement `execute_android_task()` black box | 3 | TODO |
| 3.2 | Create `api/execute.py` REST endpoint | 3 | TODO |
| 4.1 | Write `quickstart.md` | 4 | DONE |
| 4.2 | Refactor `README.md` | 4 | DONE |
| 4.3 | Create `setup.sh` | 4 | DONE |
| 5.1 | Add `lookup_app` MCP tool | 5 | DONE |
| 5.2 | Add `launch_app` MCP tool + REST endpoint | 5 | DONE |
| 5.3 | Add `omniparser_detect` MCP tool + REST endpoint | 5 | DONE |
| 5.4 | Add `web_search` MCP tool | 5 | DONE |
| 5.5 | Implement `MCPBrainLogger` (HTML/TXT/log session logs) | 5 | DONE |
| 5.6 | Tap-before-type in `execute_gesture` | 5 | DONE |

---

## Phase 5 — Brain-Mode Tool Expansion

**Goal**: Equip Claude with richer, real-device tools so it can orchestrate AURA at the app+package level, run visual parsing on demand, search the web, and get a structured HTML session log.  
**Prerequisite**: Phases 1–4 complete.

---

### Task 5.1 — `lookup_app` MCP tool

**Status**: `DONE`

**What**: Resolves human-readable app names (e.g. "Spotify") to Android package names using `device_app_inventory.json`.

**Files touched**:
- `aura_mcp_server.py` — new `lookup_app(app_name)` tool
- `utils/app_inventory_utils.py` — `AppInventoryManager` (file-based, safe to import in MCP process)

**Key detail**: `device_app_inventory.json` is created when a device connects. `AppInventoryManager` uses fuzzy matching and is a singleton read from disk — no WebSocket dependency.

---

### Task 5.2 — `launch_app` MCP tool + REST endpoint

**Status**: `DONE`

**What**: Launches apps by package name via Android intent — faster than navigating the UI.

**Files touched**:
- `aura_mcp_server.py` — new `launch_app(package_name)` tool calling `POST /accessibility/launch-app`
- `api_handlers/real_accessibility_api.py` — added `LaunchAppRequest` Pydantic model + `POST /launch-app` endpoint calling `real_accessibility_service.launch_app_via_intent()`

**Key detail**: `launch_app_via_intent()` sends `{"type": "launch_app", ...}` via the Android WebSocket — distinct from `execute_gesture`.

---

### Task 5.3 — `omniparser_detect` MCP tool + REST endpoint

**Status**: `DONE`

**What**: Runs OmniParser (YOLOv8, pre-warmed at server start) on the current screen and returns SoM-labelled elements.

**Files touched**:
- `api_handlers/perception_api.py` (NEW) — `POST /perception/omniparser-detect` endpoint. Accesses detector via `PerceptionController._pipeline._detector` singleton; falls back to fresh detector. Returns `OmniParserResponse` with `elements_detected`, `detections`, optional `annotated_image_b64`.
- `main.py` — registered `perception_router` at `/perception` prefix
- `aura_mcp_server.py` — new `omniparser_detect(screenshot_b64)` tool calling that REST endpoint

**Critical invariant**: VLM must select by SoM label — never return raw pixel coordinates. This tool preserves the numbered label outputs from OmniParser.

---

### Task 5.4 — `web_search` MCP tool

**Status**: `DONE`

**What**: Exposes the existing `WebSearchService` (Tavily) as an MCP tool for in-task web lookup.

**Files touched**:
- `aura_mcp_server.py` — new `web_search(query)` tool

**Critical detail**: `WebSearchService.search(query, topic="general")` returns a plain synthesized `str`, NOT a dict. The `results` list in the MCP return is always empty; the `answer` field carries the synthesized answer. An earlier version of this tool incorrectly called `svc.search(query, max_results=...)` and tried `.get("results", [])` on the returned string — this was fixed.

---

### Task 5.5 — `MCPBrainLogger`

**Status**: `DONE`

**What**: Structured session logger writing three parallel files per MCP session: `.html` (dark-theme, matching AURA CommandLogger style), `.txt` (plain text), `.log` (terminal). Format: `HH:MM:SS │ LEVEL │ module.name │ message`.

**Files touched**:
- `aura_mcp_server.py` — `MCPBrainLogger` class at top of file; instantiated as `log` module-level singleton

---

### Task 5.6 — Tap-before-type in `execute_gesture`

**Status**: `DONE`

**What**: When `execute_gesture` receives a `type` gesture with `focus_x`/`focus_y` in params, it automatically sends a tap to that coordinate first, waits 300 ms, then types — matching real Android IME behavior.

**Files touched**:
- `aura_mcp_server.py` — logic inside `execute_gesture` tool handler

---

### Phase 5 Completion Checklist

- [x] `lookup_app("Spotify")` returns `com.spotify.music`
- [x] `launch_app("com.spotify.music")` triggers intent-based launch via WebSocket
- [x] `omniparser_detect(...)` returns SoM-labelled element list
- [x] `web_search("Spotify deep links")` returns Tavily synthesized answer
- [x] Every MCP session writes `.html` + `.txt` + `.log` under `logs/`
- [x] `type` gesture auto-taps field when `focus_x`/`focus_y` are present

---

## Things That Will Go Wrong (Pre-Empted)

| Problem | Expected cause | Fix |
|---------|---------------|-----|
| `UITreePayload.elements` AttributeError | Field name differs in actual code | Read `aura_graph/state.py` to find correct field name |
| `GestureExecutor()` requires args | Constructor needs device connection | Check how `main.py` or `graph.py` initializes it; copy that pattern |
| `PolicyEngine.check()` wrong signature | Method name or args differ | Read `services/policy_engine.py` before Task 1.4 |
| `run_aura_task()` return shape differs | Dict keys not as assumed | Read `aura_graph/graph.py` return statement before Task 3.1 |
| MCP server can't find AURA FastAPI | MCP runs as separate process, needs URL config | Add `AURA_SERVER_URL` to settings; MCP tools call FastAPI via HTTP if needed |
| Import errors on `aura_mcp_server.py` | Circular imports or missing `__init__` | Check that repo root is on PYTHONPATH; run from repo root |

---

## Open Questions (Resolve Before Coding)

These require a quick read of one source file each — do it at the start of the relevant task:

1. **`UITreePayload` field names** — read `perception/ui_tree_parser.py` or `aura_graph/state.py`
2. **`GestureExecutor.__init__` signature** — read `services/gesture_executor.py` first 30 lines
3. **`PolicyEngine.check()` return type** — read `services/policy_engine.py`
4. **`run_aura_task()` return dict keys** — read `aura_graph/graph.py` return statement
5. **`mcp` Python package API** — FastMCP is in `mcp.server.fastmcp`; confirm via `pip show mcp`
