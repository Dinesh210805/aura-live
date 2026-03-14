"""
Planner Agent - Goal decomposition and replanning.

Wraps GoalDecomposer with coverage validation and atomic constraint
enforcement for recovery replans.
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from aura_graph.agent_state import Goal, StepMemory, Subgoal
from config.action_types import VALID_ACTIONS
from services.goal_decomposer import GoalDecomposer
from utils.logger import get_logger

if TYPE_CHECKING:
    from perception.models import PerceptionBundle

logger = get_logger(__name__)

# Subgoals containing these words must never be compound multi-action strings
ATOMIC_MAX_WORDS = 12

# Commit-like actions that must appear when the user's utterance implies them
COMMIT_KEYWORDS = {
    "add to cart", "buy", "purchase", "send", "submit", "confirm",
    "place order", "checkout", "pay", "subscribe", "follow", "like",
    "post", "share", "delete", "remove",
}


class PlannerAgent:
    """
    Goal decomposition + replanning with coverage validation.

    Wraps GoalDecomposer. Adds:
    - Atomic constraint enforcement (no compound recovery subgoals).
    - Non-skippable commit action detection.
    """

    def __init__(self, goal_decomposer: GoalDecomposer):
        self.decomposer = goal_decomposer

    def create_plan(
        self,
        utterance: str,
        intent: Dict[str, Any],
        perception: Optional["PerceptionBundle"] = None,
        step_history: Optional[List[StepMemory]] = None,
    ) -> Goal:
        """
        Decompose utterance into a Goal with ordered Subgoals.

        Validates that commit actions from the utterance are covered.
        """
        goal = self.decomposer.decompose(utterance, current_screen=perception, step_history=step_history)
        self._ensure_commit_coverage(utterance, goal)
        return goal

    def replan(
        self,
        goal: Goal,
        obstacle: str,
        perception: Optional["PerceptionBundle"] = None,
        step_history: Optional[List[StepMemory]] = None,
    ) -> List[Subgoal]:
        """
        Generate revised remaining subgoals after failure.

        Enforces atomic constraint — rejects compound multi-action subgoals.
        """
        # Enrich obstacle with VLM screen description if available on the bundle
        if perception is not None:
            vd = getattr(perception, "visual_description", None) or ""
            if vd:
                obstacle = f"{obstacle}\n\nCurrent screen when replanning:\n{vd[:600]}"

        new_subgoals = self.decomposer.replan_from_obstacle(
            goal, obstacle, current_screen=perception, step_history=step_history
        )

        # Enforce atomic constraint
        validated = []
        for sg in new_subgoals:
            if len(sg.description.split()) > ATOMIC_MAX_WORDS:
                # Split overly long compound subgoal into parts
                logger.warning(
                    f"Planner: rejecting compound subgoal ({len(sg.description.split())} words): "
                    f"'{sg.description[:60]}...' — using truncated version"
                )
                # Keep just the first action clause
                sg.description = " ".join(sg.description.split()[:ATOMIC_MAX_WORDS])
            # type actions must have a literal target — reject if empty or looks like
            # the LLM inserted reasoning/meta-text instead of the actual text to type
            if sg.action_type == "type":
                if not sg.target:
                    logger.warning(f"Planner: rejecting type subgoal with no target: '{sg.description}'")
                    continue
                if len(sg.target) > 120 or any(m in sg.target.lower() for m in ("e.g.", "such as", "etc.", "(e.g")):
                    logger.warning(f"Planner: rejecting type subgoal with meta-text target: '{sg.target[:60]}'")
                    continue
            validated.append(sg)

        # Reject subgoals with action types that don't exist in the registry
        pre_filter = len(validated)
        validated = [sg for sg in validated if sg.action_type in VALID_ACTIONS]
        if len(validated) < pre_filter:
            logger.warning(
                f"Planner: dropped {pre_filter - len(validated)} subgoal(s) with unknown action types"
            )

        if not validated:
            logger.warning("Planner: replan returned 0 subgoals, creating fallback")
            validated = [
                Subgoal(
                    description=f"Try alternative approach for: {goal.description}",
                    action_type="back",
                    target=None,
                )
            ]

        logger.info(f"Planner: replan produced {len(validated)} atomic subgoals")
        return validated

    def _ensure_commit_coverage(self, utterance: str, goal: Goal) -> None:
        """
        Ensure the plan covers commit actions implied by the utterance.

        E.g. if user says "add to cart", the plan must include an explicit
        'add to cart' subgoal.

        Skipped in reactive/phase mode: ReactiveStepGen receives commit intent
        via the COMMIT ACTIONS NEEDED prompt field and fires the commit at the
        correct step contextually.  Injecting subgoals here would pre-execute
        them before any phase has opened the target app.
        """
        if goal.phases:
            return

        utterance_lower = utterance.lower()
        plan_text = " ".join(sg.description.lower() for sg in goal.subgoals)

        for keyword in COMMIT_KEYWORDS:
            if keyword in utterance_lower and keyword not in plan_text:
                logger.warning(
                    f"Planner: commit action '{keyword}' missing from plan — injecting"
                )
                goal.subgoals.append(
                    Subgoal(
                        description=f"{keyword.capitalize()} (user-requested commit action)",
                        action_type="tap",
                        target=keyword,
                    )
                )
