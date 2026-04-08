---
last_verified: 2026-04-08
source_files: [services/hitl_service.py]
status: current
---

# HITL Service

**File:** `services/hitl_service.py`

---

## Overview

Human-in-the-Loop service manages questions that AURA needs a human to answer during task execution. Questions are surfaced to the Android app (via TTS) and the user's voice answer resolves the pending question, allowing the coordinator to continue.

---

## Question Types

```python
class HITLQuestionType(Enum):
    CONFIRMATION      # Yes/No — "Are you sure you want to delete this?"
    SINGLE_CHOICE     # Pick one from a list
    MULTIPLE_CHOICE   # Pick multiple from a list
    TEXT_INPUT        # Free text answer
    NOTIFICATION      # Informational only (no answer needed)
    ACTION_REQUIRED   # User must physically do something
    CHOICE_WITH_TEXT  # Combination: pick an option AND provide text
```

---

## Key Data Classes

### `HITLQuestion`
```python
@dataclass
class HITLQuestion:
    question_id: str
    question_type: HITLQuestionType
    question_text: str
    options: Optional[List[str]]          # for choice-type questions
    tts_text: Optional[str] = None        # spoken text for Android TTS (may differ from question_text)
    timeout_seconds: float = DEFAULT_TIMEOUT  # default: 60.0
    metadata: dict = field(default_factory=dict)
```

The `tts_text` field enables the backend to control exactly what is spoken to the user — useful when `question_text` contains UI elements or formatting that sounds awkward when read aloud.

### `HITLResponse`
Contains the user's answer with type-specific fields (selected option, text input, confirmation boolean).

---

## Async Waiting Pattern

```python
_pending_questions: Dict[str, asyncio.Future]
```

When the coordinator encounters a decision point requiring human input:
1. `ask_question(question)` creates an `asyncio.Future` keyed by `question_id`
2. Coordinator `await`s the future (up to `timeout_seconds`)
3. Android app receives the question, TTS speaks it
4. User speaks answer → WebSocket router calls `register_voice_answer(question_id, answer)`
5. `register_voice_answer()` resolves the `Future` with the user's answer
6. Coordinator unblocks and continues

---

## Barge-In Support (Fix G7)

The same `register_voice_answer()` mechanism enables **barge-in**: if the user speaks while AURA is still processing a previous step, the WebSocket router checks for a pending HITL question before dispatching a new task. If found, the utterance is treated as the HITL answer rather than a new command.

This was the G7 fix: previously there was no way for voice to resolve a pending HITL question. Now the router checks HITL pending state first in the audio message handler.

---

## Timeout

`DEFAULT_TIMEOUT = 60.0` seconds. On timeout, the coordinator receives a timeout signal and can choose to:
- Use a default/safe answer
- Mark the subgoal as failed
- Escalate to task abort

---

## Integration Points
- `agents/coordinator.py` — calls `ask_question()` at `ask_user` / `stuck` decision points
- `api_handlers/websocket_router.py` — calls `register_voice_answer()` on audio messages when HITL pending
- Android app (`UI/`) receives HITL questions via WebSocket and triggers Android TTS using `tts_text`
