"""
Coordinator Node - LangGraph node wrapping the multi-agent Coordinator.

Replaces universal_agent_node.py. Matches the same TaskState interface
so the outer graph wiring stays compatible.
"""

from typing import Any, Dict, Optional

from aura_graph.state import TaskState
from utils.logger import get_logger

logger = get_logger(__name__)

# Global reference (initialized by graph compilation)
_coordinator: Optional[Any] = None


def initialize_coordinator(coordinator: Any) -> None:
    """Initialize the coordinator. Called during graph compilation."""
    global _coordinator
    _coordinator = coordinator
    logger.info("✅ Coordinator node initialized")


async def coordinator_node(state: TaskState) -> Dict[str, Any]:
    """
    Execute a user goal via the multi-agent Coordinator.

    Input state fields:
        - intent: Parsed user intent
        - transcript / streaming_transcript: User utterance
        - session_id: Session identifier
        - perception_bundle: Optional pre-seeded perception

    Output state fields:
        - status: "executed" | "failed"
        - executed_steps: List of action records
        - feedback_message: Human-readable result
        - agent_state: Goal tracking summary
        - error_message: Error details (on failure)
    """
    global _coordinator

    if not _coordinator:
        logger.error("Coordinator not initialized")
        return {
            "status": "failed",
            "error_message": "Coordinator not available",
            "feedback_message": "Sorry, I couldn't process your request.",
        }

    # Extract inputs from TaskState
    intent = state.get("intent", {})
    transcript = state.get("transcript", "") or state.get("streaming_transcript", "")
    session_id = state.get("session_id", "")

    if not transcript and intent:
        action = intent.get("action", "")
        recipient = intent.get("recipient", "")
        content = intent.get("content", "")
        transcript = f"{action} {recipient} {content}".strip()

    if not transcript:
        return {
            "status": "failed",
            "error_message": "No goal/utterance provided",
            "feedback_message": "I didn't understand what you want me to do.",
        }

    logger.info(f"🤖 Coordinator executing: {transcript}")

    try:
        perception_bundle = state.get("perception_bundle")
        result = await _coordinator.execute(
            utterance=transcript,
            intent=intent,
            session_id=session_id,
            perception_bundle=perception_bundle,
        )

        # Map result to TaskState output
        if result["status"] == "completed":
            status = "executed"
            goal = result["goal"]
            steps = result["total_actions"]
            feedback = (
                f"Done! I completed {goal.description.lower()} in {steps} step{'s' if steps != 1 else ''}."
                if steps > 0
                else f"Done! I {goal.description.lower()}"
            )
        elif result["status"] == "aborted":
            status = "failed"
            reason = result.get("error", "Unknown reason")
            if "budget" in reason.lower() or "exhausted" in reason.lower():
                feedback = "I tried several times but couldn't complete the action. The app might be unresponsive."
            elif "loop" in reason.lower():
                feedback = "I seem to be stuck in a loop. Let me know if you'd like to try a different approach."
            else:
                feedback = f"I had to stop because: {reason}"
        else:
            status = "failed"
            completed_count = sum(1 for s in result.get("executed_steps", []) if s.get("success"))
            total = result["total_actions"]
            if completed_count > 0:
                feedback = f"I made some progress ({completed_count}/{total} steps) but couldn't finish."
            else:
                feedback = "I couldn't complete that task. Could you try rephrasing your request?"

        goal = result.get("goal")
        agent_state = {}
        if goal:
            agent_state = {
                "goal": goal.description,
                "completed": goal.completed,
                "aborted": goal.aborted,
                "abort_reason": goal.abort_reason,
                "steps_completed": result["total_actions"],
                "total_steps": len(goal.subgoals),
            }

        return {
            "status": status,
            "executed_steps": result.get("executed_steps", []),
            "feedback_message": feedback,
            "agent_state": agent_state,
            "goal_summary": goal.description if goal else None,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Coordinator execution failed: {e}", exc_info=True)

        if "no elements" in error_msg.lower() or "screen on" in error_msg.lower():
            feedback = "I can't see your phone screen. Please make sure it's on and unlocked."
        elif "permission" in error_msg.lower():
            feedback = "I need screen permission to help you. Please check your phone."
        elif "not connected" in error_msg.lower():
            feedback = "I'm not connected to your phone. Please check the AURA app."
        else:
            feedback = "I encountered an error while trying to help you."

        return {
            "status": "failed",
            "error_message": error_msg,
            "feedback_message": feedback,
        }
