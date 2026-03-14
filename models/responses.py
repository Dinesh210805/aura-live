"""Response data models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="Application version")
    timestamp: str = Field(..., description="Current timestamp")
    services: Dict[str, str] = Field(..., description="Service status details")


class GraphInfoResponse(BaseModel):
    """Response model for graph information."""

    nodes: List[str] = Field(..., description="List of graph nodes")
    entry_point: str = Field(..., description="Graph entry point")
    edges: Dict[str, List[str]] = Field(..., description="Graph edge configuration")
    supports_checkpointing: bool = Field(
        ..., description="Whether checkpointing is supported"
    )
    supports_streaming: bool = Field(..., description="Whether streaming is supported")
    version: str = Field(..., description="Graph version")
