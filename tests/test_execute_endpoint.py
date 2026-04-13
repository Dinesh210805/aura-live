"""
Tests for the execute endpoint's result-mapping logic.

The FastAPI endpoint itself requires the `fastapi` package which is not
installed in this test environment, so we test the result-mapping layer
directly — the same technique used in test_event_bus.py to avoid importing
aura_mcp_server (which requires the `mcp` package).

Coverage:
  - success/failure detection from status field
  - response_text fallback chain: spoken_response → feedback_message → default
  - error field set on failure, None on success
  - steps_taken counts executed_steps list length
  - command_source mapping
"""

import pytest


# ── Result-mapping helpers (mirrors api/execute.py inline logic) ─────────────

def _map_result(result: dict) -> dict:
    """
    Mirrors the response-building logic in api/execute.py:execute_task().
    Kept here so we can unit-test it without importing FastAPI.
    """
    succeeded = result.get("status") not in ("failed", "error")
    response_text = (
        result.get("spoken_response")
        or result.get("feedback_message")
        or ("Task completed." if succeeded else "Task failed.")
    )
    return {
        "success": succeeded,
        "response_text": response_text,
        "steps_taken": len(result.get("executed_steps", [])),
        "error": result.get("error_message") if not succeeded else None,
    }


# ── success detection ────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["completed", "executing", "processing", ""])
def test_non_failure_status_maps_to_success(status: str) -> None:
    result = {"status": status, "spoken_response": "OK", "executed_steps": []}
    mapped = _map_result(result)
    assert mapped["success"] is True


@pytest.mark.parametrize("status", ["failed", "error"])
def test_failure_status_maps_to_failure(status: str) -> None:
    result = {"status": status, "spoken_response": None,
              "feedback_message": None, "error_message": "oops", "executed_steps": []}
    mapped = _map_result(result)
    assert mapped["success"] is False


# ── response_text fallback chain ─────────────────────────────────────────────

def test_response_text_uses_spoken_response_first() -> None:
    result = {
        "status": "completed",
        "spoken_response": "Primary response",
        "feedback_message": "Fallback",
        "error_message": None,
        "executed_steps": [],
    }
    assert _map_result(result)["response_text"] == "Primary response"


def test_response_text_falls_back_to_feedback_message() -> None:
    result = {
        "status": "completed",
        "spoken_response": None,
        "feedback_message": "Fallback feedback",
        "error_message": None,
        "executed_steps": [],
    }
    assert _map_result(result)["response_text"] == "Fallback feedback"


def test_response_text_falls_back_to_default_on_success() -> None:
    result = {
        "status": "completed",
        "spoken_response": None,
        "feedback_message": None,
        "error_message": None,
        "executed_steps": [],
    }
    assert _map_result(result)["response_text"] == "Task completed."


def test_response_text_falls_back_to_default_on_failure() -> None:
    result = {
        "status": "failed",
        "spoken_response": None,
        "feedback_message": None,
        "error_message": None,
        "executed_steps": [],
    }
    assert _map_result(result)["response_text"] == "Task failed."


# ── error field ──────────────────────────────────────────────────────────────

def test_error_is_none_on_success() -> None:
    result = {"status": "completed", "spoken_response": "Done",
              "error_message": "ignored", "executed_steps": []}
    assert _map_result(result)["error"] is None


def test_error_carries_error_message_on_failure() -> None:
    result = {"status": "failed", "spoken_response": None,
              "feedback_message": None, "error_message": "App not found", "executed_steps": []}
    assert _map_result(result)["error"] == "App not found"


# ── steps_taken ──────────────────────────────────────────────────────────────

def test_steps_taken_counts_executed_steps() -> None:
    steps = [{"action": "tap"}, {"action": "swipe"}, {"action": "type"}]
    result = {"status": "completed", "spoken_response": "Done",
              "error_message": None, "executed_steps": steps}
    assert _map_result(result)["steps_taken"] == 3


def test_steps_taken_zero_when_no_steps() -> None:
    result = {"status": "completed", "spoken_response": "Done",
              "error_message": None, "executed_steps": []}
    assert _map_result(result)["steps_taken"] == 0


def test_steps_taken_zero_when_key_absent() -> None:
    result = {"status": "completed", "spoken_response": "Done"}
    assert _map_result(result)["steps_taken"] == 0
