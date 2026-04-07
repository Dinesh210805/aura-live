"""
Adapter wrappers that make Aura's existing agents implement the Agent ABC.

Each adapter:
  - Inherits from aura.core.agent.Agent
  - Holds a reference to the underlying agent instance
  - Delegates invoke() to the existing method (parse_intent, execute, perceive, etc.)
  - Does NOT rewrite or duplicate any existing agent logic

This allows all 9 existing agents to be registered in AgentRegistry
and invoked via AuraContext.spawn_agent() without any code changes to
the original agent files.
"""
from .commander_adapter import CommanderAdapter
from .perceiver_adapter import PerceiverAdapter
from .coordinator_adapter import CoordinatorAdapter
from .planner_adapter import PlannerAdapter
from .actor_adapter import ActorAdapter
from .responder_adapter import ResponderAdapter
from .verifier_adapter import VerifierAdapter

__all__ = [
    "CommanderAdapter",
    "PerceiverAdapter",
    "CoordinatorAdapter",
    "PlannerAdapter",
    "ActorAdapter",
    "ResponderAdapter",
    "VerifierAdapter",
]
