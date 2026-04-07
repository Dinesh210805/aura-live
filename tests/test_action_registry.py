"""
Unit tests for config/action_types.py.

Tests cover:
- ActionMeta dataclass: frozen, field defaults, field semantics
- ACTION_REGISTRY: key membership, metadata correctness for representative actions
- Auto-generated list consistency: VISUAL_ACTIONS, DANGEROUS_ACTIONS, etc.
- Helper functions: get_action_meta, needs_perception, needs_coordinates,
  needs_ui_analysis, is_dangerous, is_conversational, is_valid_action,
  get_required_fields, opens_settings_panel
"""

import pytest

from config.action_types import (
    ACTION_REGISTRY,
    CONVERSATIONAL_ACTIONS,
    COORDINATE_REQUIRING_ACTIONS,
    DANGEROUS_ACTIONS,
    NO_UI_ACTIONS,
    VALID_ACTIONS,
    VISUAL_ACTIONS,
    ActionMeta,
    get_action_meta,
    get_required_fields,
    is_conversational,
    is_dangerous,
    is_valid_action,
    needs_coordinates,
    needs_perception,
    needs_ui_analysis,
    opens_settings_panel,
)


# ---------------------------------------------------------------------------
# ActionMeta dataclass
# ---------------------------------------------------------------------------

class TestActionMetaDefaults:
    def test_all_fields_default_false(self):
        meta = ActionMeta()
        assert meta.needs_ui is False
        assert meta.needs_coords is False
        assert meta.needs_perception is False
        assert meta.is_dangerous is False
        assert meta.is_conversational is False
        assert meta.opens_panel is False

    def test_required_fields_default_empty_tuple(self):
        meta = ActionMeta()
        assert meta.required_fields == ()

    def test_frozen_immutable(self):
        meta = ActionMeta(needs_ui=True)
        with pytest.raises((AttributeError, TypeError)):
            meta.needs_ui = False  # type: ignore[misc]

    def test_custom_values_stored(self):
        meta = ActionMeta(
            needs_ui=True, needs_coords=True, needs_perception=True, is_dangerous=True
        )
        assert meta.needs_ui is True
        assert meta.needs_coords is True
        assert meta.needs_perception is True
        assert meta.is_dangerous is True

    def test_required_fields_as_tuple(self):
        meta = ActionMeta(required_fields=("recipient", "content"))
        assert meta.required_fields == ("recipient", "content")


# ---------------------------------------------------------------------------
# ACTION_REGISTRY membership
# ---------------------------------------------------------------------------

class TestActionRegistryMembership:
    """Spot-check that critical actions are registered."""

    @pytest.mark.parametrize("action", [
        "tap", "click", "swipe", "long_press", "type",
        "scroll", "open_app", "send_message", "make_call",
        "volume_up", "volume_down", "back", "home",
        "screenshot", "take_screenshot",
        "delete", "factory_reset",
        "greeting", "help",
        "wifi_on", "wifi_off", "toggle_wifi",
        "bluetooth_on", "bluetooth_off",
    ])
    def test_action_is_registered(self, action):
        assert action in ACTION_REGISTRY

    def test_unknown_action_not_in_registry(self):
        assert "fly_to_mars" not in ACTION_REGISTRY


# ---------------------------------------------------------------------------
# ACTION_REGISTRY metadata correctness
# ---------------------------------------------------------------------------

class TestActionRegistryMetadata:
    def test_tap_needs_ui_coords_perception(self):
        meta = ACTION_REGISTRY["tap"]
        assert meta.needs_ui is True
        assert meta.needs_coords is True
        assert meta.needs_perception is True

    def test_scroll_no_ui_no_coords_but_needs_perception(self):
        meta = ACTION_REGISTRY["scroll"]
        assert meta.needs_ui is False
        assert meta.needs_coords is False
        assert meta.needs_perception is True

    def test_open_app_has_required_field_recipient(self):
        assert "recipient" in ACTION_REGISTRY["open_app"].required_fields

    def test_send_message_requires_recipient_and_content(self):
        meta = ACTION_REGISTRY["send_message"]
        assert "recipient" in meta.required_fields
        assert "content" in meta.required_fields

    def test_wifi_on_opens_panel(self):
        assert ACTION_REGISTRY["wifi_on"].opens_panel is True

    def test_volume_up_no_panel(self):
        assert ACTION_REGISTRY["volume_up"].opens_panel is False

    def test_delete_is_dangerous(self):
        assert ACTION_REGISTRY["delete"].is_dangerous is True

    def test_greeting_is_conversational(self):
        assert ACTION_REGISTRY["greeting"].is_conversational is True

    def test_greeting_not_dangerous(self):
        assert ACTION_REGISTRY["greeting"].is_dangerous is False

    def test_type_needs_ui_and_perception_but_not_coords(self):
        meta = ACTION_REGISTRY["type"]
        assert meta.needs_ui is True
        assert meta.needs_perception is True
        assert meta.needs_coords is False


# ---------------------------------------------------------------------------
# Auto-generated lists are consistent with registry
# ---------------------------------------------------------------------------

class TestAutoGeneratedLists:
    def test_valid_actions_covers_all_registry_keys(self):
        assert set(VALID_ACTIONS) == set(ACTION_REGISTRY.keys())

    def test_visual_actions_all_have_needs_ui(self):
        for action in VISUAL_ACTIONS:
            assert ACTION_REGISTRY[action].needs_ui is True, (
                f"{action} is in VISUAL_ACTIONS but needs_ui=False"
            )

    def test_coordinate_requiring_actions_all_have_needs_coords(self):
        for action in COORDINATE_REQUIRING_ACTIONS:
            assert ACTION_REGISTRY[action].needs_coords is True

    def test_dangerous_actions_all_have_is_dangerous(self):
        for action in DANGEROUS_ACTIONS:
            assert ACTION_REGISTRY[action].is_dangerous is True

    def test_conversational_actions_all_have_is_conversational(self):
        for action in CONVERSATIONAL_ACTIONS:
            assert ACTION_REGISTRY[action].is_conversational is True

    def test_tap_in_visual_actions(self):
        assert "tap" in VISUAL_ACTIONS

    def test_greeting_in_conversational_actions(self):
        assert "greeting" in CONVERSATIONAL_ACTIONS

    def test_delete_in_dangerous_actions(self):
        assert "delete" in DANGEROUS_ACTIONS

    def test_no_ui_actions_have_no_ui_no_perception(self):
        for action in NO_UI_ACTIONS:
            meta = ACTION_REGISTRY[action]
            assert meta.needs_ui is False
            assert meta.needs_perception is False
            assert meta.is_conversational is False


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestGetActionMeta:
    def test_known_action_returns_meta(self):
        meta = get_action_meta("tap")
        assert isinstance(meta, ActionMeta)
        assert meta.needs_ui is True

    def test_unknown_action_returns_none(self):
        assert get_action_meta("unknown_xyz") is None


class TestNeedsPerception:
    def test_tap_needs_perception(self):
        assert needs_perception("tap") is True

    def test_back_does_not_need_perception(self):
        assert needs_perception("back") is False

    def test_unknown_action_does_not_need_perception(self):
        assert needs_perception("nonexistent") is False


class TestNeedsCoordinates:
    def test_tap_needs_coordinates(self):
        assert needs_coordinates("tap") is True

    def test_scroll_does_not_need_coordinates(self):
        assert needs_coordinates("scroll") is False

    def test_unknown_action_does_not_need_coordinates(self):
        assert needs_coordinates("nonexistent") is False


class TestNeedsUiAnalysis:
    def test_tap_needs_ui(self):
        assert needs_ui_analysis("tap") is True

    def test_home_does_not_need_ui(self):
        assert needs_ui_analysis("home") is False


class TestIsDangerous:
    def test_delete_is_dangerous(self):
        assert is_dangerous("delete") is True

    def test_tap_is_not_dangerous(self):
        assert is_dangerous("tap") is False

    def test_unknown_action_not_dangerous(self):
        assert is_dangerous("nonexistent") is False


class TestIsConversational:
    def test_greeting_is_conversational(self):
        assert is_conversational("greeting") is True

    def test_tap_not_conversational(self):
        assert is_conversational("tap") is False


class TestIsValidAction:
    def test_known_action_is_valid(self):
        assert is_valid_action("tap") is True

    def test_unknown_action_invalid(self):
        assert is_valid_action("foo_bar_baz") is False


class TestGetRequiredFields:
    def test_send_message_has_required_fields(self):
        fields = get_required_fields("send_message")
        assert "recipient" in fields
        assert "content" in fields

    def test_tap_has_no_required_fields(self):
        assert get_required_fields("tap") == []

    def test_unknown_action_empty_required_fields(self):
        assert get_required_fields("nonexistent") == []


class TestOpensSettingsPanel:
    def test_wifi_on_opens_panel(self):
        assert opens_settings_panel("wifi_on") is True

    def test_bluetooth_off_opens_panel(self):
        assert opens_settings_panel("bluetooth_off") is True

    def test_volume_up_does_not_open_panel(self):
        assert opens_settings_panel("volume_up") is False

    def test_unknown_action_does_not_open_panel(self):
        assert opens_settings_panel("nonexistent") is False
