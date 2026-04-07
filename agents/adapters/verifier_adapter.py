"""VerifierAgent adapter — wraps capture_post_state() in the Agent ABC."""
from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from aura.core.agent import Agent, AgentResult

if TYPE_CHECKING:
    from aura_graph.aura_context import AuraContext
    from agents.verifier_agent import VerifierAgent


class VerifierAdapter(Agent):
    """Adapts VerifierAgent.capture_post_state() to the Agent interface."""

    name = "verifier"
    description = "Capture post-action screen state and detect error screens"
    input_schema = {
        "intent": {"type": "object", "required": True},
        "action_type": {"type": "string", "required": False},
    }

    def __init__(self, verifier: "VerifierAgent") -> None:
        self._agent = verifier

    async def invoke(self, input_data: Dict[str, Any], context: "AuraContext") -> AgentResult:
        intent = input_data["intent"]
        action_type = input_data.get("action_type")
        try:
            from aura.streaming.task_update import UpdateType
            await context.progress.emit(
                UpdateType.VERIFYING_STEP,
                data={"action_type": action_type},
                message="Verifying action result...",
            )
            bundle, post_signature, elements = await self._agent.capture_post_state(
                intent=intent,
                action_type=action_type,
            )
            is_error = self._agent.is_error_screen(elements)
            await context.progress.emit(
                UpdateType.STEP_VERIFIED if not is_error else UpdateType.STEP_FAILED_RETRY,
                data={"is_error": is_error, "element_count": len(elements)},
            )
            return AgentResult(
                success=not is_error,
                output={
                    "bundle": bundle,
                    "post_signature": post_signature,
                    "elements": elements,
                    "is_error_screen": is_error,
                },
                error="Error screen detected" if is_error else None,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))
