---
last_verified: 2026-04-08
source_files: [agents/actor_agent.py]
status: current
---

# Agent: Actor

**File**: `agents/actor_agent.py`

---

## Role

`ActorAgent` executes gestures on the Android device. It has **zero LLM calls** — entirely deterministic. This is intentional: gesture execution should be fast, reliable, and auditable.

---

## ActionResult Dataclass

```python
@dataclass
class ActionResult:
    success: bool
    action_type: str
    coordinates: Optional[Tuple[int, int]]  # Where the gesture was executed
    duration_ms: float                       # Execution time
    error: Optional[str]
    details: Optional[dict]
```

---

## `execute(action_dict) -> ActionResult`

The main method. Pipeline:

1. **Validate action** — checks `action_type` exists in `ACTION_REGISTRY`
2. **Resolve gesture** — calls `resolve_gesture(action_type, target)` to get the gesture type and parameters
3. **Build action dict** — normalizes parameters
4. **Auto-inject swipe coordinates** — for directional targets (e.g., `swipe_up`, `swipe_down`), coordinates are injected automatically from screen center if not provided
5. **Delegate to `GestureExecutor._execute_single_action()`** — sends the command to the Android device

---

## GestureExecutor Strategy Selection

`GestureExecutor` automatically selects the best execution strategy:

| Strategy | Transport | When Used |
|----------|-----------|-----------|
| `WEBSOCKET` | WebSocket `/ws/device` | Preferred — instant delivery |
| `COMMAND_QUEUE` | Polling endpoint | When WebSocket is busy or unavailable |
| `DIRECT` | Direct API call | Final fallback |

---

## Supported Gesture Types

| `GestureType` | Description |
|--------------|-------------|
| `TAP` | Single tap at coordinates |
| `SWIPE` | Swipe from start to end coordinates |
| `LONG_PRESS` | Tap and hold |
| `SCROLL` | Scroll up/down/left/right |
| `TYPE_TEXT` | Type text into focused field |
| `DOUBLE_TAP` | Double tap |

---

## OPA Policy Gate

Before any gesture is sent to the device, `GestureExecutor` calls `PolicyEngine.evaluate(action_context)`. If the policy decision is `allowed=False`, the action is blocked and `ActionResult(success=False, error="Policy blocked: ...")` is returned.

Actions in `PolicyEngine.BLOCKED_ACTIONS` (e.g., `factory_reset`, `wipe_data`) are always blocked regardless of OPA availability.

---

## Phone Number Detection

`GestureExecutor._looks_like_phone_number(text)` runs on `type_text` targets. If the text looks like a phone number (regex: `[\+\d][\d\s\-\(\)]{8,}`), special handling is applied to avoid accidental dialing.

---

## NO_TARGET_ACTIONS

Some actions don't require a UI target (e.g., `press_home`, `press_back`, `press_recents`). These come from `config/action_types.py NO_UI_ACTIONS` and skip the VLM selection step in the perception pipeline.
