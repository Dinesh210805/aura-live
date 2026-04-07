# Agent: Coordinator

**File**: `agents/coordinator.py`  
**Type**: Orchestrator — the most complex agent

---

## Role

The `Coordinator` runs the main **perceive → decide → act → verify** loop. It:
1. Receives a goal (parsed intent + original utterance)
2. Calls `PlannerAgent` to create a skeleton plan (phases)
3. For each phase, calls `ReactiveStepGenerator` (RSG) to decide the next single action
4. Calls `Validator` to pre-check the action
5. Calls `Actor` to execute the gesture
6. Calls `Verifier` to confirm success
7. Retries via the 5-stage retry ladder if verification fails
8. Replans if stuck or the screen is in an unexpected state
9. Calls `HITLService` if stuck (asks user for help)

---

## Key Constants

```python
MAX_TOTAL_ACTIONS = 30      # Hard cap on gestures per task
MAX_REPLAN_ATTEMPTS = 3     # How many times coordinator will replan
MAX_STEP_MEMORY = 20        # Cap on step_memory list (G2 fix)
MAX_SCROLL_SEARCH = 2       # Max scrolls in "search mode" before giving up
```

---

## Goal Completion Detection

Two mechanisms run in parallel:

### 1. Deterministic UI-Tree Heuristic — `_detect_goal_completion()`

Examines post-action UI elements for strong completion signals. Fast — zero LLM calls.

| Goal Type | Signal |
|-----------|--------|
| `media` | Pause button visible (text/contentDescription contains "pause" or ⏸) |
| `navigation` | Navigation active indicators (ETA, End button, no Start button) |
| `messaging` | Sent/Delivered indicator (word-boundary match to avoid "undelivered") |
| `call` | Calling/ringing/on-call indicators |

**Pre-action guard**: Takes `pre_elements` to ignore signals already present before the action (e.g., a now-playing mini-player that was already showing).

**Course listing guard**: For media goals, checks for Resume+lesson rows which indicate a course overview page (not playing), preventing false positives.

### 2. VLM Verification — `VerifierAgent`

Called for `COMMIT_ACTIONS` (actions that change state and need semantic confirmation):
- Uses the same RSG VLM call to ask: "Did the action succeed?"
- Adds latency but provides semantic confirmation that UI-tree heuristics can miss

---

## Reactive Hybrid Planning

The coordinator uses a **reactive hybrid approach**:

1. `PlannerAgent.create_plan()` generates a **skeleton** of abstract phases:
   - Phase 1: "Open Spotify" → success criteria: "Spotify is visible"
   - Phase 2: "Navigate to Liked Songs" → success criteria: "Liked Songs page visible"
   - Phase 3: "Start playback" → success criteria: "Media playing indicator visible"

2. For each phase, `ReactiveStepGenerator` (RSG) generates **one concrete next action** by observing the current live screen. This is re-run after each action — the agent never commits to a specific action sequence in advance.

This hybrid approach means:
- The skeleton provides direction and prevents aimless wandering
- Reactive RSG handles unexpected UI states gracefully

---

## Retry Ladder (Per-Subgoal)

```
Attempt 0: SAME_ACTION — retry identical gesture
Attempt 1: ALTERNATE_SELECTOR — ask VLM to pick a different element
Attempt 2: SCROLL_AND_RETRY — scroll the screen, then retry
Attempt 3: VISION_FALLBACK — use full VLM analysis
Attempt 4: ABORT — give up on this subgoal
```

Each `Subgoal` manages its own `current_strategy_index`. Calling `subgoal.escalate_strategy()` advances it. The index is **not shared across subgoals** (G5 fix — previously was a task-level global).

---

## HITL Integration (G1 Fix)

When the coordinator is stuck (consecutive same screen, max retries exceeded), it calls `HITLService` to ask the user a question. Previously, this fell through to `ActorAgent` which tried to execute `ask_user`/`stuck` as gestures — causing crashes.

Now:
1. Coordinator detects `ask_user` action in RSG output
2. Calls `hitl_service.ask_choice(question, options)`
3. Suspends the task loop via `asyncio.Event`
4. The WebSocket router checks HITL before dispatching new tasks (barge-in support)
5. When user responds, `register_voice_answer()` resolves the pending event

---

## Step Memory (G2 Fix)

`step_memory` is a list of `StepMemory` objects capped at `MAX_STEP_MEMORY = 20`. Each entry records:
- Screen state before/after (UI signatures)
- Action taken
- Success/failure
- `key_state_after` (e.g., "media_playing" for media goals)

This structured history is injected into RSG calls, giving the model context about what has already been tried.

---

## Loop Detection

`AgentState.consecutive_same_screen` increments when the UI signature hasn't changed after an action. If this counter reaches a threshold:
1. Coordinator triggers a replan
2. If already at max replans, requests HITL
3. If HITL timeout, aborts

---

## Reflexion Integration

On task success where `replan_count > 0` (recovery path) or on task abort:
1. Calls `ReflexionService.generate_lesson(goal, step_history, failure_reason)`
2. Stores the lesson keyed by `_goal_key(utterance, app_name)` (R0a fix)
3. Injects stored lessons into RSG prompt context for future similar tasks (R0b fix)

---

## Token Budget (G4 Fix)

The coordinator calls `TokenTracker.check_budget(session_id)` before each LLM call. If budget is exceeded, it sets `status = "failed"` with reason `"token_budget_exceeded"` rather than making more LLM calls.
