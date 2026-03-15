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
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from utils.logger import get_logger
from services.command_logger import get_command_logger, clear_execution_logger

logger = get_logger(__name__)

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


async def handle_live_websocket(websocket: WebSocket, session_id: str) -> None:
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
    #   prefix_padding_ms=200  — 200 ms of sustained speech before turn starts.
    #                            Low enough to catch short commands; still filters
    #                            brief echo bursts (~50–100 ms) from speaker reverb.
    #   silence_duration_ms=700 — 700 ms silence = end of user turn (responsive).
    #   start_of_speech_sensitivity: use DEFAULT (MEDIUM) — LOW was too aggressive
    #                                and prevented normal-volume speech from registering.
    #   START_OF_ACTIVITY_INTERRUPTS — barge-in: user speech stops AURA mid-sentence.
    #   TURN_INCLUDES_ONLY_ACTIVITY  — only active speech, not silence, is in the turn.
    _realtime_input_cfg = None
    if _VAD_TYPES_AVAILABLE:
        try:
            _aad_kwargs: dict = {
                "disabled": False,
                "prefix_padding_ms": 200,   # 200 ms — catches short commands, filters echo
                "silence_duration_ms": 700, # 700 ms silence = end of user turn
                # start_of_speech_sensitivity intentionally omitted → server default (MEDIUM)
                # LOW required shouting to trigger; MEDIUM works at normal speaking volume.
            }
            _realtime_input_cfg = _RealtimeInputConfig(
                automatic_activity_detection=_AutomaticActivityDetection(**_aad_kwargs),
                activity_handling=_ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=_TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            )
            logger.info("[/ws/live] VAD: RealtimeInputConfig applied (200 ms prefix, 700 ms silence, default sensitivity, barge-in ON)")
        except Exception as _vad_exc:
            logger.warning(f"[/ws/live] Could not build RealtimeInputConfig: {_vad_exc} — using defaults")

    _transcription_cfg = None
    if _VAD_TYPES_AVAILABLE and _AudioTranscriptionConfig is not None:
        try:
            _transcription_cfg = _AudioTranscriptionConfig()
        except Exception as _tc_exc:
            logger.warning(f"[/ws/live] AudioTranscriptionConfig() failed: {_tc_exc}")
            _transcription_cfg = None

    # Build RunConfig kwargs — ONLY include optional fields when the config object
    # is not None. Passing None for output_audio_transcription silently disables
    # transcription even when no TypeError is raised, so we omit the key entirely
    # when AudioTranscriptionConfig was unavailable.
    _run_config_kwargs: dict = {
        "response_modalities": ["AUDIO"],
        "streaming_mode": _StreamingMode.BIDI,
    }
    if _transcription_cfg is not None:
        _run_config_kwargs["output_audio_transcription"] = _transcription_cfg
        _run_config_kwargs["input_audio_transcription"] = _transcription_cfg
    else:
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
                    # UI tree sent as supplementary text context via send_content
                    import json as _json

                    tree_text = _json.dumps(raw.get("tree", {}), ensure_ascii=False)[:4096]
                    pkg = raw.get("packageName", "unknown")
                    context_text = (
                        f"[Current app: {pkg}]\n"
                        f"[UI accessibility tree (truncated):\n{tree_text}]"
                    )
                    live_queue.send_content(
                        _Content(role="user", parts=[_Part(text=context_text)])
                    )

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
        # User: Gemini sends partial then corrected input_transcription events.
        #   We track ONLY THE LATEST (overwrite each time) so corrections replace
        #   partials instead of accumulating "ഹ ലോ ദേർ ഹലോ ദേർ" duplicates.
        # AI: Accumulate streaming fragments, send as ONE message at turn end.
        user_transcript_latest: str = ""   # latest (corrected) user input_transcription
        ai_transcript_buf: list[str] = []  # AI response fragments this turn
        user_turn_sent = False             # did we already flush user message?

        try:
            async for event in runner.run_live(
                user_id=session_id,
                session_id=session.id,
                run_config=run_config,
                live_request_queue=live_queue,
            ):
                # Tool call in flight — notify app that a task is executing
                if event.get_function_calls():
                    await websocket.send_json({
                        "type": "task_progress",
                        "status": "executing",
                    })

                # ── Extract audio, transcript, and turn-complete from event ───
                audio_chunks: list[bytes] = []
                is_final = False

                # Parse content.parts for audio blobs
                content = getattr(event, "content", None)
                if content:
                    for part in (getattr(content, "parts", None) or []):
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            mime = getattr(inline, "mime_type", "")
                            if "audio" in mime:
                                audio_chunks.append(inline.data)

                # Transcript from output_transcription (AI speech → text)
                transcription = getattr(event, "output_transcription", None)
                transcript_text = getattr(transcription, "text", None) if transcription else None

                # Input transcription (user speech → text)
                # Check event.server_content.input_transcription (newer ADK) then
                # event.input_transcription (older ADK / direct genai path).
                input_text: str | None = None
                server_content = getattr(event, "server_content", None)
                if server_content:
                    it = getattr(server_content, "input_transcription", None)
                    input_text = getattr(it, "text", None) if it else None
                if not input_text:
                    it2 = getattr(event, "input_transcription", None)
                    input_text = getattr(it2, "text", None) if it2 else None

                # Use server_content.turn_complete for true turn-end detection.
                # is_final_response() also fires on each streaming output_transcription
                # partial, which would flush the transcript as multiple fragmented messages
                # instead of one complete message per turn.
                is_final = bool(getattr(server_content, "turn_complete", False)) if server_content else False

                # Relay barge-in interruption to the client immediately.
                # When the user starts speaking mid-response Gemini sets
                # server_content.interrupted=True before sending turn_complete.
                # The Android client uses this to clear its audio queue and
                # stop playback right away rather than waiting for the queue drain.
                is_interrupted = bool(getattr(server_content, "interrupted", False)) if server_content else False
                if is_interrupted:
                    await websocket.send_json({"type": "interrupted"})

                # Debug: log all transcript/turn events so we can verify Gemini
                # is actually returning transcription data with this model + config.
                if audio_chunks:
                    logger.debug(f"[/ws/live] audio: {len(audio_chunks)} chunks")
                if transcript_text:
                    logger.debug(f"[/ws/live] output_transcription: {transcript_text[:80]!r}")
                if input_text:
                    logger.debug(f"[/ws/live] input_transcription: {input_text[:80]!r}")
                if is_final:
                    logger.debug("[/ws/live] turn_complete received")
                if is_interrupted:
                    logger.debug("[/ws/live] interrupted received")

                # ── Track latest user transcript (overwrite, not append) ──────
                # Gemini sends a partial then a corrected input_transcription
                # for the same utterance. Always take the latest — it's best.
                if input_text:
                    user_transcript_latest = input_text

                # ── Accumulate AI transcript fragments (non-final events only) ──
                # On the turn_complete event, transcript_text is the clean finalized
                # version — skip adding it to the buffer; use it directly at flush time.
                if transcript_text and not is_final:
                    ai_transcript_buf.append(transcript_text)

                # ── Relay audio chunks ────────────────────────────────────────
                # When audio starts arriving, AI is now speaking — flush the
                # latest user transcript as ONE complete chat message.
                if audio_chunks and not user_turn_sent and user_transcript_latest:
                    full_user_text = user_transcript_latest.strip()
                    if full_user_text:
                        cmd_logger = _get_live_command_logger()
                        if cmd_logger:
                            cmd_logger.log_agent_decision(
                                agent_name="GeminiLive",
                                decision_type="LIVE_TRANSCRIPT",
                                details={
                                    "speaker": "user",
                                    "text": full_user_text,
                                    "source": "input_transcription",
                                    "session_id": session_id,
                                },
                            )
                        await websocket.send_json({
                            "type": "transcript",
                            "text": full_user_text,
                            "is_user": True,
                            "is_final": True,
                        })
                    user_transcript_latest = ""
                    user_turn_sent = True

                for chunk in audio_chunks:
                    encoded = base64.b64encode(chunk).decode("ascii")
                    await websocket.send_json({
                        "type": "audio_response",
                        "data": encoded,
                    })

                # ── Flush AI transcript as ONE message at turn end ────────────
                if is_final:
                    # If user spoke but no audio came (tool-only / execute turn), flush now
                    if not user_turn_sent and user_transcript_latest:
                        full_user_text = user_transcript_latest.strip()
                        if full_user_text:
                            cmd_logger = _get_live_command_logger()
                            if cmd_logger:
                                cmd_logger.log_agent_decision(
                                    agent_name="GeminiLive",
                                    decision_type="LIVE_TRANSCRIPT",
                                    details={
                                        "speaker": "user",
                                        "text": full_user_text,
                                        "source": "input_transcription",
                                        "session_id": session_id,
                                    },
                                )
                            await websocket.send_json({
                                "type": "transcript",
                                "text": full_user_text,
                                "is_user": True,
                                "is_final": True,
                            })
                        user_transcript_latest = ""

                    # Send complete AI transcript as a single chat message.
                    # Prefer transcript_text from the turn_complete event (clean, corrected
                    # final version) over the accumulated streaming fragments (may have
                    # spacing/casing artifacts from incremental streaming).
                    full_ai_text = transcript_text.strip() if transcript_text else " ".join(ai_transcript_buf).strip()
                    logger.info(
                        f"[/ws/live] turn_complete → ai_text={full_ai_text[:60]!r} "
                        f"(from_event={bool(transcript_text)}, buf_len={len(ai_transcript_buf)})"
                    )
                    if full_ai_text:
                        cmd_logger = _get_live_command_logger()
                        if cmd_logger:
                            cmd_logger.log_agent_decision(
                                agent_name="GeminiLive",
                                decision_type="LIVE_TRANSCRIPT",
                                details={
                                    "speaker": "assistant",
                                    "text": full_ai_text,
                                    "source": "output_transcription",
                                    "session_id": session_id,
                                },
                            )
                        await websocket.send_json({
                            "type": "transcript",
                            "text": full_ai_text,
                            "is_user": False,
                            "is_final": True,
                        })
                    ai_transcript_buf.clear()
                    user_turn_sent = False  # reset for next user turn

                    await websocket.send_json({
                        "type": "task_progress",
                        "status": "idle",
                    })

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
