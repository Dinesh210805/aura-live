"""
Phase 1 MCP tool tests — all run with mocked device/services.

These tests validate the return shape and logic of each MCP tool
without requiring a connected Android device or running FastAPI server.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# perceive_screen
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_perceive_screen_returns_expected_shape():
    mock_bundle = MagicMock()
    mock_bundle.snapshot_id = "snap_001"
    mock_bundle.screenshot.screenshot_base64 = "base64data"
    mock_bundle.screenshot.screen_width = 1080
    mock_bundle.screenshot.screen_height = 2400
    mock_bundle.ui_tree.elements = []
    mock_bundle.visual_description = "Home screen"
    mock_bundle.screen_meta = None

    with patch("aura_mcp_server.get_perception_controller") as mock_ctrl:
        mock_ctrl.return_value.request_perception = AsyncMock(return_value=mock_bundle)
        from aura_mcp_server import perceive_screen
        result = await perceive_screen()

    assert result["snapshot_id"] == "snap_001"
    assert result["screen_width"] == 1080
    assert result["screen_height"] == 2400
    assert result["screenshot_base64"] == "base64data"
    assert result["ui_summary"] == "Home screen"
    assert isinstance(result["som_elements"], list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perceive_screen_with_som_elements():
    mock_el = MagicMock()
    mock_el.som_label = "A1"
    mock_el.content_desc = "Search bar"
    mock_el.text = ""
    mock_el.class_name = "android.widget.EditText"
    mock_el.bounds = {"left": 0, "top": 0, "right": 100, "bottom": 50}
    mock_el.clickable = True

    mock_bundle = MagicMock()
    mock_bundle.snapshot_id = "snap_002"
    mock_bundle.screenshot.screenshot_base64 = "data"
    mock_bundle.screenshot.screen_width = 1080
    mock_bundle.screenshot.screen_height = 2400
    mock_bundle.ui_tree.elements = [mock_el]
    mock_bundle.visual_description = "Search screen"
    mock_bundle.screen_meta = None

    with patch("aura_mcp_server.get_perception_controller") as mock_ctrl:
        mock_ctrl.return_value.request_perception = AsyncMock(return_value=mock_bundle)
        from aura_mcp_server import perceive_screen
        result = await perceive_screen()

    assert len(result["som_elements"]) == 1
    assert result["som_elements"][0]["label"] == "A1"
    assert result["som_elements"][0]["clickable"] is True


# ---------------------------------------------------------------------------
# execute_gesture
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_gesture_back():
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.action_type = "back"
    mock_result.duration_ms = 50.0
    mock_result.error = None
    mock_result.details = {}

    with patch("aura_mcp_server.ActorAgent") as MockActor, \
         patch("aura_mcp_server.GestureExecutor"):
        MockActor.return_value.execute = AsyncMock(return_value=mock_result)
        # Reset singleton so patch takes effect
        import aura_mcp_server
        aura_mcp_server._actor = None
        from aura_mcp_server import execute_gesture
        result = await execute_gesture("back")

    assert result["success"] is True
    assert result["action_type"] == "back"
    assert result["error"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_gesture_tap_with_coordinates():
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.action_type = "tap"
    mock_result.duration_ms = 80.0
    mock_result.error = None
    mock_result.details = {"coordinates": [540, 960]}

    with patch("aura_mcp_server.ActorAgent") as MockActor, \
         patch("aura_mcp_server.GestureExecutor"):
        MockActor.return_value.execute = AsyncMock(return_value=mock_result)
        import aura_mcp_server
        aura_mcp_server._actor = None
        from aura_mcp_server import execute_gesture
        result = await execute_gesture("tap", target="A3", params={"x": 540, "y": 960})

    assert result["success"] is True
    # Verify coordinates were extracted from params
    call_kwargs = MockActor.return_value.execute.call_args
    assert call_kwargs.kwargs.get("coordinates") == (540, 960) or \
           call_kwargs.args[2] == (540, 960)


# ---------------------------------------------------------------------------
# validate_action
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_action_allowed():
    mock_decision = MagicMock()
    mock_decision.allowed = True
    mock_decision.reason = ""
    mock_decision.requires_confirmation = False

    with patch("aura_mcp_server.PolicyEngine") as MockPolicy:
        MockPolicy.return_value.evaluate = AsyncMock(return_value=mock_decision)
        import aura_mcp_server
        aura_mcp_server._policy = None
        from aura_mcp_server import validate_action
        result = await validate_action("tap", "A1")

    assert result["allowed"] is True
    assert result["requires_confirmation"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_action_blocked():
    mock_decision = MagicMock()
    mock_decision.allowed = False
    mock_decision.reason = "Action factory_reset is blocked"
    mock_decision.requires_confirmation = False

    with patch("aura_mcp_server.PolicyEngine") as MockPolicy:
        MockPolicy.return_value.evaluate = AsyncMock(return_value=mock_decision)
        import aura_mcp_server
        aura_mcp_server._policy = None
        from aura_mcp_server import validate_action
        result = await validate_action("factory_reset", "")

    assert result["allowed"] is False
    assert "factory_reset" in result["reason"]


# ---------------------------------------------------------------------------
# watch_device_events
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_watch_device_events_returns_empty_list():
    from aura_mcp_server import watch_device_events
    result = await watch_device_events(timeout_seconds=1)
    assert result == []
    assert isinstance(result, list)
