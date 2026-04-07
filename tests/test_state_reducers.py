"""
Unit tests for LangGraph state reducers in aura_graph/state.py.

These reducers control how fields are merged when multiple graph nodes
write to the same TaskState key. A wrong reducer silently corrupts state
for the entire pipeline — so every code path must be covered.
"""

import pytest

from aura_graph.state import (
    MAX_EXECUTED_STEPS,
    add_errors,
    cap_executed_steps,
    set_once,
    update_status,
    update_step,
)


# ---------------------------------------------------------------------------
# add_errors
# ---------------------------------------------------------------------------

class TestAddErrors:
    def test_first_error_on_empty_state(self):
        """First error write: existing is None, should just return new."""
        assert add_errors(None, "stt_failed") == "stt_failed"

    def test_second_error_appends_with_semicolon(self):
        """Two errors must be joined so nothing is lost."""
        result = add_errors("stt_failed", "intent_failed")
        assert result == "stt_failed; intent_failed"

    def test_empty_existing_treated_same_as_none(self):
        """Empty string existing behaves like None — no leading separator."""
        assert add_errors("", "perception_failed") == "perception_failed"

    def test_three_errors_chain(self):
        """Reducer is applied left-to-right by LangGraph; simulate a chain."""
        first = add_errors(None, "err_a")
        second = add_errors(first, "err_b")
        third = add_errors(second, "err_c")
        assert third == "err_a; err_b; err_c"


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    def test_last_writer_wins(self):
        """Later status always replaces earlier one."""
        assert update_status("processing", "completed") == "completed"

    def test_first_write_from_none(self):
        assert update_status(None, "executing") == "executing"

    def test_same_value_is_idempotent(self):
        assert update_status("completed", "completed") == "completed"


# ---------------------------------------------------------------------------
# set_once
# ---------------------------------------------------------------------------

class TestSetOnce:
    def test_first_write_is_accepted(self):
        """None existing → accept new value."""
        assert set_once(None, 1234.5) == 1234.5

    def test_second_write_is_ignored(self):
        """Existing value must be preserved; second write is a no-op."""
        assert set_once(1000.0, 9999.0) == 1000.0

    def test_zero_is_a_valid_first_value(self):
        """0.0 is a legitimate timestamp — must not be treated as None."""
        assert set_once(0.0, 100.0) == 0.0

    def test_subsequent_writes_do_not_overwrite(self):
        """Simulate three writes; only the first should persist."""
        v = set_once(None, 1.0)
        v = set_once(v, 2.0)
        v = set_once(v, 3.0)
        assert v == 1.0


# ---------------------------------------------------------------------------
# cap_executed_steps
# ---------------------------------------------------------------------------

class TestCapExecutedSteps:
    def test_empty_inputs_return_empty_list(self):
        assert cap_executed_steps(None, None) == []

    def test_none_existing_with_new_items(self):
        steps = [{"action": "tap", "step": i} for i in range(5)]
        result = cap_executed_steps(None, steps)
        assert result == steps

    def test_none_new_preserves_existing(self):
        steps = [{"action": "tap", "step": 0}]
        result = cap_executed_steps(steps, None)
        assert result == steps

    def test_combined_within_cap_keeps_all(self):
        existing = [{"step": i} for i in range(20)]
        new = [{"step": i + 20} for i in range(10)]
        result = cap_executed_steps(existing, new)
        assert len(result) == 30

    def test_combined_exceeding_cap_keeps_most_recent(self):
        """When existing + new > MAX_EXECUTED_STEPS, only the tail is kept."""
        existing = [{"step": i} for i in range(40)]
        new = [{"step": i + 40} for i in range(20)]  # total = 60 > 50
        result = cap_executed_steps(existing, new)
        assert len(result) == MAX_EXECUTED_STEPS
        # Last entry must be the most recent (step 59)
        assert result[-1]["step"] == 59

    def test_exactly_at_cap_boundary(self):
        """Exactly MAX_EXECUTED_STEPS entries should all be kept."""
        steps = [{"step": i} for i in range(MAX_EXECUTED_STEPS)]
        result = cap_executed_steps(steps, [])
        assert len(result) == MAX_EXECUTED_STEPS

    def test_order_is_preserved(self):
        """The reducer must append new after existing — order matters for replay."""
        existing = [{"step": 0}, {"step": 1}]
        new = [{"step": 2}, {"step": 3}]
        result = cap_executed_steps(existing, new)
        assert [r["step"] for r in result] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# update_step
# ---------------------------------------------------------------------------

class TestUpdateStep:
    def test_none_existing_returns_new(self):
        assert update_step(None, 3) == 3

    def test_higher_new_wins(self):
        assert update_step(2, 5) == 5

    def test_higher_existing_wins(self):
        """Concurrent write with lower value must not regress current step."""
        assert update_step(7, 3) == 7

    def test_equal_values(self):
        assert update_step(4, 4) == 4

    def test_zero_step(self):
        assert update_step(None, 0) == 0
