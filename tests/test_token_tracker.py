"""
Unit tests for TokenTracker in utils/token_tracker.py.

TokenTracker is a singleton — tests must reset its state between runs.
Tests cover: budget enforcement, stats aggregation, per-task accumulation.
No disk I/O is performed (we patch _append_to_disk).
"""

import pytest
from unittest.mock import patch, MagicMock

from utils.token_tracker import TokenTracker, TokenStats


# ---------------------------------------------------------------------------
# Fixture: fresh tracker for each test
# ---------------------------------------------------------------------------

@pytest.fixture()
def tracker():
    """
    Return a fresh TokenTracker with cleared state.

    The singleton pattern means we must manually reset between tests.
    We also patch disk I/O so tests don't write to logs/.
    """
    t = TokenTracker()
    t.usage_history.clear()
    t._task_budgets.clear()
    t._task_usage.clear()
    with patch.object(t, "_append_to_disk"):
        yield t


def _track(tracker, agent="commander", total=100, task_id=None):
    """Helper to record one usage entry."""
    return tracker.track(
        agent=agent,
        model_type="llm",
        provider="groq",
        model="llama3-8b",
        prompt_tokens=total - 20,
        completion_tokens=20,
        total_tokens=total,
        task_id=task_id,
    )


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_within_budget_returns_true(self, tracker):
        tracker.set_task_budget("task_1", 1000)
        result = _track(tracker, total=500, task_id="task_1")
        assert result is True

    def test_exceeding_budget_returns_false(self, tracker):
        tracker.set_task_budget("task_1", 100)
        result = _track(tracker, total=200, task_id="task_1")
        assert result is False

    def test_accumulated_usage_triggers_budget_exceeded(self, tracker):
        """Two calls that together exceed budget → second returns False."""
        tracker.set_task_budget("task_1", 150)
        _track(tracker, total=100, task_id="task_1")
        result = _track(tracker, total=100, task_id="task_1")
        assert result is False

    def test_no_budget_always_returns_true(self, tracker):
        """No set_task_budget call means unlimited — always within budget."""
        result = _track(tracker, total=999999, task_id="task_1")
        assert result is True

    def test_zero_budget_means_unlimited(self, tracker):
        """Budget of 0 is treated as unlimited (DEFAULT_TASK_BUDGET=0)."""
        tracker.set_task_budget("task_1", 0)
        result = _track(tracker, total=999999, task_id="task_1")
        assert result is True

    def test_different_tasks_have_independent_budgets(self, tracker):
        tracker.set_task_budget("task_a", 100)
        tracker.set_task_budget("task_b", 100)
        _track(tracker, total=90, task_id="task_a")
        # task_b should be untouched
        result = _track(tracker, total=50, task_id="task_b")
        assert result is True

    def test_no_task_id_never_fails_budget_check(self, tracker):
        """Calls without task_id must always return True."""
        result = _track(tracker, total=999999, task_id=None)
        assert result is True


# ---------------------------------------------------------------------------
# Usage accumulation
# ---------------------------------------------------------------------------

class TestUsageAccumulation:
    def test_get_task_usage_after_one_call(self, tracker):
        _track(tracker, total=300, task_id="t1")
        assert tracker.get_task_usage("t1") == 300

    def test_get_task_usage_accumulates_across_calls(self, tracker):
        _track(tracker, total=100, task_id="t1")
        _track(tracker, total=200, task_id="t1")
        assert tracker.get_task_usage("t1") == 300

    def test_get_task_usage_for_unknown_task_returns_zero(self, tracker):
        assert tracker.get_task_usage("nonexistent") == 0


# ---------------------------------------------------------------------------
# Stats aggregation
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_empty_tracker_returns_zero_stats(self, tracker):
        stats = tracker.get_stats()
        assert stats.total_calls == 0
        assert stats.total_tokens == 0

    def test_total_calls_increments(self, tracker):
        _track(tracker, agent="commander", total=100)
        _track(tracker, agent="responder", total=50)
        assert tracker.get_stats().total_calls == 2

    def test_total_tokens_sums_correctly(self, tracker):
        _track(tracker, total=100)
        _track(tracker, total=200)
        assert tracker.get_stats().total_tokens == 300

    def test_by_agent_breakdown(self, tracker):
        _track(tracker, agent="commander", total=100)
        _track(tracker, agent="commander", total=50)
        _track(tracker, agent="responder", total=200)
        stats = tracker.get_stats()
        assert stats.by_agent["commander"] == 150
        assert stats.by_agent["responder"] == 200

    def test_by_provider_breakdown(self, tracker):
        _track(tracker, agent="commander", total=100)
        stats = tracker.get_stats()
        assert stats.by_provider["groq"] == 100

    def test_filter_by_agent(self, tracker):
        _track(tracker, agent="commander", total=100)
        _track(tracker, agent="responder", total=200)
        stats = tracker.get_stats(agent="commander")
        assert stats.total_calls == 1
        assert stats.total_tokens == 100

    def test_filter_by_nonexistent_agent_returns_zeros(self, tracker):
        _track(tracker, agent="commander", total=100)
        stats = tracker.get_stats(agent="ghost_agent")
        assert stats.total_calls == 0
        assert stats.total_tokens == 0

    def test_prompt_and_completion_token_split(self, tracker):
        tracker.track(
            agent="a", model_type="llm", provider="groq", model="m",
            prompt_tokens=80, completion_tokens=20, total_tokens=100,
        )
        stats = tracker.get_stats()
        assert stats.total_prompt_tokens == 80
        assert stats.total_completion_tokens == 20
