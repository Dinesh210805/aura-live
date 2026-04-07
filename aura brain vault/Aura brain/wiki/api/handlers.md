# API Handlers

**Primary file:** `api_handlers/websocket_router.py`

---

## WebSocket Router

The WebSocket router is the entry point for all real-time device communication. Two critical globals are initialized at module level:

```python
conversation_manager = ConversationManager(max_turns=5)
```

`ConversationManager` maintains a rolling 5-turn conversation buffer per session — used for the conversational (non-task) intent tier.

---

## `_execute_task()` — Core Task Dispatch

Called after STT transcription, PromptGuard screening, and intent classification.

### Two execution paths:

**Path 1 — AuraQueryEngine (when `engine` is not None)**
```python
async for update in engine.stream_task(command, session_id):
    await ws.send_json({
        "type": "progress_update",
        "message": update.message,
        ...
    })
```
Streams `TaskUpdate` events as JSON over the WebSocket in real time. Terminal events: `UpdateType.TASK_COMPLETED`, `UpdateType.TASK_FAILED`.

**Path 2 — Direct streaming (fallback)**
```python
async for chunk in execute_aura_task_from_streaming(command, graph):
    await ws.send_text(chunk)
```
Falls back to `execute_aura_task_from_streaming()` when the query engine is disabled or unavailable.

---

## Audio Message Handler

Order of operations in the audio WebSocket message handler:

1. Decode audio chunk from base64 PCM
2. Accumulate audio until silence detection (VAD)
3. Send accumulated audio to Groq Whisper STT
4. **Check HITL pending first**: if `hitl_service.has_pending_question(session_id)` → call `register_voice_answer()` and return (barge-in support, G7 fix)
5. Run PromptGuard screening
6. Run intent classification (fuzzy_classifier → tier: conversational / simple / medium / complex)
7. Dispatch to `_execute_task()` or conversational handler

---

## Intent Classification Tiers

| Tier | Handling | Example |
|------|---------|---------|
| `conversational` | `ConversationManager.respond()` — no task graph | "What's the weather?" |
| `simple` | Fast path task graph (fewer retry steps) | "Open Chrome" |
| `medium` | Standard task graph | "Search YouTube for jazz music" |
| `complex` | Full task graph with planner | "Go to Settings and enable dark mode" |

---

## HITL Barge-In (G7 Fix)
The audio handler now checks for pending HITL questions **before** running PromptGuard or intent classification. This means the user's spoken answer to "Are you sure?" goes directly to the waiting `asyncio.Future` in `HITLService`, not into a new task dispatch. Without this fix, the answer would have been treated as a new command and potentially started a conflicting task.

---

## Other Handler Files

| File | Purpose |
|------|---------|
| `api_handlers/task_router.py` | REST task submission and polling |
| `api_handlers/device_router.py` | Screenshot, UI tree, direct gesture endpoints |
| `api_handlers/real_accessibility_api.py` | Accessibility tree queries and app listing |
