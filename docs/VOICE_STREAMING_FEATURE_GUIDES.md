# AURA Voice Streaming Feature Guides (Agent Implementation Manual)

This document converts the planned voice upgrade into **agent-ready implementation guides**.

Source-of-truth inputs reviewed:
- `docs/VOICE_UPGRADE_IMPLEMENTATION_PLAN.md`
- `docs/COPILOT_IMPLEMENTATION_GUIDE.md`
- Current implementation in `services/llm.py`, `services/tts.py`, `services/stt.py`, `api_handlers/websocket_router.py`, `aura_graph/nodes.py`, `aura_graph/state.py`, `config/settings.py`
- Original SDK docs via Context7 + Exa:
  - Groq Python SDK async streaming (`AsyncGroq`, `stream=True`, `async for chunk in stream`)
  - Google GenAI Python async streaming (`client.aio.models.generate_content_stream`)
  - edge-tts stream iterator behavior (`Communicate(...).stream()` with `chunk["type"] == "audio"`)
  - pydantic-settings patterns for env-driven config
  - asyncio queue producer/consumer sentinel/cancellation patterns

---

## Executive Feasibility Verdict

**Yes — these updates are feasible in your current codebase with moderate risk.**

What already exists and helps:
- STT streaming entry point already exists (`STTService.transcribe_streaming`) and conversation websocket is mature.
- Conversation orchestration + session management already exists in `/ws/conversation`.
- TTS and LLM services are centralized and can be safely extended without rewriting graph core.

Main gaps to implement:
- No LLM token streaming path in `LLMService`.
- No sentence processor / queue / stream orchestrator.
- No incremental audio protocol in websocket conversation response path.
- Graph `speak_node` always generates full audio blob; no streaming bypass flag.

Important repo note:
- Root has `requirements copy.txt` but no canonical `requirements.txt`. Standardize dependency source before rollout.

---

## Feature 0 — Streaming LLM Infrastructure

### Goal
Add non-blocking LLM token streaming so downstream sentence/TTS pipeline can start before full completion.

### Current state
- `services/llm.py` has only synchronous `run()` and provider-specific blocking methods.

### Feasibility
- **High**. Existing provider abstraction supports a clean addition.

### Official doc alignment
- Groq: use `AsyncGroq().chat.completions.create(..., stream=True)` and `async for chunk in stream`.
- Gemini: use `await client.aio.models.generate_content_stream(...)` and iterate chunks.

### Required changes
- `services/llm.py`
  - Add async client member for Groq (`groq.AsyncGroq`).
  - Add `async def run_streaming(...)-> AsyncGenerator[str, None]`.
  - Implement provider-specific streaming adapters (`_stream_groq`, `_stream_gemini`, optional `_stream_nvidia`).
  - Preserve `run()` behavior for backward compatibility.
- `config/settings.py`
  - Add `streaming_llm_model`, `streaming_llm_provider`, `streaming_llm_temperature`, `streaming_llm_max_tokens`.

### Agent coding guardrails
- Do not break existing `run()` call sites.
- Yield only non-empty text deltas.
- Ensure cancellation is propagated (`CancelledError` re-raised).
- Log first-token timestamp hook for telemetry integration.

### Acceptance checks
- Unit test validates >=3 yielded chunks on long prompt.
- Cancellation test stops generator cleanly without leaked tasks.

---

## Feature 1 — Sentence Processor

### Goal
Convert token stream into stable, TTS-ready sentence units.

### Current state
- No sentence segmentation service exists in primary codebase.

### Feasibility
- **High**. Pure utility layer.

### Official/pattern alignment
- Streaming voice systems split on sentence boundaries and flush residual tail.
- Handle abbreviation and decimal edge cases to avoid premature splits.

### Required changes
- New file: `services/sentence_processor.py`
  - `process_chunk(chunk: str) -> list[str]`
  - `flush() -> str | None`
  - Dedup guard + `min_words` threshold.
- `config/settings.py`
  - Add `sentence_min_words`.

### Agent coding guardrails
- Keep deterministic behavior (no LLM in this stage).
- Never drop residual buffer on normal completion; return via `flush()`.

### Acceptance checks
- Tests for abbreviations (`Dr.`, `e.g.`), decimals (`3.14`), empty chunks, trailing partial sentence.

---

## Feature 2 — Per-session Sentence Queue

### Goal
Decouple LLM production speed from TTS consumption speed.

### Current state
- No per-session async queue abstraction in current services.

### Feasibility
- **High**. Natural fit with asyncio in existing websocket code.

### Official/pattern alignment
- asyncio producer-consumer best practice: bounded queue + clear completion signal + clean cancellation.

### Required changes
- New file: `services/sentence_queue.py`
  - `SentenceMessage` dataclass (`content`, `is_last`, `sequence_number`)
  - `SentenceQueue` with `put/get/clear/remove_session`
- `config/settings.py`
  - Add `sentence_queue_maxsize`, `sentence_queue_timeout`.

### Agent coding guardrails
- Bound queue size for backpressure.
- Use explicit end marker (`is_last=True`) rather than implicit timeout-only completion.
- Ensure `clear(session_id)` drains safely without blocking.

### Acceptance checks
- Ordering consistency.
- Isolation between two concurrent sessions.
- Mid-stream clear does not deadlock consumer.

---

## Feature 3 — Streaming TTS

### Goal
Emit audio progressively per sentence/chunk instead of one full WAV payload.

### Current state
- `services/tts.py` buffers full MP3 and converts full blob to WAV before returning.

### Feasibility
- **Medium-High**. API supports chunked input; audio format decision must be coordinated with Android player.

### Official doc alignment
- edge-tts `Communicate(...).stream()` yields chunk events where `type == "audio"` carries bytes.

### Required changes
- `services/tts.py`
  - Add provider abstraction (`TTSProvider`, `EdgeTTSProvider`).
  - Add `async def speak_streaming(...)-> AsyncGenerator[bytes, None]`.
  - Keep `speak_async/speak` unchanged.
- `config/settings.py`
  - Add `tts_streaming_chunk_size`, `tts_audio_format`.

### Agent coding guardrails
- Keep backward compatibility for existing WAV consumers.
- Choose one stream format first release (recommended: PCM16 mono with explicit metadata frame).
- Do not transcode per tiny packet; batch to configurable chunk size.

### Acceptance checks
- First audio chunk delivered before full text completes.
- Empty text returns no chunks.
- Voice mapping still works for PlayAI aliases.

---

## Feature 4 — Stream Manager Orchestrator

### Goal
Coordinate dual tasks: LLM producer and TTS consumer per session.

### Current state
- No dedicated orchestrator service; websocket handler mixes control flow directly.

### Feasibility
- **High**. Existing websocket async model supports this cleanly.

### Required changes
- New file: `services/stream_manager.py`
  - `start_streaming_response(...)` (spawns producer + consumer tasks)
  - `_produce_sentences(...)`
  - `_consume_and_stream(...)`
  - `cancel(session_id)`

### Agent coding guardrails
- `asyncio.wait(..., return_when=FIRST_EXCEPTION)` to fail fast.
- Ensure both tasks are cancelled/joined in `finally`.
- Always remove session resources on completion/disconnect.

### Acceptance checks
- Producer/consumer both terminate on exception.
- Cancel call stops active stream within target latency budget.

---

## Feature 5 — WebSocket Protocol Upgrade

### Goal
Upgrade `/ws/conversation` to support incremental transcript/text/audio events.

### Current state
- Response is mostly batch-style: one `response` payload (and optionally one full audio blob from graph).

### Feasibility
- **Medium**. Requires protocol evolution and Android/client coordination, but server side is straightforward.

### Required changes
- `api_handlers/websocket_router.py`
  - Add new outbound types: `partial_transcript`, `response_start`, `response_sentence`, `audio_stream_start`, `audio_chunk`, `audio_sentence_end`, `response_end`.
  - Add inbound `barge_in` handling.
  - Keep current `response` flow behind backward-compat flag.
- `aura_graph/state.py`
  - Add `streaming: Optional[bool]`.
- `aura_graph/nodes.py` (`speak_node`)
  - If `streaming=True`, return text only; skip full audio generation.

### Agent coding guardrails
- Parse `start` message option like `streaming: true`.
- If absent/false, execute legacy behavior unchanged.
- Never send both full `spoken_audio` and streamed chunks for same turn.

### Acceptance checks
- Correct message order for streaming path.
- Legacy client still receives prior `response` format without crashes.

---

## Feature 6 — Barge-in / Turn Interruption

### Goal
User speech can interrupt assistant playback immediately.

### Current state
- No explicit barge-in message type in active websocket conversation flow.

### Feasibility
- **High** server-side, **Medium** full end-to-end (depends on Android state transitions).

### Required changes
- `services/stream_manager.py`
  - `cancel(session_id)` sets inactive flag, clears queue, cancels tasks.
- `api_handlers/websocket_router.py`
  - Handle inbound `barge_in` and emit `audio_stream_stopped`.

### Agent coding guardrails
- Cancellation must be idempotent.
- Ensure no stale chunks are sent after cancellation.

### Acceptance checks
- Time from `barge_in` to no further `audio_chunk` < target threshold.

---

## Feature 7 — Improved Streaming STT (Chunk Strategy)

### Goal
Improve partial transcript quality and continuity without changing provider initially.

### Current state
- `transcribe_streaming` exists but still calls batch transcribe per buffered chunk.

### Feasibility
- **High** for overlap-window strategy.

### Required changes
- `services/stt.py`
  - Add overlap buffer support (e.g., keep trailing context frames).
  - Return quicker partials in `/ws/audio-stream` and conversation mode.
- `api_handlers/websocket_router.py`
  - Harmonize message naming (`partial_transcript` preferred) while preserving existing `partial` if needed.

### Agent coding guardrails
- Do not block on final-quality decoding for partial UI updates.
- Reconcile final transcript at end-turn.

### Acceptance checks
- Partial transcript updates occur consistently during speech.
- Final transcript remains accurate and stable.

---

## Feature 8 — Optional Server-side VAD

### Goal
Add robust server-side speech/silence detection as optional enhancement.

### Current state
- No server VAD service in core backend.

### Feasibility
- **Medium** (new dependencies + CPU considerations), should stay opt-in.

### Required changes
- New file: `services/vad.py`
- `config/settings.py`: `enable_server_vad`, thresholds.
- Dependency source: add `silero-vad`/`onnxruntime` in canonical requirements file.

### Agent coding guardrails
- Feature flag default `False`.
- If VAD unavailable, graceful fallback to current client-end-turn flow.

### Acceptance checks
- Auto endpointing works when enabled.
- No behavior change when disabled.

---

## Feature 9 — Voice Telemetry

### Goal
Measure true latency bottlenecks and barge-in behavior per turn.

### Current state
- Logging exists, but no per-turn structured voice metrics object.

### Feasibility
- **High**.

### Required changes
- New file: `services/voice_telemetry.py`
- Hook capture points in websocket and stream manager.
- Emit structured logs (JSON) at turn completion.
- `config/settings.py`: `enable_voice_telemetry`.

### Agent coding guardrails
- Use monotonic timestamps for durations.
- Do not fail request path if telemetry write fails.

### Acceptance checks
- Metrics include STT end, first token, first sentence, first audio, total turn, barge-in.

---

## Feature 10 — Android Streaming Client Support (Protocol Consumer)

### Goal
Consume stream events and play audio incrementally on device.

### Current state
- Backend currently sends mostly batch response payloads; Android integration for stream events is not active in this repo.

### Feasibility
- **Externally feasible** (requires Android app repo updates in lockstep).

### Required backend contract (must remain stable)
- Message event schema and ordering from Feature 5.
- Audio format metadata on stream start.
- Explicit stream stop/end events.

### Agent coding guardrails
- Treat Android changes as a separate coordinated rollout item.
- Keep server fallback path for old app builds.

---

## Cross-cutting Guardrails for All Agents

1. **Backward compatibility first**
   - Keep current `/ws/audio-stream`, `/ws/audio-stream-final`, and non-streaming `/ws/conversation` behavior.
2. **Feature flags**
   - Gate new behavior behind settings and per-session handshake (`streaming=true`).
3. **One source of dependencies**
   - Create/standardize root `requirements.txt` (current repo uses `requirements copy.txt`).
4. **Cancellation safety**
   - All stream tasks must be cancellable without zombie tasks.
5. **No duplicate TTS paths**
   - In streaming mode, graph should return text; websocket owns stream TTS delivery.

---

## Suggested Implementation Sequence for Your Team

1. Feature 0 (`LLMService.run_streaming`) + tests
2. Feature 1/2 (`sentence_processor`, `sentence_queue`) + tests
3. Feature 3 (`TTSService.speak_streaming`) + tests
4. Feature 4 (`StreamManager`) + integration tests
5. Feature 5/6 (websocket protocol + barge-in) + backward compat tests
6. Feature 9 telemetry hooks
7. Feature 7 STT overlap refinements
8. Feature 8 optional server VAD
9. Feature 10 Android rollout

---

## Definition of Done (Per Feature)

A feature is done only when all are true:
- Code implemented with backward compatibility
- Unit/integration tests added and passing
- Message contract documented
- Feature flag and defaults set
- Failure/cancellation paths verified
- Observability hooks added where applicable

---

## Final Recommendation

Proceed with the upgrade. The architecture and codebase are ready for this with staged delivery.

The lowest-risk, highest-impact slice is:
**Feature 0 + 1 + 2 + 4 + 5 (text streaming first), then Feature 3 (audio streaming)**.

This gives immediate UX gains while keeping rollback simple.
