"""
Integration tests for the Aura Agent execution loop.

Uses SimulatedDevice to exercise the real Coordinator → PerceiverAgent →
VerifierAgent logic without real ADB connections, LLM API calls, or hardware.

Mock points:
  - PerceptionController.request_perception  →  SimulatedDevice.make_perception_call
  - ActorAgent.execute                       →  SimulatedDevice.apply_action + ActionResult
  - PlannerAgent.create_plan                 →  canned Goal (bypasses LLM entirely)
  - VisualLocator.locate_from_bundle         →  fixed pixel coordinates

asyncio.sleep calls in Coordinator and VerifierAgent are patched to instant so
the test suite finishes in < 1 s.
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from agents.actor_agent import ActorAgent, ActionResult
from agents.coordinator import Coordinator
from agents.perceiver_agent import PerceiverAgent
from agents.planner_agent import PlannerAgent
from agents.verifier_agent import VerifierAgent
from agents.visual_locator import VisualLocator
from aura_graph.agent_state import Goal, StepMemory, Subgoal
from services.goal_decomposer import GoalDecomposer
from services.perception_controller import PerceptionController
from mock_device import SimulatedDevice


# ---------------------------------------------------------------------------
# Patch asyncio.sleep everywhere it is awaited during the agent loop
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Replace asyncio.sleep with an instant coroutine for all tests here."""
    async def _instant(_):
        pass
    monkeypatch.setattr("agents.coordinator.asyncio.sleep", _instant)
    monkeypatch.setattr("agents.verifier_agent.asyncio.sleep", _instant)


# ---------------------------------------------------------------------------
# Canned Amazon goal — bypasses the LLM planner entirely
# ---------------------------------------------------------------------------

def make_amazon_goal() -> Goal:
    """Hardcoded 6-subgoal plan for 'add iPhone 17 Pro to cart on Amazon'."""
    return Goal(
        original_utterance="open amazon and add iphone 17 pro to cart",
        description="Add iPhone 17 Pro to cart on Amazon",
        subgoals=[
            Subgoal(description="Open Amazon app",         action_type="open_app",    target="Amazon"),
            Subgoal(description="Tap search bar",          action_type="tap",         target="Search Amazon"),
            Subgoal(description="Type iPhone 17 Pro",      action_type="type",        target="iPhone 17 Pro"),
            Subgoal(description="Submit search",           action_type="press_enter", target=None),
            Subgoal(description="Tap first result",        action_type="tap",         target="iPhone 17 Pro"),
            Subgoal(description="Tap Add to Cart",         action_type="tap",         target="Add to Cart"),
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def device() -> SimulatedDevice:
    return SimulatedDevice(initial_state="launcher")


@pytest.fixture
def coordinator(device: SimulatedDevice) -> Coordinator:
    """
    Fully-wired Coordinator with mocked I/O via SimulatedDevice.

    Real objects exercised: PerceiverAgent, VerifierAgent (all logic paths run).
    """
    # ── Shared perception controller (perceiver + verifier use the same mock) ──
    perception_ctrl = MagicMock(spec=PerceptionController)
    perception_ctrl.request_perception = AsyncMock(
        side_effect=device.make_perception_call
    )

    # ── VisualLocator: always return fixed coordinates (no real OmniParser) ──
    visual_locator = MagicMock(spec=VisualLocator)
    visual_locator.locate_from_bundle = Mock(
        return_value={"x": 540, "y": 800, "source": "mock_vlm", "confidence": 0.9}
    )

    # ── PerceiverAgent (real logic, mocked I/O) ──
    perceiver = PerceiverAgent(
        perception_controller=perception_ctrl,
        perception_pipeline=None,
        visual_locator=visual_locator,
    )

    # ── PlannerAgent: return canned plan, never call replan on happy path ──
    planner = MagicMock(spec=PlannerAgent)
    planner.create_plan = Mock(return_value=make_amazon_goal())
    planner.replan = Mock(return_value=[])

    # ── ActorAgent: advance device state, always succeed ──
    actor = MagicMock(spec=ActorAgent)

    async def _mock_execute(action_type, target=None, coordinates=None, parameters=None):
        device.apply_action(action_type, target)
        return ActionResult(
            success=True,
            action_type=action_type,
            coordinates=coordinates,
            duration_ms=10.0,
            error=None,
        )

    actor.execute = AsyncMock(side_effect=_mock_execute)

    # ── VerifierAgent (real logic, shared mocked perception controller) ──
    verifier = VerifierAgent(perception_controller=perception_ctrl)

    # ── TaskProgressService (broadcast only) ──
    task_progress = MagicMock()
    task_progress.start_task = Mock()
    task_progress.complete_current_step = Mock()

    return Coordinator(planner, perceiver, actor, verifier, task_progress)


_INTENT: Dict[str, Any] = {
    "raw": "open amazon and add iphone 17 pro to cart",
    "action": "add_to_cart",
    "app": "amazon",
}


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_amazon_flow_completes(coordinator, device):
    """Happy path: all 6 subgoals complete and device ends in cart_confirmed."""
    result = await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    assert result["status"] == "completed", (
        f"Expected 'completed', got '{result['status']}': {result.get('error')}"
    )
    assert device.current_state == "cart_confirmed", (
        f"Device should be in cart_confirmed, got '{device.current_state}'"
    )


@pytest.mark.asyncio
async def test_open_app_skips_perceive(coordinator, device):
    """
    open_app is in NO_TARGET_ACTIONS — perceiver.perceive() must not fire.
    Only _snapshot_pre (action_type='verify') calls are expected while
    the device is still on the launcher screen.
    """
    await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    perceive_calls_during_launch = [
        c for c in device.perception_calls
        if c["device_state"] == "launcher" and c["action_type"] != "verify"
    ]
    assert len(perceive_calls_during_launch) == 0, (
        f"perceiver.perceive() fired {len(perceive_calls_during_launch)} time(s) "
        "during open_app. Expected 0 — open_app is in NO_TARGET_ACTIONS."
    )


@pytest.mark.asyncio
async def test_webview_triggers_vlm_description(coordinator, device):
    """
    When a screen is classified as WebView, the perceiver must re-request
    perception with skip_description=False to get VLM semantic content.
    """
    await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    webview_description_calls = [
        c for c in device.perception_calls
        if c["device_state"] in ("amazon_results", "product_detail")
        and not c["skip_description"]
    ]
    assert len(webview_description_calls) > 0, (
        "No perception call with skip_description=False for WebView screens. "
        "Perceiver should re-fetch with description for amazon_results / product_detail."
    )


@pytest.mark.asyncio
async def test_step_memory_captures_webview_description(coordinator, device):
    """StepMemory for WebView subgoals must contain a non-None screen_description."""
    result = await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    step_memory: List[StepMemory] = result.get("step_memory", [])
    webview_steps = [s for s in step_memory if s.screen_type == "webview"]

    assert len(webview_steps) > 0, "Expected at least one webview step in step_memory."
    for step in webview_steps:
        assert step.screen_description is not None, (
            f"StepMemory for '{step.subgoal_description}' missing screen_description. "
            "WebView steps must carry VLM description for replanning context."
        )


@pytest.mark.asyncio
async def test_planner_uses_open_app_not_tap(coordinator, device):
    """First subgoal must be action_type='open_app' (not 'tap') for app launches."""
    result = await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    first = result["goal"].subgoals[0]
    assert first.action_type == "open_app", (
        f"First subgoal should be 'open_app', got '{first.action_type}'. "
        "Planner must use open_app rule from planning prompt."
    )
    assert first.target and "amazon" in first.target.lower(), (
        f"open_app target should contain 'amazon', got '{first.target}'."
    )


@pytest.mark.asyncio
async def test_type_action_no_perceive_call(coordinator, device):
    """
    'type' is in NO_TARGET_ACTIONS — perceiver.perceive() must not fire.
    Only snapshot/verify perception calls (action_type='verify') are expected
    while the device is in amazon_search_empty.
    """
    await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    bad_calls = [
        c for c in device.perception_calls
        if c["device_state"] == "amazon_search_empty" and c["action_type"] == "type"
    ]
    assert len(bad_calls) == 0, (
        "perceiver.perceive() was called with action_type='type'. "
        "That action is in NO_TARGET_ACTIONS and must skip perception."
    )


@pytest.mark.asyncio
async def test_executed_steps_count(coordinator, device):
    """Coordinator must record exactly 6 executed steps (one per subgoal)."""
    result = await coordinator.execute(
        utterance="open amazon and add iphone 17 pro to cart",
        intent=_INTENT,
        session_id="test-session",
    )

    assert len(result["executed_steps"]) == 6, (
        f"Expected 6 executed steps, got {len(result['executed_steps'])}."
    )


# ---------------------------------------------------------------------------
# Unit tests: GoalDecomposer._extract_screen_context priority
# ---------------------------------------------------------------------------

def test_extract_screen_context_prefers_visual_description():
    """visual_description must take priority over UI tree scraping."""
    decomposer = GoalDecomposer.__new__(GoalDecomposer)

    bundle = MagicMock()
    bundle.visual_description = "Product listing page with iPhone cards and prices."
    bundle.ui_tree = MagicMock()
    bundle.ui_tree.elements = [
        {"className": "android.webkit.WebView", "text": "", "contentDescription": ""},
    ]

    ctx = decomposer._extract_screen_context(bundle)
    assert "Product listing" in ctx, (
        f"Expected visual_description content in context, got: {ctx!r}"
    )


def test_extract_screen_context_falls_back_to_ui_tree():
    """When visual_description is None, fall back to UI tree scraping."""
    decomposer = GoalDecomposer.__new__(GoalDecomposer)

    bundle = MagicMock()
    bundle.visual_description = None
    bundle.ui_tree = MagicMock()
    bundle.ui_tree.elements = [
        {
            "className": "android.widget.EditText",
            "text": "Search Amazon",
            "contentDescription": "",
            "clickable": True,
        },
    ]

    ctx = decomposer._extract_screen_context(bundle)
    assert ctx, "Context should not be empty when UI tree has elements."
    assert "Product listing" not in ctx, (
        "Context should be from UI tree scraping, not a WebView description."
    )
