"""
Base Agent interface for the Aura orchestration layer.

All agents must implement this interface to be composable, registry-loadable,
and spawnable as sub-agents by the AuraQueryEngine.

Design: mirrors the reference coding agent's Tool interface, where every
agent is just a typed callable with a name, description, and input schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext


@dataclass
class AgentResult:
    """
    Standardized result envelope returned by every Agent.

    Mirrors the reference system's ToolResult — structured output prevents
    callers from having to guess the shape of agent responses.
    """

    success: bool
    """Whether the agent completed without a fatal error."""

    output: Dict[str, Any] = field(default_factory=dict)
    """Agent-specific output payload."""

    error: Optional[str] = None
    """Human-readable error message if success=False."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Timing, token usage, retry counts, and other observability data."""

    messages: List[Dict[str, Any]] = field(default_factory=list)
    """Optional new messages to inject into the session context (for sub-agents)."""


class Agent(ABC):
    """
    Base class for all Aura agents.

    Agents are first-class actors: they have a name, a description (used by
    the registry for discovery), an input schema (JSON Schema dict), and a
    single async entrypoint — invoke().

    Existing agent classes (CommanderAgent, ActorAgent, etc.) are NOT rewritten.
    Instead, thin Adapter subclasses wrap them and delegate to their existing
    methods. This preserves all existing logic while making agents composable.

    Usage::

        class CommanderAdapter(Agent):
            name = "commander"
            description = "Parse voice command into structured intent"
            input_schema = {"type": "object", "properties": {"transcript": {"type": "string"}}}

            def __init__(self, commander_agent: CommanderAgent):
                self._inner = commander_agent

            async def invoke(self, input_data: Dict, context: AuraContext) -> AgentResult:
                result = await self._inner.parse(input_data["transcript"])
                return AgentResult(success=True, output={"intent": result})
    """

    # Subclasses MUST define these at class level
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    async def invoke(
        self,
        input_data: Dict[str, Any],
        context: "AuraContext",
    ) -> AgentResult:
        """
        Execute the agent with the given input and session context.

        Args:
            input_data: Dict matching the agent's input_schema.
            context: Session-scoped AuraContext providing shared state,
                     file cache, progress callbacks, and sub-agent spawning.

        Returns:
            AgentResult with success flag, output payload, and metadata.
        """
        ...

    def __repr__(self) -> str:
        return f"<Agent name={self.name!r}>"
