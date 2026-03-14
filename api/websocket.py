"""WebSocket endpoints."""

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.logger import get_logger
from websocket.audio_buffer import AudioBuffer

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/audio-stream")
async def websocket_audio_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio streaming and STT processing.

    Accepts binary audio chunks and returns partial/final transcripts.
    """
    await websocket.accept()
    logger.info("WebSocket audio stream connection established")

    audio_buffer = AudioBuffer()

    try:
        from config.settings import get_settings
        from services.stt import STTService

        settings = get_settings()
        stt_service = STTService(settings)

        await websocket.send_json(
            {
                "type": "connection",
                "status": "connected",
                "message": "Audio streaming ready",
            }
        )

        while True:
            try:
                data = await websocket.receive_bytes()
                # Silent - don't log every audio chunk

                if audio_buffer.add_chunk(data):
                    audio_data = audio_buffer.get_audio_data()

                    try:
                        transcript = await stt_service.transcribe_streaming(
                            audio_data=audio_data, is_final=False
                        )

                        if transcript:
                            await websocket.send_json(
                                {
                                    "type": "partial",
                                    "text": transcript,
                                    "confidence": 0.8,
                                    "timestamp": time.time(),
                                }
                            )

                    except Exception as stt_error:
                        logger.error(f"STT processing error: {stt_error}")
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"STT processing failed: {stt_error}",
                            }
                        )

            except WebSocketDisconnect:
                logger.info("WebSocket audio stream disconnected by client")
                break

            except Exception as e:
                logger.error(f"WebSocket audio stream error: {e}")
                await websocket.send_json(
                    {"type": "error", "message": f"Streaming error: {e}"}
                )

    except Exception as e:
        logger.error(f"WebSocket audio stream setup error: {e}")
        await websocket.send_json({"type": "error", "message": f"Setup error: {e}"})
    finally:
        if audio_buffer:
            audio_buffer.clear()
        logger.info("WebSocket audio stream connection closed")


@router.websocket("/ws/audio-stream-final")
async def websocket_audio_stream_final(websocket: WebSocket):
    """
    WebSocket endpoint to signal end of audio stream and get final transcript.

    Used when the user stops speaking to get the final, polished transcript.
    """
    await websocket.accept()
    logger.info("WebSocket final audio stream connection established")

    try:
        from config.settings import get_settings
        from services.stt import STTService

        settings = get_settings()
        stt_service = STTService(settings)

        while True:
            try:
                data = await websocket.receive_bytes()
                logger.info(f"Received final audio chunk: {len(data)} bytes")

                if len(data) > 0:
                    from utils.audio_utils import (
                        ensure_wav_format,
                        validate_audio_format,
                    )

                    is_valid, error = validate_audio_format(data)
                    if not is_valid:
                        logger.warning(
                            f"Invalid audio format: {error} - attempting to convert"
                        )
                        data = ensure_wav_format(
                            data, sample_rate=16000, channels=1, sample_width=2
                        )
                        logger.info(f"Converted to WAV format: {len(data)} bytes")

                    transcript = await stt_service.transcribe_streaming(
                        audio_data=data, is_final=True
                    )

                    await websocket.send_json(
                        {
                            "type": "final",
                            "text": transcript,
                            "confidence": 0.95,
                            "timestamp": time.time(),
                        }
                    )

                    if transcript and len(transcript.strip()) > 0:
                        try:
                            from aura_graph.graph import (
                                execute_aura_task_from_streaming,
                            )
                            from main import graph_app

                            result = await execute_aura_task_from_streaming(
                                app=graph_app,
                                streaming_transcript=transcript,
                                config=None,
                                thread_id=None,
                                track_workflow=True,
                            )

                            await websocket.send_json(
                                {
                                    "type": "task_result",
                                    "transcript": transcript,
                                    "intent": result.get("intent"),
                                    "spoken_response": result.get(
                                        "spoken_response", ""
                                    ),
                                    "spoken_audio": result.get("spoken_audio"),
                                    "spoken_audio_format": result.get(
                                        "spoken_audio_format"
                                    ),
                                    "status": result.get("status", "completed"),
                                    "execution_time": result.get("execution_time", 0.0),
                                    "debug_info": result.get("debug_info", {}),
                                }
                            )

                        except Exception as task_error:
                            logger.error(f"Task execution error: {task_error}")
                            await websocket.send_json(
                                {
                                    "type": "task_error",
                                    "message": f"Task execution failed: {task_error}",
                                    "transcript": transcript,
                                }
                            )

                else:
                    await websocket.send_json(
                        {"type": "stream_end", "message": "Audio stream ended"}
                    )
                    break

            except WebSocketDisconnect:
                logger.info("WebSocket final audio stream disconnected by client")
                break

            except Exception as e:
                logger.error(f"WebSocket final audio stream error: {e}")
                await websocket.send_json(
                    {"type": "error", "message": f"Final processing error: {e}"}
                )

    except Exception as e:
        logger.error(f"WebSocket final audio stream setup error: {e}")
    finally:
        logger.info("WebSocket final audio stream connection closed")
