"""Gesture action models for standardized gesture pipeline."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class TapAction(BaseModel):
    """Standardized tap/click action format."""

    action: Literal["tap", "click"]
    x: int = Field(..., ge=0, description="X coordinate in absolute pixels")
    y: int = Field(..., ge=0, description="Y coordinate in absolute pixels")
    format: Literal["pixels"] = "pixels"
    step: int = Field(default=1, ge=1, description="Execution order in multi-step plan")
    description: str = Field(default="", description="Human-readable action description")
    timeout: float = Field(default=5.0, gt=0, description="Max wait time in seconds")
    max_retries: int = Field(default=2, ge=0, description="Retry attempts on failure")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="UI element match confidence score"
    )
    snapshot_id: str = Field(
        default="", description="UI snapshot ID for provenance tracking"
    )

    model_config = {"extra": "forbid"}


class SwipeAction(BaseModel):
    """Standardized swipe action format."""

    action: Literal["swipe", "scroll"]
    x1: int = Field(..., ge=0, description="Start X coordinate in absolute pixels")
    y1: int = Field(..., ge=0, description="Start Y coordinate in absolute pixels")
    x2: int = Field(..., ge=0, description="End X coordinate in absolute pixels")
    y2: int = Field(..., ge=0, description="End Y coordinate in absolute pixels")
    duration: int = Field(
        default=300, ge=0, description="Swipe duration in milliseconds"
    )
    format: Literal["pixels"] = "pixels"
    step: int = Field(default=1, ge=1, description="Execution order in multi-step plan")
    description: str = Field(default="", description="Human-readable action description")
    timeout: float = Field(default=3.0, gt=0, description="Max wait time in seconds")

    model_config = {"extra": "forbid"}


class TypeAction(BaseModel):
    """Standardized text input action format."""

    action: Literal["type", "type_text", "input"]
    text: str = Field(..., min_length=1, description="Text to input")
    step: int = Field(default=1, ge=1, description="Execution order in multi-step plan")
    description: str = Field(default="", description="Human-readable action description")
    timeout: float = Field(default=5.0, gt=0, description="Max wait time in seconds")
    max_retries: int = Field(default=2, ge=0, description="Retry attempts on failure")

    model_config = {"extra": "forbid"}


class LongPressAction(BaseModel):
    """Standardized long press action format."""

    action: Literal["long_press", "long_tap"]
    x: int = Field(..., ge=0, description="X coordinate in absolute pixels")
    y: int = Field(..., ge=0, description="Y coordinate in absolute pixels")
    duration: int = Field(
        default=1000, ge=0, description="Press duration in milliseconds"
    )
    format: Literal["pixels"] = "pixels"
    step: int = Field(default=1, ge=1, description="Execution order in multi-step plan")
    description: str = Field(default="", description="Human-readable action description")
    timeout: float = Field(default=5.0, gt=0, description="Max wait time in seconds")
    max_retries: int = Field(default=2, ge=0, description="Retry attempts on failure")

    model_config = {"extra": "forbid"}
