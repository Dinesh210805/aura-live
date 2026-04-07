"""
Unit tests for the structured error taxonomy in utils/error_types.py.

Tests cover:
- get_recovery: returns correct RecoveryStrategy for each ErrorType
- get_recovery: accepts raw strings for backward-compat (existing edge code)
- get_recovery: gracefully handles unknown strings
- classify_abort_reason: maps coordinator abort strings to ErrorType enum values
"""

import pytest

from utils.error_types import (
    ErrorType,
    RecoveryStrategy,
    classify_abort_reason,
    get_recovery,
)


# ---------------------------------------------------------------------------
# get_recovery — enum input
# ---------------------------------------------------------------------------

class TestGetRecoveryWithEnum:
    def test_stt_failed_is_abort(self):
        strategy = get_recovery(ErrorType.STT_FAILED)
        assert strategy.action == "abort"

    def test_perception_failed_is_retry_with_3_attempts(self):
        strategy = get_recovery(ErrorType.PERCEPTION_FAILED)
        assert strategy.action == "retry"
        assert strategy.max_attempts == 3
        assert strategy.escalate_to == "replan"

    def test_target_not_found_escalates_to_replan(self):
        strategy = get_recovery(ErrorType.TARGET_NOT_FOUND)
        assert strategy.action == "retry"
        assert strategy.escalate_to == "replan"

    def test_gesture_rejected_asks_user(self):
        strategy = get_recovery(ErrorType.GESTURE_REJECTED)
        assert strategy.action == "ask_user"

    def test_budget_exhausted_aborts(self):
        strategy = get_recovery(ErrorType.BUDGET_EXHAUSTED)
        assert strategy.action == "abort"

    def test_action_loop_replans(self):
        strategy = get_recovery(ErrorType.ACTION_LOOP)
        assert strategy.action == "replan"

    def test_screen_loop_replans(self):
        strategy = get_recovery(ErrorType.SCREEN_LOOP)
        assert strategy.action == "replan"

    def test_stuck_asks_user(self):
        strategy = get_recovery(ErrorType.STUCK)
        assert strategy.action == "ask_user"

    def test_replan_limit_aborts(self):
        strategy = get_recovery(ErrorType.REPLAN_LIMIT)
        assert strategy.action == "abort"

    def test_unknown_aborts(self):
        strategy = get_recovery(ErrorType.UNKNOWN)
        assert strategy.action == "abort"

    def test_every_error_type_has_a_user_message(self):
        """Every defined ErrorType must produce a non-empty user message."""
        for error_type in ErrorType:
            strategy = get_recovery(error_type)
            assert strategy.user_message, f"{error_type} has no user_message"

    def test_return_type_is_recovery_strategy(self):
        strategy = get_recovery(ErrorType.EXECUTION_FAILED)
        assert isinstance(strategy, RecoveryStrategy)


# ---------------------------------------------------------------------------
# get_recovery — string input (backward compatibility)
# ---------------------------------------------------------------------------

class TestGetRecoveryWithString:
    def test_string_stt_failed(self):
        strategy = get_recovery("stt_failed")
        assert strategy.action == "abort"

    def test_string_perception_failed(self):
        strategy = get_recovery("perception_failed")
        assert strategy.action == "retry"

    def test_unknown_string_falls_back_to_unknown_strategy(self):
        strategy = get_recovery("complete_nonsense_xyz")
        assert strategy.action == "abort"  # UNKNOWN strategy is abort

    def test_empty_string_falls_back_gracefully(self):
        strategy = get_recovery("")
        assert isinstance(strategy, RecoveryStrategy)

    def test_string_values_match_enum_values(self):
        """String shortcut must produce the exact same strategy as the enum."""
        for error_type in ErrorType:
            assert get_recovery(error_type.value) == get_recovery(error_type)


# ---------------------------------------------------------------------------
# classify_abort_reason
# ---------------------------------------------------------------------------

class TestClassifyAbortReason:
    def test_perception_in_reason(self):
        assert classify_abort_reason("perception timeout") == ErrorType.PERCEPTION_FAILED

    def test_target_not_found(self):
        assert classify_abort_reason("target not found after 3 retries") == ErrorType.TARGET_NOT_FOUND

    def test_budget_exhausted(self):
        assert classify_abort_reason("action budget exceeded") == ErrorType.BUDGET_EXHAUSTED

    def test_replan_limit_exceeded(self):
        assert classify_abort_reason("replan limit exceeded") == ErrorType.REPLAN_LIMIT

    def test_action_loop(self):
        assert classify_abort_reason("action loop detected") == ErrorType.ACTION_LOOP

    def test_screen_loop(self):
        assert classify_abort_reason("stuck on same screen loop") == ErrorType.SCREEN_LOOP

    def test_stuck(self):
        assert classify_abort_reason("agent stuck, no progress") == ErrorType.STUCK

    def test_hitl_timeout(self):
        assert classify_abort_reason("hitl timeout waiting for user") == ErrorType.HITL_TIMEOUT

    def test_gesture_execution_failed(self):
        assert classify_abort_reason("gesture execution failed") == ErrorType.EXECUTION_FAILED

    def test_screen_mismatch(self):
        assert classify_abort_reason("screen mismatch detected") == ErrorType.SCREEN_MISMATCH

    def test_cancelled_maps_to_blocked(self):
        assert classify_abort_reason("task was cancelled by guard") == ErrorType.BLOCKED

    def test_completely_unknown_reason(self):
        assert classify_abort_reason("something unrecognizable happened") == ErrorType.UNKNOWN

    def test_empty_string_is_unknown(self):
        assert classify_abort_reason("") == ErrorType.UNKNOWN

    def test_case_insensitive(self):
        """abort_reason strings from coordinator may vary in casing."""
        assert classify_abort_reason("PERCEPTION FAILED") == ErrorType.PERCEPTION_FAILED
