"""
Unit tests for services/intent_normalizer.py.

Tests cover:
- normalize_intent_action: pass-through for valid actions
- App-opening normalization: "open_settings", "launch-instagram", "start Maps"
- Screen-read normalization: "describe", "analyze_screen", "view-screen"
- Fallback to general_interaction for unknown actions
- delegate_to_planner flag when recipient + task params present
- Empty action → general_interaction fallback
- is_valid_action and list_valid_actions helpers
"""

import pytest

from services.intent_normalizer import (
    is_valid_action,
    list_valid_actions,
    normalize_intent_action,
)


# ---------------------------------------------------------------------------
# Pass-through: action already in ACTION_REGISTRY
# ---------------------------------------------------------------------------

class TestPassThrough:
    def test_tap_passes_through(self):
        intent = {"action": "tap", "x": 100, "y": 200}
        result = normalize_intent_action(intent)
        assert result["action"] == "tap"
        assert result is intent  # Same dict returned for registered actions

    def test_scroll_passes_through(self):
        result = normalize_intent_action({"action": "scroll"})
        assert result["action"] == "scroll"

    def test_send_message_passes_through(self):
        intent = {"action": "send_message", "recipient": "mom", "content": "hi"}
        result = normalize_intent_action(intent)
        assert result["action"] == "send_message"

    def test_home_passes_through(self):
        result = normalize_intent_action({"action": "home"})
        assert result["action"] == "home"

    def test_uppercase_action_passthrough(self):
        """Case insensitive matching — original intent returned unchanged (action not lowercased)."""
        intent = {"action": "TAP", "x": 0, "y": 0}
        result = normalize_intent_action(intent)
        # Implementation lowercases internally for registry lookup but returns original dict
        assert result is intent


# ---------------------------------------------------------------------------
# App-opening normalization patterns
# ---------------------------------------------------------------------------

class TestAppOpenNormalization:
    def test_open_spotify(self):
        """'open_settings' is a registered action and passes through — use an unregistered app."""
        result = normalize_intent_action({"action": "open_spotify"})
        assert result["action"] == "open_app"
        assert result["recipient"] == "Spotify"

    def test_launch_instagram(self):
        result = normalize_intent_action({"action": "launch-instagram"})
        assert result["action"] == "open_app"
        assert result["recipient"] == "Instagram"

    def test_start_maps(self):
        result = normalize_intent_action({"action": "start maps"})
        assert result["action"] == "open_app"
        assert result["recipient"] == "Maps"

    def test_access_camera(self):
        result = normalize_intent_action({"action": "access_camera"})
        assert result["action"] == "open_app"
        assert result["recipient"] == "Camera"

    def test_recipient_not_overridden_if_present(self):
        """Existing recipient is preserved when app open normalization runs."""
        result = normalize_intent_action({"action": "open_camera", "recipient": "Existing"})
        assert result["action"] == "open_app"
        # Original recipient preserved since it was already set
        assert result["recipient"] == "Existing"

    def test_go_to_app_pattern(self):
        result = normalize_intent_action({"action": "goto_youtube"})
        assert result["action"] == "open_app"


# ---------------------------------------------------------------------------
# Screen-read normalization
# ---------------------------------------------------------------------------

class TestScreenReadNormalization:
    def test_describe_screen_maps_to_read_screen(self):
        """'describe' is registered and passes through; use 'describe_screen' to trigger normalization."""
        result = normalize_intent_action({"action": "describe_screen"})
        assert result["action"] == "read_screen"

    def test_analyze_screen(self):
        result = normalize_intent_action({"action": "analyze_screen"})
        assert result["action"] == "read_screen"

    def test_what_is_on_screen(self):
        result = normalize_intent_action({"action": "what_is_on_screen"})
        assert result["action"] == "read_screen"

    def test_view_dash_screen(self):
        result = normalize_intent_action({"action": "view-screen"})
        assert result["action"] == "read_screen"

    def test_read_screen_action(self):
        result = normalize_intent_action({"action": "read_screen"})
        # read_screen is in ACTION_REGISTRY — passes through unchanged
        assert result["action"] == "read_screen"


# ---------------------------------------------------------------------------
# Fallback to general_interaction
# ---------------------------------------------------------------------------

class TestFallbackToGeneralInteraction:
    def test_unknown_action_becomes_general_interaction(self):
        result = normalize_intent_action({"action": "fly_to_moon"})
        assert result["action"] == "general_interaction"

    def test_original_action_preserved_in_params(self):
        result = normalize_intent_action({"action": "some_weird_action"})
        assert result["parameters"]["original_action"] == "some_weird_action"

    def test_goal_set_from_content(self):
        result = normalize_intent_action({
            "action": "mystery", "content": "Do something cool"
        })
        assert result["parameters"]["goal"] == "Do something cool"

    def test_goal_fallback_to_action_name(self):
        result = normalize_intent_action({"action": "mystery_action"})
        assert result["parameters"]["goal"] == "mystery_action"

    def test_empty_action_becomes_general_interaction(self):
        result = normalize_intent_action({"action": ""})
        assert result["action"] == "general_interaction"

    def test_missing_action_key_becomes_general_interaction(self):
        result = normalize_intent_action({})
        assert result["action"] == "general_interaction"


# ---------------------------------------------------------------------------
# delegate_to_planner flag
# ---------------------------------------------------------------------------

class TestDelegateToPlannerFlag:
    def test_recipient_plus_task_params_sets_delegate(self):
        result = normalize_intent_action({
            "action": "unknown_complex_task",
            "recipient": "Google Maps",
            "parameters": {"destination": "airport"}
        })
        assert result["parameters"].get("delegate_to_planner") is True

    def test_recipient_alone_does_not_set_delegate(self):
        """recipient without extra task params → no delegation."""
        result = normalize_intent_action({
            "action": "unknown_task",
            "recipient": "Some App",
            "parameters": {}
        })
        assert result["parameters"].get("delegate_to_planner") is not True

    def test_no_recipient_no_delegate(self):
        result = normalize_intent_action({"action": "mystery"})
        assert result["parameters"].get("delegate_to_planner") is not True


# ---------------------------------------------------------------------------
# is_valid_action and list_valid_actions helpers
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    def test_tap_is_valid(self):
        assert is_valid_action("tap") is True

    def test_unknown_invalid(self):
        assert is_valid_action("not_a_real_action") is False

    def test_case_insensitive_valid(self):
        assert is_valid_action("TAP") is True

    def test_list_valid_actions_sorted(self):
        actions = list_valid_actions()
        assert actions == sorted(actions)

    def test_list_valid_actions_nonempty(self):
        assert len(list_valid_actions()) > 0

    def test_list_valid_actions_contains_tap(self):
        assert "tap" in list_valid_actions()
