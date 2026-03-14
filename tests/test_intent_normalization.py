"""
Test suite for Intent Normalization (Phase 9)

Validates that semantic actions are correctly normalized to canonical form.
"""

import pytest
from services.intent_normalizer import (
    normalize_intent_action,
    is_valid_action,
    list_valid_actions,
)


class TestNormalizeIntentAction:
    """Tests for the main normalization function."""

    def test_open_settings(self):
        """Test: open_settings → open_app (recipient: Settings)"""
        result = normalize_intent_action({
            "action": "open_settings",
            "recipient": None,
            "confidence": 0.92
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Settings"
        assert result["confidence"] == 0.92

    def test_launch_instagram(self):
        """Test: launch_instagram → open_app (recipient: Instagram)"""
        result = normalize_intent_action({
            "action": "launch_instagram",
            "recipient": None,
            "confidence": 0.88
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Instagram"

    def test_start_youtube(self):
        """Test: start_youtube → open_app (recipient: Youtube)"""
        result = normalize_intent_action({
            "action": "start_youtube",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Youtube"

    def test_go_to_spotify(self):
        """Test: go_to_spotify → open_app (recipient: Spotify)"""
        result = normalize_intent_action({
            "action": "go_to_spotify",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Spotify"

    def test_access_gmail(self):
        """Test: access_gmail → open_app (recipient: Gmail)"""
        result = normalize_intent_action({
            "action": "access_gmail",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Gmail"

    def test_use_chrome(self):
        """Test: use_chrome → open_app (recipient: Chrome)"""
        result = normalize_intent_action({
            "action": "use_chrome",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Chrome"

    def test_multi_word_app_names(self):
        """Test: multi-word app names are normalized correctly"""
        # Test with underscores
        result = normalize_intent_action({
            "action": "open_google_play_store",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Google Play Store"

        # Test with hyphens
        result = normalize_intent_action({
            "action": "launch-google-play-store",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Google Play Store"

    def test_canonical_action_unchanged(self):
        """Test: canonical actions pass through unchanged"""
        canonical_actions = [
            "tap",
            "swipe",
            "scroll",
            "long_press",
            "send_message",
            "make_call",
            "greeting",
        ]

        for action in canonical_actions:
            result = normalize_intent_action({
                "action": action,
                "recipient": None,
            })
            assert result["action"] == action

    def test_case_insensitive(self):
        """Test: normalization is case-insensitive"""
        variants = [
            "OPEN_SETTINGS",
            "Open_Settings",
            "opeN_settingS",
            "LAUNCH_INSTAGRAM",
        ]

        for action in variants:
            result = normalize_intent_action({
                "action": action,
                "recipient": None,
            })
            assert result["action"] == "open_app"

    def test_whitespace_handling(self):
        """Test: extra whitespace is handled correctly"""
        result = normalize_intent_action({
            "action": "  open_settings  ",
            "recipient": None,
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "Settings"

    def test_unknown_action_fallback(self):
        """Test: unknown actions gracefully fallback to general_interaction"""
        result = normalize_intent_action({
            "action": "foobar",
            "recipient": None,
        })
        assert result["action"] == "general_interaction"
        assert result["parameters"]["original_action"] == "foobar"

    def test_empty_action_fallback(self):
        """Test: empty action falls back to general_interaction"""
        result = normalize_intent_action({
            "action": "",
            "recipient": None,
        })
        assert result["action"] == "general_interaction"

    def test_missing_action_fallback(self):
        """Test: missing action field falls back to general_interaction"""
        result = normalize_intent_action({
            "recipient": None,
        })
        assert result["action"] == "general_interaction"

    def test_recipient_preserved_if_set(self):
        """Test: existing recipient is not overridden"""
        result = normalize_intent_action({
            "action": "open_settings",
            "recipient": "MyCustomApp",  # Already set by LLM
        })
        assert result["action"] == "open_app"
        assert result["recipient"] == "MyCustomApp"  # Preserved

    def test_all_fields_preserved(self):
        """Test: all original fields are preserved"""
        intent = {
            "action": "launch_instagram",
            "recipient": None,
            "content": "some content",
            "parameters": {"key": "value"},
            "confidence": 0.85,
            "custom_field": "custom_value",
        }

        result = normalize_intent_action(intent)

        # Action normalized
        assert result["action"] == "open_app"

        # Recipient updated
        assert result["recipient"] == "Instagram"

        # All other fields preserved
        assert result["content"] == "some content"
        assert result["parameters"] == {"key": "value"}
        assert result["confidence"] == 0.85
        assert result["custom_field"] == "custom_value"


class TestValidActionCheck:
    """Tests for is_valid_action() function."""

    def test_valid_actions_recognized(self):
        """Test: valid actions from ACTION_REGISTRY are recognized"""
        valid = [
            "tap",
            "swipe",
            "scroll",
            "open_app",
            "send_message",
            "greeting",
            "play_song",  # app-specific action in registry
        ]
        for action in valid:
            assert is_valid_action(action) is True

    def test_non_registry_actions_rejected(self):
        """Test: actions not in registry are rejected"""
        non_valid = [
            "open_settings",  # semantic variant, not in registry
            "launch_instagram",
            "foobar",
        ]
        for action in non_valid:
            assert is_valid_action(action) is False

    def test_case_insensitive_check(self):
        """Test: check is case-insensitive"""
        assert is_valid_action("TAP") is True
        assert is_valid_action("Tap") is True
        assert is_valid_action("OPEN_APP") is True


class TestAppNameNormalization:
    """Tests for app name normalization via open_* patterns."""

    def test_single_word_apps(self):
        """Test: single-word app names are title-cased"""
        test_cases = [
            ("open_settings", "Settings"),
            ("open_instagram", "Instagram"),
            ("open_youtube", "Youtube"),
            ("open_spotify", "Spotify"),
            ("open_gmail", "Gmail"),
        ]
        for action, expected in test_cases:
            result = normalize_intent_action({"action": action, "recipient": None})
            assert result["recipient"] == expected

    def test_underscore_separated_apps(self):
        """Test: underscore-separated names become space-separated"""
        test_cases = [
            ("open_google_play_store", "Google Play Store"),
            ("open_google_maps", "Google Maps"),
        ]
        for action, expected in test_cases:
            result = normalize_intent_action({"action": action, "recipient": None})
            assert result["recipient"] == expected

    def test_hyphen_separated_apps(self):
        """Test: hyphen-separated names become space-separated"""
        test_cases = [
            ("open-google-play-store", "Google Play Store"),
            ("open-google-maps", "Google Maps"),
        ]
        for action, expected in test_cases:
            result = normalize_intent_action({"action": action, "recipient": None})
            assert result["recipient"] == expected


class TestValidActionsList:
    """Tests for list_valid_actions() function."""

    def test_returns_sorted_list(self):
        """Test: returns a sorted list of valid actions from ACTION_REGISTRY"""
        actions = list_valid_actions()
        assert isinstance(actions, list)
        assert len(actions) > 50  # ACTION_REGISTRY has 100+ actions
        assert actions == sorted(actions)

    def test_includes_key_actions(self):
        """Test: list includes all key actions"""
        actions = list_valid_actions()
        required = [
            "tap",
            "swipe",
            "open_app",
            "send_message",
            "greeting",
            "play_song",  # app-specific
            "wifi_on",    # system toggle
        ]
        for action in required:
            assert action in actions


class TestRealWorldScenarios:
    """Tests for real-world command scenarios."""

    def test_open_settings_flow(self):
        """Test: 'open settings' command normalized correctly"""
        # Simulates: User says "open settings"
        # → LLM parses to "open_settings"
        # → Normalizer converts to canonical "open_app"
        intent = {
            "action": "open_settings",
            "recipient": None,
            "confidence": 0.92,
        }
        result = normalize_intent_action(intent)

        assert result["action"] == "open_app"
        assert result["recipient"] == "Settings"
        # Routing would then decide: action="open_app" → parallel_processing

    def test_wifi_toggle_flow(self):
        """Test: 'turn on wifi' command (already canonical)"""
        # LLM might produce: "wifi_on" (already canonical)
        # Normalizer should pass through
        intent = {
            "action": "wifi_on",
            "recipient": None,
        }
        result = normalize_intent_action(intent)

        assert result["action"] == "wifi_on"
        # Routing would then decide: action="wifi_on" → execute

    def test_tap_gesture_flow(self):
        """Test: 'tap the blue button' command (already canonical)"""
        # LLM produces: "tap" with target description
        # Normalizer passes through
        intent = {
            "action": "tap",
            "recipient": None,
            "parameters": {"target": "blue button"},
        }
        result = normalize_intent_action(intent)

        assert result["action"] == "tap"
        assert result["parameters"]["target"] == "blue button"
        # Routing would then decide: action="tap" → parallel_processing

    def test_multi_app_normalization(self):
        """Test: normalization works for multiple different apps"""
        test_cases = [
            ("open_settings", "Settings"),
            ("launch_instagram", "Instagram"),
            ("start_youtube", "Youtube"),
            ("go_to_whatsapp", "Whatsapp"),
            ("access_telegram", "Telegram"),
            ("use_tiktok", "Tiktok"),
        ]

        for action, expected_app in test_cases:
            result = normalize_intent_action({
                "action": action,
                "recipient": None,
            })
            assert result["action"] == "open_app"
            assert result["recipient"] == expected_app


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
