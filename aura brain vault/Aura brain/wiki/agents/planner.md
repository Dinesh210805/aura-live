# Agent: Planner

**File**: `agents/planner_agent.py`

---

## Role

`PlannerAgent` decomposes a user goal into a skeleton plan of phases. In reactive mode (default), each phase is a high-level abstract step; the coordinator's `ReactiveStepGenerator` handles the concrete per-step decisions.

---

## `create_plan(utterance, intent) -> Goal`

1. Calls `GoalDecomposer` to break the utterance into phases
2. Validates commit coverage — ensures phases that need `COMMIT_ACTIONS` have them
3. Returns a `Goal` object with populated `phases` list

**In reactive/phase mode**: `_ensure_commit_coverage()` is **skipped** — the RSG handles atomic actions dynamically.

---

## `replan(current_state, obstacle, vlm_description) -> List[Phase]`

Called when the coordinator is stuck and needs a new plan:

1. **Enriches obstacle description** with VLM's screen description (what the VLM actually sees)
2. **Enforces atomic constraint**: each phase must be ≤ 12 words in description
3. **Validates action types**: checks all suggested actions against `VALID_ACTIONS` list
4. **Creates fallback plan** if 0 phases returned (LLM returned empty plan)

The replanned phases replace the existing phases in the `Goal` object.

---

## Constraint: Action Types Must Match Registry

All action types in the plan must match entries in `config/action_types.py ACTION_REGISTRY`. If an LLM-generated plan contains an unknown action type (e.g., "navigate" instead of "open_url"), the planner rejects or remaps it.

---

## MAX_REPLAN_ATTEMPTS

The coordinator tracks how many times it has called `replan()`. After `MAX_REPLAN_ATTEMPTS = 3`, no more replanning occurs — the task is aborted with `"max_replans_exceeded"`.

---

## Static vs Reactive Mode

| Mode | Plan Type | Who decides each step |
|------|-----------|-----------------------|
| Reactive (default) | Abstract skeleton phases | RSG observes screen, decides next action |
| Static (legacy) | Concrete `Subgoal` list | Pre-determined action sequence |

Reactive mode is significantly more robust to unexpected UI states because it re-evaluates after each action rather than following a pre-committed script.
