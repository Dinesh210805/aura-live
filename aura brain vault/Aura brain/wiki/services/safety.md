# Safety Services

Two independent safety layers protect AURA: **PromptGuard** (input screening) and **PolicyEngine** (gesture gating).

---

## PromptGuard

**File:** `services/prompt_guard.py` (100 lines)

### Purpose
Screens all voice input transcriptions before they reach any agent. Blocks prompt injection, jailbreak attempts, and unsafe instructions.

### Model
```python
MODEL = "meta-llama/llama-prompt-guard-2-86m"
```
Served via Groq API (very fast, lightweight 86M parameter model).

### `is_safe(user_input: str) -> Tuple[bool, float]`
- Calls Groq chat with `max_tokens=20, temperature=0.0`
- Returns `(is_safe: bool, confidence: float)`
- **Label interpretation**:
  - `BENIGN` or `SAFE` → safe, allow through
  - `INJECTION`, `JAILBREAK`, or `UNSAFE` → blocked
- **Fail-safe**: any exception (timeout, API error, unknown label) → defaults to `(True, 0.0)` (safe). This prevents PromptGuard availability from blocking legitimate commands.
- **Timeout**: 8 seconds

### Integration
Called in `api_handlers/websocket_router.py` after STT transcription, before task dispatch.

---

## PolicyEngine

**File:** `services/policy_engine.py` (380 lines)

### Purpose
Gates every gesture execution. OPA (Open Policy Agent) Rego policies are the authoritative layer; a Python fallback provides equivalent rules when OPA is unavailable.

### Key Data Classes

```python
@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool
    confirmation_message: Optional[str]
    policy_violated: Optional[str]
    metadata: dict

@dataclass
class ActionContext:
    action_type: str
    target: str
    app_name: str
    package_name: str
    text_content: Optional[str]
    coordinates: Optional[tuple]
    user_id: str
    session_id: str
    timestamp: float
    previous_actions: List[str]
    action_count_last_minute: int
```

### Blocked Actions (Hard Blocks)
```python
BLOCKED_ACTIONS = {
    "factory_reset",
    "wipe_data",
    "delete_all",
    "format_storage",
    "root_device",
    "install_unknown_apk"
}
```
These are **always blocked**, no exceptions.

### Other Blocked Lists
- `BLOCKED_FINANCIAL_APPS` — apps like mobile banking that trigger confirmation or block
- `BLOCKED_AUTH_APPS` — authentication apps
- `BANKING_PATTERNS` — text patterns that indicate banking operations
- `CONFIRMATION_ACTIONS` — action types that require user confirmation before execution

### `evaluate(action_context: ActionContext) -> PolicyDecision`
Runs 5 checks in sequence. Returns on first failure:
1. **blocked_actions** — hard block list above
2. **sensitive_apps** — financial/auth app check
3. **confirmation_required** — certain action types need confirmation
4. **rate_limits** — `action_count_last_minute` cap
5. **dangerous_content** — `text_content` checked for patterns:
   - `"password is"`, `"pin is"`, `"ssn is"`, `"social security"`, `"credit card"`, `"cvv"`

### Fail-Safe Behavior
When OPA is unavailable (network error, service down), the Python fallback rules run. When even the Python fallback errors, the policy is **permissive** (allow). This prevents infrastructure unavailability from blocking legitimate automation tasks.

### Integration
Called in `services/gesture_executor.py` before every gesture is sent to the Android device. Critical invariant: **every gesture passes through OPA policy check**.
