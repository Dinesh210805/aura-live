"""
Perception data models - PerceptionBundle and payloads.

Implements the core data structures for the UI Perception Pipeline.
"""

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PerceptionModality(str, Enum):
    """UI perception modality selection."""

    UI_TREE = "ui_tree"  # Accessibility API only
    VISION = "vision"  # Screenshot + VLM only
    HYBRID = "hybrid"  # UI Tree + Screenshot + VLM


class UITreePayload(BaseModel):
    """
    UI Tree payload from Android AccessibilityNodeInfo.

    Contains minimal deterministic fields only as per blueprint.
    """

    elements: List[Dict[str, Any]] = Field(
        ..., description="List of UI elements with minimal fields"
    )
    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    orientation: str = Field(default="portrait", description="Screen orientation")
    timestamp: int = Field(..., description="Timestamp when tree was captured (ms)")
    root_node_id: Optional[str] = Field(
        default=None, description="Root node identifier if available"
    )

    @property
    def source_package(self) -> str:
        """
        Get package name from root element safely.
        
        Provides safe access to prevent AttributeError when code expects
        this attribute. Extracts packageName from elements[0] if available.
        
        Returns:
            Package name string or empty string if not available.
        """
        if self.elements:
            return self.elements[0].get("packageName", "")
        return ""


class ScreenshotPayload(BaseModel):
    """
    Screenshot payload from Android MediaProjection.

    Contains base64-encoded screenshot with metadata.
    """

    screenshot_base64: str = Field(..., description="Base64-encoded PNG screenshot")
    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    orientation: str = Field(default="portrait", description="Screen orientation")
    timestamp: int = Field(..., description="Timestamp when screenshot was captured (ms)")


class ScreenMeta(BaseModel):
    """Screen metadata for perception bundle."""

    width: int = Field(..., description="Screen width in pixels")
    height: int = Field(..., description="Screen height in pixels")
    orientation: str = Field(default="portrait", description="Screen orientation")
    density_dpi: Optional[int] = Field(
        default=None, description="Screen density DPI"
    )


class PerceptionBundle(BaseModel):
    """
    Immutable perception bundle - single snapshot per execution step.

    This is the core data structure that flows through the perception pipeline.
    It is immutable and scoped to a single graph step.
    """

    snapshot_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this perception snapshot",
    )
    modality: PerceptionModality = Field(
        ..., description="Selected perception modality"
    )
    ui_tree: Optional[UITreePayload] = Field(
        default=None, description="UI tree data (if modality includes UI_TREE)"
    )
    screenshot: Optional[ScreenshotPayload] = Field(
        default=None, description="Screenshot data (if modality includes VISION)"
    )
    screen_meta: ScreenMeta = Field(..., description="Screen metadata")
    visual_description: Optional[str] = Field(
        default=None, description="VLM-generated semantic description of screenshot"
    )
    captured_at: float = Field(
        default_factory=time.time, description="Timestamp when bundle was created"
    )
    request_id: Optional[str] = Field(
        default=None, description="Request ID for tracking"
    )
    reason: Optional[str] = Field(
        default=None, description="Reason for this perception request"
    )

    class Config:
        """Pydantic config."""

        frozen = True  # Immutable bundle
        use_enum_values = True

    def is_valid(self, max_age_seconds: float = 2.0) -> bool:
        """
        Check if bundle is still valid (not stale).

        Args:
            max_age_seconds: Maximum age in seconds before bundle is considered stale

        Returns:
            True if bundle is valid, False if stale
        """
        age = time.time() - self.captured_at
        return age <= max_age_seconds

    def get_age_seconds(self) -> float:
        """Get age of bundle in seconds."""
        return time.time() - self.captured_at
