# Backlog

Active improvement items from self-reflection (2026-03-29). P0 items already fixed. P1–P3 pending.

---

## P1 — Structured RSG Diagnosis Field

**What:** Add a `__diagnosis__` JSON field to the RSG output schema alongside `__prev_step_ok__`.

**Why:** The model currently outputs `__prev_step_ok__` (boolean) and `__prev_step_issue__` (freeform string). A structured diagnosis is more reliably parsed and more useful as input context for the next step.

**Schema to add to `prompts/reactive_step.py`:**
```json
"__diagnosis__": {
  "what_happened": "Tapped Search bar but target was not in search results",
  "dead_end": "Search bar is not the right path for this target",
  "try_instead": "Navigate to Library tab"
}
```

**Wiring in `agents/coordinator.py`:**
After reading `__prev_step_issue__`, also extract `__diagnosis__` from `next_step.parameters` and:
1. Log it via `_cmd_logger.log_agent_decision("STEP_DIAGNOSIS", ...)`
2. Pass it as a `prev_diagnosis` kwarg into the next RSG call so the model builds on its own reasoning

**Impact:** Reduces repetitive mistakes within a single task execution. Currently the model can repeat the same failing path because it only has a boolean "prev step failed" with no structured context on *why*.

---

## P2 — Persistent App Knowledge Store

**What:** New `services/app_knowledge.py` — `AppKnowledgeStore` class storing *structural* facts about app layouts learned during successful task executions.

**Why:** Reflexion captures task-level failure lessons (ephemeral, task-specific). App layout facts are different — they're stable across sessions. "Spotify Liked Songs is under Library tab" is always true; discovering it once should benefit all future tasks.

**Interface:**
```python
class AppKnowledgeStore:
    async def record_successful_path(self, app: str, goal_type: str, path: List[str]) -> None:
        """Called on task success. e.g. record("spotify", "liked_songs", ["Library tab", "Liked Songs"])"""

    async def get_app_hints(self, app: str, goal_type: str) -> str:
        """Returns formatted hint string for RSG prompt injection."""
```

**Storage:** JSON files at `data/app_knowledge/{app}.json`, keyed by `goal_type`. Written only on **successful** task completion — never on failure, so only verified paths accumulate (success reinforcement pattern).

**Wiring:**
- Inject `app_hints` into RSG prompt as highest-priority context block, before reflexion lessons
- Detect app from `goal.original_utterance` using the same `_APP_NAMES` list in `ReflexionService`

---

## P3 — Post-Phase Reflection Summary

**What:** After each skeleton phase completes in the coordinator, run a lightweight LLM call (~100 tokens) summarizing what the agent learned about the screen/app during that phase.

**Why:** Cross-phase context is carried only by `__agent_memory__` (VLM-chosen freeform). The phase boundary is a natural checkpoint for consolidation: "Phase 1 established that Search leads to a dead end; Phase 2 should go via Library instead."

**Where:** In `agents/coordinator.py`, at the `PHASE_COMPLETE` log event (around line 1530). Add a non-blocking background call to generate and store a `phase_summary` string. Pass this forward as `agent_memory` seed for the next phase's RSG calls.

**Tradeoff:** Adds one LLM call per phase (~100ms latency, ~200 tokens). Only worthwhile for tasks with 3+ phases. Could gate behind a `phase_reflection_enabled` settings flag.

---

## Completed P0 Items (reference)

| Fix | Location | Summary |
|-----|---------|---------|
| G1 — HITL never called | `coordinator.py:559` | Coordinator now routes `ask_user`/`stuck` to HITLService |
| G2 — Unbounded history | `coordinator.py` | `step_memory` capped |
| G3 — No error taxonomy | `utils/error_types.py` | Structured error types added |
| G4 — No token budget cap | `utils/token_tracker.py` | Budget enforcement added |
| R0a — Goal key too coarse | `reflexion_service.py` | App name appended to goal key |
| R0b — Lessons only on abort | `coordinator.py` | Also written on success with replanning |
