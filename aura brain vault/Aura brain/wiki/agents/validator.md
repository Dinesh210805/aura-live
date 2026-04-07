# Agent: Validator

**File**: `agents/validator.py`

---

## Role

`ValidatorAgent` performs rule-based pre-execution validation of planned actions. It has **zero LLM calls** — entirely rule-based for speed.

Called by the coordinator *before* sending an action to `ActorAgent`.

---

## Validation Checks

1. **Action exists** — `action_type` is not None or empty
2. **Valid action** — `action_type` matches ACTION_REGISTRY or a common alias (e.g., "click" → "tap")
3. **Required fields** — checks that required parameters for the action type are present
4. **Dangerous actions** — flags sensitive actions for extra scrutiny
5. **Confidence threshold** — rejects actions with `confidence < 0.3`

---

## ValidationResult

```python
@dataclass
class ValidationResult:
    valid: bool
    issues: List[str]           # List of validation failures
    suggestions: List[str]      # Suggestions for fixing issues
    requires_confirmation: bool # True for high-risk actions
```

---

## Common Aliases

The validator accepts shorthand action names and normalizes them:
- `"click"` → `"tap"`
- `"press"` → `"tap"`
- `"navigate"` → `"open_url"`
- `"type_in"` → `"type"`

This handles cases where the LLM uses a common synonym rather than the exact registered action type.

---

## Dangerous Actions

Actions flagged as dangerous trigger `requires_confirmation=True`:
- Actions that send data (type + submit patterns)
- Actions targeting sensitive app features (payments, settings)
- Actions with very high confidence on irreversible steps

The coordinator respects `requires_confirmation` by calling `HITLService.ask_confirmation()` before proceeding.
