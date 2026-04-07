# LangGraph — TaskState & Models

**Files**: `aura_graph/state.py`, `aura_graph/agent_state.py`

---

## TaskState TypedDict

The single shared state object that flows through every LangGraph node. All nodes read from it and return partial updates — LangGraph merges updates using per-field reducers.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Active device session |
| `thread_id` | `str` | Conversation thread for checkpointing |
| `input_type` | `str` | `"audio"`, `"text"`, or `"streaming"` |
| `audio_data` | `bytes` | Raw PCM audio (cleared after STT) |
| `text_input` | `str` | Text command (for text/streaming modes) |
| `transcript` | `str` | STT output |
| `intent` | `dict` | Parsed intent from Commander |
| `goal` | `Goal` | The active goal with phases/subgoals |
| `goal_summary` | `str` | Short description for logging |
| `perception_bundle` | `PerceptionBundle` | Current screen state |
| `snapshot_id` | `str` | Unique ID for current screen snapshot |
| `agent_state` | `AgentState` | Loop detection, retry counters |
| `executed_steps` | `List[dict]` | Action history (capped at 50) |
| `step_memory` | `List[StepMemory]` | Structured step history (capped at `MAX_STEP_MEMORY=20`) |
| `status` | `str` | Current state: `"pending"`, `"executing"`, `"completed"`, `"failed"` |
| `spoken_response` | `str` | Text to speak to the user |
| `error` | `str` | Last error message |
| `errors` | `List[str]` | All errors (accumulated via `add_errors` reducer) |
| `log_url` | `str` | GCS public URL of execution log |
| `token_usage` | `dict` | Accumulated token counts |
| `phase_timings` | `dict` | Per-phase start/end timestamps (G10 fix) |

### Deprecated Fields (do not use)
- `ui_screenshot` → replaced by `perception_bundle`
- `ui_tree` → replaced by `perception_bundle`
- `ui_elements` → replaced by `perception_bundle`

---

## Custom Reducers

LangGraph reducers define how state fields are merged when a node returns a partial update.

### `cap_executed_steps`

```python
MAX_EXECUTED_STEPS = 50

def cap_executed_steps(existing, new):
    combined = list(existing or []) + list(new or [])
    return combined[-MAX_EXECUTED_STEPS:]
```

Keeps only the 50 most recent executed steps. Prevents unbounded growth that would overflow LLM context windows.

### `add_errors`

Appends new errors to the existing list rather than overwriting. Ensures all errors across retries are preserved for diagnosis.

### `update_status`

Last-write-wins for the `status` field.

### `set_once`

Set a field the first time only; subsequent updates are ignored. Used for `goal`, `session_id`, `intent`.

### `update_step`

Merges dict updates into an existing dict field.

---

## Goal, Subgoal, Phase Models

**File**: `aura_graph/agent_state.py`

### `Goal` Dataclass

```python
@dataclass
class Goal:
    original_utterance: str    # "Open Spotify and play liked songs"
    intent: dict               # Parsed intent from Commander
    phases: List[Phase]        # Skeleton phases from Planner (reactive mode)
    subgoals: List[Subgoal]    # Static subgoals (legacy mode)
    pending_commits: List[str] # Actions that need post-action verification
```

### `Phase` Dataclass

A high-level abstract phase in the skeleton plan:
```python
@dataclass
class Phase:
    description: str    # "Open Spotify"
    success_criteria: str  # "Spotify app is visible on screen"
    phase_index: int
```

### `Subgoal` Dataclass

An atomic step with its own retry ladder:
```python
@dataclass
class Subgoal:
    description: str
    action_type: str           # Must match ACTION_REGISTRY
    target: Optional[str]
    current_strategy_index: int = 0  # Position in retry ladder

    def escalate_strategy(self) -> RetryStrategy:
        """Advance to next retry strategy."""
        self.current_strategy_index = min(
            self.current_strategy_index + 1,
            len(RETRY_LADDER) - 1
        )
        return RETRY_LADDER[self.current_strategy_index]
```

---

## Retry Ladder

**File**: `aura_graph/agent_state.py`

```python
class RetryStrategy(Enum):
    SAME_ACTION = "same_action"
    ALTERNATE_SELECTOR = "alternate_selector"
    SCROLL_AND_RETRY = "scroll_and_retry"
    VISION_FALLBACK = "vision_fallback"
    ABORT = "abort"

RETRY_LADDER = [
    RetryStrategy.SAME_ACTION,
    RetryStrategy.ALTERNATE_SELECTOR,
    RetryStrategy.SCROLL_AND_RETRY,
    RetryStrategy.VISION_FALLBACK,
    RetryStrategy.ABORT,
]
```

Each `Subgoal` has its own `current_strategy_index` — escalates independently of other subgoals.

---

## StepMemory

Structured record of each executed step:
```python
@dataclass
class StepMemory:
    step_number: int
    action_type: str
    target: Optional[str]
    screen_before: str          # UI signature before action
    screen_after: str           # UI signature after action
    success: bool
    key_state_after: Optional[str]  # e.g., "media_playing", "nav_active"
```

`step_memory` is capped at `MAX_STEP_MEMORY = 20` to prevent LLM context overflow (G2 fix).

---

## AgentState

Tracks per-task loop detection and scroll state:
```python
@dataclass
class AgentState:
    consecutive_same_screen: int = 0  # Increments when screen hasn't changed
    replan_count: int = 0              # Global replanning attempts (per-task)
    scroll_search_count: int = 0       # Scrolls done in search mode
    abort_requested: bool = False

    def reset_for_new_task(self):
        """Resets all per-task counters. Called when starting a new subgoal."""
        self.consecutive_same_screen = 0
        self.replan_count = 0
        self.scroll_search_count = 0
        self.abort_requested = False
```
