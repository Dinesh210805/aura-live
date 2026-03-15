# AURA Retry Architecture

AURA has three retry/recovery systems operating at different layers.
Understanding their scope prevents duplicate retry logic and counter conflicts.

## System 1: Coordinator Internal Retry (DISABLED by FIX-007)
- **File**: `agents/coordinator.py` → `_handle_target_not_found()`
- **Status**: DISABLED. Now raises `TargetNotFoundError` immediately.
- **Previous behavior**: Internal scroll × 4 + replan. Hidden from LangGraph.

## System 2: LangGraph Validation + Retry Ladder
- **Files**: `validate_outcome_node.py` → `retry_router_node.py`
- **Trigger**: After every gesture execution when `agent_state` is present
- **Stages**: SAME_ACTION → ALTERNATE_SELECTOR → SCROLL_AND_RETRY → VISION_FALLBACK → ABORT
- **Abort conditions**: `max_total_attempts=15`, `max_same_screen=3`, `max_subgoal_attempts=5`

## System 3: LangGraph Error Handler
- **File**: `aura_graph/nodes/error_handler_node.py`
- **Trigger**: Uncaught exceptions bubbling up from any node
- **Scope**: Catches `TargetNotFoundError`, `PerceptionFailureError`, STT failures, etc.
- **Routes to**: `retry_router_node` for retry-able errors, `speak` for fatal errors

## Attempt Counter Authority

`agent_state.total_attempts` is the single source of truth.
It is incremented ONLY in `retry_router_node.py`.
All other places that previously incremented it have been removed.

## Per-Task Reset

Call `agent_state.reset_for_new_task()` at the start of each new user command
(implemented in `aura_graph/core_nodes.py` coordinator node).
