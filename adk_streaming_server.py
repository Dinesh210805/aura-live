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

try:
    from google.adk.runners import Runner as _Runner  # type: ignore[assignment]
    from google.adk.sessions import InMemorySessionService as _InMemorySessionService  # type: ignore[assignment]
    from google.adk.agents.live_request_queue import LiveRequestQueue as _LiveRequestQueue  # type: ignore[assignment]
    from google.adk.agents.run_config import RunConfig as _RunConfig, StreamingMode as _StreamingMode  # type: ignore[assignment]
    from google.genai.types import Blob as _Blob, Part as _Part, Content as _Content, Modality as _Modality  # type: ignore[assignment]

    _ADK_AVAILABLE = True
    logger.info("ADK streaming: all imports resolved successfully")
except ImportError as _e:
    logger.warning(
        f"ADK streaming imports unavailable ({_e}). "
        "/ws/live endpoint will return a graceful error until "
        "'google-adk' and 'google-genai' are installed."
    )

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
You are AURA, an autonomous Android UI navigation agent speaking with a user in real time.

When the user gives a command to control their device, call execute_aura_task
immediately with the full natural-language command.

Confirmation policy — ask the user ONLY for:
  • Sending messages or emails
  • Making purchases
  • Permanently deleting data
  • Posting publicly to social media
For all other navigation actions, proceed without confirmation.

After execute_aura_task returns:
  • If success=true: confirm in one concise spoken sentence.
  • If success=false: briefly explain and suggest a simpler rephrasing.

Keep all responses short — you are being spoken aloud. Never use lists or markdown.
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

    # response_modalities passed as string to avoid Pydantic enum warning
    run_config = _RunConfig(
        response_modalities=["AUDIO"],
        streaming_mode=_StreamingMode.BIDI,
        output_audio_transcription=None,  # transcripts emitted as event.text when available
    )

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
                # Events use content.parts for audio/text blobs.
                # Transcript comes from event.output_transcription.text.
                # Turn completion is signalled by event.is_final_response().
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

                # Input transcription (user speech → text, two possible locations in ADK)
                # Check event.server_content.input_transcription first (newer ADK), then
                # event.input_transcription (older ADK / direct genai path).
                input_text: str | None = None
                server_content = getattr(event, "server_content", None)
                if server_content:
                    it = getattr(server_content, "input_transcription", None)
                    input_text = getattr(it, "text", None) if it else None
                if not input_text:
                    it2 = getattr(event, "input_transcription", None)
                    input_text = getattr(it2, "text", None) if it2 else None

                # is_final_response() is a callable on the event
                try:
                    is_final = bool(event.is_final_response())
                except Exception:
                    is_final = False

                # ── Relay audio chunks ────────────────────────────────────────
                for chunk in audio_chunks:
                    encoded = base64.b64encode(chunk).decode("ascii")
                    await websocket.send_json({
                        "type": "audio_response",
                        "data": encoded,
                    })

                # ── Relay user speech transcript (input_transcription) ─────────
                if input_text:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": input_text,
                        "is_user": True,
                        "is_final": True,
                    })

                # ── Relay AI output transcript ────────────────────────────────
                if transcript_text:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": transcript_text,
                        "is_user": False,
                        "is_final": is_final,
                    })

                # ── Notify idle when turn is complete ─────────────────────────
                if is_final:
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
