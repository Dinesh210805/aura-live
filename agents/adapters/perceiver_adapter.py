"""PerceiverAgent adapter — wraps perceive() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.perceiver_agent import PerceiverAgent


class PerceiverAdapter(Agent):
    """Adapts PerceiverAgent.perceive() to the Agent interface."""

    name = "perceiver"
    description = "Capture and analyze current screen state using perception pipeline"
    input_schema = {
        "subgoal": {"type": "object", "required": True},
        "intent": {"type": "object", "required": True},
        "force_screenshot": {"type": "boolean", "required": False},
        "step_history": {"type": "array", "required": False},
        "user_command": {"type": "string", "required": False},
        "plan_context": {"type": "string", "required": False},
    }

    def __init__(self, perceiver: "PerceiverAgent") -> None:
        self._agent = perceiver

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        try:
            await context.progress.perceiving()
            screen_state = await self._agent.perceive(
                subgoal=input_data["subgoal"],
                intent=input_data.get("intent", {}),
                force_screenshot=input_data.get("force_screenshot", False),
                step_history=input_data.get("step_history"),
                user_command=input_data.get("user_command", ""),
                plan_context=input_data.get("plan_context", ""),
            )
            element_count = len(getattr(screen_state, "elements", []) or [])
            await context.progress.screen_perceived(element_count)
            return AgentResult(
                success=True,
                output={"screen_state": screen_state},
                metadata={"element_count": element_count},
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
