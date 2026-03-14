"""
Task execution router for AURA backend.

Handles voice command processing and task execution endpoints.
"""

import base64
import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from aura_graph.graph import execute_aura_task, execute_aura_task_from_text
from config.settings import get_settings
from utils.exceptions import AuraBaseException, ConfigurationError
from utils.logger import get_logger
from utils.token_tracker import token_tracker

logger = get_logger(__name__)
settings = get_settings()

# Router with /tasks prefix for task execution endpoints
router = APIRouter(prefix="/tasks", tags=["Task Execution"])


class TaskRequest(BaseModel):
    """Request model for task execution."""

    audio_data: Optional[str] = Field(
        default=None, description="Base64 encoded audio data"
    )
    text_input: Optional[str] = Field(default=None, description="Direct text input")
    input_type: str = Field(
        default="audio", description="Type of input: 'audio' or 'text'"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional execution configuration"
    )
    thread_id: Optional[str] = Field(
        default=None, description="Optional thread ID for state persistence"
    )

    @field_validator("input_type")
    @classmethod
    def validate_input_type(cls, v):
        """Validate input type."""
        if v not in ["audio", "text"]:
            raise ValueError("input_type must be 'audio' or 'text'")
        return v

    @field_validator("audio_data")
    @classmethod
    def validate_audio_data(cls, v, info):
        """Validate audio data when input_type is audio."""
        if info.data.get("input_type") == "audio" and not v:
            raise ValueError("audio_data is required when input_type is 'audio'")
        return v

    @field_validator("text_input")
    @classmethod
    def validate_text_input(cls, v, info):
        """Validate text input when input_type is text."""
        if info.data.get("input_type") == "text" and not v:
            raise ValueError("text_input is required when input_type is 'text'")
        if v and len(v) > 1000:
            raise ValueError("text_input must not exceed 1000 characters")
        return v


class TaskResponse(BaseModel):
    """Response model for task execution."""

    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task execution status")
    transcript: str = Field(default="", description="Transcribed speech")
    intent: Optional[Dict[str, Any]] = Field(
        default=None, description="Parsed intent object"
    )
    spoken_response: str = Field(default="", description="Generated spoken response")
    spoken_audio: Optional[str] = Field(
        default=None, description="Base64 encoded audio data for spoken response"
    )
    spoken_audio_format: Optional[str] = Field(
        default=None, description="MIME type for spoken audio data"
    )
    execution_time: float = Field(
        default=0.0, description="Total execution time in seconds"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if task failed"
    )
    debug_info: Dict[str, Any] = Field(
        default_factory=dict, description="Debug information"
    )


@router.post("/execute", response_model=TaskResponse)
async def execute_task(request: TaskRequest, http_request: Request) -> TaskResponse:
    """
    Execute a voice command task.

    Args:
        request: Task execution request
        http_request: FastAPI request object

    Returns:
        Task execution results
    """
    task_id = f"task_{int(time.time() * 1000)}"
    request_id = getattr(http_request.state, "request_id", "unknown")

    try:
        logger.info(f"Task execution requested: {task_id} [Request: {request_id}]")

        # Get graph app from main module
        import main

        app_instance = main.graph_app

        if not app_instance:
            raise ConfigurationError("Graph application not initialized")

        # Handle different input types
        if request.input_type == "text":
            result = await execute_aura_task_from_text(
                app=app_instance,
                text_input=request.text_input,
                config=request.config,
                thread_id=request.thread_id,
            )
        else:
            # Decode and validate audio data
            try:
                audio_bytes = base64.b64decode(request.audio_data)

                # Validate audio size
                max_size = 10 * 1024 * 1024  # 10MB
                if len(audio_bytes) > max_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Audio data exceeds maximum size of {max_size} bytes",
                    )

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid audio data: {e}",
                )

            result = await execute_aura_task(
                app=app_instance,
                raw_audio=audio_bytes,
                config=request.config,
                thread_id=request.thread_id,
            )

        # Validate audio response before sending to client
        spoken_audio = result.get("spoken_audio")
        if spoken_audio:
            # Validate base64 audio payload
            try:
                decoded_audio = base64.b64decode(spoken_audio)
                if len(decoded_audio) < 44:  # WAV header minimum is 44 bytes
                    logger.warning(
                        f"⚠️ Audio payload corrupted or too small ({len(decoded_audio)} bytes), sending text-only"
                    )
                    spoken_audio = None
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to validate audio response: {e}, sending text-only"
                )
                spoken_audio = None

        # Create response
        response = TaskResponse(
            task_id=task_id,
            status=result.get("status", "unknown"),
            transcript=result.get("transcript", ""),
            intent=result.get("intent"),
            spoken_response=result.get("spoken_response", ""),
            spoken_audio=spoken_audio,
            spoken_audio_format=(
                result.get("spoken_audio_format") if spoken_audio else None
            ),
            execution_time=result.get("execution_time", 0.0),
            error_message=result.get("error_message"),
            debug_info=result.get("debug_info", {}),
        )

        logger.info(f"Task {task_id} completed: {response.status}")
        return response

    except HTTPException:
        raise
    except AuraBaseException as e:
        logger.error(f"AURA error in task {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message=str(e),
            spoken_response="I encountered an error while processing your request.",
        )
    except Exception as e:
        logger.error(f"Unexpected error in task {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message="Internal server error",
            spoken_response="I'm sorry, I encountered an unexpected error.",
        )


@router.post("/execute-file", response_model=TaskResponse)
async def execute_task_from_file(
    file: UploadFile = File(...),
    config: Optional[str] = None,
    thread_id: Optional[str] = None,
    http_request: Request = None,
) -> TaskResponse:
    """
    Execute a voice command task from uploaded audio file.

    Args:
        file: Uploaded audio file
        config: Optional JSON configuration string
        thread_id: Optional thread ID for state persistence
        http_request: FastAPI request object

    Returns:
        Task execution results
    """
    task_id = f"file_task_{int(time.time() * 1000)}"

    try:
        logger.info(f"File task execution requested: {task_id}")

        # Validate file type
        if not file.content_type or not file.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an audio file",
            )

        # Read and validate file content
        audio_bytes = await file.read()

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio file"
            )

        max_size = 10 * 1024 * 1024  # 10MB
        if len(audio_bytes) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum of {max_size} bytes",
            )

        # Parse config if provided
        task_config = None
        if config:
            try:
                task_config = json.loads(config)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON configuration",
                )

        # Create task request
        request = TaskRequest(
            audio_data=base64.b64encode(audio_bytes).decode(),
            input_type="audio",
            config=task_config,
            thread_id=thread_id,
        )

        # Execute task
        return await execute_task(request, http_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File task error {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message="Failed to process audio file",
            spoken_response="I couldn't process the audio file you provided.",
        )


@router.get("/token-stats")
async def get_token_stats():
    """
    Get token usage statistics.

    Returns aggregated token usage data including total calls,
    tokens consumed, and breakdowns by agent, model, and provider.
    """
    try:
        stats = token_tracker.get_stats()

        return {
            "total_calls": stats.total_calls,
            "total_tokens": stats.total_tokens,
            "prompt_tokens": stats.total_prompt_tokens,
            "completion_tokens": stats.total_completion_tokens,
            "by_agent": stats.by_agent,
            "by_provider": stats.by_provider,
            "by_model": stats.by_model,
            "history_count": len(token_tracker.usage_history),
        }
    except Exception as e:
        logger.error(f"Error getting token stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get token statistics: {str(e)}",
        )


@router.post("/token-stats/reset")
async def reset_token_stats():
    """
    Reset token usage tracking.

    Clears all historical token usage data.
    Use this to start fresh tracking for a new test session.
    """
    try:
        token_tracker.reset()
        return {"status": "success", "message": "Token tracking history cleared"}
    except Exception as e:
        logger.error(f"Error resetting token stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset token statistics: {str(e)}",
        )
