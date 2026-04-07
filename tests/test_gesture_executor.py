"""
Unit tests for GestureExecutor in services/gesture_executor.py.

Tests cover the deterministic, side-effect-free helpers and the
routing branches that do not require a live WebSocket or device:

- _looks_like_phone_number    — regex classifier, fully sync
- _create_result              — pure dict builder, no I/O
- _extract_coordinates        — dict-parsing utility, no I/O
- _execute_single_action      — routing to scroll/type/tap handlers;
                                tests verify correct delegation by mocking
                                the downstream async methods

No real WebSocket or accessibility service is contacted.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.gesture_executor import GestureExecutor, GestureResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor() -> GestureExecutor:
    """
    Return a GestureExecutor instance with infrastructure patched out.

    The constructor calls logger.info — that's fine.  The device-facing
    services are never imported here; we patch only what the methods under
    test actually invoke.
    """
    return GestureExecutor()


def _ok_result(gesture_type: str = "tap") -> GestureResult:
    return GestureResult(success=True, gesture_type=gesture_type,
                         execution_time=0, strategy_used="websocket")


def _fail_result(gesture_type: str = "tap", error: str = "fail") -> GestureResult:
    return GestureResult(success=False, gesture_type=gesture_type,
                         execution_time=0, strategy_used="none", error=error)


# ---------------------------------------------------------------------------
# _looks_like_phone_number
# ---------------------------------------------------------------------------

class TestLooksLikePhoneNumber:
    def setup_method(self):
        self.executor = _make_executor()

    def test_plain_ten_digit_number(self):
        assert self.executor._looks_like_phone_number("9876543210") is True

    def test_international_prefix(self):
        assert self.executor._looks_like_phone_number("+919876543210") is True

    def test_country_code_no_plus(self):
        assert self.executor._looks_like_phone_number("919876543210") is True

    def test_dashes_and_spaces(self):
        assert self.executor._looks_like_phone_number("98765 43210") is True

    def test_parentheses_format(self):
        assert self.executor._looks_like_phone_number("(040) 2345678") is True

    def test_plain_name_is_not_phone(self):
        assert self.executor._looks_like_phone_number("John") is False

    def test_empty_string_is_not_phone(self):
        assert self.executor._looks_like_phone_number("") is False

    def test_short_number_is_not_phone(self):
        """Fewer than 9 total digit-adjacent chars should NOT match."""
        assert self.executor._looks_like_phone_number("12345") is False

    def test_email_is_not_phone(self):
        assert self.executor._looks_like_phone_number("user@example.com") is False


# ---------------------------------------------------------------------------
# _create_result
# ---------------------------------------------------------------------------

class TestCreateResult:
    def setup_method(self):
        self.executor = _make_executor()

    def test_all_success(self):
        result = self.executor._create_result(
            success=True, total_steps=3, success_count=3,
            executed_steps=[{}, {}, {}], errors=[]
        )
        assert result["success"] is True
        assert result["total_steps"] == 3
        assert result["successful_steps"] == 3
        assert result["failed_steps"] == 0
        assert result["errors"] == []

    def test_partial_failure(self):
        result = self.executor._create_result(
            success=False, total_steps=3, success_count=2,
            executed_steps=[{}, {}, {}], errors=["Step 3: timeout"]
        )
        assert result["success"] is False
        assert result["successful_steps"] == 2
        assert result["failed_steps"] == 1
        assert "Step 3: timeout" in result["errors"]

    def test_zero_steps(self):
        result = self.executor._create_result(
            success=False, total_steps=0, success_count=0,
            executed_steps=[], errors=["Empty action plan"]
        )
        assert result["total_steps"] == 0
        assert result["failed_steps"] == 0

    def test_summary_string_format(self):
        result = self.executor._create_result(
            success=True, total_steps=5, success_count=5,
            executed_steps=[], errors=[]
        )
        assert "5/5" in result["summary"]

    def test_total_time_present(self):
        result = self.executor._create_result(
            success=True, total_steps=1, success_count=1,
            executed_steps=[], errors=[], total_time=1.23
        )
        assert result["total_execution_time"] == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# _extract_coordinates
# ---------------------------------------------------------------------------

class TestExtractCoordinates:
    def setup_method(self):
        self.executor = _make_executor()

    def test_flat_x_y_in_action(self):
        action = {"action": "tap", "x": 540, "y": 960}
        assert self.executor._extract_coordinates(action) == (540, 960)

    def test_nested_coordinates_dict(self):
        action = {"coordinates": {"x": 100, "y": 200}}
        assert self.executor._extract_coordinates(action) == (100, 200)

    def test_nested_centerX_centerY(self):
        action = {"coordinates": {"centerX": 300, "centerY": 600}}
        assert self.executor._extract_coordinates(action) == (300, 600)

    def test_coordinates_as_list(self):
        action = {"coordinates": [450, 900]}
        assert self.executor._extract_coordinates(action) == (450, 900)

    def test_coordinates_list_longer_than_two(self):
        """Only the first two elements should be used."""
        action = {"coordinates": [450, 900, 999]}
        assert self.executor._extract_coordinates(action) == (450, 900)

    def test_missing_coordinates_returns_none(self):
        action = {"action": "tap"}
        assert self.executor._extract_coordinates(action) is None

    def test_empty_coordinates_dict_returns_none(self):
        action = {"coordinates": {}}
        assert self.executor._extract_coordinates(action) is None


# ---------------------------------------------------------------------------
# _execute_single_action — scroll direction normalization
# ---------------------------------------------------------------------------
#
# The key invariant:  `scroll_down` / `scroll_up` / `scroll_left` / `scroll_right`
# must each inject `direction: <suffix>` into the action dict BEFORE delegating
# to _execute_scroll, so that _execute_scroll.direction is always explicit.
#
# We test by patching `_execute_scroll` with an AsyncMock and capturing the
# action dict it receives.
# ---------------------------------------------------------------------------

class TestScrollDirectionNormalization:
    """Verify that directional scroll variants inject the right direction key."""

    @pytest.mark.asyncio
    async def test_scroll_down_injects_direction_down(self):
        executor = _make_executor()
        captured = {}

        async def fake_scroll(action):
            captured.update(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        await executor._execute_single_action({"action": "scroll_down"})
        assert captured.get("direction") == "down"

    @pytest.mark.asyncio
    async def test_scroll_up_injects_direction_up(self):
        executor = _make_executor()
        captured = {}

        async def fake_scroll(action):
            captured.update(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        await executor._execute_single_action({"action": "scroll_up"})
        assert captured.get("direction") == "up"

    @pytest.mark.asyncio
    async def test_scroll_left_injects_direction_left(self):
        executor = _make_executor()
        captured = {}

        async def fake_scroll(action):
            captured.update(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        await executor._execute_single_action({"action": "scroll_left"})
        assert captured.get("direction") == "left"

    @pytest.mark.asyncio
    async def test_scroll_right_injects_direction_right(self):
        executor = _make_executor()
        captured = {}

        async def fake_scroll(action):
            captured.update(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        await executor._execute_single_action({"action": "scroll_right"})
        assert captured.get("direction") == "right"

    @pytest.mark.asyncio
    async def test_explicit_direction_not_overwritten(self):
        """If action already has 'direction', scroll_down must NOT overwrite it."""
        executor = _make_executor()
        captured = {}

        async def fake_scroll(action):
            captured.update(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        # Explicitly set direction=up even though action type says scroll_down
        await executor._execute_single_action({"action": "scroll_down", "direction": "up"})
        # The existing direction must be preserved (branch condition: "direction" not in action)
        assert captured.get("direction") == "up"

    @pytest.mark.asyncio
    async def test_bare_scroll_delegates_without_injecting(self):
        """Plain 'scroll' (no directional suffix) must also route to _execute_scroll."""
        executor = _make_executor()
        called = []

        async def fake_scroll(action):
            called.append(action)
            return _ok_result("scroll")

        executor._execute_scroll = fake_scroll
        await executor._execute_single_action({"action": "scroll", "direction": "down"})
        assert len(called) == 1


# ---------------------------------------------------------------------------
# _execute_single_action — routing to type handler
# ---------------------------------------------------------------------------

class TestTypeActionRouting:
    @pytest.mark.asyncio
    async def test_type_routes_to_execute_type(self):
        executor = _make_executor()
        called = []

        async def fake_type(action):
            called.append(action)
            return _ok_result("type")

        executor._execute_type = fake_type
        await executor._execute_single_action({"action": "type", "text": "hello"})
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_input_alias_routes_to_execute_type(self):
        executor = _make_executor()
        called = []

        async def fake_type(action):
            called.append(action)
            return _ok_result("type")

        executor._execute_type = fake_type
        await executor._execute_single_action({"action": "input", "text": "hello"})
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_type_text_alias_routes_to_execute_type(self):
        executor = _make_executor()
        called = []

        async def fake_type(action):
            called.append(action)
            return _ok_result("type")

        executor._execute_type = fake_type
        await executor._execute_single_action({"action": "type_text", "text": "hello"})
        assert len(called) == 1


# ---------------------------------------------------------------------------
# _execute_single_action — unknown action type
# ---------------------------------------------------------------------------

class TestUnknownActionType:
    @pytest.mark.asyncio
    async def test_unknown_action_returns_failure(self):
        executor = _make_executor()
        result = await executor._execute_single_action({"action": "fly_to_moon"})
        assert result.success is False
        assert "Unknown action type" in (result.error or "")
        assert result.gesture_type == "fly_to_moon"


# ---------------------------------------------------------------------------
# _create_execution_plan
# ---------------------------------------------------------------------------

class TestCreateExecutionPlan:
    def setup_method(self):
        self.executor = _make_executor()

    def test_step_count(self):
        plan = self.executor._create_execution_plan([
            {"action": "tap"}, {"action": "type"}
        ])
        assert plan.total_steps == 2

    def test_requires_ui_refresh_when_open_app_present(self):
        plan = self.executor._create_execution_plan([
            {"action": "open_app"}, {"action": "tap"}
        ])
        assert plan.requires_ui_refresh is True

    def test_no_ui_refresh_for_simple_taps(self):
        plan = self.executor._create_execution_plan([
            {"action": "tap"}, {"action": "type"}
        ])
        assert plan.requires_ui_refresh is False

    def test_estimated_time_sums_timeout_fields(self):
        actions = [{"action": "tap", "timeout": 3.0}, {"action": "type", "timeout": 2.0}]
        plan = self.executor._create_execution_plan(actions)
        assert plan.estimated_time == pytest.approx(5.0)
