"""
Task progress event types for real-time streaming to WebSocket clients.

The reference coding agent streams intermediate results as they happen.
Aura previously only sent a final TTS response. These event types enable
live feedback: "Perceiving screen...", "Executing tap...", "Verifying..."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class UpdateType(str, Enum):
    """Categories of progress events emitted during task execution."""

    # Graph lifecycle
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Node-level events (coarse)
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"

    # Agent-level events (fine-grained)
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"

    # Tool-level events
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"

    # Perception-specific
    PERCEIVING_SCREEN = "perceiving_screen"
    SCREEN_PERCEIVED = "screen_perceived"

    # Action-specific
    EXECUTING_GESTURE = "executing_gesture"
    GESTURE_COMPLETED = "gesture_completed"

    # Verification
    VERIFYING_STEP = "verifying_step"
    STEP_VERIFIED = "step_verified"
    STEP_FAILED_RETRY = "step_failed_retry"

    # Planning
    PLANNING = "planning"
    PLAN_READY = "plan_ready"

    # Human-in-the-loop
    HITL_QUESTION = "hitl_question"
    HITL_ANSWERED = "hitl_answered"

    # General status
    STATUS_UPDATE = "status_update"


@dataclass
class TaskUpdate:
    """
    A single progress event emitted during task execution.

    These are serialized to JSON and streamed over the WebSocket connection
    to the Android client, which can display live progress indicators.

    Example JSON payload::

        {
            "type": "executing_gesture",
            "session_id": "abc123",
            "task_id": "streaming_1712345678000",
            "data": {"action": "tap", "target": "Play button", "x": 540, "y": 960},
            "message": "Tapping Play button",
            "timestamp": 1712345678.123
        }
    """

    type: UpdateType
    session_id: str
    task_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for WebSocket transmission."""
        return {
            "type": self.type.value,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "data": self.data,
            "message": self.message,
            "timestamp": self.timestamp,
        }
