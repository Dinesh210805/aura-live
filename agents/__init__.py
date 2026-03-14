"""AURA Agent System — Multi-Agent Architecture

Agents:
- Commander: Intent parsing (Groq - llama-3.1-8b-instant, 560 tps)
- Responder: Feedback generation (Groq - llama-3.3-70b-versatile)
- PerceiverAgent: Screen understanding + visual perception (description, location, comparison)
- Validator: Intent pre-validation (Groq - fast)

Phase 3 Specialist Agents:
- PlannerAgent: Goal decomposition + replanning
- PerceiverAgent: Screen understanding + OmniParser auto-escalation + VLM calls
- ActorAgent: Single gesture execution
- VerifierAgent: Post-action verification + loop detection
- Coordinator: LangGraph subgraph orchestrating the 4 specialists

Note: ScreenVLM is a backward-compat alias for PerceiverAgent (merged).
"""

from agents.commander import CommanderAgent
from agents.responder import ResponderAgent
from agents.visual_locator import ScreenVLM
from agents.validator import ValidationResult, ValidatorAgent
from agents.planner_agent import PlannerAgent
from agents.perceiver_agent import PerceiverAgent
from agents.actor_agent import ActorAgent
from agents.verifier_agent import VerifierAgent
from agents.coordinator import Coordinator

__all__ = [
    "CommanderAgent",
    "ResponderAgent",
    "ScreenVLM",
    "ValidatorAgent",
    "ValidationResult",
    "PlannerAgent",
    "PerceiverAgent",
    "ActorAgent",
    "VerifierAgent",
    "Coordinator",
]
