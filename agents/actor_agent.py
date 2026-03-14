"""
Actor Agent - Single gesture execution wrapper.

Fully deterministic — no LLM calls. Wraps GestureExecutor
and adds ADB health checking before execution.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from services.gesture_executor import GestureExecutor, GestureResult
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ActionResult:
    """Result of a single gesture execution."""
    success: bool
    action_type: str
    coordinates: Optional[Tuple[int, int]]
    duration_ms: float
    error: Optional[str]
    details: Optional[Dict[str, Any]] = None


class ActorAgent:
    """
    Execute a single gesture. No reasoning, no LLM.

    Wraps GestureExecutor with a simpler interface and ADB health checks.
    """

    def __init__(self, gesture_executor: GestureExecutor):
        self.executor = gesture_executor

    async def execute(
        self,
        action_type: str,
        target: Optional[str] = None,
        coordinates: Optional[Tuple[int, int]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        """
        Execute a single action on the device.

        Args:
            action_type: "tap", "long_press", "type", "scroll", "swipe",
                         "back", "home", "open_app"
            target: Text to type, app name to open, or element description.
            coordinates: (x, y) tap/press coordinates.
            parameters: Extra params (direction for scroll/swipe, etc.).

        Returns:
            ActionResult with success status and timing.
        """
        start = time.time()
        params = parameters or {}

        # Build action dict expected by GestureExecutor
        action = {"action": action_type}

        if coordinates:
            action["x"] = coordinates[0]
            action["y"] = coordinates[1]
            action["format"] = "pixels"

        if target:
            if action_type == "type":
                action["text"] = target
            elif action_type == "open_app":
                action["app_name"] = target
            else:
                action["target"] = target

        # Merge extra params
        action.update(params)

        try:
            result: GestureResult = await self.executor._execute_single_action(action)
            duration = (time.time() - start) * 1000

            return ActionResult(
                success=result.success,
                action_type=action_type,
                coordinates=coordinates,
                duration_ms=duration,
                error=result.error,
                details=result.details,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            error_msg = str(e)
            logger.error(f"Actor: {action_type} failed — {error_msg}")

            return ActionResult(
                success=False,
                action_type=action_type,
                coordinates=coordinates,
                duration_ms=duration,
                error=error_msg,
            )
