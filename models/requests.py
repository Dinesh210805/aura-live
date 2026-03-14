"""Request data models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("audio_data", "text_input")
    @classmethod
    def validate_input(cls, v, info):
        """Ensure either audio_data or text_input is provided."""
        values = info.data if hasattr(info, "data") else {}
        if values.get("input_type") == "audio" and not values.get("audio_data"):
            raise ValueError("audio_data is required when input_type is 'audio'")
        if values.get("input_type") == "text" and not values.get("text_input"):
            raise ValueError("text_input is required when input_type is 'text'")
        return v


class DeviceRegistration(BaseModel):
    """Device registration request model."""

    device_name: str = Field(..., description="Device name/identifier")
    android_version: str = Field(..., description="Android OS version")
    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    density_dpi: int = Field(default=420, description="Screen density DPI")
    app_version: str = Field(default="1.0.0", description="AURA app version")
    capabilities: List[str] = Field(
        default_factory=list, description="Device capabilities"
    )


class DeviceUIData(BaseModel):
    """UI data upload from device."""

    screenshot: str = Field(..., description="Base64 encoded screenshot")
    ui_elements: List[Dict[str, Any]] = Field(..., description="UI element hierarchy")
    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    timestamp: int = Field(..., description="Capture timestamp")
    package_name: str = Field(default="", description="Current app package name")
    activity_name: str = Field(default="", description="Current activity name")
    capture_reason: str = Field(default="manual", description="Reason for capture")


class GestureRequest(BaseModel):
    """Gesture execution request."""

    action: str = Field(..., description="Gesture action type")
    x: Optional[int] = Field(None, description="X coordinate")
    y: Optional[int] = Field(None, description="Y coordinate")
    x2: Optional[int] = Field(None, description="Second X coordinate for swipe")
    y2: Optional[int] = Field(None, description="Second Y coordinate for swipe")
    duration: int = Field(default=300, description="Gesture duration in ms")


class AppActionRequest(BaseModel):
    """Quick app action request for deep linking."""

    action: str = Field(
        ..., description="Action type (open_app, send_message, make_call, etc.)"
    )
    target: str = Field(..., description="Target app or contact")
    content: Optional[str] = Field(
        None, description="Additional content (message text, etc.)"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="Additional parameters"
    )
