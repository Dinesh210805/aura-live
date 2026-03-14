# AURA Voice Pipeline Upgrade — Production Implementation Plan

## Executive Summary

This plan transforms Aura's **synchronous, batch-oriented voice pipeline** into a **streaming, interruptible, real-time conversation system** comparable to ChatGPT Voice / Google Assistant. Every decision is grounded in concrete analysis of Aura's current codebase and the five helper repos.

**Current State:** Audio in → full STT → full LLM → full TTS → single WAV blob out (~4-8s latency per turn)  
**Target State:** Audio in → streaming STT → streaming LLM → sentence-queued TTS → chunked audio out (<1s to first audio)

---

## Source Repo Verdict

| Repo | Adopt | What To Adopt | What To Skip |
|------|-------|---------------|--------------|
| **AI-realtime-voice-agent** | **Heavy** | Sentence queue, sentence processor, TTS provider abstraction, stream manager orchestration, dual-task WebSocket pattern | Redis dependency (use asyncio.Queue instead), Deepgram STT (keep Groq), hardcoded system prompt |
| **realtime-whisper** | **Medium** | Pydantic config pattern for all audio/transcription thresholds, logprob-based confidence scoring concept, async iterator pattern for streaming results | Whisper transformers model (keep Groq API), Gradio interface |
| **llm-voice-assistant** | **Selective** | Silero VAD with EMA smoothing, thread-based producer-consumer pipeline concept (adapt to asyncio), sentence-level language detection, TOML-style structured config | Threading (use async), wake-word (already have Porcupine), file-based TTS |
| **llm_sts** | **Selective** | TextSegmenter sentence splitting (adapt for English), per-client send queues, modular service separation pattern | Vosk STT, Chinese-first config, separate port per service |
| **Low-latency-AI-Voice-Assistant** | **Skip** | - | Everything (demo-grade, no streaming, no error handling) |

---

## Architecture Delta: Current vs Target

```
CURRENT PIPELINE (Blocking Sequential)
═══════════════════════════════════════
Client Audio → [AudioBuffer 16KB] → STT (Groq batch) → Intent Parse → Task Execute
→ LLM (batch completion) → TTS (full Edge-TTS → MP3 → WAV) → Base64 WAV → Client

Latency: STT ~800ms + LLM ~2s + TTS ~2s + encode ~200ms = ~5s minimum

TARGET PIPELINE (Streaming Parallel)
═══════════════════════════════════════
Client Audio ──→ [StreamingSTT] ──→ Partial Transcripts → Client (real-time)
                      │
                      ├──→ Final Transcript → Intent Parse → Task Execute
                      │                            │
                      │              ┌──────────────┘
                      │              ▼
                      │    [StreamingLLM] ──→ token stream
                      │              │
                      │              ▼
                      │    [SentenceProcessor] ──→ complete sentences
                      │              │
                      │              ▼
                      │    [SentenceQueue] (asyncio.Queue per session)
                      │              │
                      │              ▼
                      │    [StreamingTTS] ──→ audio chunks per sentence
                      │              │
                      │              ▼
                      │    Client receives sentence audio chunks (real-time)
                      │
Barge-in ◄────────────┘ (client speech detected → cancel queue + TTS)

Latency: STT ~500ms + LLM first token ~300ms + first sentence ~200ms + TTS ~400ms = ~1.4s to first audio
```

---

## Phase 0: Streaming LLM Infrastructure

**Goal:** Make `LLMService` support async token streaming. This unblocks everything else.

### 0.1 Add streaming method to `services/llm.py`

**Source pattern:** `AI-realtime-voice-agent/utils/llm_providers.py` — `BaseLLMProvider.generate_response_stream()`

**What to implement in `services/llm.py`:**

```python
# New method on LLMService
async def run_streaming(
    self,
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    system_prompt: str | None = None,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Yields text chunks as they arrive from the LLM provider."""
```

**Provider implementations:**

| Provider | Streaming API | Notes |
|----------|--------------|-------|
| Groq | `groq.AsyncGroq().chat.completions.create(stream=True)` | Add `groq.AsyncGroq` client alongside existing sync client |
| Gemini | `genai.Client().models.generate_content_stream()` | Already async-capable |
| OpenRouter | `openai.AsyncOpenAI(base_url="https://openrouter.ai/api/v1").chat.completions.create(stream=True)` | Used for intent classification — extend |

**File changes:**
- `services/llm.py` — Add `AsyncGroq` import. Add `run_streaming()` method. Keep existing `run()` untouched.
- `config/settings.py` — Add `streaming_llm_model: str` field (separate model for voice responses, can be faster/cheaper than planning model).
- `requirements.txt` — Verify `groq>=0.9.0` (async streaming support).

**Validation:** Unit test that calls `run_streaming()` and collects ≥5 chunks from a simple prompt.

---

## Phase 1: Sentence Processor

**Goal:** Split streaming LLM output into complete sentences suitable for TTS.

### 1.1 Create `services/sentence_processor.py`

**Source pattern:** `AI-realtime-voice-agent/utils/sentence_processor.py` — `SentenceProcessor`

**Adaptations from source:**
- Source uses regex `(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])$` — works for English but fragile
- **Improvement:** Use a configurable boundary pattern, support abbreviations (Mr., Dr., U.S.) and decimal numbers
- **Add:** Deduplication set (from source), minimum word count check (from source)
- **Skip:** Source's uppercase requirement (breaks for responses starting with lowercase)

```python
# services/sentence_processor.py

class SentenceProcessor:
    """Extracts complete sentences from a streaming token buffer."""

    def __init__(self, min_words: int = 2):
        self.buffer: str = ""
        self.processed: set[str] = set()
        self.min_words = min_words
        # Regex: sentence ends at .!? followed by space or end, but not after abbreviations
        self._abbreviations = {"Mr.", "Mrs.", "Dr.", "Sr.", "Jr.", "vs.", "etc.", "e.g.", "i.e."}

    def process_chunk(self, chunk: str) -> list[str]:
        """Feed a token chunk, return any newly completed sentences."""
        ...

    def flush(self) -> str | None:
        """Return remaining buffer content (last incomplete sentence)."""
        ...
```

**File:** `services/sentence_processor.py` — new file  
**Tests:** `tests/test_sentence_processor.py` — edge cases: abbreviations, numbered lists, URLs, empty chunks, single-word responses

---

## Phase 2: Sentence Queue

**Goal:** Decouple LLM output from TTS consumption using an async per-session queue.

### 2.1 Create `services/sentence_queue.py`

**Source pattern:** `AI-realtime-voice-agent/utils/queue_manager.py` — Redis-based FIFO queue

**Adaptation:** Use `asyncio.Queue` instead of Redis. Aura has no Redis dependency and doesn't need distributed queuing for single-server deployment.

```python
# services/sentence_queue.py

from dataclasses import dataclass, field
from asyncio import Queue

@dataclass
class SentenceMessage:
    content: str
    is_last: bool = False          # Signals end of LLM response
    sequence_number: int = 0       # For ordering verification

class SentenceQueue:
    """Per-session async FIFO queue for sentence-level TTS processing."""

    def __init__(self, maxsize: int = 50):
        self._queues: dict[str, Queue[SentenceMessage]] = {}

    async def put(self, session_id: str, message: SentenceMessage) -> None: ...
    async def get(self, session_id: str, timeout: float = 2.0) -> SentenceMessage | None: ...
    async def clear(self, session_id: str) -> None: ...
    def remove_session(self, session_id: str) -> None: ...
```

**Key design decisions:**
- `maxsize=50` prevents unbounded memory if TTS is slow (backpressure)
- `timeout` on `get()` prevents deadlock if LLM stops producing (from source's `asyncio.wait_for` pattern)
- `is_last` sentinel replaces source's Redis `DELETE` approach — cleaner signal
- `session_id` isolation matches source's `queue:{user_id}` pattern
- No Redis — avoids new infrastructure dependency

**File:** `services/sentence_queue.py` — new file  
**Tests:** `tests/test_sentence_queue.py` — concurrent put/get, timeout, clear during processing, session cleanup

---

## Phase 3: Streaming TTS

**Goal:** Convert sentences to audio chunks and stream them to the client as they're ready.

### 3.1 Upgrade `services/tts.py` with streaming method

**Source pattern:** `AI-realtime-voice-agent/core/speech_generator.py` — `TextToSpeechHandler.stream_audio()`

**What to add to existing `TTSService`:**

```python
async def speak_streaming(
    self, text: str, voice: str | None = None, chunk_size: int = 16384
) -> AsyncGenerator[bytes, None]:
    """Yield WAV audio chunks as Edge-TTS generates them."""
```

**Implementation approach:**
- Edge-TTS already streams MP3 chunks via `communicate.stream()`
- **Current code** buffers ALL chunks into `mp3_buffer`, then converts entire buffer to WAV
- **New approach:** Accumulate MP3 chunks to ~`chunk_size` bytes, transcode each mini-buffer to WAV, yield WAV chunk
- Each chunk is a self-contained WAV segment (with header) for Android `AudioTrack` playback
- **Alternative:** Stream raw PCM without WAV headers (smaller, but client needs to know format upfront)

**Decision: Raw PCM streaming** — send format metadata once, then stream raw PCM frames. Matches `AI-realtime-voice-agent`'s approach (base64 audio chunks without individual headers).

**Protocol extension (new message types):**

```json
{"type": "audio_stream_start", "format": "pcm_16bit_16khz_mono", "sentence_index": 0}
{"type": "audio_chunk", "data": "<base64 PCM>", "chunk_index": 0, "sentence_index": 0}
{"type": "audio_stream_end", "sentence_index": 0, "sentences_remaining": 3}
```

**Source reference:** Directly from `AI-realtime-voice-agent/api/websocket.py` message types.

### 3.2 TTS Provider Abstraction

**Source pattern:** `AI-realtime-voice-agent/utils/tts_providers.py` — `AsyncBaseTTSProvider`

**Add to `services/tts.py`:**

```python
from abc import ABC, abstractmethod

class TTSProvider(ABC):
    @abstractmethod
    async def generate_audio_stream(self, text: str, voice: str) -> AsyncGenerator[bytes, None]:
        """Yield raw audio bytes for the given text."""
        ...

class EdgeTTSProvider(TTSProvider):
    """Current Edge-TTS backend, extracted from TTSService."""
    ...

# Future providers slot in here:
# class OpenAITTSProvider(TTSProvider): ...
# class DeepgramTTSProvider(TTSProvider): ...
```

**Why:** The existing `TTSService` has provider logic hardcoded to Edge-TTS. The abstraction lets us add OpenAI TTS-1 or Deepgram Aura as drop-in alternatives without touching streaming logic.

**Config change in `settings.py`:**
```python
# Existing
default_tts_provider: str = "edge-tts"
default_tts_model: str = "en-US-AriaNeural"

# New
tts_streaming_chunk_size: int = 16384  # bytes per streamed audio chunk
tts_providers: dict = {}  # populated at runtime from available providers
```

---

## Phase 4: Stream Manager (Orchestrator)

**Goal:** Wire streaming LLM → sentence processor → sentence queue → streaming TTS into a single orchestrated flow.

### 4.1 Create `services/stream_manager.py`

**Source pattern:** `AI-realtime-voice-agent/core/stream_manager.py` — `AudioStreamManager`

**This is the core orchestrator. It runs two concurrent tasks per session:**

**Task 1: LLM Producer** — streams LLM response, splits into sentences, pushes to queue  
**Task 2: TTS Consumer** — pulls sentences from queue, streams TTS audio to WebSocket

```python
# services/stream_manager.py

class StreamManager:
    """Orchestrates streaming LLM → sentence queue → streaming TTS."""

    def __init__(
        self,
        llm_service: LLMService,
        tts_service: TTSService,
        sentence_queue: SentenceQueue,
    ):
        self.llm = llm_service
        self.tts = tts_service
        self.queue = sentence_queue
        self._active_sessions: dict[str, bool] = {}  # session_id → is_running

    async def start_streaming_response(
        self,
        session_id: str,
        websocket: WebSocket,
        prompt: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
        voice: str | None = None,
    ) -> str:
        """
        Run LLM producer + TTS consumer concurrently.
        Returns the full text response when complete.
        """
        self._active_sessions[session_id] = True

        producer = asyncio.create_task(
            self._produce_sentences(session_id, prompt, system_prompt, conversation_history)
        )
        consumer = asyncio.create_task(
            self._consume_and_stream(session_id, websocket, voice)
        )

        done, pending = await asyncio.wait(
            [producer, consumer], return_when=asyncio.FIRST_EXCEPTION
        )
        # Cancel remaining task, collect full response text
        ...

    async def cancel(self, session_id: str) -> None:
        """Barge-in: stop current response immediately."""
        self._active_sessions[session_id] = False
        await self.queue.clear(session_id)
```

**Key design from source applied:**
- Dual `asyncio.create_task` pattern (from `AI-realtime-voice-agent/api/websocket.py`)
- `is_running` flag checked in consumer loop (from `stream_manager.py`'s `self.is_streaming`)
- `FIRST_EXCEPTION` return strategy (from source's `FIRST_COMPLETED`)
- `cancel()` method clears queue + stops consumer (barge-in foundation)

**File:** `services/stream_manager.py` — new file

---

## Phase 5: WebSocket Protocol Upgrade

**Goal:** Upgrade `/ws/conversation` endpoint to use streaming response delivery with backward compatibility.

### 5.1 New message types

**Add to server → client messages:**

| Type | When | Payload |
|------|------|---------|
| `partial_transcript` | During STT streaming | `{text, is_final}` |
| `response_start` | LLM begins generating | `{session_id}` |
| `response_sentence` | Each complete sentence | `{text, sentence_index}` |
| `audio_stream_start` | Before first audio chunk | `{format, sample_rate, channels, sentence_index}` |
| `audio_chunk` | Each TTS audio chunk | `{data (base64), chunk_index, sentence_index}` |
| `audio_sentence_end` | Sentence audio complete | `{sentence_index, sentences_remaining}` |
| `response_end` | Full response complete | `{full_text, total_sentences}` |

**Add to client → server messages:**

| Type | When | Payload |
|------|------|---------|
| `barge_in` | User starts speaking during playback | `{session_id}` |
| `audio_ack` | Client confirms chunk received | `{sentence_index, chunk_index}` (optional, for backpressure) |

**Source reference:** Message types adapted from `AI-realtime-voice-agent/api/websocket.py` (`audio_stream_start`, `audio_chunk`, `audio_stream_end`).

### 5.2 Modify `api_handlers/websocket_router.py`

**Changes to `/ws/conversation` handler:**

1. **Replace blocking speak node call** with `stream_manager.start_streaming_response()`
2. **Add `barge_in` message handler** — calls `stream_manager.cancel(session_id)` then re-enters listening mode
3. **Keep backward compatibility** — if client sends `{"streaming": false}` in start message, fall back to current batch behavior (existing code path)

**Response flow change:**

```
BEFORE (current):
  graph.invoke() → returns {spoken_response, spoken_audio} → send one JSON message

AFTER (streaming):
  graph.invoke() → returns {spoken_response} (text only, no audio)
  stream_manager.start_streaming_response() → sends multiple audio_chunk messages
```

### 5.3 Graph Node Adaptation

**Modify `aura_graph/core_nodes.py` `speak_node`:**

- Add a `streaming` flag to `TaskState`
- When `streaming=True`: generate text response only (skip TTS), return `spoken_response` text
- The WebSocket handler runs TTS streaming separately via `StreamManager`
- When `streaming=False`: existing behavior (full WAV generation)

This keeps the graph nodes stateless and TTS-agnostic.

---

## Phase 6: Barge-in & Turn Management

**Goal:** Allow user to interrupt bot responses and take over the conversation.

### 6.1 Backend barge-in handler

**Source pattern:** `AI-realtime-voice-agent/core/speech_generator.py` — `stop_streaming()`

**Implementation in `api_handlers/websocket_router.py`:**

```python
# Inside the /ws/conversation handler message loop:
if msg_type == "barge_in":
    await stream_manager.cancel(session_id)
    await websocket.send_json({"type": "audio_stream_stopped"})
    # Re-enter listening state — next audio chunk starts new STT
```

**What `cancel()` does:**
1. Sets `_active_sessions[session_id] = False` (stops TTS consumer loop)
2. Calls `sentence_queue.clear(session_id)` (discards pending sentences)
3. LLM producer task gets cancelled via `asyncio.Task.cancel()`

### 6.2 Android client barge-in detection

**Location:** `VoiceCaptureController.kt`

**Logic:** When Android's `SimpleVAD` detects speech AND `AuraTTSManager` is currently playing:
1. Stop TTS playback immediately (`AuraTTSManager.stop()`)
2. Send `{"type": "barge_in", "session_id": "..."}` to backend WebSocket
3. Begin streaming new audio chunks to backend
4. Resume audio recording → new STT cycle begins

**Not new code — this wires existing components:** `SimpleVAD` already exists in the Android app, `AuraTTSManager.stop()` already exists. The new piece is the `barge_in` WebSocket message and the state transition from "playing" to "listening."

---

## Phase 7: Streaming STT Enhancement

**Goal:** Improve STT to provide partial transcripts during user speech.

### 7.1 Upgrade `services/stt.py` with real streaming

**Current state:** `transcribe_streaming()` exists but still does batch transcription (sends full audio buffer to Groq, waits for complete response).

**Two options evaluated:**

| Approach | Pros | Cons |
|----------|------|------|
| **Groq Whisper with smaller chunks** | No new dependency, same API | Still batch per chunk, ~500ms per call |
| **Deepgram live streaming** | True streaming, partial transcripts, built-in VAD | New dependency + API key, cost |

**Recommended: Keep Groq, improve chunking strategy**

The current `AudioBuffer` sends audio when 16KB accumulated (~1s). Instead:

1. Send overlapping audio segments (current chunk + 500ms of previous chunk for context)
2. Return partial transcript to client immediately
3. On `end_turn`, send final accumulated audio for definitive transcript

**Source pattern:** `realtime-whisper`'s stride-based windowing — send overlapping windows for context continuity.

### 7.2 Add Deepgram as optional STT provider (future)

**Source pattern:** `AI-realtime-voice-agent/core/transcriber.py` — `DeepgramTranscriber`

If Groq latency is insufficient, add Deepgram as an alternative STT provider using the same provider abstraction from Phase 3's TTS pattern:

```python
class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_data: bytes, language: str | None = None) -> str: ...

    @abstractmethod
    async def transcribe_stream(self, audio_chunks: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]: ...

class GroqSTTProvider(STTProvider): ...
class DeepgramSTTProvider(STTProvider): ...   # Optional future addition
```

**Config:** `default_stt_provider: str = "groq"` (already exists in settings). Add `deepgram_api_key: str = ""` to settings.

---

## Phase 8: Voice Activity Detection (Server-side)

**Goal:** Add server-side VAD to detect speech boundaries independent of client.

### 8.1 Add `services/vad.py`

**Source pattern:** `llm-voice-assistant/src/llm-voice-assistant-client/main.py` — Silero VAD with EMA smoothing

**Why server-side VAD?**
- Client (Android `SimpleVAD`) already does basic VAD, but it's simple amplitude-based
- Server-side Silero VAD gives confidence scores for smarter endpointing
- Enables auto-`end_turn` without explicit client signal

**Implementation:**

```python
# services/vad.py

class VoiceActivityDetector:
    """Silero VAD for server-side speech/silence detection."""

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        silence_duration_ms: int = 1000,
        speech_pad_ms: int = 100,
        ema_alpha: float = 0.3,
    ):
        ...

    def process_chunk(self, audio_chunk: bytes) -> VADResult:
        """Process a single audio chunk, return speech/silence state."""
        ...

@dataclass
class VADResult:
    is_speech: bool
    confidence: float
    silence_duration_ms: int  # How long silence has lasted
```

**EMA smoothing from source:**
```python
ema_confidence = ema_alpha * raw_confidence + (1 - ema_alpha) * ema_confidence
```

**Config additions in `settings.py`:**
```python
vad_confidence_threshold: float = 0.5
vad_silence_duration_ms: int = 1000
vad_ema_alpha: float = 0.3
enable_server_vad: bool = False  # Opt-in, don't break existing flow
```

**Dependency:** `silero-vad` or `onnxruntime` with Silero ONNX model. Add to `requirements.txt`.

---

## Phase 9: Telemetry & Observability

**Goal:** Instrument the voice pipeline to measure and optimize latency.

### 9.1 Create `services/voice_telemetry.py`

**Source insight:** `AI-realtime-voice-agent` logs timing but has no structured telemetry. `realtime-whisper` logs but doesn't export metrics.

**What to track per voice turn:**

| Metric | Measurement Point |
|--------|-------------------|
| `stt_start_ms` | First audio chunk received |
| `stt_end_ms` | Final transcript returned |
| `llm_first_token_ms` | First token from streaming LLM |
| `llm_complete_ms` | Last token from LLM |
| `first_sentence_ms` | First complete sentence from processor |
| `tts_first_chunk_ms` | First audio chunk sent to client |
| `tts_complete_ms` | Last audio chunk sent |
| `total_turn_ms` | `stt_start_ms` to `tts_complete_ms` |
| `barge_in_count` | Number of interruptions in this session |

```python
# services/voice_telemetry.py

@dataclass
class VoiceTurnMetrics:
    session_id: str
    turn_number: int
    stt_start_ms: float = 0
    stt_end_ms: float = 0
    llm_first_token_ms: float = 0
    llm_complete_ms: float = 0
    first_sentence_ms: float = 0
    tts_first_chunk_ms: float = 0
    tts_complete_ms: float = 0
    total_sentences: int = 0
    barge_in: bool = False

    @property
    def time_to_first_audio(self) -> float:
        """The metric users feel most: how long from end of speech to hearing a response."""
        return self.tts_first_chunk_ms - self.stt_end_ms

    def to_log_dict(self) -> dict: ...
```

**Logging:** Emit as structured JSON log at end of each turn. Compatible with existing `command_logger` patterns.

**Config:** `enable_voice_telemetry: bool = True` in settings.

---

## Phase 10: Android Client Updates

**Goal:** Update Android to consume streaming audio and support barge-in.

### 10.1 `AuraTTSManager.kt` — Streaming audio playback

**Current:** Receives full WAV base64, decodes, plays via `AudioTrack`.  
**New:** Receives `audio_stream_start` → queues PCM chunks → plays from buffer continuously.

**Changes:**
- Add `AudioTrack` in `MODE_STREAM` (currently uses `MODE_STATIC`)
- On `audio_chunk` message: decode base64 → write to `AudioTrack`
- On `audio_sentence_end`: continue playing (next sentence audio follows)
- On `audio_stream_stopped` (barge-in): `AudioTrack.stop()` + `flush()`

### 10.2 `VoiceCaptureController.kt` — Barge-in detection

**Changes:**
- When `SimpleVAD.isSpeech()` and `AuraTTSManager.isPlaying`:
  - Call `AuraTTSManager.stop()`
  - Send `{"type": "barge_in"}` on WebSocket
  - Resume audio capture pipeline

### 10.3 `ConversationViewModel.kt` — State machine update

**New states:**
```
IDLE → LISTENING → PROCESSING → STREAMING_RESPONSE → IDLE
                                      ↓
                                 BARGE_IN → LISTENING
```

### 10.4 WebSocket message handler additions

**Handle new message types:**
- `partial_transcript` → show live transcript in UI
- `response_start` → show "thinking" indicator
- `response_sentence` → show text incrementally
- `audio_stream_start` → prepare `AudioTrack`
- `audio_chunk` → feed to `AudioTrack`
- `audio_sentence_end` → optionally log progress
- `response_end` → finalize UI state
- `audio_stream_stopped` → cleanup on barge-in

---

## Configuration Summary

All new settings added to `config/settings.py` with environment variable backing:

```python
# === Voice Streaming Settings ===
streaming_llm_model: str = ""                # Empty = use default LLM model for streaming too
streaming_llm_provider: str = ""             # Empty = use default provider
streaming_llm_temperature: float = 0.7       # Conversation temperature
streaming_llm_max_tokens: int = 300          # Max response length for voice turns
streaming_response_enabled: bool = True      # Master toggle for streaming vs batch

# === TTS Streaming ===
tts_streaming_chunk_size: int = 16384        # Bytes per audio chunk sent to client
tts_audio_format: str = "pcm_16bit_16khz"   # Audio format for streaming

# === Sentence Processing ===
sentence_min_words: int = 2                  # Minimum words for a valid sentence
sentence_queue_maxsize: int = 50             # Max buffered sentences per session
sentence_queue_timeout: float = 2.0          # Seconds to wait for next sentence

# === VAD (Server-side) ===
enable_server_vad: bool = False              # Opt-in server-side VAD
vad_confidence_threshold: float = 0.5
vad_silence_duration_ms: int = 1000
vad_ema_alpha: float = 0.3

# === Telemetry ===
enable_voice_telemetry: bool = True
```

---

## New Files Created

| File | Purpose | Phase |
|------|---------|-------|
| `services/sentence_processor.py` | Split streaming LLM output into sentences | 1 |
| `services/sentence_queue.py` | Per-session async FIFO queue | 2 |
| `services/stream_manager.py` | Orchestrate LLM→queue→TTS pipeline | 4 |
| `services/vad.py` | Server-side Silero VAD | 8 |
| `services/voice_telemetry.py` | Latency metrics per voice turn | 9 |
| `tests/test_sentence_processor.py` | Sentence processor tests | 1 |
| `tests/test_sentence_queue.py` | Queue tests | 2 |
| `tests/test_stream_manager.py` | Integration tests | 4 |

## Existing Files Modified

| File | Changes | Phase |
|------|---------|-------|
| `services/llm.py` | Add `run_streaming()` async generator method + `AsyncGroq` client | 0 |
| `services/tts.py` | Add `TTSProvider` ABC + `EdgeTTSProvider` + `speak_streaming()` method | 3 |
| `services/stt.py` | Add `STTProvider` ABC, improve chunking with overlap | 7 |
| `config/settings.py` | Add all new voice streaming settings | 0-9 |
| `api_handlers/websocket_router.py` | Integrate `StreamManager`, add `barge_in` handler, streaming response | 5 |
| `aura_graph/core_nodes.py` | Add `streaming` flag to `speak_node`, skip TTS when streaming | 5 |
| `aura_graph/state.py` | Add `streaming: bool` to `TaskState` | 5 |
| `agents/responder.py` | Support streaming text generation | 5 |
| `requirements.txt` | Add `silero-vad` (Phase 8 only, optional) | 8 |

---

## Dependency Changes

| Package | Version | Phase | Required? |
|---------|---------|-------|-----------|
| `groq` | `>=0.9.0` | 0 | Already present — verify async support |
| `silero-vad` | `>=5.0` | 8 | Optional — only if server VAD enabled |
| `onnxruntime` | `>=1.16` | 8 | Optional — Silero VAD runtime |

**No Redis.** No new API keys required (all use existing Groq/Edge-TTS).

---

## Implementation Order & Dependencies

```
Phase 0: Streaming LLM           ← No dependencies, pure addition
    ↓
Phase 1: Sentence Processor      ← No dependencies, pure addition
    ↓
Phase 2: Sentence Queue           ← No dependencies, pure addition
    ↓
Phase 3: Streaming TTS            ← Depends on Phase 1 design
    ↓
Phase 4: Stream Manager           ← Depends on Phases 0, 1, 2, 3
    ↓
Phase 5: WebSocket Protocol       ← Depends on Phase 4
    ↓
Phase 6: Barge-in                 ← Depends on Phase 5
    ↓
Phase 7: Streaming STT            ← Independent (can start after Phase 5)
Phase 8: Server VAD               ← Independent (can start after Phase 5)
Phase 9: Telemetry                ← Can start at Phase 0, grows with each phase
Phase 10: Android Client          ← Depends on Phase 5 (protocol changes)
```

**Parallelizable:** Phases 7, 8, 9 can all run in parallel after Phase 5.

---

## Testing Strategy

### Unit Tests (per phase)

| Phase | Test | Validates |
|-------|------|-----------|
| 0 | `test_llm_streaming.py` | `run_streaming()` yields chunks, handles errors, respects cancellation |
| 1 | `test_sentence_processor.py` | Abbreviations, numbers, edge cases, dedup, flush |
| 2 | `test_sentence_queue.py` | Put/get ordering, timeout, clear, session isolation, backpressure |
| 3 | `test_tts_streaming.py` | `speak_streaming()` yields valid audio chunks, handles empty text |
| 4 | `test_stream_manager.py` | Producer/consumer coordination, cancel mid-stream, error propagation |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_streaming_pipeline.py` | Full LLM → sentence → queue → TTS → base64 chunks pipeline |
| `test_websocket_streaming.py` | WebSocket client receives correct message sequence |
| `test_barge_in.py` | Barge-in cancels streaming and clears queue |
| `test_backward_compat.py` | Non-streaming clients still receive single WAV response |

### Performance Benchmarks

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Time to first audio | < 1.5s | `tts_first_chunk_ms - stt_end_ms` from telemetry |
| Barge-in response | < 200ms | Time from `barge_in` message to `audio_stream_stopped` |
| Session memory | < 5MB | Track `SentenceQueue` + `AudioBuffer` peak sizes |
| Concurrent sessions | ≥ 10 | Load test with 10 parallel WebSocket conversations |

---

## Backward Compatibility

**All changes are opt-in.** The existing pipeline continues to work unchanged:

1. **Android client** sends `{"type": "start", "streaming": true}` to opt into streaming. Without this flag, existing batch behavior is preserved.
2. **Graph execution** checks `state["streaming"]` flag. If `False`, existing `speak_node` generates full WAV as before.
3. **`/ws/audio-stream-final`** and **`/ws/audio-stream`** endpoints are untouched.
4. **REST API** (`/tts/preview`, `/tts/voices`) continues to use existing batch `TTSService.speak_async()`.

---

## Rollout Strategy

| Stage | What | Who Tests |
|-------|------|-----------|
| **Alpha** | Backend Phases 0-5 behind `streaming_response_enabled=False` | Dev (Postman/wscat) |
| **Beta** | Enable streaming, test with Android debug build | Dev + 1-2 testers |
| **RC** | Add telemetry (Phase 9), measure latency in real conditions | Extended testing |
| **GA** | Enable server VAD (Phase 8) if needed, finalize Android UI | All users |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Edge-TTS streaming latency too high | Audio gaps between sentences | Prefetch: start TTS for sentence N+1 while sentence N plays |
| LLM response too short (1 sentence) | Streaming overhead not worth it | Detect response length, fall back to batch for < 2 sentences |
| pcm chunk playback glitches on Android | Poor UX | Send WAV headers per chunk instead of raw PCM; test on low-end devices |
| Groq rate limits during streaming | Interrupted responses | Add exponential backoff + graceful degradation message to client |
| Sentence processor splits mid-word | Garbled TTS | Extensive unit tests, whitelist known abbreviations, min-word guard |
| Concurrent session memory pressure | OOM on server | `maxsize` on queue, session cleanup on disconnect, periodic GC |

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Time to first audio | ~5s | < 1.5s |
| Full response delivery | ~7s (30-word response) | < 3s |
| Barge-in to silence | Not supported | < 300ms |
| Interruption recovery | Not supported | Resumes listening within 500ms |
| CPU usage per session | ~15% (batch burst) | ~8% (spread over streaming) |
| Backward compatibility | N/A | 100% (non-streaming clients work unchanged) |
