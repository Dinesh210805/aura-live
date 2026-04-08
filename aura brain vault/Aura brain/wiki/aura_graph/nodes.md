---
last_verified: 2026-04-08
source_files: [aura_graph/core_nodes.py, aura_graph/nodes/]
status: current
---

# LangGraph — Node Implementations

**Files**: `aura_graph/core_nodes.py`, `aura_graph/nodes/`

---

## Node Overview

Each node in the LangGraph graph is a function that takes `TaskState` and returns a partial state update dict. LangGraph calls the appropriate reducer for each returned field.

---

## Helper Functions

### `add_workflow_step(state, step_name, details)`

Utility used by most nodes to append an entry to `executed_steps` with the node name, timestamp, and arbitrary details dict.

### `track_agent_usage(state, agent_name, tokens_used)`

Records token usage for a specific agent call into `state["token_usage"]`.

---

## `stt` Node

- Calls `stt_service.transcribe(audio_data)`
- Returns `{transcript: str, status: "transcribed"}`
- Clears `audio_data` from state after transcription

**STT Service**: `services/stt.py` — Groq Whisper Large v3 Turbo

---

## `parse_intent` Node

- Calls `commander_agent.parse(transcript or text_input, context)`
- Returns `{intent: dict, status: str}`
- Status is set to `"web_search_needed"`, `"conversational"`, or `"ready"` based on intent classification

**Commander Agent**: See [agents/commander.md](../agents/commander.md)

---

## `coordinator` Node

The most complex node — runs one iteration of the perceive→decide→act→verify loop.

- Calls `coordinator_agent.execute_step(state)`
- Returns partial state update with new `status`, updated `goal`, `executed_steps`, `perception_bundle`, etc.
- Loops back to itself until `status` becomes `"completed"` or `"failed"`

**Coordinator Agent**: See [agents/coordinator.md](../agents/coordinator.md)

---

## `perception` Node

- Calls `perceiver_agent.perceive(session_id, hint)`
- Returns `{perception_bundle: PerceptionBundle, status: str}`
- Sets `status = "perception_failed"` if PerceptionController returns no data

**Perceiver Agent**: See [agents/perceiver.md](../agents/perceiver.md)

---

## `speak` Node

1. Calls `responder_agent.generate(state)` to produce `spoken_response`
2. Calls `tts_service.speak(spoken_response)` or sends TTS WebSocket message
3. Returns `{spoken_response: str, status: "completed"}`

**TTS path**:
- `ANDROID_TTS_ENABLED=true` (default): sends `{"type": "tts_response", "text": ..., "voice": ...}` over WebSocket
- `ANDROID_TTS_ENABLED=false`: synthesizes WAV server-side with Edge-TTS and streams bytes

---

## `error_handler` Node

- Examines `state["status"]` and `state["errors"]`
- Increments `state["error_retry_count"]`
- Tries to recover or constructs an error `spoken_response`
- Returns updated status for routing

---

## `web_search` Node

- Extracts search query from intent
- Calls `TavilyClient.search()` (requires `TAVILY_API_KEY`)
- Formats results and sets `spoken_response` directly (bypasses coordinator)
- Returns `{spoken_response: str, status: "completed"}`

If Tavily is unavailable, falls back to a "I can't search right now" response.

---

## Phase Timing (G10 Fix)

Nodes record phase start/end in `state["phase_timings"]`:
```python
# At node entry:
state_update["phase_timings"] = {f"{node_name}_start": time.time()}
# At node exit:
state_update["phase_timings"] = {f"{node_name}_end": time.time()}
```

This enables post-mortem analysis of which phases are slowest.
