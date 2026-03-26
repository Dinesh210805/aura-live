"""
WebSocket router for real-time audio streaming.

Handles WebSocket connections for streaming audio transcription and task execution.
"""

import asyncio
import base64
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.conversation_manager import ConversationManager
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket Streaming"])

# Global conversation manager instance
conversation_manager = ConversationManager(max_turns=5)


async def background_websocket_reader(websocket: WebSocket, stop_event: asyncio.Event):
    """
    Background task to read websocket messages during task execution.
    
    This allows UI tree and screenshot responses to be processed
    while the main task execution is awaiting results.
    """
    logger.info("🔄 Starting background websocket reader")
    
    while not stop_event.is_set():
        try:
            # Short timeout to check stop_event frequently
            message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
            
            if "text" in message:
                msg_data = message["text"]
                try:
                    msg_json = json.loads(msg_data) if isinstance(msg_data, str) else msg_data
                    msg_type = msg_json.get("type")
                    
                    # Handle perception responses
                    if msg_type == "ui_tree_response":
                        request_id = msg_json.get("request_id")
                        ui_tree_data = msg_json.get("ui_tree", msg_json)
                        logger.info(
                            f"📋 [BG] Received UI tree response: request_id={request_id}, "
                            f"elements={len(ui_tree_data.get('elements', []))}"
                        )
                        
                        from services.ui_tree_service import get_ui_tree_service
                        ui_tree_service = get_ui_tree_service()
                        if request_id:
                            handled = ui_tree_service.handle_ui_tree_response(request_id, ui_tree_data)
                            logger.info(f"📋 [BG] UI tree response handled: {handled}")
                    
                    elif msg_type == "screenshot_response":
                        request_id = msg_json.get("request_id")
                        screenshot_b64 = msg_json.get("screenshot_base64") or msg_json.get("screenshot") or ""
                        screenshot_data = {
                            "screenshot_base64": screenshot_b64,
                            "screen_width": msg_json.get("screen_width", msg_json.get("screenWidth", 1080)),
                            "screen_height": msg_json.get("screen_height", msg_json.get("screenHeight", 1920)),
                            "orientation": msg_json.get("orientation", "portrait"),
                            "timestamp": msg_json.get("timestamp", int(time.time() * 1000)),
                        }
                        logger.info(
                            f"📸 [BG] Received screenshot response: request_id={request_id}, "
                            f"size={len(screenshot_data['screenshot_base64'])} bytes"
                        )
                        
                        from services.screenshot_service import get_screenshot_service
                        screenshot_service = get_screenshot_service()
                        if request_id:
                            handled = screenshot_service.handle_screenshot_response(request_id, screenshot_data)
                            logger.info(f"📸 [BG] Screenshot response handled: {handled}")
                    
                    elif msg_type == "gesture_ack":
                        command_id = msg_json.get("command_id")
                        if command_id:
                            from services.real_accessibility import real_accessibility_service
                            ack_success = msg_json.get("success", True)
                            real_accessibility_service.handle_gesture_ack(command_id, ack_success)
                            logger.debug(f"⚡ [BG] Gesture ack handled: {command_id}, success={ack_success}")
                    
                    elif msg_type == "hitl_response":
                        # Human-in-the-loop response from user (background reader)
                        from services.hitl_service import get_hitl_service
                        hitl_service = get_hitl_service()
                        question_id = msg_json.get("question_id")
                        logger.info(f"🙋 [BG] HITL response received: {question_id}")
                        hitl_service.handle_response(msg_json)
                    
                    elif msg_type == "cancel_task":
                        # User pressed cancel in notification
                        cancel_session_id = msg_json.get("session_id", "")
                        logger.warning(f"🚫 [BG] Cancel task requested: session={cancel_session_id}")
                        from services.task_progress import get_task_progress_service
                        tp = get_task_progress_service()
                        tp.abort_task(cancel_session_id, reason="Cancelled by user")
                    
                    # Ignore other message types (handled by main loop when it resumes)
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"[BG] Failed to parse message as JSON: {e}")
            
        except asyncio.TimeoutError:
            # Normal timeout, check if we should stop
            continue
        except WebSocketDisconnect:
            logger.info("🔄 Background reader: WebSocket disconnected")
            break
        except Exception as e:
            error_msg = str(e)
            # Break on disconnect-related errors to avoid tight error loop
            if "disconnect" in error_msg.lower() or "once a disconnect" in error_msg.lower():
                logger.info("🔄 Background reader: WebSocket disconnected (via exception)")
                break
            logger.warning(f"[BG] Background reader error: {e}")
            await asyncio.sleep(0.5)
    
    logger.info("🔄 Background websocket reader stopped")


async def _ensure_screen_capture_ready(websocket: WebSocket) -> bool:
    """
    Pre-flight permission gate for screen capture.

    Notifies the client while waiting for the user to grant the permission dialog.
    Returns True if permission is (or becomes) granted, False if device is
    disconnected or the user denies / times out.
    """
    from services.screenshot_service import get_screenshot_service
    from services.real_accessibility import real_accessibility_service as _ras

    ss = get_screenshot_service()
    if ss._permission_granted:
        return True

    if not _ras.is_device_connected():
        logger.warning("📸 Device not connected — cannot request screen capture permission")
        return False

    logger.info("📸 Screen capture permission required — requesting before task starts")
    try:
        await websocket.send_json({
            "type": "permission_required",
            "permission": "screen_capture",
            "message": "Waiting for screen capture permission — please tap Allow on your device",
        })
    except Exception:
        pass

    await _ras.request_screen_capture_permission()
    granted = await ss.wait_for_permission(timeout=25.0)
    logger.info(f"📸 Screen capture permission: {'granted ✅' if granted else 'denied/timeout ❌'}")

    try:
        await websocket.send_json({
            "type": "permission_result",
            "permission": "screen_capture",
            "granted": granted,
            "message": "Screen capture ready" if granted else "Screen capture permission denied — automation blocked",
        })
    except Exception:
        pass

    return granted


# OpenRouter client for intent classification (lazy initialization)
_openrouter_client = None
_groq_client = None
CLASSIFIER_REQUEST_TIMEOUT_S = 8.0
CLASSIFIER_TOTAL_TIMEOUT_S = 12.0

def _get_openrouter_client():
    """Lazy initialize OpenRouter client."""
    global _openrouter_client
    if _openrouter_client is None:
        from config.settings import Settings
        import openai
        
        settings = Settings()
        if settings.openrouter_api_key:
            _openrouter_client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key
            )
            logger.info("✅ OpenRouter client initialized for intent classification")
        else:
            logger.warning("⚠️ OPENROUTER_API_KEY not set, using pattern fallback")
    return _openrouter_client

def _get_groq_client():
    """Lazy initialize Groq client for fallback."""
    global _groq_client
    if _groq_client is None:
        from config.settings import Settings
        from groq import Groq
        
        settings = Settings()
        _groq_client = Groq(api_key=settings.groq_api_key)
        logger.info("✅ Groq client initialized for intent classification fallback")
    return _groq_client

def _classify_with_llm(transcript: str) -> str:
    """
    Classify intent using tiny LLM via OpenRouter + Groq fallback.
    
    Uses 3-tier fallback:
    1. GLM 4.5 Air (OpenRouter, free)
    2. Llama 3.3 70B Instruct (OpenRouter, free)
    3. Llama 3.3 70B Versatile (Groq, no rate limits)
    
    Args:
        transcript: User's spoken text
        
    Returns:
        "ACTIONABLE" or "CONVERSATIONAL"
        
    Raises:
        Exception: If all models fail
    """
    from config.settings import Settings
    import time
    
    settings = Settings()
    
    # Build models list with provider info
    models = [
        ("openrouter", settings.intent_classification_model),
        ("openrouter", settings.intent_classification_fallback),
        ("groq", settings.intent_classification_fallback_groq),
    ]
    
    for model_idx, (provider, model) in enumerate(models):
        try:
            # Get appropriate client
            if provider == "groq":
                client = _get_groq_client()
            else:
                client = _get_openrouter_client()
                if not client:
                    logger.warning(f"⚠️ OpenRouter client not available, skipping {model}")
                    continue
            
            # Build request params
            request_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a classifier. Answer with ONE word only: ACTIONABLE or CONVERSATIONAL."
                    },
                    {
                        "role": "user",
                        "content": f"""Classify this command:
"{transcript}"

ACTIONABLE = requesting device control OR screen information
- Device control: "Open app", "Tap button", "Send message", "Navigate", etc.
- Screen information: "Describe screen", "What do you see", "Read screen", "What's on screen", etc.
- Includes: "Can you X?", "Could you X?", "Please X", "I want to X"
- Examples: "Can you open WhatsApp?", "Describe the screen", "What do you see?", "Turn on WiFi"

CONVERSATIONAL = talking/asking about capabilities (NO screen visibility needed)
- Examples: "Hello", "How are you?", "What can you do?", "Who are you?", "Help"

Answer:"""
                    }
                ],
                "max_tokens": 5,
                "temperature": 0
            }
            
            # Add GLM-specific parameters (disable thinking mode)
            if "glm" in model.lower():
                request_params["extra_body"] = {"reasoning": {"enabled": False}}
            
            request_client = client
            if hasattr(client, "with_options"):
                try:
                    request_client = client.with_options(
                        timeout=CLASSIFIER_REQUEST_TIMEOUT_S
                    )
                except Exception as timeout_opt_error:
                    logger.debug(
                        f"Could not apply classifier timeout options: {timeout_opt_error}"
                    )

            response = request_client.chat.completions.create(**request_params)
            
            result = response.choices[0].message.content.strip().upper()
            
            # Validate output
            if result in ["ACTIONABLE", "CONVERSATIONAL"]:
                logger.info(f"✅ Intent classified ({model}): {result} | '{transcript[:50]}...'")
                return result
            else:
                logger.warning(f"⚠️ Invalid classification from {model}: {result}")
                continue  # Try next model
                
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Check for rate limit (multiple ways to detect it)
            if ("429" in error_msg or "rate limit" in error_msg.lower() or 
                "Too Many Requests" in error_msg or error_type == "RateLimitError"):
                logger.warning(f"⚠️ Rate limit hit on {model}, trying fallback...")
                continue  # Try next model immediately
            
            # Check for 400 errors (invalid params)
            elif "400" in error_msg or error_type == "BadRequestError":
                logger.warning(f"⚠️ Invalid request to {model}: {error_msg[:100]}")
                continue  # Try next model
            
            else:
                logger.warning(f"⚠️ Classification failed with {model}: {error_type}: {str(e)[:100]}")
                continue  # Try next model
    
    # If we get here, both models failed
    raise Exception("All LLM classification models failed")

def _classify_with_patterns(transcript: str) -> str:
    """
    Fallback pattern-based classification.
    
    Used when OpenRouter API is unavailable or fails.
    
    Args:
        transcript: User's spoken text
        
    Returns:
        "ACTIONABLE" or "CONVERSATIONAL"
    """
    text = transcript.lower().strip()

    # Conversational keywords
    conversational_patterns = [
        "hello", "hi", "hey", "greetings",
        "good morning", "good afternoon", "good evening",
        "how are you", "what's up",
        "thanks", "thank you", "bye", "goodbye", "see you",
        "who are you", "what can you do", "help",
        "tell me about", "what are your capabilities",
    ]

    # Actionable keywords (device control actions)
    actionable_patterns = [
        "open", "close", "launch", "start", "stop",
        "send", "call", "message", "text",
        "search", "find", "show", "display",
        "install", "uninstall", "delete", "remove",
        "go to", "take me to", "bring me to", "navigate",
        "scroll", "swipe", "tap", "press", "click",
        "type", "write",
        "turn on", "turn off", "enable", "disable",
        "torch", "flashlight", "flash",
        "home screen", "home", "back",
    ]

    # Information query patterns (screen reading - actionable)
    info_query_patterns = [
        "what is on", "what's on", "whats on",
        "what is in", "what's in", "whats in",
        "can you see", "do you see", "describe",
        "read screen", "read the screen", "read my screen",
        "what do you see", "what can you see",
        "tell me what", "on my screen", "in my screen", "on screen",
        "what's visible", "analyze screen",
        "see my screen", "see the screen",
    ]

    # Check for patterns
    conversational_score = sum(1 for p in conversational_patterns if p in text)
    actionable_score = sum(1 for p in actionable_patterns if p in text)
    info_query_score = sum(1 for p in info_query_patterns if p in text)

    if info_query_score > 0:
        return "ACTIONABLE"
    if actionable_score > 0:
        return "ACTIONABLE"
    elif conversational_score > 0:
        return "CONVERSATIONAL"
    else:
        return "CONVERSATIONAL"

def classify_simple_intent(transcript: str) -> str:
    """
    Classify intent as ACTIONABLE or CONVERSATIONAL.
    
    Uses tiny LLM (GLM 4.5 Air / Llama 3.3 70B) via OpenRouter for accurate
    classification, with pattern matching as fallback.
    
    Args:
        transcript: User's spoken text

    Returns:
        "CONVERSATIONAL" or "ACTIONABLE"
    """
    try:
        # Try LLM classification first (fast, accurate)
        return _classify_with_llm(transcript)
    except Exception as e:
        # Fallback to pattern matching
        logger.warning(f"⚠️ LLM classification failed, using pattern fallback: {e}")
        result = _classify_with_patterns(transcript)
        logger.info(f"📝 Pattern fallback classification: {result}")
        return result


async def _classify_intent_with_timeout(transcript: str) -> str:
    """Run intent classification with a hard timeout to avoid stuck websocket tasks."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(classify_simple_intent, transcript),
            timeout=CLASSIFIER_TOTAL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"⏱️ Intent classification timed out after {CLASSIFIER_TOTAL_TIMEOUT_S}s; using pattern fallback"
        )
        return _classify_with_patterns(transcript)
    except Exception as e:
        logger.warning(
            f"⚠️ Intent classification failed unexpectedly, using pattern fallback: {e}"
        )
        return _classify_with_patterns(transcript)


class AudioBuffer:
    """Buffer for managing streaming audio chunks with enhanced validation."""

    def __init__(self, threshold: int = 16000, max_size: int = 1024 * 1024):
        self.chunks = []
        self.total_size = 0
        self.threshold = threshold
        self.max_size = max_size

    def add_chunk(self, chunk: bytes) -> bool:
        """
        Add audio chunk to buffer.

        Args:
            chunk: Audio data chunk

        Returns:
            True if buffer is ready for processing
        """
        if len(chunk) == 0:
            return False

        # Check max buffer size
        if self.total_size + len(chunk) > self.max_size:
            logger.warning("Buffer full, clearing old data")
            self.clear()

        self.chunks.append(chunk)
        self.total_size += len(chunk)

        return self.total_size >= self.threshold

    def get_audio_data(self) -> bytes:
        """Get combined audio data and reset buffer."""
        if not self.chunks:
            return b""

        audio_data = b"".join(self.chunks)
        self.chunks.clear()
        self.total_size = 0
        return audio_data

    def clear(self):
        """Clear the buffer."""
        self.chunks.clear()
        self.total_size = 0


@router.websocket("/ws/audio-stream")
async def websocket_audio_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio streaming and STT processing.

    Accepts binary audio chunks and returns partial/final transcripts.

    Protocol:
    1. Client sends JSON config message (optional): {"type": "config", "language": "en" or "ta" or null for auto-detect}
    2. Client sends binary audio chunks
    3. Server responds with partial transcripts

    Supported languages: en, ta, hi, es, fr, de, ja, ko, zh, ar, ru, and 90+ more
    If no language specified, Whisper will automatically detect it.
    """
    await websocket.accept()
    logger.info("WebSocket audio stream connection established")

    audio_buffer = AudioBuffer(threshold=16000, max_size=1024 * 1024)
    last_activity = time.time()
    timeout = 60  # 60 second timeout
    language_hint = None  # Default: auto-detect

    try:
        # Import STT service
        from config.settings import get_settings
        from services.stt import STTService

        settings = get_settings()
        stt_service = STTService(settings)

        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connection",
                "status": "connected",
                "message": "Audio streaming ready",
                "timeout": timeout,
            }
        )

        while True:
            try:
                # Check timeout
                if time.time() - last_activity > timeout:
                    await websocket.send_json(
                        {
                            "type": "timeout",
                            "message": "Connection timeout due to inactivity",
                        }
                    )
                    break

                # Try to receive data (could be JSON config or binary audio)
                try:
                    # Try JSON first (for config messages)
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=0.1
                    )

                    # Handle config message
                    if message.get("type") == "config":
                        language_hint = message.get("language")
                        logger.info(
                            f"Client set language preference: {language_hint or 'auto-detect'}"
                        )
                        await websocket.send_json(
                            {
                                "type": "config_ack",
                                "language": language_hint,
                                "message": f"Language set to: {language_hint or 'auto-detect'}",
                            }
                        )
                        continue

                except asyncio.TimeoutError:
                    pass  # No JSON message, try binary
                except Exception:
                    pass  # Not JSON, try binary

                # Receive binary audio data with timeout
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=5.0)

                last_activity = time.time()
                logger.debug(f"Received audio chunk: {len(data)} bytes")

                # Add chunk to buffer
                if audio_buffer.add_chunk(data):
                    audio_data = audio_buffer.get_audio_data()

                    try:
                        # Process audio with STT (auto-detect language or use client-specified)
                        transcript = await stt_service.transcribe_streaming(
                            audio_data=audio_data,
                            is_final=False,
                            language=language_hint,
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

            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json(
                    {"type": "heartbeat", "timestamp": time.time()}
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
        try:
            await websocket.send_json({"type": "error", "message": f"Setup error: {e}"})
        except Exception:
            pass
    finally:
        audio_buffer.clear()
        logger.info("WebSocket audio stream connection closed")


@router.websocket("/ws/audio-stream-final")
async def websocket_audio_stream_final(websocket: WebSocket):
    """
    WebSocket endpoint for final audio processing and task execution.

    Used when the user stops speaking to get the final transcript and execute the task.

    Protocol:
    1. Client sends JSON config (optional): {"type": "config", "language": "en" or "ta" or null}
    2. Client sends final binary audio chunk
    3. Server transcribes and executes the task

    Supports all languages that Whisper supports (90+), including Tamil, English, Hindi, etc.
    """
    await websocket.accept()
    logger.info("WebSocket final audio stream connection established")

    language_hint = None  # Default: auto-detect

    try:
        from aura_graph.graph import execute_aura_task_from_streaming
        from config.settings import get_settings
        from services.stt import STTService

        settings = get_settings()
        stt_service = STTService(settings)

        # Get graph app from main module
        import main

        app_instance = main.graph_app

        while True:
            try:
                # Try to receive config message first
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=0.1
                    )

                    if message.get("type") == "config":
                        language_hint = message.get("language")
                        logger.info(
                            f"Final stream: language set to {language_hint or 'auto-detect'}"
                        )
                        await websocket.send_json(
                            {"type": "config_ack", "language": language_hint}
                        )
                        continue

                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass

                data = await websocket.receive_bytes()
                logger.info(f"Received final audio chunk: {len(data)} bytes")

                if len(data) > 0:
                    # Validate and convert audio format
                    from utils.audio_utils import (
                        ensure_wav_format,
                        validate_audio_format,
                    )

                    is_valid, error = validate_audio_format(data)
                    if not is_valid:
                        logger.warning(f"Invalid audio format: {error} - converting")
                        data = ensure_wav_format(
                            data, sample_rate=16000, channels=1, sample_width=2
                        )

                    # Process final audio with language hint
                    transcript = await stt_service.transcribe_streaming(
                        audio_data=data, is_final=True, language=language_hint
                    )

                    await websocket.send_json(
                        {
                            "type": "final",
                            "text": transcript,
                            "confidence": 0.95,
                            "timestamp": time.time(),
                        }
                    )

                    # Execute task if transcript available
                    if transcript and len(transcript.strip()) > 0 and app_instance:
                        # G7: barge-in — if HITL is waiting for user input, route the
                        # transcript as the answer instead of launching a new task.
                        try:
                            from services.hitl_service import get_hitl_service as _get_hitl
                            if _get_hitl().register_voice_answer(transcript):
                                logger.info(
                                    f"🎙️ Voice transcript routed to HITL: '{transcript[:60]}'"
                                )
                                await websocket.send_json({
                                    "type": "hitl_voice_answer",
                                    "text": transcript,
                                    "timestamp": time.time(),
                                })
                                continue
                        except Exception as _hitl_barge_err:
                            logger.debug(f"HITL barge-in check failed: {_hitl_barge_err}")

                        try:
                            # Pre-flight screen capture permission gate
                            if not await _ensure_screen_capture_ready(websocket):
                                logger.warning("📸 Screen capture not available — voice task skipped")
                                continue

                            from services.screenshot_service import get_screenshot_service
                            _ss_voice = get_screenshot_service()
                            _ss_voice.mark_task_active()
                            try:
                                result = await execute_aura_task_from_streaming(
                                    app=app_instance,
                                    streaming_transcript=transcript,
                                    config=None,
                                    thread_id=None,
                                    track_workflow=True,
                                )
                            finally:
                                _ss_voice.mark_task_done()

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
                logger.info("WebSocket final audio stream disconnected")
                break

            except Exception as e:
                logger.error(f"WebSocket final audio error: {e}")
                await websocket.send_json(
                    {"type": "error", "message": f"Processing error: {e}"}
                )

    except Exception as e:
        logger.error(f"WebSocket final audio setup error: {e}")
    finally:
        logger.info("WebSocket final audio stream closed")


@router.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """
    WebSocket endpoint for continuous conversation mode (like Siri/Alexa).

    Protocol:
    1. Client: {"type": "start", "session_id": "unique_id"}
    2. Client: binary audio chunks (while speaking)
    3. Client: {"type": "end_turn"}
    4. Server: {"type": "response", "text": "...", "audio": "base64...", "audio_format": "audio/wav"}
    5. Repeat steps 1-4 for multi-turn conversation
    6. Client: {"type": "end_conversation"}

    Step-by-step automation protocol:
    7. Server: {"type": "request_ui"}
    8. Client: {"type": "ui_snapshot", "tree": {...}, "screenshot_base64": "..."}
    9. Server: {"type": "execute_step", "step_id": "1", "action": {...}}
    10. Client: {"type": "step_result", "step_id": "1", "success": true, "ui_after": {...}}

    Auto-connects device on WebSocket connection for seamless operation.
    """
    await websocket.accept()
    logger.info("Conversation WebSocket established")

    # AUTO-CONNECT DEVICE: Register device immediately when WebSocket connects
    try:
        from services.real_accessibility import real_accessibility_service
        from services.visual_feedback import get_visual_feedback_service
        from utils.app_inventory_utils import get_app_inventory_manager

        # Register WebSocket for instant gesture execution
        real_accessibility_service.set_websocket(websocket)
        logger.info("⚡ WebSocket registered for instant gesture execution")
        
        # Register WebSocket for visual feedback
        visual_feedback = get_visual_feedback_service()
        visual_feedback.set_websocket(websocket)
        logger.info("✨ WebSocket registered for visual feedback")
        
        # Register WebSocket for task progress updates
        from services.task_progress import get_task_progress_service
        task_progress_service = get_task_progress_service()
        task_progress_service.register_websocket(websocket)
        logger.info("📋 WebSocket registered for task progress updates")
        
        # Register WebSocket for Human-in-the-Loop interactions
        from services.hitl_service import get_hitl_service
        hitl_service = get_hitl_service()
        hitl_service.register_websocket(websocket)
        logger.info("🙋 WebSocket registered for HITL interactions")

        # Try to get device name from app inventory (matches command polling)
        inventory_manager = get_app_inventory_manager()
        device_name = (
            inventory_manager.get_first_device_name() or "Android Device (WebSocket)"
        )

        # Set device info - will be updated when Android sends actual info via device_info message
        default_device_info = {
            "screen_width": 1080,
            "screen_height": 2400,
            "density_dpi": 420,
            "device_name": device_name,
            "android_version": "Unknown",
            "connected_at": time.time(),
        }
        real_accessibility_service.set_device_connection(default_device_info)
        logger.info(f"🔌 Device auto-connected via WebSocket: {device_name}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to auto-connect device: {e}")

    # Increased threshold for better transcription quality (0.5 seconds of audio at 16kHz)
    audio_buffer = AudioBuffer(threshold=32000, max_size=2 * 1024 * 1024)
    session_id = None
    is_recording = False
    language_hint = None
    session_voice_id = None  # Voice ID from Android client for TTS

    try:
        import main
        from agents.responder import ResponderAgent
        from aura_graph.graph import execute_aura_task_from_streaming
        from config.settings import get_settings
        from services.llm import LLMService
        from services.stt import STTService
        from services.tts import TTSService

        settings = get_settings()
        stt_service = STTService(settings)
        tts_service = TTSService(settings)
        llm_service = LLMService(settings)
        responder = ResponderAgent(llm_service=llm_service, tts_service=tts_service)
        app_instance = main.graph_app

        await websocket.send_json(
            {"type": "connected", "message": "Conversation mode ready"}
        )

        while True:
            try:
                # Try to receive any message (JSON or binary)
                try:
                    # Use receive() to get either text or binary
                    message = await asyncio.wait_for(websocket.receive(), timeout=10.0)

                    # Check if it's a text message (JSON)
                    if "text" in message:
                        msg_data = message["text"]
                        msg_json = (
                            json.loads(msg_data)
                            if isinstance(msg_data, str)
                            else msg_data
                        )
                        msg_type = msg_json.get("type")

                        if msg_type == "start":
                            session_id = msg_json.get(
                                "session_id", f"session_{time.time()}"
                            )
                            language_hint = msg_json.get("language")
                            session_voice_id = msg_json.get("voice_id")  # Extract voice preference
                            is_recording = True
                            audio_buffer.clear()
                            logger.info(f"Started turn for session {session_id}, voice={session_voice_id}")
                            await websocket.send_json(
                                {
                                    "type": "recording",
                                    "session_id": session_id,
                                    "state": "listening",
                                }
                            )
                            continue

                        elif msg_type == "device_info":
                            # Android app sends device info to update connection with real values
                            try:
                                from services.real_accessibility import (
                                    real_accessibility_service,
                                )

                                device_info = {
                                    "screen_width": msg_json.get("screen_width", msg_json.get("screenWidth", 1080)),
                                    "screen_height": msg_json.get("screen_height", msg_json.get("screenHeight", 1920)),
                                    "density_dpi": msg_json.get("density_dpi", 420),
                                    "device_name": msg_json.get(
                                        "device_name", "Android Device"
                                    ),
                                    "android_version": msg_json.get(
                                        "android_version", "Unknown"
                                    ),
                                    "connected_at": time.time(),
                                }
                                real_accessibility_service.set_device_connection(
                                    device_info
                                )
                                logger.info(
                                    f"📱 Device info updated: {device_info.get('device_name')}"
                                )
                                
                                # Sync screen capture permission state from Android
                                screen_capture_available = msg_json.get("screen_capture_available", False)
                                if screen_capture_available:
                                    from services.screenshot_service import get_screenshot_service
                                    ss = get_screenshot_service()
                                    ss.handle_permission_result(True)
                                    logger.info("📸 Screen capture permission synced from device_info: GRANTED")

                                await websocket.send_json(
                                    {
                                        "type": "device_info_ack",
                                        "status": "connected",
                                        "device_name": device_info.get("device_name"),
                                        "backend_ready": True,
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Failed to update device info: {e}")
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "message": f"Device info update failed: {e}",
                                    }
                                )
                            continue

                        elif msg_type == "text_input":
                            # Handle text command from Android (text input instead of voice)
                            text_command = msg_json.get("text", "").strip()
                            session_id = msg_json.get("session_id", session_id or f"session_{time.time()}")
                            # Update voice preference if provided in this message
                            if msg_json.get("voice_id"):
                                session_voice_id = msg_json.get("voice_id")
                            logger.info(f"📝 Received text command: '{text_command}', voice={session_voice_id}")
                            
                            if not text_command:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Empty text command"
                                })
                                continue
                            
                            # Note: Don't send transcript ack - Android already shows the message
                            # Just notify that we're processing
                            
                            # Process the text command (same logic as voice transcript)
                            # Get conversation history
                            history = conversation_manager.format_history(session_id)
                            
                            # Classify intent (run in thread pool - makes blocking HTTP API calls)
                            intent_class = await _classify_intent_with_timeout(text_command)
                            logger.info(f"🎯 Text command intent: {intent_class}")
                            
                            response_text = ""
                            automation_result = None
                            
                            if intent_class == "CONVERSATIONAL":
                                logger.info("💭 Generating conversational response for text input...")
                                text_lower = text_command.lower().strip()
                                if any(g in text_lower for g in ["hello", "hi ", "hey", "greetings", "good morning", "good afternoon", "good evening"]):
                                    conv_action = "greeting"
                                elif any(h in text_lower for h in ["help", "what can you do", "capabilities"]):
                                    conv_action = "help"
                                else:
                                    conv_action = "question"
                                
                                response_text = await asyncio.to_thread(
                                    responder.generate_feedback,
                                    intent={"action": conv_action, "content": text_command, "confidence": 1.0},
                                    status="conversational",
                                    transcript=text_command,
                                    conversation_history=history,
                                )
                            else:
                                logger.info("🤖 Executing automation task from text input...")

                                # Pre-flight screen capture permission gate
                                if not await _ensure_screen_capture_ready(websocket):
                                    logger.warning("📸 Screen capture not available — text task skipped")
                                    continue

                                from services.screenshot_service import get_screenshot_service
                                _ss = get_screenshot_service()

                                # Spawn background reader
                                stop_event = asyncio.Event()
                                bg_reader = asyncio.create_task(
                                    background_websocket_reader(websocket, stop_event)
                                )

                                _ss.mark_task_active()
                                try:
                                    result = await execute_aura_task_from_streaming(
                                        app=app_instance,
                                        streaming_transcript=text_command,
                                        config=None,
                                        thread_id=session_id,
                                        track_workflow=True,
                                        session_id=session_id,
                                    )
                                finally:
                                    _ss.mark_task_done()
                                    stop_event.set()
                                    try:
                                        await asyncio.wait_for(bg_reader, timeout=1.0)
                                    except asyncio.TimeoutError:
                                        bg_reader.cancel()
                                    except Exception as e:
                                        logger.warning(f"Error stopping bg reader: {e}")
                                
                                response_text = result.get("spoken_response", "Task completed")
                                automation_result = {
                                    "status": result.get("status", "completed"),
                                    "intent": result.get("intent"),
                                    "execution_time": result.get("execution_time", 0.0),
                                }
                            
                            # Store conversation turn
                            conversation_manager.add_turn(
                                session_id=session_id,
                                user_message=text_command,
                                assistant_message=response_text,
                                success=True,
                                error=None,
                            )
                            
                            # Send response
                            response_payload = {
                                "type": "response",
                                "text": response_text,
                                "state": "responding",
                                "ready_for_next_turn": True,
                                "intent_type": intent_class.lower(),
                            }
                            if automation_result:
                                response_payload["automation_result"] = automation_result
                            
                            await websocket.send_json(response_payload)
                            logger.info("✅ Text command response sent")
                            continue

                        elif msg_type == "end_turn":
                            is_recording = False
                            audio_data = audio_buffer.get_audio_data()
                            transcript = ""  # Initialize transcript

                            if len(audio_data) > 0:
                                logger.info(
                                    f"Audio processing started: size={len(audio_data)} bytes"
                                )
                                # Transcribe
                                transcript = await stt_service.transcribe_streaming(
                                    audio_data=audio_data,
                                    is_final=True,
                                    language=language_hint,
                                )
                                logger.info(f"Transcription completed: text='{transcript}'")
                            else:
                                logger.warning(
                                    "Audio data empty, transcription skipped"
                                )

                            await websocket.send_json(
                                {
                                    "type": "transcript",
                                    "text": transcript,
                                    "final": True,
                                    "state": "thinking",
                                }
                            )

                            if transcript and transcript.strip():
                                logger.info(
                                    f"Response generation started: input='{transcript.strip()}'"
                                )
                                # Get conversation history
                                history = conversation_manager.format_history(
                                    session_id
                                )

                                # Check if conversational or actionable (run in thread pool - makes blocking HTTP API calls)
                                intent_class = await _classify_intent_with_timeout(transcript)
                                logger.info(f"🎯 Intent classification: {intent_class}")

                                response_text = ""

                                if intent_class == "CONVERSATIONAL":
                                    logger.info(
                                        "💭 Generating conversational response..."
                                    )
                                    # Detect specific conversational intent
                                    text_lower = transcript.lower().strip()
                                    if any(
                                        g in text_lower
                                        for g in [
                                            "hello",
                                            "hi ",
                                            "hey",
                                            "greetings",
                                            "good morning",
                                            "good afternoon",
                                            "good evening",
                                        ]
                                    ):
                                        conv_action = "greeting"
                                    elif any(
                                        h in text_lower
                                        for h in [
                                            "help",
                                            "what can you do",
                                            "capabilities",
                                        ]
                                    ):
                                        conv_action = "help"
                                    else:
                                        conv_action = "question"  # General questions

                                    # Direct conversational response (run in thread pool since it's sync)
                                    response_text = await asyncio.to_thread(
                                        responder.generate_feedback,
                                        intent={
                                            "action": conv_action,
                                            "content": transcript,
                                            "confidence": 1.0,
                                        },
                                        status="conversational",
                                        transcript=transcript,
                                        conversation_history=history,
                                    )
                                    automation_result = None
                                    logger.info(
                                        f"✅ Response generated: '{response_text[:100]}...'"
                                    )
                                else:
                                    logger.info("🤖 Executing automation task...")

                                    # Pre-flight screen capture permission gate
                                    if not await _ensure_screen_capture_ready(websocket):
                                        logger.warning("📸 Screen capture not available — conversation task skipped")
                                        continue

                                    from services.screenshot_service import get_screenshot_service
                                    _ss_conv = get_screenshot_service()

                                    # Spawn background reader to process UI tree and screenshot responses
                                    # while task execution is running
                                    stop_event = asyncio.Event()
                                    bg_reader = asyncio.create_task(
                                        background_websocket_reader(websocket, stop_event)
                                    )

                                    _ss_conv.mark_task_active()
                                    try:
                                        # Execute task through AURA graph
                                        result = await execute_aura_task_from_streaming(
                                            app=app_instance,
                                            streaming_transcript=transcript,
                                            config=None,
                                            thread_id=session_id,
                                            track_workflow=True,
                                            session_id=session_id,  # NEW: Pass session for context
                                        )
                                    finally:
                                        _ss_conv.mark_task_done()
                                        # Stop background reader
                                        stop_event.set()
                                        try:
                                            await asyncio.wait_for(bg_reader, timeout=1.0)
                                        except asyncio.TimeoutError:
                                            bg_reader.cancel()
                                        except Exception as e:
                                            logger.warning(f"Error stopping bg reader: {e}")

                                    response_text = result.get(
                                        "spoken_response", "Task completed"
                                    )

                                    automation_result = {
                                        "status": result.get("status", "completed"),
                                        "intent": result.get("intent"),
                                        "execution_time": result.get(
                                            "execution_time", 0.0
                                        ),
                                    }

                                # Store conversation turn with error tracking
                                if intent_class == "CONVERSATIONAL":
                                    conversation_manager.add_turn(
                                        session_id=session_id,
                                        user_message=transcript,
                                        assistant_message=response_text,
                                        success=True,
                                        error=None,
                                    )
                                else:
                                    result_status = result.get("status", "completed")
                                    error_msg = result.get("error_message")
                                    conversation_manager.add_turn(
                                        session_id=session_id,
                                        user_message=transcript,
                                        assistant_message=response_text,
                                        success=(result_status != "failed"),
                                        error=error_msg,
                                    )

                                # Send response
                                response_payload = {
                                    "type": "response",
                                    "text": response_text,
                                    # Optional new fields
                                    "state": "responding",
                                    "ready_for_next_turn": True,
                                    "intent_type": intent_class.lower(),
                                }

                                # Add automation result if available
                                if automation_result:
                                    response_payload["automation_result"] = (
                                        automation_result
                                    )

                                logger.info("📤 Sending response to client...")
                                await websocket.send_json(response_payload)
                                logger.info("✅ Response sent successfully")
                            else:
                                logger.warning(
                                    "⚠️ Empty transcript, no response generated"
                                )

                        elif msg_type == "end_conversation":
                            if session_id:
                                conversation_manager.clear_session(session_id)
                            await websocket.send_json(
                                {"type": "goodbye", "message": "Conversation ended"}
                            )
                            break

                        elif msg_type == "ui_snapshot":
                            # Android sent UI snapshot in response to request_ui (legacy)
                            # Note: This is legacy - new pipeline uses request_ui_tree and request_screenshot separately
                            # via the Perception Controller. This handler is kept for backward compatibility.
                            ui_tree = msg_json.get("tree", {})
                            screenshot_b64 = msg_json.get("screenshot_base64", "")
                            timestamp = msg_json.get(
                                "timestamp", int(time.time() * 1000)
                            )
                            logger.info(
                                f"📱 Received UI snapshot (legacy): {len(ui_tree.get('elements', []))} elements, screenshot: {bool(screenshot_b64)}"
                            )

                            # Update real_accessibility_service with screenshot data (for backward compatibility)
                            try:
                                from services.real_accessibility import (
                                    RealScreenshotData,
                                    RealUIElement,
                                    real_accessibility_service,
                                )

                                # Convert UI elements to RealUIElement objects
                                ui_elements = []
                                for elem in ui_tree.get("elements", []):
                                    ui_elements.append(
                                        RealUIElement(
                                            id=elem.get("id"),
                                            className=elem.get("className"),
                                            text=elem.get("text"),
                                            contentDescription=elem.get(
                                                "contentDescription"
                                            ),
                                            bounds=elem.get("bounds", {}),
                                            isClickable=elem.get("isClickable", False),
                                            isScrollable=elem.get(
                                                "isScrollable", False
                                            ),
                                            isEditable=elem.get("isEditable", False),
                                            isEnabled=elem.get("isEnabled", True),
                                            packageName=elem.get("packageName"),
                                            viewId=elem.get("viewId"),
                                        )
                                    )

                                # Create screenshot data
                                screenshot_data = RealScreenshotData(
                                    screenshot=screenshot_b64,
                                    screenWidth=ui_tree.get("screenWidth", 1080),
                                    screenHeight=ui_tree.get("screenHeight", 2400),
                                    timestamp=timestamp,
                                    uiElements=ui_elements,
                                )

                                real_accessibility_service.last_screenshot = (
                                    screenshot_data
                                )
                                # Sync real display dimensions into device_info so gesture
                                # bounds checking uses the actual screen size, not defaults
                                snap_w = ui_tree.get("screenWidth", 0)
                                snap_h = ui_tree.get("screenHeight", 0)
                                if snap_w > real_accessibility_service.device_info.get("screen_width", 0):
                                    real_accessibility_service.device_info["screen_width"] = snap_w
                                if snap_h > real_accessibility_service.device_info.get("screen_height", 0):
                                    real_accessibility_service.device_info["screen_height"] = snap_h
                                logger.info(
                                    f"✅ Updated accessibility service with {len(ui_elements)} UI elements"
                                )

                            except Exception as e:
                                logger.error(
                                    f"Failed to update accessibility service: {e}"
                                )

                            await websocket.send_json(
                                {
                                    "type": "ui_snapshot_ack",
                                    "elements_count": len(ui_tree.get("elements", [])),
                                    "has_screenshot": bool(screenshot_b64),
                                }
                            )

                        elif msg_type == "ui_tree_response":
                            # Android sent UI tree in response to request_ui_tree
                            request_id = msg_json.get("request_id")
                            ui_tree_data = msg_json.get("ui_tree", msg_json)  # Fall back to full msg if no nested ui_tree
                            logger.info(
                                f"📋 Received UI tree response: request_id={request_id}, "
                                f"elements={len(ui_tree_data.get('elements', []))}, keys={list(ui_tree_data.keys())[:5]}"
                            )

                            # Forward to UI tree service
                            from services.ui_tree_service import get_ui_tree_service
                            ui_tree_service = get_ui_tree_service()
                            if request_id:
                                handled = ui_tree_service.handle_ui_tree_response(request_id, ui_tree_data)
                                logger.info(f"📋 UI tree response handled: {handled}")

                        elif msg_type == "screenshot_response":
                            # Android sent screenshot in response to request_screenshot
                            request_id = msg_json.get("request_id")
                            screenshot_b64 = msg_json.get("screenshot_base64") or msg_json.get("screenshot") or ""
                            screenshot_data = {
                                "screenshot_base64": screenshot_b64,
                                "screen_width": msg_json.get("screen_width", msg_json.get("screenWidth", 1080)),
                                "screen_height": msg_json.get("screen_height", msg_json.get("screenHeight", 1920)),
                                "orientation": msg_json.get("orientation", "portrait"),
                                "timestamp": msg_json.get("timestamp", int(time.time() * 1000)),
                            }
                            logger.info(
                                f"📸 Received screenshot response: request_id={request_id}, "
                                f"size={len(screenshot_data['screenshot_base64'])} bytes"
                            )

                            # Forward to screenshot service
                            from services.screenshot_service import get_screenshot_service
                            screenshot_service = get_screenshot_service()
                            if request_id:
                                handled = screenshot_service.handle_screenshot_response(request_id, screenshot_data)
                                logger.info(f"📸 Screenshot response handled: {handled}")

                        elif msg_type == "contact_resolution_result":
                            # Android sent contact resolution result
                            request_id = msg_json.get("request_id")
                            contact_name = msg_json.get("contact_name", "")
                            phone_number = msg_json.get("phone_number")
                            success = msg_json.get("success", False)
                            error = msg_json.get("error")
                            
                            logger.info(
                                f"📞 Received contact resolution result: {contact_name} → "
                                f"{'✅ ' + phone_number if success else '❌ ' + (error or 'not found')}"
                            )

                            # Forward to contact resolver
                            from services.contact_resolver import ContactResolver
                            # Create a temporary contact resolver to handle the result
                            # Note: The actual contact resolver that made the request is in gesture_executor
                            # We need to handle this result globally
                            if request_id:
                                # Store result in global registry for any pending contact resolver to pick up
                                # This is handled by ContactResolver's handle_contact_resolution_result method
                                # We need to make it accessible globally
                                if hasattr(real_accessibility_service, '_contact_resolver'):
                                    real_accessibility_service._contact_resolver.handle_contact_resolution_result(msg_json)
                                else:
                                    logger.warning("⚠️ No contact resolver registered to handle result")

                        elif msg_type == "step_result":
                            # Android reports result of executed step
                            step_id = msg_json.get("step_id")
                            success = msg_json.get("success", False)
                            error = msg_json.get("error")
                            ui_after = msg_json.get("ui_after", {})
                            logger.info(
                                f"📱 Step {step_id} result: {'✅' if success else '❌'} {error or ''}"
                            )

                        elif msg_type == "gesture_ack":
                            # Phase 7: Android acknowledges gesture receipt/execution
                            command_id = msg_json.get("command_id")
                            if command_id:
                                from services.real_accessibility import real_accessibility_service
                                ack_success = msg_json.get("success", True)
                                real_accessibility_service.handle_gesture_ack(command_id, ack_success)
                            else:
                                logger.warning("⚠️ gesture_ack missing command_id")

                        elif msg_type == "screen_capture_permission_result":
                            # Android reports screen capture permission grant/deny
                            granted = msg_json.get("granted", False)
                            error = msg_json.get("error")
                            logger.info(
                                f"📸 Screen capture permission result: {'granted' if granted else 'denied'}"
                                f"{' - ' + error if error else ''}"
                            )
                            
                            from services.screenshot_service import get_screenshot_service
                            screenshot_service = get_screenshot_service()
                            screenshot_service.handle_permission_result(granted, error)

                        elif msg_type == "hitl_response":
                            # Human-in-the-loop response from user
                            from services.hitl_service import get_hitl_service
                            hitl_service = get_hitl_service()
                            question_id = msg_json.get("question_id")
                            logger.info(f"🙋 HITL response received: {question_id}")
                            handled = hitl_service.handle_response(msg_json)
                            if not handled:
                                logger.warning(f"⚠️ HITL response not handled: {question_id}")

                    # Check if it's a binary message (audio data)
                    elif "bytes" in message:
                        if is_recording:
                            audio_data_chunk = message["bytes"]
                            audio_buffer.add_chunk(audio_data_chunk)
                            # Silent - don't log every audio chunk

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    try:
                        await websocket.send_json(
                            {"type": "heartbeat", "timestamp": time.time()}
                        )
                    except Exception:
                        # Connection likely closed
                        break

            except WebSocketDisconnect:
                logger.info("WebSocket connection closed: reason=client_disconnect")
                break

            except Exception as e:
                logger.error(f"Conversation error occurred: {e}", exc_info=True)
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except Exception:
                    break

    except Exception as e:
        logger.error(f"Conversation setup error: {e}")
    finally:
        if session_id:
            conversation_manager.clear_session(session_id)

        # Clear WebSocket and disconnect device when connection closes
        try:
            from services.real_accessibility import real_accessibility_service
            from services.visual_feedback import get_visual_feedback_service

            real_accessibility_service.clear_websocket()
            real_accessibility_service.disconnect_device()
            
            # Clear visual feedback WebSocket
            visual_feedback = get_visual_feedback_service()
            visual_feedback.clear_websocket()
            
            logger.info("🔌 Device disconnected (WebSocket closed)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to disconnect device: {e}")

        logger.info("Conversation WebSocket closed")


@router.websocket("/ws/screen-mirror")
async def websocket_screen_mirror(websocket: WebSocket):
    """
    WebSocket endpoint for real-time ADB screen mirroring.

    Continuously captures screenshots via ADB and streams them as base64-encoded images.
    Target: ~10 FPS for smooth mirroring with minimal latency.

    Protocol:
    1. Client connects
    2. Server continuously sends: {"type": "frame", "data": "base64_png", "timestamp": 123.45}
    3. Client can send: {"type": "ping"} for keepalive
    4. Server responds: {"type": "pong", "timestamp": 123.45}
    """
    await websocket.accept()
    logger.info("🖼️  Screen mirror WebSocket connected")

    import subprocess

    frame_count = 0
    start_time = time.time()
    target_fps = 10
    frame_delay = 1.0 / target_fps  # 0.1 seconds between frames

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "message": "ADB screen mirroring active",
                "target_fps": target_fps,
            }
        )

        while True:
            try:
                frame_start = time.time()

                # Capture screenshot via ADB (fastest method: screencap -p to stdout)
                result = subprocess.run(
                    ["adb", "exec-out", "screencap", "-p"],
                    capture_output=True,
                    timeout=2.0,
                    check=False,
                )

                if result.returncode == 0 and result.stdout:
                    # Encode to base64
                    screenshot_b64 = base64.b64encode(result.stdout).decode("utf-8")

                    # Send frame to client
                    await websocket.send_json(
                        {
                            "type": "frame",
                            "data": screenshot_b64,
                            "timestamp": time.time(),
                            "frame_number": frame_count,
                        }
                    )

                    frame_count += 1

                    # Log FPS every 30 frames
                    if frame_count % 30 == 0:
                        elapsed = time.time() - start_time
                        actual_fps = frame_count / elapsed
                        logger.info(
                            f"📊 Screen mirror: {actual_fps:.1f} FPS ({frame_count} frames)"
                        )

                else:
                    # ADB error
                    logger.warning(
                        f"ADB screencap failed: {result.stderr.decode() if result.stderr else 'Unknown error'}"
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "ADB screencap failed - is device connected?",
                            "timestamp": time.time(),
                        }
                    )
                    await asyncio.sleep(1.0)  # Wait before retry
                    continue

                # Rate limiting: maintain target FPS
                frame_elapsed = time.time() - frame_start
                sleep_time = max(0, frame_delay - frame_elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Check for client messages (ping/pong keepalive)
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=0.001
                    )
                    if message.get("type") == "ping":
                        await websocket.send_json(
                            {"type": "pong", "timestamp": time.time()}
                        )
                except asyncio.TimeoutError:
                    pass  # No message from client, continue streaming

            except WebSocketDisconnect:
                logger.info("🖼️  Screen mirror client disconnected")
                break

            except subprocess.TimeoutExpired:
                logger.warning("⏱️  ADB screencap timeout - device may be slow")
                await websocket.send_json(
                    {
                        "type": "warning",
                        "message": "Capture timeout",
                        "timestamp": time.time(),
                    }
                )

            except Exception as e:
                logger.error(f"Screen mirror frame error: {e}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Frame capture error: {str(e)}",
                        "timestamp": time.time(),
                    }
                )
                await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Screen mirror setup error: {e}")
        try:
            await websocket.send_json(
                {"type": "error", "message": f"Mirror setup failed: {str(e)}"}
            )
        except Exception:
            pass

    finally:
        elapsed = time.time() - start_time
        if frame_count > 0:
            avg_fps = frame_count / elapsed if elapsed > 0 else 0
            logger.info(
                f"🖼️  Screen mirror closed: {frame_count} frames, {avg_fps:.1f} avg FPS"
            )
        else:
            logger.info("🖼️  Screen mirror closed (no frames)")
