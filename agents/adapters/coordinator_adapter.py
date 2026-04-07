"""Coordinator adapter — wraps Coordinator.execute() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.coordinator import Coordinator


class CoordinatorAdapter(Agent):
    """Adapts Coordinator.execute() to the Agent interface."""

    name = "coordinator"
    description = "Orchestrate perceive→decide→act→verify loop to accomplish a goal"
    input_schema = {
        "utterance": {"type": "string", "required": True},
        "intent": {"type": "object", "required": True},
        "session_id": {"type": "string", "required": False},
        "perception_bundle": {"type": "object", "required": False},
    }

    def __init__(self, coordinator: "Coordinator") -> None:
        self._agent = coordinator

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        try:
            result = await self._agent.execute(
                utterance=input_data["utterance"],
                intent=input_data["intent"],
                session_id=input_data.get("session_id", context.session_id),
                perception_bundle=input_data.get("perception_bundle"),
            )
            success = result.get("status") not in ("failed", "error")
            return AgentResult(
                success=success,
                output=result,
                error=result.get("error_message") if not success else None,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
