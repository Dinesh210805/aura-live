---
last_verified: 2026-04-08
source_files: [aura_graph/edges.py]
status: current
---

# LangGraph — Conditional Routing (Edges)

**File**: `aura_graph/edges.py`

---

## Overview

All conditional routing logic lives in `edges.py` as pure functions. This separates routing concerns from node logic, making the state machine easy to reason about.

**Performance note**: Settings are cached at import time (`_SETTINGS = _get_settings()`) to avoid per-transition Pydantic overhead on hot paths.

---

## `route_from_start(state: TaskState) -> str`

Called at graph entry to route based on input type:

```
input_type == "text" or "streaming"  →  "parse_intent"   (skip STT)
input_type == "audio"                →  "stt"             (transcribe first)
```

---

## `should_continue_after_intent_parsing(state: TaskState) -> str`

The most complex routing function. Determines what happens after `CommanderAgent` parses the intent.

```
status == "web_search_needed"          →  "web_search"
status == "conversational"             →  "speak"          (no device action)
intent has NO_UI flag                  →  "coordinator"     (direct dispatch)
utterance matches multi-step regex     →  "coordinator"     (e.g. "open X and do Y")
default                                →  "coordinator"
```

**Conversational detection**: Uses a word-boundary regex on the utterance to detect pure-conversation requests that don't require device interaction (greetings, questions, etc.).

**Multi-step detection**: Regex checks for connectors like " and ", "/", " then " — routes these directly to coordinator to handle as compound goals.

---

## `should_continue_after_perception(state: TaskState) -> str`

Routes after the perception node captures screen state:

```
status == "perception_failed"          →  "error_handler"
status == "screen_reading"             →  "speak"           (describe screen)
else                                   →  "coordinator"     (execute task)
```

---

## `should_continue_after_error_handling(state: TaskState) -> str`

Routes after the error handler runs:

```
status == "perception_failed"          →  "perception"      (retry perception)
  AND retry_count < MAX_PERCEPTION_RETRIES
else                                   →  "speak"           (report failure)
```

Only retries perception if the failure was specifically perception — other errors go directly to speak.

---

## `should_continue_after_coordinator(state: TaskState) -> str`

Routes after the coordinator loop step:

```
status == "completed"                  →  "speak"
status == "failed"                     →  "speak"
status == "needs_perception"           →  "perception"
status == "web_search_needed"          →  "web_search"
else (still executing)                 →  "coordinator"     (loop back)
```

---

## The 5-Stage Retry Ladder

The retry ladder is not an edge function — it lives inside the coordinator's execution loop. But its results affect the `status` field that the edges above read.

| Stage | Strategy | What coordinator does |
|-------|----------|----------------------|
| 0 | `SAME_ACTION` | Retry identical action on same target |
| 1 | `ALTERNATE_SELECTOR` | Ask VLM to select a different element |
| 2 | `SCROLL_AND_RETRY` | Scroll screen, retry after |
| 3 | `VISION_FALLBACK` | Use full VLM analysis instead of rule-based |
| 4 | `ABORT` | Give up on current subgoal, report failure |

Each `Subgoal` advances through this ladder independently via `subgoal.escalate_strategy()`.

---

## Routing Summary Diagram

```
__start__
    │
    ▼ route_from_start
    ├── audio ─────────────────────────────────────► stt
    └── text/streaming ─────────────────────────► parse_intent
                                                       │
                                          should_continue_after_intent_parsing
                                                       │
                        ┌──────────────────────────────┼──────────────────┐
                        ▼                              ▼                  ▼
                   web_search                     coordinator           speak
                        │                              │               (end)
                        └──────────────────────────────┤
                                                       │ should_continue_after_coordinator
                                          ┌────────────┼────────────┐
                                          ▼            ▼            ▼
                                       speak     perception    coordinator (loop)
                                                       │
                                     should_continue_after_perception
                                          │            │
                                     error_handler coordinator
                                          │
                               should_continue_after_error_handling
                                          │            │
                                     perception      speak
```
