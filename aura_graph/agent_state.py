"""
Agent state management for goal-driven, failure-resilient execution.

This module provides the core state model for long-horizon task execution,
including goal/subgoal hierarchies, retry strategies, and abort conditions.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Escalating retry strategies for failed actions."""
    SAME_ACTION = "same_action"           # Retry exact same action
    ALTERNATE_SELECTOR = "alternate_selector"  # Try different UI element selector
    SCROLL_AND_RETRY = "scroll_and_retry"      # Scroll to find element, retry
    VISION_FALLBACK = "vision_fallback"        # Use VLM coordinate detection
    ABORT = "abort"                            # Give up on this subgoal


# Retry ladder: each failure escalates to next strategy
RETRY_LADDER = [
    RetryStrategy.SAME_ACTION,
    RetryStrategy.ALTERNATE_SELECTOR,
    RetryStrategy.SCROLL_AND_RETRY,
    RetryStrategy.VISION_FALLBACK,
    RetryStrategy.ABORT,
]


class AbortCondition(Enum):
    """Conditions that trigger immediate task abort."""
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    SAME_SCREEN_LOOP = "same_screen_loop"      # Stuck on same UI state
    CRITICAL_ERROR = "critical_error"          # App crash, permission denied
    USER_INTERRUPT = "user_interrupt"
    SAFETY_VIOLATION = "safety_violation"      # Destructive action detected


@dataclass
class SuccessCriteria:
    """Defines how to validate an action succeeded."""
    ui_changed: bool = True                    # Expect UI tree to change
    target_element_gone: bool = False          # Element we acted on should disappear
    target_screen_reached: Optional[str] = None  # Expected screen/activity name
    text_appeared: Optional[str] = None        # Text that should appear
    custom_validator: Optional[str] = None     # Name of custom validation function


@dataclass
class StepMemory:
    """
    Short-term memory record for one completed subgoal.

    Accumulated in the Coordinator and passed forward so each perception
    and planning call has context about what has already happened.
    """
    subgoal_description: str
    action_type: str
    target: Optional[str]
    result: str                          # "success" | "failed"
    screen_type: str                     # "native" | "webview" | "keyboard_open" | "unknown"
    screen_before: str                   # UI signature pre-action
    screen_after: str                    # UI signature post-action
    coordinates: Optional[Tuple[int, int]] = None
    # VLM-generated semantic description of the screen at the time of this step.
    # Populated for WebView screens and forced-screenshot steps where UI tree is
    # unreliable. Used by the planner to understand screen state without relying
    # solely on the accessibility tree.
    screen_description: Optional[str] = None
    # Compact post-action state extracted from the element tree after the action
    # (e.g. "playing New York Nagaram | Pause"). Shown in HISTORY so the next VLM
    # call can verify the previous action's outcome from the element tree delta.
    key_state_after: Optional[str] = None


@dataclass
class Subgoal:
    """A single step in achieving a goal."""
    description: str
    action_type: str
    target: Optional[str] = None               # Element description or identifier
    parameters: dict = field(default_factory=dict)
    success_criteria: SuccessCriteria = field(default_factory=SuccessCriteria)
    completed: bool = False
    attempts: int = 0
    current_strategy_index: int = 0
    requires_vlm_verify: bool = False          # Set True for commit actions (add to cart, send, etc.)
    pre_action_context: dict = field(default_factory=dict)  # Baseline counters captured before commit action

    @property
    def current_strategy(self) -> RetryStrategy:
        """Get current retry strategy based on attempt count."""
        idx = min(self.current_strategy_index, len(RETRY_LADDER) - 1)
        return RETRY_LADDER[idx]

    def escalate_strategy(self) -> RetryStrategy:
        """Move to next retry strategy, return new strategy."""
        self.current_strategy_index = min(
            self.current_strategy_index + 1, 
            len(RETRY_LADDER) - 1
        )
        return self.current_strategy


@dataclass
class Phase:
    """A high-level phase in a goal skeleton (reactive planning layer 1)."""
    description: str
    completed: bool = False


@dataclass
class Goal:
    """A high-level user goal that may require multiple subgoals."""
    original_utterance: str
    description: str
    # ── Reactive hybrid planning ─────────────────────────────────────────────
    # Layer 1: abstract skeleton phases generated once at planning time.
    # When non-empty, the coordinator drives execution reactively: each step is
    # decided after observing the live screen rather than committing to a full
    # pre-baked path.  Old-style Goals without phases fall back to the static
    # subgoal list approach for backward compatibility.
    phases: List[Phase] = field(default_factory=list)
    current_phase_index: int = 0
    # Irreversible side effects the user asked for (add to cart, send, delete…).
    # The reactive executor guarantees these fire before goal completion.
    pending_commits: List[str] = field(default_factory=list)
    # ── Step execution (both modes) ──────────────────────────────────────────
    subgoals: list[Subgoal] = field(default_factory=list)
    current_subgoal_index: int = 0
    completed: bool = False
    aborted: bool = False
    abort_reason: Optional[str] = None

    @property
    def utterance(self) -> str:
        """Backward compatibility alias for original_utterance."""
        return self.original_utterance

    @property
    def current_phase(self) -> Optional[Phase]:
        """Active skeleton phase (reactive mode only)."""
        if self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None

    def advance_phase(self) -> None:
        """Mark current phase complete and move to the next."""
        if self.current_phase:
            self.current_phase.completed = True
        self.current_phase_index += 1

    @property
    def current_subgoal(self) -> Optional[Subgoal]:
        """Get the current active subgoal."""
        if self.current_subgoal_index < len(self.subgoals):
            return self.subgoals[self.current_subgoal_index]
        return None

    def advance_subgoal(self) -> Optional[Subgoal]:
        """Mark current subgoal complete, move to next. Returns new subgoal or None."""
        if self.current_subgoal:
            self.current_subgoal.completed = True
        self.current_subgoal_index += 1
        if self.current_subgoal_index >= len(self.subgoals):
            # In reactive mode (goal has phases) the coordinator manages completion;
            # don't auto-set completed here so remaining phases can continue.
            if not self.phases:
                self.completed = True
            return None
        return self.current_subgoal


@dataclass
class AgentState:
    """
    Persistent state for goal-driven execution.

    This tracks the agent's progress through a goal hierarchy,
    retry attempts, and UI state signatures for loop detection.
    """
    goal: Optional[Goal] = None

    # UI state tracking for loop detection
    ui_signature_history: list[str] = field(default_factory=list)
    last_ui_signature: Optional[str] = None

    # Retry tracking
    total_attempts: int = 0
    consecutive_same_screen: int = 0

    # Safety limits
    max_total_attempts: int = 15
    max_same_screen: int = 3
    max_subgoal_attempts: int = 5

    # Current screen identity (populated from UI tree)
    # FIXED: FIX-003 — added for target_screen_reached validation
    current_package_name: str = ""
    current_activity_name: str = ""

    # Scroll tracking for dynamic direction (FIX-010)
    scroll_attempts_for_current_target: int = 0
    scroll_target: str = ""

    def record_ui_signature(self, signature: str) -> None:
        """Record a UI signature and update loop detection counters."""
        if signature == self.last_ui_signature:
            self.consecutive_same_screen += 1
        else:
            self.consecutive_same_screen = 0
        
        self.last_ui_signature = signature
        self.ui_signature_history.append(signature)
        # Keep only last 10 signatures
        if len(self.ui_signature_history) > 10:
            self.ui_signature_history = self.ui_signature_history[-10:]

    def check_abort_conditions(self) -> Optional[AbortCondition]:
        """Check if any abort condition is met. Returns condition or None."""
        if self.total_attempts >= self.max_total_attempts:
            return AbortCondition.MAX_RETRIES_EXCEEDED
        
        if self.consecutive_same_screen >= self.max_same_screen:
            return AbortCondition.SAME_SCREEN_LOOP
        
        if self.goal and self.goal.current_subgoal:
            if self.goal.current_subgoal.attempts >= self.max_subgoal_attempts:
                return AbortCondition.MAX_RETRIES_EXCEEDED
        
        return None

    def reset_for_new_task(self) -> None:
        """Reset all per-task counters. Call at start of every new user command.

        # FIXED: FIX-006 — counters persisted across independent tasks, causing
        # second command to start with depleted retry budget and abort immediately.
        """
        self.total_attempts = 0
        self.consecutive_same_screen = 0
        self.last_ui_signature = None
        self.scroll_attempts_for_current_target = 0
        self.scroll_target = ""
        logger.debug("AgentState reset for new task")

    def reset_for_new_goal(self, goal: Goal) -> None:
        """Reset state for a new goal."""
        self.goal = goal
        self.ui_signature_history = []
        self.last_ui_signature = None
        self.total_attempts = 0
        self.consecutive_same_screen = 0


def create_simple_goal(utterance: str, action_type: str, target: Optional[str] = None, 
                       parameters: Optional[dict] = None) -> Goal:
    """
    Factory for simple single-action goals (backward compatibility).
    
    Used when a command doesn't require decomposition.
    """
    subgoal = Subgoal(
        description=utterance,
        action_type=action_type,
        target=target,
        parameters=parameters or {},
    )
    return Goal(
        original_utterance=utterance,
        description=utterance,
        subgoals=[subgoal],
    )
