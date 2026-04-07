"""ResponderAgent adapter — wraps generate_feedback() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.responder import ResponderAgent


class ResponderAdapter(Agent):
    """Adapts ResponderAgent.generate_feedback() to the Agent interface."""

    name = "responder"
    description = "Generate natural-language response text for TTS delivery"
    input_schema = {
        "intent": {"type": "object", "required": False},
        "status": {"type": "string", "required": False},
        "error_message": {"type": "string", "required": False},
        "transcript": {"type": "string", "required": False},
        "goal_summary": {"type": "string", "required": False},
        "completed_steps": {"type": "array", "required": False},
    }

    def __init__(self, responder: "ResponderAgent") -> None:
        self._agent = responder

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        try:
            feedback = self._agent.generate_feedback(
                intent=input_data.get("intent"),
                status=input_data.get("status", "completed"),
                error_message=input_data.get("error_message"),
                transcript=input_data.get("transcript"),
                goal_summary=input_data.get("goal_summary"),
                completed_steps=input_data.get("completed_steps"),
            )
            return AgentResult(success=True, output={"feedback": feedback})
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
