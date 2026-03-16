"""
ADK Streaming Server — Gemini Live bidirectional audio + vision WebSocket handler.

Adds a NEW /ws/live endpoint alongside the existing /ws/audio and /ws/device
endpoints. It does NOT replace or modify existing endpoints.

Architecture:
    Android companion app  ←─WebSocket /ws/live─→  handle_live_websocket()
         │                                                   │
    audio chunks (PCM)                        LiveRequestQueue → Gemini Live
    screenshots (JPEG)                        ←─ audio response ─────────────
    ui_tree JSON                              ←─ transcript text ────────────
                                              ←─ task_progress  ────────────

Message protocol (same JSON envelope as /ws/audio for Android compatibility):

    Incoming from Android:
        {"type": "audio_chunk",  "data": "<base64 PCM 16kHz mono int16>"}
        {"type": "screenshot",   "data": "<base64 JPEG>"}
        {"type": "ui_tree",      "tree": {...}, "packageName": "com.example"}
        {"type": "ping"}

    Outgoing to Android:
        {"type": "audio_response", "data": "<base64 PCM>"}
        {"type": "transcript",     "text": "Opening Spotify..."}
        {"type": "task_progress",  "status": "executing" | "idle"}
        {"type": "error",          "message": "..."}
        {"type": "pong"}

Feature flag: this endpoint only registers when GEMINI_LIVE_ENABLED=true in
settings so it cannot break the existing pipeline during development.

Enable with:
    GEMINI_LIVE_ENABLED=true
    GEMINI_LIVE_MODEL=gemini-2.0-flash-live-001
"""

import asyncio
import base64
import logging
import re
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from utils.logger import get_logger
from services.command_logger import get_command_logger, clear_execution_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Thinking-content filter
# ---------------------------------------------------------------------------
# Gemini 2.5 (and other thinking-capable models) emit reasoning tokens as
# text parts BEFORE generating the spoken audio response. These are internal
# chain-of-thought fragments and must never be shown in the chat transcript.
# They are identifiable by markdown bold headings (**Heading**) and verbose
# reasoning prose that the model never actually speaks aloud.

_THINKING_HEADER_RE = re.compile(r"^\*\*[^*\n]+\*\*", re.MULTILINE)


def _is_thinking_content(text: str) -> bool:
    """Return True if *text* looks like model reasoning rather than spoken output."""
    stripped = text.strip()
    # Pattern 1: starts with a **Bold Title** (chain-of-thought section header)
    if _THINKING_HEADER_RE.match(stripped):
        return True
    # Pattern 2: contains multiple **Bold** headers inline (thinking paragraphs)
    if len(_THINKING_HEADER_RE.findall(stripped)) >= 2:
        return True
    return False


# ---------------------------------------------------------------------------
# ADK imports — guarded so the server still starts if google-adk is absent
# ---------------------------------------------------------------------------

_ADK_AVAILABLE = False
_Runner = None
_InMemorySessionService = None
_LiveRequestQueue = None
_RunConfig = None
_StreamingMode = None
_Part = None
_Blob = None
_Content = None
_Modality = None
_StartSensitivity = None  # Optional: noise sensitivity tuning (google-genai ≥ 0.9)

try:
    from google.adk.runners import Runner as _Runner  # type: ignore[assignment]
    from google.adk.sessions import InMemorySessionService as _InMemorySessionService  # type: ignore[assignment]
    from google.adk.agents.live_request_queue import LiveRequestQueue as _LiveRequestQueue  # type: ignore[assignment]
    from google.adk.agents.run_config import RunConfig as _RunConfig, StreamingMode as _StreamingMode  # type: ignore[assignment]
    from google.genai.types import Blob as _Blob, Part as _Part, Content as _Content, Modality as _Modality  # type: ignore[assignment]
    from google.genai.types import SpeechConfig as _SpeechConfig, VoiceConfig as _VoiceConfig, PrebuiltVoiceConfig as _PrebuiltVoiceConfig  # type: ignore[assignment]

    # VAD / turn-detection types (available in google-genai ≥ 0.8)
    try:
        from google.genai.types import (  # type: ignore[assignment]
            AutomaticActivityDetection as _AutomaticActivityDetection,
            RealtimeInputConfig as _RealtimeInputConfig,
            ActivityHandling as _ActivityHandling,
            TurnCoverage as _TurnCoverage,
            AudioTranscriptionConfig as _AudioTranscriptionConfig,
        )
        _VAD_TYPES_AVAILABLE = True
        # Optional: StartSensitivity — tune speech detection threshold (google-genai ≥ 0.9)
        try:
            from google.genai.types import StartSensitivity as _StartSensitivity  # type: ignore[assignment]
        except ImportError:
            pass  # _StartSensitivity stays None (declared at module level above)
        logger.info("ADK streaming: VAD / RealtimeInputConfig types available")
    except ImportError:
        _VAD_TYPES_AVAILABLE = False
        _AutomaticActivityDetection = None
        _RealtimeInputConfig = None
        _ActivityHandling = None
        _TurnCoverage = None
        _AudioTranscriptionConfig = None
        logger.warning(
            "ADK streaming: VAD types (RealtimeInputConfig) not available in this "
            "google-genai version — using default server VAD."
        )

    _ADK_AVAILABLE = True
    logger.info("ADK streaming: all imports resolved successfully")
except ImportError as _e:
    logger.warning(
        f"ADK streaming imports unavailable ({_e}). "
        "/ws/live endpoint will return a graceful error until "
        "'google-adk' and 'google-genai' are installed."
    )
    _VAD_TYPES_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level ADK runner (singleton, shared across connections)
# ---------------------------------------------------------------------------

_session_service: Optional[object] = None
_runner: Optional[object] = None


def _get_runner():
    """Lazily initialise the ADK Runner singleton for Gemini Live bidi streaming.

    Uses a dedicated live agent with the model specified by GEMINI_LIVE_MODEL
    (default: gemini-2.0-flash-live-001) which supports bidiGenerateContent.
    This is separate from the tool-use root_agent (gemini-2.5-flash) in adk_agent.py.
    """
    global _session_service, _runner

    if _runner is not None:
        return _runner

    if not _ADK_AVAILABLE:
        raise RuntimeError("google-adk is not installed. Run: pip install google-adk")

    from google.adk import Agent  # type: ignore[import]
    from adk_agent import aura_tool, root_agent
    from config.settings import get_settings

    settings = get_settings()

    # Use the live-capable model; fall back to root_agent's model only if the
    # setting is empty (which would be a misconfiguration).
    live_model = getattr(settings, "gemini_live_model", None) or "gemini-2.5-flash-native-audio-preview-12-2025"

    # Build a live-specific agent that uses the bidi-capable model
    # but still has access to the AURA tool for device control.
    try:
        live_agent = Agent(
            name="AURA_Live",
            model=live_model,
            description=(
                "AURA Live — voice-first Android automation agent with real-time "
                "bidirectional audio and vision via Gemini Live."
            ),
            instruction="""
CRITICAL — SILENCE IS MANDATORY: Never say "I'm listening", "I'm here", "I'm waiting", "How can I help", or any unprompted filler. If you receive no clear spoken command, say absolutely nothing. Silence on your end is always correct between turns. Only speak when a human has clearly said something intelligible to you.

You are AURA, a voice-controlled Android automation assistant.

You can control the user's Android device by calling execute_aura_task.
Capabilities: open apps, tap/scroll/type in any UI element, search, navigate, read screen content, multi-step tasks.

SILENCE RULE — the most important rule:
  - Stay completely SILENT between turns. Do not say "I'm listening", "I'm waiting", "I'm here", or anything else unprompted.
  - Only speak when the user has clearly said something to you.
  - If you receive audio that is background noise, room echo, your own playback, or silence — say NOTHING.
  - Never generate filler responses. Silence is always better than a filler response.

COMMAND RULE:
  - Only call execute_aura_task when you clearly understand the full intent of a device command.
  - If unsure, ask the user to repeat once. Do not guess.

Confirmation required ONLY for: sending messages, making purchases, deleting data, public posts.
All other navigation tasks: proceed immediately.

After execute_aura_task:
  - success=true: one short confirmation sentence.
  - success=false: briefly explain and suggest rephrasing.

Style: short spoken sentences, no lists, no markdown.

LANGUAGE RULE:
  - DEFAULT LANGUAGE IS ENGLISH. Always respond in English unless the user explicitly and clearly asks you to switch to another language (e.g. "speak to me in Hindi", "reply in Tamil").
  - Do NOT infer language from accent, pronunciation style, or ambiguous audio. Indian English accents are English — respond in English.
  - NEVER switch to Hindi, Tamil, Malayalam, or any other language just because a word or phrase sounded like it. When in doubt, use English.
  - If the user genuinely and clearly speaks a full sentence in a specific language, you may respond in that language. One ambiguous word is not enough.
  - Do not mix languages mid-response (e.g. no Hindi words inside an English sentence).
""",
            tools=[aura_tool] if aura_tool is not None else [],
        )
        logger.info(f"ADK Live Runner: using model={live_model}")
    except Exception as exc:
        logger.warning(
            f"Could not build dedicated live agent ({exc}), "
            "falling back to root_agent"
        )
        if root_agent is None:
            raise RuntimeError(
                "ADK root_agent is None — google-adk may not be installed properly."
            )
        live_agent = root_agent

    _session_service = _InMemorySessionService()
    _runner = _Runner(
        agent=live_agent,
        session_service=_session_service,
        app_name=settings.adk_app_name,
    )
    logger.info(f"ADK Live Runner singleton created (model={live_model})")
    return _runner


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------


async def handle_live_websocket(
    websocket: WebSocket,
    session_id: str,
    voice: str | None = None,
    transcription_language: str | None = None,
) -> None:
    """
    Bidirectional Gemini Live session handler for a connected Android device.

    This coroutine drives two concurrent tasks:
        receive_from_device — reads messages from the Android app and feeds
                              them into the Gemini Live session queue.
        send_to_device      — consumes Gemini Live events and streams audio /
                              transcripts back to the Android app.

    Args:
        websocket: The accepted FastAPI WebSocket connection.
        session_id: Unique identifier for this device session. Used to
                    maintain Gemini Live conversation state.
        voice: Optional prebuilt voice name for this session.
        transcription_language: Optional language code override for this
                    session's input/output audio transcription.
    """
    await websocket.accept()
    logger.info(f"[/ws/live] New Gemini Live session: {session_id}")

    if not _ADK_AVAILABLE:
        await websocket.send_json({
            "type": "error",
            "message": (
                "Gemini Live streaming is not available: google-adk is not installed. "
                "Install it with: pip install google-adk google-genai"
            ),
        })
        await websocket.close()
        return

    try:
        runner = _get_runner()
    except Exception as exc:
        logger.error(f"[/ws/live] Failed to initialise ADK runner: {exc}")
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    # Create an ADK session for this connection
    try:
        from config.settings import get_settings

        settings = get_settings()
        session = await _session_service.create_session(
            app_name=settings.adk_app_name,
            user_id=session_id,
        )
    except Exception as exc:
        logger.error(f"[/ws/live] Failed to create ADK session: {exc}")
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    live_queue = _LiveRequestQueue()
    live_logger = None
    live_logger_owned = False

    def _get_live_command_logger():
        """Get/create a CommandLogger for this live session."""
        nonlocal live_logger, live_logger_owned
        try:
            if live_logger is None:
                candidate = get_command_logger(execution_id=f"live_{session_id}")
                live_logger = candidate
                live_logger_owned = str(
                    getattr(candidate, "execution_id", "")
                ).startswith(f"live_{session_id}")
            return live_logger
        except Exception as _log_exc:
            logger.debug(f"[/ws/live] Could not access CommandLogger: {_log_exc}")
            return None

    # ── Build RunConfig with VAD and transcription ────────────────────────────
    # VAD settings:
    #   prefix_padding_ms=100  — 100 ms of sustained speech before turn starts.
    #                            Low enough to catch short commands; still filters
    #                            brief echo bursts (~50 ms) from speaker reverb.
    #   silence_duration_ms=400 — 400 ms silence = end of user turn.
    #                             Reduced from 700 ms to cut round-trip latency by ~300 ms.
    #   start_of_speech_sensitivity: use DEFAULT (MEDIUM) — LOW was too aggressive
    #                                and prevented normal-volume speech from registering.
    #   START_OF_ACTIVITY_INTERRUPTS — barge-in: user speech stops AURA mid-sentence.
    #   TURN_INCLUDES_ONLY_ACTIVITY  — only active speech, not silence, is in the turn.
    _realtime_input_cfg = None
    if _VAD_TYPES_AVAILABLE:
        try:
            _aad_kwargs: dict = {
                "disabled": False,
                "prefix_padding_ms": 100,   # 100 ms — catches short commands, filters echo
                "silence_duration_ms": 400, # 400 ms silence = end of user turn (low latency)
                # start_of_speech_sensitivity intentionally omitted → server default (MEDIUM)
                # LOW required shouting to trigger; MEDIUM works at normal speaking volume.
            }
            _realtime_input_cfg = _RealtimeInputConfig(
                automatic_activity_detection=_AutomaticActivityDetection(**_aad_kwargs),
                activity_handling=_ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=_TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            )
            logger.info("[/ws/live] VAD: RealtimeInputConfig applied (100 ms prefix, 400 ms silence, default sensitivity, barge-in ON)")
        except Exception as _vad_exc:
            logger.warning(f"[/ws/live] Could not build RealtimeInputConfig: {_vad_exc} — using defaults")

    _transcription_cfg = None
    _input_transcription_cfg = None  # separate config for user's voice (input)

    if _VAD_TYPES_AVAILABLE and _AudioTranscriptionConfig is not None:
        # Determine whether language_code is supported once, then build both configs.
        # Locking to en-US prevents auto-detection from drifting to Hindi/other scripts
        # on Indian devices where the accent triggers incorrect language detection.
        try:
            # The Gemini Live API does NOT support language_codes in AudioTranscriptionConfig
            # at runtime — the field exists in the SDK types but the API rejects it.
            # Language is controlled exclusively via the agent's system instruction.
            # See: https://ai.google.dev/gemini-api/docs/live-guide (transcription section)
            _transcription_cfg = _AudioTranscriptionConfig()
            _input_transcription_cfg = _AudioTranscriptionConfig()
            logger.info(
                "[/ws/live] AudioTranscriptionConfig: enabled (language locked via system instruction)"
            )
        except Exception as _tc_exc:
            logger.warning(f"[/ws/live] AudioTranscriptionConfig() failed: {_tc_exc}")
            _transcription_cfg = None
            _input_transcription_cfg = None

    # ── Build speech config (voice selection) ────────────────────────────────
    # `voice` param overrides GEMINI_LIVE_VOICE env var for this connection only.
    # Available prebuilt voices: Aoede, Charon, Fenrir, Kore, Puck,
    #   Schedar, Gacrux, Pulcherrima, Achird, Zubenelgenubi
    _speech_cfg = None
    try:
        voice_name = voice or getattr(settings, "gemini_live_voice", "Charon") or "Charon"
        _speech_cfg = _SpeechConfig(
            voice_config=_VoiceConfig(
                prebuilt_voice_config=_PrebuiltVoiceConfig(voice_name=voice_name)
            )
        )
        logger.info(f"[/ws/live] Voice: {voice_name}")
    except Exception as _vc_exc:
        logger.warning(f"[/ws/live] Could not build SpeechConfig: {_vc_exc} — using model default voice")

    # Build RunConfig kwargs — ONLY include optional fields when the config object
    # is not None. Passing None for output_audio_transcription silently disables
    # transcription even when no TypeError is raised, so we omit the key entirely
    # when AudioTranscriptionConfig was unavailable.
    _run_config_kwargs: dict = {
        "response_modalities": ["AUDIO"],
        "streaming_mode": _StreamingMode.BIDI,
    }
    if _speech_cfg is not None:
        _run_config_kwargs["speech_config"] = _speech_cfg
    if _transcription_cfg is not None:
        _run_config_kwargs["output_audio_transcription"] = _transcription_cfg
    if _input_transcription_cfg is not None:
        _run_config_kwargs["input_audio_transcription"] = _input_transcription_cfg
    if _transcription_cfg is None and _input_transcription_cfg is None:
        logger.warning("[/ws/live] AudioTranscriptionConfig unavailable — chat transcripts will be empty")
    if _realtime_input_cfg is not None:
        _run_config_kwargs["realtime_input_config"] = _realtime_input_cfg

    run_config = None
    # Attempt 1: full config (both transcription directions + VAD)
    try:
        run_config = _RunConfig(**_run_config_kwargs)
        logger.info("[/ws/live] RunConfig: full config (VAD + input + output transcription)")
    except TypeError:
        pass

    # Attempt 2: drop input_audio_transcription (not supported in older ADK)
    if run_config is None:
        _run_config_kwargs.pop("input_audio_transcription", None)
        try:
            run_config = _RunConfig(**_run_config_kwargs)
            logger.info("[/ws/live] RunConfig: output transcription only (input_audio_transcription unsupported in this ADK)")
        except TypeError:
            pass

    # Attempt 3: drop output_audio_transcription too — keep VAD only
    if run_config is None:
        _run_config_kwargs.pop("output_audio_transcription", None)
        try:
            run_config = _RunConfig(**_run_config_kwargs)
            logger.warning("[/ws/live] RunConfig: VAD only — no transcription (ADK too old)")
        except TypeError:
            pass

    # Attempt 4: absolute minimal — should always work
    if run_config is None:
        run_config = _RunConfig(
            response_modalities=["AUDIO"],
            streaming_mode=_StreamingMode.BIDI,
        )
        logger.warning("[/ws/live] RunConfig: minimal fallback — no VAD, no transcription")

    async def receive_from_device() -> None:
        """Read Android app messages and push them into the Gemini Live queue."""
        try:
            while True:
                raw = await websocket.receive_json()
                msg_type = raw.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type == "audio_chunk":
                    # PCM audio from device microphone (base64-encoded int16 16kHz mono)
                    # send_realtime() is synchronous and takes a raw Blob
                    raw_data = raw.get("data", "")
                    try:
                        audio_bytes = base64.b64decode(raw_data)
                    except Exception:
                        logger.warning("[/ws/live] Invalid base64 in audio_chunk, skipping")
                        continue

                    live_queue.send_realtime(
                        _Blob(mime_type="audio/pcm;rate=16000", data=audio_bytes)
                    )

                elif msg_type == "screenshot":
                    # Current device screen — gives Gemini visual context
                    raw_data = raw.get("data", "")
                    try:
                        img_bytes = base64.b64decode(raw_data)
                    except Exception:
                        logger.warning("[/ws/live] Invalid base64 in screenshot, skipping")
                        continue

                    live_queue.send_realtime(
                        _Blob(mime_type="image/jpeg", data=img_bytes)
                    )

                elif msg_type == "ui_tree":
                    # UI tree is intentionally NOT injected into the Gemini Live queue.
                    # Injecting it as role="user" content caused Gemini to misread app
                    # names (e.g. "Current app: com.whatsapp") as spoken commands and
                    # trigger unintended automation. Screenshots (sent every 3 s) already
                    # give Gemini visual context — text UI tree is redundant and harmful.
                    pass

                elif msg_type == "text_command":
                    # User typed a text command instead of speaking
                    text = raw.get("text", "").strip()
                    if text:
                        live_queue.send_content(
                            _Content(role="user", parts=[_Part(text=text)])
                        )
                        cmd_logger = _get_live_command_logger()
                        if cmd_logger:
                            cmd_logger.log_command(
                                command=text,
                                input_type="text",
                                session_id=session_id,
                                metadata={"source": "ws_live_text_command"},
                            )

                elif msg_type == "end_turn":
                    # Client signals end of audio — automatic server-side VAD handles
                    # speech boundary detection, so no explicit signal needed here.
                    pass

                elif msg_type == "cancel_task":
                    # Acknowledge cancellation (actual task cancellation happens via
                    # the /ws/conversation device control channel on the backend).
                    logger.info(f"[/ws/live] cancel_task received for session {session_id}")
                    await websocket.send_json({"type": "task_progress", "status": "idle"})

                else:
                    logger.debug(f"[/ws/live] Unknown message type: {msg_type!r}")

        except WebSocketDisconnect:
            logger.info(f"[/ws/live] Client disconnected: {session_id}")
            live_queue.close()
        except Exception as exc:
            logger.error(f"[/ws/live] receive_from_device error: {exc}", exc_info=True)
            live_queue.close()

    async def send_to_device() -> None:
        """Consume Gemini Live events and relay them to the Android app."""
        # ── Per-turn transcript accumulators ─────────────────────────────────
        # These accumulate across ALL sub-turns in a single AI response.
        # They are only reset when a SILENT turn_complete fires (no audio in
        # the current event) or when new user input arrives after the AI spoke.
        # This is critical for native-audio models (e.g. gemini-2.5-flash-native-audio)
        # which fire turn_complete after every audio segment — resetting on each
        # sub-turn would fragment the transcript into word-per-bubble chaos.
        user_transcript_buf: str = ""      # growing accumulated user sentence
        user_transcript_latest: str = ""   # last corrected full user sentence
        ai_transcript_buf: list[str] = []  # output_audio_transcription fragments this response
        user_transcript_flushed: bool = False  # True once user final sent this response
        ai_audio_sent: bool = False            # True once any AI audio chunk has been sent
        _deferred_flush_task: asyncio.Task | None = None  # delayed flush for audio+turn_complete edge case

        async def _flush_response(source: str) -> None:
            """Send is_final=True transcripts for both user and AI, then reset all buffers."""
            nonlocal user_transcript_flushed, user_transcript_buf, user_transcript_latest
            nonlocal ai_transcript_buf, ai_audio_sent

            # User transcript — only if not already flushed at audio-start
            _deferred_user_log_text: str | None = None
            if not user_transcript_flushed:
                full_user = user_transcript_latest.strip()
                if full_user:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": full_user,
                        "is_user": True,
                        "is_final": True,
                    })
                    _deferred_user_log_text = full_user

            # AI transcript — joined from all accumulated fragments
            full_ai_text = " ".join(
                frag for frag in ai_transcript_buf
                if frag and not _is_thinking_content(frag)
            ).strip()
            if full_ai_text:
                await websocket.send_json({
                    "type": "transcript",
                    "text": full_ai_text,
                    "is_user": False,
                    "is_final": True,
                })

            await websocket.send_json({"type": "task_progress", "status": "idle"})

            logger.info(
                f"[/ws/live] response_flush [{source}] → "
                f"ai={full_ai_text[:60]!r} buf_frags={len(ai_transcript_buf)}"
            )
            cmd_logger = _get_live_command_logger()
            if cmd_logger:
                if _deferred_user_log_text:
                    cmd_logger.log_agent_decision(
                        agent_name="GeminiLive",
                        decision_type="LIVE_TRANSCRIPT",
                        details={"speaker": "user", "text": _deferred_user_log_text,
                                 "source": source, "session_id": session_id},
                    )
                if full_ai_text:
                    cmd_logger.log_agent_decision(
                        agent_name="GeminiLive",
                        decision_type="LIVE_TRANSCRIPT",
                        details={"speaker": "assistant", "text": full_ai_text,
                                 "source": "output_transcription", "session_id": session_id},
                    )

            # Reset ALL per-response buffers
            ai_transcript_buf.clear()
            user_transcript_buf = ""
            user_transcript_latest = ""
            user_transcript_flushed = False
            ai_audio_sent = False

        try:
            async for event in runner.run_live(
                user_id=session_id,
                session_id=session.id,
                run_config=run_config,
                live_request_queue=live_queue,
            ):
                # Cancel any pending deferred flush — a new event arrived so the
                # model is still active; we'll reschedule it if needed below.
                if _deferred_flush_task is not None and not _deferred_flush_task.done():
                    _deferred_flush_task.cancel()
                    _deferred_flush_task = None

                # Tool call in flight — notify app that a task is executing
                if event.get_function_calls():
                    await websocket.send_json({
                        "type": "task_progress",
                        "status": "executing",
                    })

                # ── Extract audio, transcript, and turn-complete from event ───
                audio_chunks: list[bytes] = []

                # Pull server_content early — needed for audio, transcription, and
                # turn-complete detection on every path below.
                server_content = getattr(event, "server_content", None)

                # ── PRIMARY audio path: server_content.model_turn.parts ──────────
                # In ADK runner.run_live() events, Gemini Live audio arrives in
                # server_content.model_turn.parts[].inline_data, NOT in event.content.
                # Text parts from model_turn are intentionally skipped — on thinking-
                # capable models they contain reasoning tokens (**Heading** / chain-of-
                # thought prose) that the model never actually speaks aloud.
                if server_content:
                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn:
                        for part in (getattr(model_turn, "parts", None) or []):
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                mime = getattr(inline, "mime_type", "") or ""
                                if "audio" in mime:
                                    audio_chunks.append(inline.data)

                # ── FALLBACK audio path: event.content.parts ─────────────────────
                content = getattr(event, "content", None)
                if content:
                    for part in (getattr(content, "parts", None) or []):
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            mime = getattr(inline, "mime_type", "") or ""
                            if "audio" in mime:
                                audio_chunks.append(inline.data)

                # ── Transcript from output_transcription (AI speech → text) ──────
                transcript_text: str | None = None
                if server_content:
                    ot = getattr(server_content, "output_transcription", None)
                    _ot_text = getattr(ot, "text", None) if ot else None
                    if _ot_text and not _is_thinking_content(_ot_text):
                        transcript_text = _ot_text
                if not transcript_text:
                    transcription = getattr(event, "output_transcription", None)
                    _t_text = getattr(transcription, "text", None) if transcription else None
                    if _t_text and not _is_thinking_content(_t_text):
                        transcript_text = _t_text

                # ── Input transcription (user speech → text) ─────────────────────
                input_text: str | None = None
                if server_content:
                    it = getattr(server_content, "input_transcription", None)
                    input_text = getattr(it, "text", None) if it else None
                if not input_text:
                    it2 = getattr(event, "input_transcription", None)
                    input_text = getattr(it2, "text", None) if it2 else None

                # ── Turn-complete detection ───────────────────────────────────────
                # IMPORTANT: event.is_final_response() is intentionally NOT used here.
                # That method was designed for single-turn batch requests. In bidi live
                # streaming (especially with native-audio thinking models), it returns
                # True for every audio-bearing event — treating each audio chunk as a
                # "final" response. This caused every word to appear as a separate
                # finalized bubble instead of accumulating in one growing bubble.
                # Only server_content.turn_complete and event.turn_complete are reliable
                # end-of-model-turn signals in the live streaming context.
                is_turn_complete = (
                    bool(getattr(server_content, "turn_complete", False)) if server_content else False
                )
                if not is_turn_complete:
                    is_turn_complete = bool(getattr(event, "turn_complete", False))

                # Relay barge-in interruption to the client immediately.
                is_interrupted = bool(getattr(server_content, "interrupted", False)) if server_content else False
                if is_interrupted:
                    await websocket.send_json({"type": "interrupted"})
                    # Barge-in ends the current response — flush what we have
                    if ai_audio_sent or ai_transcript_buf:
                        await _flush_response("interrupted")

                if audio_chunks:
                    total_bytes = sum(len(c) for c in audio_chunks)
                    logger.info(f"[/ws/live] audio: {len(audio_chunks)} chunk(s), {total_bytes} bytes")
                if transcript_text:
                    logger.debug(f"[/ws/live] output_transcription: {transcript_text[:80]!r}")
                if input_text:
                    logger.debug(f"[/ws/live] input_transcription: {input_text[:80]!r}")
                if is_turn_complete:
                    logger.info(f"[/ws/live] turn_complete (has_audio={bool(audio_chunks)}, "
                                f"has_transcript={bool(transcript_text)})")

                # ── New user input: implicit end of previous AI response ──────────
                # If the user starts speaking and AI has already sent audio, flush
                # the accumulated AI response before processing the new user input.
                # This handles the case where the deferred flush hasn't fired yet.
                if input_text and ai_audio_sent:
                    await _flush_response("new_user_input")

                # ── Build user transcript incrementally for "typing" animation ──
                if input_text:
                    new_stripped = input_text.strip()
                    buf_stripped = user_transcript_buf.strip()
                    if buf_stripped:
                        check_len = min(6, len(buf_stripped))
                        is_correction = new_stripped.lower().startswith(buf_stripped[:check_len].lower())
                    else:
                        is_correction = False

                    if is_correction:
                        user_transcript_buf = new_stripped
                    else:
                        user_transcript_buf = (user_transcript_buf + input_text)

                    user_transcript_latest = user_transcript_buf
                    await websocket.send_json({
                        "type": "transcript",
                        "text": user_transcript_buf.strip(),
                        "is_user": True,
                        "is_final": False,
                    })

                # ── Accumulate AI transcript fragments and stream live ────────────
                # Always accumulate into ai_transcript_buf regardless of turn_complete.
                # The buffer is only reset at _flush_response(), not at each sub-turn.
                if transcript_text:
                    ai_transcript_buf.append(transcript_text)
                    if not is_turn_complete:
                        # Stream the growing sentence as a partial for "typing" animation
                        growing_ai_text = " ".join(ai_transcript_buf).strip()
                        if growing_ai_text and not _is_thinking_content(growing_ai_text):
                            await websocket.send_json({
                                "type": "transcript",
                                "text": growing_ai_text,
                                "is_user": False,
                                "is_final": False,
                            })

                # ── Relay audio chunks ────────────────────────────────────────────
                # First audio chunk signals the user's turn is definitively over —
                # flush the final user transcript NOW (not at turn_complete) to avoid
                # contamination from the next turn's input_transcription fragments.
                _deferred_log_flush_text: str | None = None
                if audio_chunks and not user_transcript_flushed:
                    user_transcript_flushed = True
                    flush_text = user_transcript_latest.strip()
                    if flush_text:
                        await websocket.send_json({
                            "type": "transcript",
                            "text": flush_text,
                            "is_user": True,
                            "is_final": True,
                        })
                        _deferred_log_flush_text = flush_text
                        logger.debug(f"[/ws/live] User transcript flushed at audio start: {flush_text[:60]!r}")

                if audio_chunks:
                    ai_audio_sent = True

                for chunk in audio_chunks:
                    encoded = base64.b64encode(chunk).decode("ascii")
                    await websocket.send_json({"type": "audio_response", "data": encoded})

                if _deferred_log_flush_text:
                    cmd_logger = _get_live_command_logger()
                    if cmd_logger:
                        cmd_logger.log_agent_decision(
                            agent_name="GeminiLive",
                            decision_type="LIVE_TRANSCRIPT",
                            details={"speaker": "user", "text": _deferred_log_flush_text,
                                     "source": "input_transcription_at_audio_start",
                                     "session_id": session_id},
                        )

                # ── Handle turn_complete ──────────────────────────────────────────
                # Native-audio models fire turn_complete after EVERY audio segment
                # (micro-turns), not just at the end of the full response.
                # Strategy:
                #   - Silent turn_complete (no audio in this event) → model is done →
                #     flush immediately as is_final=True.
                #   - Audio+turn_complete (micro-turn) → model still speaking →
                #     don't flush yet; schedule a 500 ms deferred flush that will be
                #     cancelled if more events arrive.
                if is_turn_complete:
                    has_audio_this_event = bool(audio_chunks)

                    if not has_audio_this_event:
                        # Silent turn_complete — model has finished speaking
                        await _flush_response("silent_turn_complete")
                    else:
                        # Audio arrived in same event as turn_complete (micro-turn or
                        # last-chunk-of-response pattern). Schedule a deferred flush
                        # that fires only if no further events arrive within 500 ms.
                        async def _deferred_flush():
                            await asyncio.sleep(0.5)
                            await _flush_response("deferred_turn_complete")
                        _deferred_flush_task = asyncio.create_task(_deferred_flush())

        except WebSocketDisconnect:
            logger.info(f"[/ws/live] Device disconnected during send: {session_id}")
        except Exception as exc:
            logger.error(f"[/ws/live] send_to_device error: {exc}", exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    # Run both coroutines concurrently; cancel the other when one exits
    receive_task = asyncio.create_task(receive_from_device(), name=f"live-recv-{session_id}")
    send_task = asyncio.create_task(send_to_device(), name=f"live-send-{session_id}")

    try:
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except Exception as exc:
        logger.error(f"[/ws/live] Session error for {session_id}: {exc}", exc_info=True)
    finally:
        logger.info(f"[/ws/live] Session closed: {session_id}")
        try:
            live_queue.close()
        except Exception:
            pass
        try:
            if live_logger is not None and live_logger_owned:
                live_logger.finalize(status="completed")
                clear_execution_logger()
        except Exception as _finalize_exc:
            logger.warning(f"[/ws/live] Failed to finalize live CommandLogger: {_finalize_exc}")
