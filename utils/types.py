"""
Core data types and Pydantic models for the AURA backend.

This module defines structured data models used throughout the application,
including intent objects and UI element representations.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UIMode(str, Enum):
    """
    UI modality selection for step-wise execution.

    Defines which UI data sources should be used for each step.
    Decision is made per-step, not per-task.
    """

    NO_UI = "no_ui"  # Action doesn't require UI (e.g., Wi-Fi, volume)
    UI_TREE_ONLY = "ui_tree_only"  # Default: Accessibility data sufficient
    UI_TREE_AND_VLM = "ui_tree_and_vlm"  # Hybrid: UI tree + VLM for visual reasoning
    SCREENSHOT_ONLY = "screenshot_only"  # VLM only: games, canvas, images


class UIResult(BaseModel):
    """
    Result of UI understanding with confidence score.

    Every UI operation must return confidence to enable escalation.
    """

    coordinates: Optional[List[int]] = Field(
        default=None, description="X, Y coordinates of the target element"
    )
    element: Optional["UIElement"] = Field(
        default=None, description="The matched UI element (if from Accessibility API)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0). Must be >= 0.75 to execute.",
    )
    source: str = Field(
        ..., description="Data source used: 'ui_tree', 'vlm', or 'hybrid'"
    )
    visual_reference: bool = Field(
        default=False, description="Whether this step requires visual reasoning"
    )


class IntentObject(BaseModel):
    """
    Structured representation of user intent parsed from natural language.

    This model captures the essential components of a user's command,
    including the action to perform, target recipient, and content.
    """

    action: str = Field(
        ...,
        description="The primary action the user wants to perform (e.g., 'send_message', 'open_app')",
    )
    recipient: Optional[str] = Field(
        default=None,
        description="The target recipient or destination for the action (e.g., contact name, app name)",
    )
    content: Optional[str] = Field(
        default=None,
        description="The content or message associated with the action (e.g., message text, search query)",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters and context for the action",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for the intent parsing (0.0 to 1.0)",
    )


class UIElement(BaseModel):
    """
    Structured representation of a UI element on the screen.

    This model captures the essential properties of UI elements needed
    for navigation and interaction.
    """

    element_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the UI element (if available)",
        alias="id",
    )
    element_type: str = Field(
        default="unknown",
        description="Type of the UI element (e.g., 'button', 'text_field', 'image')",
        alias="type",
    )
    text: Optional[str] = Field(
        default=None, description="Visible text content of the element"
    )
    content_description: Optional[str] = Field(
        default=None,
        description="Accessibility description of the element",
        alias="content_desc",
    )
    coordinates: List[int] = Field(
        default_factory=lambda: [0, 0],
        min_items=2,
        max_items=2,
        description="X, Y coordinates of the element center [x, y]",
    )
    bounds: List[int] = Field(
        default_factory=lambda: [0, 0, 0, 0],
        min_items=4,
        max_items=4,
        description="Bounding box coordinates [left, top, right, bottom]",
    )
    clickable: bool = Field(
        default=False, description="Whether the element is clickable"
    )
    scrollable: bool = Field(
        default=False, description="Whether the element is scrollable"
    )
    enabled: bool = Field(
        default=True, description="Whether the element is enabled for interaction"
    )
    visible: bool = Field(
        default=True, description="Whether the element is visible on screen"
    )

    class Config:
        populate_by_name = True

    @classmethod
    def from_android_element(cls, element_data: Dict[str, Any]) -> "UIElement":
        """
        Create UIElement from Android automation element data.

        Args:
            element_data: Raw element data from Android automation.

        Returns:
            UIElement instance with properly mapped fields.
        """
        # Handle different coordinate formats from Android
        coordinates = [0, 0]
        bounds = [0, 0, 0, 0]

        # Extract coordinates and bounds from different possible formats
        if "x1" in element_data and "y1" in element_data:
            # Format: {'x1': 620, 'y1': 1855, 'x2': 909, 'y2': 2184, 'width': 289, 'height': 329}
            x1, y1 = element_data.get("x1", 0), element_data.get("y1", 0)
            x2, y2 = element_data.get("x2", 0), element_data.get("y2", 0)
            bounds = [x1, y1, x2, y2]
            coordinates = [(x1 + x2) // 2, (y1 + y2) // 2]
        elif "bounds" in element_data:
            # Standard bounds format
            bounds_data = element_data["bounds"]
            if isinstance(bounds_data, list) and len(bounds_data) >= 4:
                bounds = bounds_data
                coordinates = [
                    (bounds[0] + bounds[2]) // 2,
                    (bounds[1] + bounds[3]) // 2,
                ]
            elif isinstance(bounds_data, str):
                # Handle string format bounds: "100,200,300,400" (x1,y1,x2,y2)
                # Also handle Android format: "[100,200][300,400]"
                try:
                    # Try Android format first
                    import re

                    android_match = re.match(
                        r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_data
                    )
                    if android_match:
                        bounds = list(map(int, android_match.groups()))
                        coordinates = [
                            (bounds[0] + bounds[2]) // 2,
                            (bounds[1] + bounds[3]) // 2,
                        ]
                    else:
                        # Try comma-separated format
                        bounds_values = [int(x.strip()) for x in bounds_data.split(",")]
                        if len(bounds_values) >= 4:
                            bounds = bounds_values[:4]
                            coordinates = [
                                (bounds[0] + bounds[2]) // 2,
                                (bounds[1] + bounds[3]) // 2,
                            ]
                except (ValueError, IndexError):
                    # If parsing fails, use defaults
                    pass
            elif isinstance(bounds_data, dict):
                # Handle dict format bounds: {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 100, 'width': 100, 'height': 100}
                x1 = bounds_data.get("x1", 0)
                y1 = bounds_data.get("y1", 0)
                x2 = bounds_data.get("x2", x1 + bounds_data.get("width", 0))
                y2 = bounds_data.get("y2", y1 + bounds_data.get("height", 0))
                bounds = [x1, y1, x2, y2]
                coordinates = [(x1 + x2) // 2, (y1 + y2) // 2]
        elif "x" in element_data and "y" in element_data:
            # Simple x,y coordinates
            x, y = element_data.get("x", 0), element_data.get("y", 0)
            w, h = element_data.get("width", 0), element_data.get("height", 0)
            coordinates = [x + w // 2, y + h // 2]
            bounds = [x, y, x + w, y + h]

        # Determine element type from various fields
        element_type = "unknown"
        if element_data.get("type"):
            element_type = element_data["type"]
        elif element_data.get("class"):
            element_type = element_data["class"].split(".")[-1].lower()
        elif element_data.get("resource-id"):
            # Android resource IDs often indicate type
            resource_id = element_data["resource-id"].lower()
            if "button" in resource_id:
                element_type = "button"
            elif "text" in resource_id or "edit" in resource_id:
                element_type = "text_field"
            elif "image" in resource_id or "icon" in resource_id:
                element_type = "image"
        elif element_data.get("clickable"):
            element_type = "button"
        elif element_data.get("text"):
            element_type = "text"

        return cls(
            element_id=element_data.get("id", element_data.get("resource-id", "")),
            element_type=element_type,
            text=element_data.get("text", ""),
            content_description=element_data.get(
                "content_desc", element_data.get("content-desc", "")
            ),
            coordinates=coordinates,
            bounds=bounds,
            clickable=bool(element_data.get("clickable", False)),
            scrollable=bool(element_data.get("scrollable", False)),
            enabled=bool(element_data.get("enabled", True)),
            visible=bool(element_data.get("visible", True)),
        )


class ActionResult(BaseModel):
    """
    Result of an executed action on the device.

    This model captures the outcome of UI interactions and device actions.
    """

    success: bool = Field(
        ..., description="Whether the action was executed successfully"
    )
    action_type: str = Field(
        ..., description="Type of action performed (e.g., 'tap', 'swipe', 'type')"
    )
    target_element: Optional[UIElement] = Field(
        default=None, description="The UI element that was targeted by the action"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if the action failed"
    )
    execution_time: float = Field(
        default=0.0, ge=0.0, description="Time taken to execute the action in seconds"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the action execution",
    )
    execution_steps: List[Dict[str, Any]] = Field(
        default_factory=list, description="Steps taken during execution"
    )
    strategy_used: str = Field(
        default="unknown", description="Strategy used for automation"
    )
    visual_confirmations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Visual confirmations collected during execution",
    )
    summary: str = Field(
        default="Task executed", description="Summary of the execution"
    )
    performance_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Performance metrics from execution"
    )


class EntityReference(BaseModel):
    """
    Tracked entity from conversation for context resolution.
    
    Used to resolve pronouns like 'it', 'that', 'there' to actual entities.
    """

    entity_type: str = Field(
        ...,
        description="Type of entity: 'app', 'contact', 'action', 'location', 'feature'",
    )
    value: str = Field(..., description="The actual entity value (e.g., 'Instagram', 'John')")
    timestamp: float = Field(
        default_factory=lambda: __import__("time").time(),
        description="When this entity was mentioned",
    )


class DeviceState(BaseModel):
    """
    Current device feature states for context-aware responses.
    
    Tracks on/off states to enable 'turn it off' after 'turn on wifi'.
    """

    wifi: Optional[bool] = Field(default=None, description="WiFi enabled/disabled")
    bluetooth: Optional[bool] = Field(default=None, description="Bluetooth enabled/disabled")
    torch: Optional[bool] = Field(default=None, description="Flashlight/torch enabled/disabled")
    volume_level: Optional[int] = Field(
        default=None, ge=0, le=100, description="Volume level percentage"
    )
    brightness_level: Optional[int] = Field(
        default=None, ge=0, le=100, description="Brightness level percentage"
    )


class FullConversationContext(BaseModel):
    """
    Full context for conversational AI responses.
    
    Aggregates all context needed for natural, context-aware responses:
    - Entity tracking for pronoun resolution
    - Device states for feature toggles
    - Response history for variation
    - Emotional context for empathy
    """

    current_app: Optional[str] = Field(
        default=None, description="Currently open/focused app"
    )
    last_action: Optional[str] = Field(
        default=None, description="Most recent action performed"
    )
    last_target: Optional[str] = Field(
        default=None, description="Most recent target (contact, app, element)"
    )
    entity_stack: List[EntityReference] = Field(
        default_factory=list,
        description="Stack of recent entities (max 10) for resolution",
    )
    device_states: DeviceState = Field(
        default_factory=DeviceState, description="Current device feature states"
    )
    response_history: List[str] = Field(
        default_factory=list,
        description="Last 5 responses for variation tracking",
    )
    emotional_context: Optional[str] = Field(
        default=None,
        description="Detected emotion: 'frustrated', 'grateful', 'confused', 'urgent'",
    )
    conversation_turn: int = Field(
        default=0, description="Current turn number in session"
    )
    has_introduced: bool = Field(
        default=False, description="Whether AURA has introduced itself"
    )
    session_id: Optional[str] = Field(
        default=None, description="Session identifier"
    )

    def get_last_entity(self, entity_type: Optional[str] = None) -> Optional[EntityReference]:
        """Get the most recent entity, optionally filtered by type."""
        if not self.entity_stack:
            return None
        if entity_type is None:
            return self.entity_stack[-1]
        for entity in reversed(self.entity_stack):
            if entity.entity_type == entity_type:
                return entity
        return None

