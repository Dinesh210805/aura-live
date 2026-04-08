---
last_verified: 2026-04-08
source_files: [agents/verifier_agent.py]
status: current
---

# Agent: Verifier

**File**: `agents/verifier_agent.py`

---

## Role

`VerifierAgent` runs post-action verification. After the `ActorAgent` executes a gesture, the verifier checks if the action produced the expected outcome.

---

## Settle Delays

Before checking the screen, the verifier waits for the UI to settle:

```python
ACTION_SETTLE_DELAYS = {
    "tap": 0.8,         # seconds
    "open_app": 3.0,    # apps take longer to load
    "back": 1.0,
    "type": 0.3,
    # default: 0.5s
}
```

Without these delays, the screenshot captured for verification might show the screen mid-transition, leading to false negatives.

---

## Error Indicator Detection

The verifier scans the post-action screen for error indicators:

```python
ERROR_INDICATORS = [
    "unfortunately", "has stopped", "not responding",
    "connection error", "no internet", "network error",
    "failed to load", "something went wrong",
    "error", "crashed", "unable to connect"
]
```

If any of these appear in the UI text or content descriptions, verification fails immediately.

---

## Verification Methods

### `verify_action(action, pre_state, post_state) -> VerificationResult`

The main verification entry point:

1. Waits for `ACTION_SETTLE_DELAYS[action_type]`
2. Captures new screenshot (via perceiver)
3. Checks error indicators
4. For `COMMIT_ACTIONS`: calls `semantic_verify()` via RSG
5. Returns `VerificationResult`

### `semantic_verify(goal, action, screen_state) -> bool`

Uses `ReactiveStepGenerator` with a minimal system prompt (`PromptMode.MINIMAL`) to ask:
"Did this action succeed in moving toward the goal?" (G15 fix — `VerifierAgent` now uses `PromptMode.MINIMAL` instead of the full agent prompt)

---

## COMMIT_ACTIONS

Actions that change persistent state and require semantic verification:
- `type` (text was typed correctly)
- `submit` (form was submitted)
- `confirm_payment`, `delete`, `send_message`

Non-commit actions (tap, scroll, back) only get the fast heuristic check.

---

## VerificationResult

```python
@dataclass
class VerificationResult:
    success: bool
    confidence: float
    evidence: str           # What the verifier observed
    suggested_retry: bool   # Whether coordinator should retry
    error_detected: bool
    error_type: Optional[str]
```

The coordinator reads `success` and `suggested_retry` to decide whether to advance or escalate the retry ladder.
