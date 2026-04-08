---
last_verified: 2026-04-08
source_files: [services/reflexion_service.py]
status: current
---

# Reflexion Service

**File:** `services/reflexion_service.py`

---

## Overview

Implements **verbal reinforcement learning** (Reflexion pattern): after task failures, an LLM generates a natural language "lesson" about what went wrong. On the next attempt with a similar goal, the lesson is injected into the RSG prompt to guide the model away from the same mistake.

---

## `_ACTION_BUCKETS` — Goal Key Normalization

Ten broad categories used to group similar goals into shared lesson pools:

| Bucket | Example phrases |
|--------|----------------|
| `open_app` | "open", "launch", "start" |
| `send_message` | "send", "message", "text", "chat" |
| `make_call` | "call", "dial", "phone" |
| `play_media` | "play", "music", "video", "podcast" |
| `search` | "search", "find", "look up" |
| `navigate` | "go to", "navigate", "scroll" |
| `take_screenshot` | "screenshot", "capture" |
| `settings` | "settings", "toggle", "enable", "disable" |
| `email` | "email", "mail", "compose" |
| `social` | "post", "tweet", "share" |

### Fix R0a — App-scoped goal keys
`_goal_key()` now appends the app name so lessons don't bleed across apps:
```python
# Before: "play_media"
# After: "play_media__spotify" vs "play_media__youtube"
```
Detected via `_APP_NAMES` list matched against `goal.original_utterance`.

---

## Lesson Generation

### `generate_lesson(goal, step_history, failure_reason) -> str`
- Takes the last **10 steps** of `step_history` (full steps would overflow LLM context)
- Sends to LLM with prompt: *"Given this goal and these steps, what went wrong and what should be done differently next time?"*
- Returns a concise natural language lesson string

### Storage
Lessons stored as JSON at `data/reflexion_lessons/{goal_key}.json`:
```json
{
  "lessons": [
    "Spotify Liked Songs requires navigating to Library tab first, not Search",
    "..."
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

---

## Lesson Retrieval

### `get_lessons_for_goal(goal, max_lessons=3) -> List[str]`
- Reads from the JSON file keyed by `_goal_key(goal)`
- Returns up to `max_lessons` most recent lessons
- Called by coordinator before building the RSG prompt — lessons injected as context

---

## When Lessons Are Written

### Fix R0b — Lessons written on success too
Previously, lessons were only written on full task abort. This missed recovery paths.

Now lessons are also written when:
- **Task fails** (abort) — captures what went wrong
- **Task succeeds** AND `replan_count > 0` — captures the recovery path that worked

This means "I failed trying X, then succeeded by doing Y" is also recorded, benefiting future attempts.

---

## Threading

`ReflexionService` uses `ThreadPoolExecutor(max_workers=2)` for lesson generation — it's a non-blocking background operation that shouldn't slow down the task completion response.

---

## Integration Points
- `agents/coordinator.py` calls `generate_lesson()` on failure/success-with-replanning
- `agents/coordinator.py` calls `get_lessons_for_goal()` at RSG prompt build time
- Lesson data lives in `data/reflexion_lessons/` (gitignored; session-persistent)
