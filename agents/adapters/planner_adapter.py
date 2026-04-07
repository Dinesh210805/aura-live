"""PlannerAgent adapter — wraps create_plan() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.planner_agent import PlannerAgent


class PlannerAdapter(Agent):
    """Adapts PlannerAgent.create_plan() to the Agent interface."""

    name = "planner"
    description = "Decompose a user utterance into an ordered Goal with Subgoals"
    input_schema = {
        "utterance": {"type": "string", "required": True},
        "intent": {"type": "object", "required": True},
        "perception": {"type": "object", "required": False},
        "step_history": {"type": "array", "required": False},
        "web_hints": {"type": "string", "required": False},
    }

    def __init__(self, planner: "PlannerAgent") -> None:
        self._agent = planner

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        try:
            await context.progress.planning(goal=input_data.get("utterance"))
            goal = self._agent.create_plan(
                utterance=input_data["utterance"],
                intent=input_data["intent"],
                perception=input_data.get("perception"),
                step_history=input_data.get("step_history"),
                web_hints=input_data.get("web_hints", ""),
            )
            from aura.streaming.task_update import UpdateType
            await context.progress.emit(
                UpdateType.PLAN_READY,
                data={"subgoal_count": len(getattr(goal, "subgoals", []) or [])},
            )
            return AgentResult(success=True, output={"goal": goal})
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
