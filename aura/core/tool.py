"""
Base Tool interface for the Aura orchestration layer.

Tools are atomic, reusable capabilities (gestures, perception queries, web
searches) that agents invoke. Unlike agents, tools are typically stateless
single-operation callables with explicit permission gates.

Design mirrors the reference coding agent's Tool interface:
  - call()            → execute the tool
  - check_permissions() → fail-closed gate before execution
  - is_concurrency_safe → hint for the parallel executor
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext


@dataclass
class ToolResult:
    """
    Standardized result envelope returned by every Tool.
    """

    success: bool
    """Whether the tool completed without error."""

    data: Any = None
    """Tool-specific output (coordinates, text, status, etc.)."""

    error: Optional[str] = None
    """Human-readable error if success=False."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Timing, retry count, provider used, etc."""


class PermissionError(Exception):
    """Raised when a tool's permission check fails."""


class Tool(ABC):
    """
    Base class for all Aura tools.

    Tools differ from agents in scope: a tool does ONE thing (tap, swipe,
    read screen, search web). An agent may call many tools and apply reasoning.

    Existing gesture_executor calls become GestureTool subclasses.
    Perception calls become a PerceptionTool subclass.

    Usage::

        class TapTool(Tool):
            name = "tap"
            description = "Tap a screen coordinate"
            input_schema = {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            }
            is_concurrency_safe = False

            async def call(self, args: Dict, context: AuraContext) -> ToolResult:
                result = await context.gesture_executor.tap(args["x"], args["y"])
                return ToolResult(success=result.success, data=result)
    """

    # Subclasses MUST define these
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    # Hint: can this tool run concurrently with other tools?
    # Gesture tools are False (device is serial). Read tools are True.
    is_concurrency_safe: bool = False

    @abstractmethod
    async def call(
        self,
        args: Dict[str, Any],
        context: "AuraContext",
    ) -> ToolResult:
        """
        Execute the tool.

        Args:
            args: Dict matching input_schema.
            context: Session-scoped AuraContext (shared state, progress callbacks).

        Returns:
            ToolResult with success flag and data payload.
        """
        ...

    async def check_permissions(
        self,
        args: Dict[str, Any],
        context: "AuraContext",
    ) -> None:
        """
        Validate that this tool call is permitted.

        Override to add custom permission gates (e.g. OPA policy checks).
        Raise PermissionError to block execution — fail-closed by default.

        Default implementation: allow all.
        """

    def __repr__(self) -> str:
        return f"<Tool name={self.name!r} concurrency_safe={self.is_concurrency_safe}>"
