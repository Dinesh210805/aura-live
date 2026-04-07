"""CommanderAgent adapter — wraps parse_intent() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.commander import CommanderAgent


class CommanderAdapter(Agent):
    """Adapts CommanderAgent.parse_intent() to the Agent interface."""

    name = "commander"
    description = "Parse user transcript into a structured IntentObject"
    input_schema = {
        "transcript": {"type": "string", "required": True},
        "context": {"type": "object", "required": False},
    }

    def __init__(self, commander: "CommanderAgent") -> None:
        self._agent = commander

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        transcript = input_data.get("transcript", "")
        ctx = input_data.get("context", {})
        try:
            intent = self._agent.parse_intent(transcript, context=ctx)
            return AgentResult(
                success=True,
                output={"intent": intent.__dict__ if hasattr(intent, "__dict__") else dict(intent)},
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
