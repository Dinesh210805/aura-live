# Voice Code Helpers Guide

Purpose: Fast reference for reusing code patterns from cloned helper repositories to improve Aura voice UX.

## Quick Recommendation

Best overall source for orchestration patterns:
- AI-realtime-voice-agent

Best source for STT streaming internals:
- realtime-whisper

Best source for simple Edge-TTS examples:
- Low-latency-AI-Voice-Assistant and llm_sts

Best source for local-first and multilingual sentence-to-TTS flow:
- llm-voice-assistant

## Repo Comparison Matrix

| Repo | Best For | Reuse Confidence | Notes |
|---|---|---|---|
| Low-latency-AI-Voice-Assistant | Simple end-to-end Whisper + Edge-TTS flow | Medium | Good starter patterns, less production structure |
| llm_sts | WebSocket split-service ASR/LLM/TTS pipeline | Medium-High | Modular but tuned for Vosk and Chinese-first setup |
| AI-realtime-voice-agent | Real-time queue orchestration and sentence-level streaming | High | Best event and queue design patterns for your target UX |
| llm-voice-assistant | Local-first offline architecture, wake-word, Piper | Medium | Useful ideas, but AGPL license needs careful handling |
| realtime-whisper | Focused real-time Whisper streaming server | High | Strong STT subsystem and clean packaging structure |

## What To Copy From Each Repo

### 1) AI-realtime-voice-agent
Copy ideas from:
- core/stream_manager.py
- core/transcriber.py
- core/response_generator.py
- core/speech_generator.py
- utils/sentence_processor.py
- utils/silence_detector.py
- utils/queue_manager.py
- utils/redis_manager.py

Reuse in Aura for:
- Sentence queue and FIFO response playback
- Pause detection and response segmentation
- Provider abstraction for STT, LLM, TTS
- Event-driven websocket loop design

### 2) realtime-whisper
Copy ideas from:
- src/realtime_whisper/realtime_whisper.py
- src/realtime_whisper/speech_transcription_interfaces/websocket_server_interface.py
- src/realtime_whisper/config/transcription_config.py
- src/realtime_whisper/config/model_config.py
- scripts/pyaudio_client.py

Reuse in Aura for:
- Streaming STT framing and buffering
- STT websocket protocol and server wiring
- STT model and runtime config structure
- Testable, isolated STT module boundaries

### 3) llm_sts
Copy ideas from:
- core/audio_core.py
- core/text_core.py
- core/websocket_core.py
- servers/ws_asr_server.py
- servers/ws_llm_server.py
- servers/ws_tts_server.py

Reuse in Aura for:
- Service split by concern (ASR, LLM, TTS)
- Text segmentation before TTS synthesis
- Separate websocket channels for subsystems

### 4) Low-latency-AI-Voice-Assistant
Copy ideas from:
- utils/audio_processing.py
- utils/llm_interaction.py
- utils/tts_conversion.py
- Models/faster_whisper_stt_tiny.py

Reuse in Aura for:
- Lightweight baseline and quick experiment scripts
- Practical Edge-TTS parameter knobs

### 5) llm-voice-assistant
Copy ideas from:
- src/llm-voice-assistant-client/main.py
- src/llm-voice-assistant-client/textToSpeech.py
- src/llm-voice-assistant-client/wakeWord.py

Reuse in Aura for:
- Wake-word and hands-free interaction concepts
- Language-aware sentence chunk to TTS flow
- Local-first fallback architecture patterns

## Aura Integration Map

Use these target files in Aura when adapting patterns:
- api_handlers/websocket_router.py
- services/stt.py
- services/tts.py
- agents/responder.py
- UI/app/src/main/java/com/aura/aura_ui/voice/VoiceCaptureController.kt
- UI/app/src/main/java/com/aura/aura_ui/audio/AuraTTSManager.kt

Suggested adaptation order:
1. Import sentence queue and sentence boundary logic from AI-realtime-voice-agent into websocket_router flow.
2. Improve streaming STT buffering and partial handling using realtime-whisper patterns in services/stt.py.
3. Add barge-in and turn arbitration in VoiceCaptureController and server websocket flow.
4. Keep Android local TTS primary, keep backend Edge-TTS as fallback only.
5. Add structured latency telemetry around VAD start, endpoint, final transcript, response first token, and playback start.

## Use and Safety Notes

- Prefer pattern adaptation, not direct copy-paste of whole files.
- Keep existing Aura architecture as source of truth.
- Verify license compatibility before copying substantial code, especially from AGPL repositories.

## First Tasks To Start Tomorrow

1. Add sentence queue primitive and tests in Aura backend.
2. Add partial transcript event contract in websocket protocol.
3. Add barge-in stop event from Android client to backend.
4. Add unified timing trace object across one voice turn.
5. Run A/B test against current flow for latency and interruption success.
