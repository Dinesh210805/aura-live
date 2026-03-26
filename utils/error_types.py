"""
Structured error taxonomy for AURA's agentic pipeline.

Replaces ad-hoc string status codes with a proper enum so that:
- Typos are caught at import time, not at runtime
- Per-error recovery strategies are co-located with the error definition
- Edges and coordinator can query `RecoveryStrategy` without string matching

Usage:
    from utils.error_types import ErrorType, get_recovery

    error = ErrorType.PERCEPTION_FAILED
    strategy = get_recovery(error)
    # RecoveryStrategy(action="retry", max_attempts=3, escalate_to="replan")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# =============================================================================
# ERROR TYPE ENUM
# =============================================================================

class ErrorType(str, Enum):
    """All failure modes that can occur in the AURA pipeline.

    Each value matches the string status code used in edges.py and coordinator.py
    to preserve backward compatibility — existing `status == "..."` checks still
    work while new code can use the enum.
    """
    # STT / input layer
    STT_FAILED          = "stt_failed"
    INTENT_FAILED       = "intent_failed"
    BLOCKED             = "blocked"           # Prompt Guard blocked the request

    # Planning
    PLANNING_FAILED     = "planning_failed"

    # Perception / screen reading
    PERCEPTION_FAILED   = "perception_failed"
    TARGET_NOT_FOUND    = "target_not_found"
    SCREEN_MISMATCH     = "screen_mismatch"   # VLM flagged wrong screen

    # Execution / gestures
    EXECUTION_FAILED    = "execution_failed"
    GESTURE_REJECTED    = "gesture_rejected"  # OPA policy denial
    INPUT_FIELD_MISSING = "input_field_missing"

    # Loop / budget
    ACTION_LOOP         = "action_loop"       # Same action repeated N times
    SCREEN_LOOP         = "screen_loop"       # Stuck on same screen
    BUDGET_EXHAUSTED    = "budget_exhausted"  # MAX_TOTAL_ACTIONS reached
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"

    # Human-in-the-loop
    HITL_TIMEOUT        = "hitl_timeout"      # User didn't respond in time
    STUCK               = "stuck"             # Agent reported stuck

    # Replan
    REPLAN_LIMIT        = "replan_limit"      # MAX_REPLAN_ATTEMPTS exceeded

    # Generic
    UNKNOWN             = "unknown"


# =============================================================================
# RECOVERY STRATEGY
# =============================================================================

@dataclass(frozen=True)
class RecoveryStrategy:
    """Describes how the pipeline should respond to a given error type.

    Attributes:
        action:       Primary recovery action — one of:
                        "retry"   — repeat the failed step (up to max_attempts)
                        "replan"  — request a new plan from PlannerAgent
                        "abort"   — give up and surface the error to the user
                        "ask_user"— pause and ask the user for guidance
        max_attempts: How many times to retry before escalating (only for "retry")
        escalate_to:  If retries are exhausted, what to do next
                        ("replan" | "abort" | "ask_user")
        user_message: Human-readable hint for what went wrong (used in TTS response)
    """
    action: str
    max_attempts: int = 1
    escalate_to: Optional[str] = None
    user_message: str = "Something went wrong. I'll try again."


# =============================================================================
# RECOVERY STRATEGY MAP
# =============================================================================

RECOVERY_STRATEGIES: dict[ErrorType, RecoveryStrategy] = {
    ErrorType.STT_FAILED: RecoveryStrategy(
        action="abort",
        user_message="I couldn't hear that. Please try again.",
    ),
    ErrorType.INTENT_FAILED: RecoveryStrategy(
        action="abort",
        user_message="I didn't understand that command. Could you rephrase?",
    ),
    ErrorType.BLOCKED: RecoveryStrategy(
        action="abort",
        user_message="I can't perform that action — it was flagged as unsafe.",
    ),
    ErrorType.PLANNING_FAILED: RecoveryStrategy(
        action="retry",
        max_attempts=2,
        escalate_to="abort",
        user_message="I had trouble planning that. Let me try again.",
    ),
    ErrorType.PERCEPTION_FAILED: RecoveryStrategy(
        action="retry",
        max_attempts=3,
        escalate_to="replan",
        user_message="I couldn't read the screen. Retrying.",
    ),
    ErrorType.TARGET_NOT_FOUND: RecoveryStrategy(
        action="retry",
        max_attempts=3,
        escalate_to="replan",
        user_message="I couldn't find what I was looking for. Trying a different approach.",
    ),
    ErrorType.SCREEN_MISMATCH: RecoveryStrategy(
        action="replan",
        max_attempts=3,
        escalate_to="abort",
        user_message="The screen doesn't look right. Replanning.",
    ),
    ErrorType.EXECUTION_FAILED: RecoveryStrategy(
        action="retry",
        max_attempts=3,
        escalate_to="replan",
        user_message="The action didn't work. Retrying.",
    ),
    ErrorType.GESTURE_REJECTED: RecoveryStrategy(
        action="ask_user",
        user_message="That action requires your confirmation before I can proceed.",
    ),
    ErrorType.INPUT_FIELD_MISSING: RecoveryStrategy(
        action="retry",
        max_attempts=2,
        escalate_to="replan",
        user_message="I couldn't find a text field to type in.",
    ),
    ErrorType.ACTION_LOOP: RecoveryStrategy(
        action="replan",
        max_attempts=2,
        escalate_to="abort",
        user_message="I seem to be going in circles. Trying a different path.",
    ),
    ErrorType.SCREEN_LOOP: RecoveryStrategy(
        action="replan",
        max_attempts=2,
        escalate_to="abort",
        user_message="I'm stuck on the same screen. Let me try something different.",
    ),
    ErrorType.BUDGET_EXHAUSTED: RecoveryStrategy(
        action="abort",
        user_message="That took too many steps. I've stopped to avoid unintended actions.",
    ),
    ErrorType.TOKEN_BUDGET_EXCEEDED: RecoveryStrategy(
        action="abort",
        user_message="This task used too many AI tokens. Please try a simpler command.",
    ),
    ErrorType.HITL_TIMEOUT: RecoveryStrategy(
        action="abort",
        user_message="I was waiting for your input but didn't get a response in time.",
    ),
    ErrorType.STUCK: RecoveryStrategy(
        action="ask_user",
        user_message="I'm not sure how to proceed. Could you clarify?",
    ),
    ErrorType.REPLAN_LIMIT: RecoveryStrategy(
        action="abort",
        user_message="I've tried several approaches without success. Please try rephrasing your command.",
    ),
    ErrorType.UNKNOWN: RecoveryStrategy(
        action="abort",
        user_message="An unexpected error occurred.",
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_recovery(error: ErrorType | str) -> RecoveryStrategy:
    """Return the RecoveryStrategy for the given error type.

    Accepts either an ErrorType enum value or a raw string status code
    for backward compatibility with existing edge/coordinator code.
    """
    if isinstance(error, str):
        try:
            error = ErrorType(error)
        except ValueError:
            return RECOVERY_STRATEGIES[ErrorType.UNKNOWN]
    return RECOVERY_STRATEGIES.get(error, RECOVERY_STRATEGIES[ErrorType.UNKNOWN])


def classify_abort_reason(abort_reason: str) -> ErrorType:
    """Map a coordinator abort_reason string to the closest ErrorType.

    Used post-execution to categorise goal failures for logging/metrics.
    """
    r = abort_reason.lower()
    if "perception" in r:
        return ErrorType.PERCEPTION_FAILED
    if "target" in r and "not found" in r:
        return ErrorType.TARGET_NOT_FOUND
    if "budget" in r or "action budget" in r:
        return ErrorType.BUDGET_EXHAUSTED
    if "replan" in r and "exceeded" in r:
        return ErrorType.REPLAN_LIMIT
    if "loop" in r:
        return ErrorType.ACTION_LOOP if "action" in r or "coord" in r else ErrorType.SCREEN_LOOP
    if "stuck" in r:
        return ErrorType.STUCK
    if "hitl" in r or "human resolution" in r:
        return ErrorType.HITL_TIMEOUT
    if "cancelled" in r:
        return ErrorType.BLOCKED
    if "gesture" in r or "execution" in r:
        return ErrorType.EXECUTION_FAILED
    if "screen mismatch" in r:
        return ErrorType.SCREEN_MISMATCH
    return ErrorType.UNKNOWN
