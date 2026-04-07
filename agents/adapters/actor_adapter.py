"""ActorAgent adapter — wraps execute() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.actor_agent import ActorAgent


class ActorAdapter(Agent):
    """Adapts ActorAgent.execute() to the Agent interface."""

    name = "actor"
    description = "Execute a single gesture on the device (zero LLM calls)"
    input_schema = {
        "action_type": {"type": "string", "required": True},
        "target": {"type": "string", "required": False},
        "coordinates": {"type": "array", "required": False},
        "parameters": {"type": "object", "required": False},
    }

    def __init__(self, actor: "ActorAgent") -> None:
        self._agent = actor

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        action_type = input_data["action_type"]
        target = input_data.get("target")
        coords_raw = input_data.get("coordinates")
        coordinates: Optional[Tuple[int, int]] = tuple(coords_raw) if coords_raw else None
        parameters = input_data.get("parameters")

        try:
            await context.progress.executing_gesture(action=action_type, target=target)
            result = await self._agent.execute(
                action_type=action_type,
                target=target,
                coordinates=coordinates,
                parameters=parameters,
            )
            from aura.streaming.task_update import UpdateType
            await context.progress.emit(
                UpdateType.GESTURE_COMPLETED,
                data={"action": action_type, "success": result.success},
            )
            return AgentResult(
                success=result.success,
                output={"action_result": result},
                error=result.error_message if not result.success else None,
                metadata={"action_type": action_type, "target": target},
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
