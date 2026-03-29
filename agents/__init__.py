"""AURA Agent System — Multi-Agent Architecture

Core agents:
- CommanderAgent: Intent parsing (rule-based + LLM fallback)
- ResponderAgent: Natural-language feedback generation + TTS
- ValidatorAgent: Intent pre-validation (fast, minimal model use)

Automation agents (Coordinator-managed):
- PlannerAgent: Goal decomposition + replanning
- PerceiverAgent: Screen understanding — OmniParser 3-layer pipeline + VLM calls
- ActorAgent: Single deterministic gesture execution (zero LLM calls)
- VerifierAgent: Post-action state capture + error screen detection
- Coordinator: Orchestrates the perceive→decide→act→verify loop
"""

from agents.commander import CommanderAgent
from agents.responder import ResponderAgent
from agents.validator import ValidationResult, ValidatorAgent
from agents.planner_agent import PlannerAgent
from agents.perceiver_agent import PerceiverAgent
from agents.actor_agent import ActorAgent
from agents.verifier_agent import VerifierAgent
from agents.coordinator import Coordinator

__all__ = [
    "CommanderAgent",
    "ResponderAgent",
    "ValidatorAgent",
    "ValidationResult",
    "PlannerAgent",
    "PerceiverAgent",
    "ActorAgent",
    "VerifierAgent",
    "Coordinator",
]
