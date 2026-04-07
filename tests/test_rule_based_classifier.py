"""
Unit tests for utils/rule_based_classifier.py.

Tests cover:
- WiFi on/off/toggle
- Bluetooth on/off
- DND (Do Not Disturb) on/off/toggle
- Airplane mode on/off
- Location/GPS on/off
- Brightness up/down
- Volume up/down/mute
- Navigation: back, home, scroll up/down
- Screenshot
- Multi-action deferral returns None
- enable/disable → on/off state extraction
- _build_intent structure: action, recipient=None, content=None, parameters, confidence

No I/O or LLM calls — purely regex matching.
"""

import pytest

from utils.rule_based_classifier import RuleBasedClassifier


@pytest.fixture()
def clf():
    return RuleBasedClassifier()


# ---------------------------------------------------------------------------
# WiFi
# ---------------------------------------------------------------------------

class TestWifi:
    def test_turn_on_wifi(self, clf):
        result = clf.classify("turn on wifi")
        assert result["action"] == "wifi_on"
        assert result["parameters"]["state"] == "on"

    def test_turn_off_wifi(self, clf):
        result = clf.classify("turn off wifi")
        assert result["action"] == "wifi_off"
        assert result["parameters"]["state"] == "off"

    def test_enable_wifi(self, clf):
        result = clf.classify("enable wifi")
        assert result["action"] == "wifi_on"

    def test_disable_wifi(self, clf):
        result = clf.classify("disable wifi")
        assert result["action"] == "wifi_off"

    def test_toggle_wifi_no_state(self, clf):
        result = clf.classify("toggle wifi")
        assert result["action"] == "toggle_wifi"

    def test_wi_fi_hyphenated(self, clf):
        result = clf.classify("turn on wi-fi")
        assert result["action"] == "wifi_on"


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------

class TestBluetooth:
    def test_turn_on_bluetooth(self, clf):
        result = clf.classify("turn on bluetooth")
        assert result["action"] == "bluetooth_on"

    def test_turn_off_bluetooth(self, clf):
        result = clf.classify("turn off bluetooth")
        assert result["action"] == "bluetooth_off"

    def test_enable_bluetooth(self, clf):
        result = clf.classify("enable bluetooth")
        assert result["action"] == "bluetooth_on"

    def test_disable_bluetooth(self, clf):
        result = clf.classify("disable bluetooth")
        assert result["action"] == "bluetooth_off"


# ---------------------------------------------------------------------------
# DND / Do Not Disturb
# ---------------------------------------------------------------------------

class TestDnd:
    def test_turn_on_dnd(self, clf):
        result = clf.classify("turn on do not disturb")
        assert result["action"] == "dnd_on"

    def test_turn_off_dnd(self, clf):
        result = clf.classify("turn off dnd")
        assert result["action"] == "dnd_off"

    def test_enable_dnd(self, clf):
        result = clf.classify("enable dnd")
        assert result["action"] == "dnd_on"

    def test_silence_notifications(self, clf):
        result = clf.classify("silence notifications")
        assert result is not None
        assert "dnd" in result["action"] or result["action"] in {"dnd_on", "dnd_off", "toggle_dnd"}


# ---------------------------------------------------------------------------
# Airplane Mode
# ---------------------------------------------------------------------------

class TestAirplaneMode:
    def test_turn_on_airplane_mode(self, clf):
        result = clf.classify("turn on airplane mode")
        assert result["action"] == "airplane_mode_on"

    def test_turn_off_airplane_mode(self, clf):
        result = clf.classify("turn off airplane mode")
        assert result["action"] == "airplane_mode_off"

    def test_enable_flight_mode(self, clf):
        result = clf.classify("enable flight mode")
        assert result["action"] == "airplane_mode_on"


# ---------------------------------------------------------------------------
# Location / GPS
# ---------------------------------------------------------------------------

class TestLocation:
    def test_turn_on_location(self, clf):
        result = clf.classify("turn on location")
        assert result["action"] == "location_on"

    def test_turn_off_gps(self, clf):
        result = clf.classify("turn off gps")
        assert result["action"] == "location_off"

    def test_enable_location(self, clf):
        result = clf.classify("enable location")
        assert result["action"] == "location_on"

    def test_disable_gps(self, clf):
        result = clf.classify("disable gps")
        assert result["action"] == "location_off"


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------

class TestBrightness:
    def test_brightness_up(self, clf):
        result = clf.classify("brightness up")
        assert result["action"] == "brightness_up"

    def test_increase_brightness(self, clf):
        result = clf.classify("increase the brightness")
        assert result["action"] == "brightness_up"

    def test_brightness_down(self, clf):
        result = clf.classify("brightness down")
        assert result["action"] == "brightness_down"

    def test_decrease_brightness(self, clf):
        result = clf.classify("decrease the brightness")
        assert result["action"] == "brightness_down"

    def test_make_screen_brighter(self, clf):
        result = clf.classify("make the screen brighter")
        assert result["action"] == "brightness_up"

    def test_dim_screen(self, clf):
        result = clf.classify("dim the screen")
        assert result["action"] == "brightness_down"


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

class TestVolume:
    def test_volume_up(self, clf):
        result = clf.classify("volume up")
        assert result["action"] == "volume_up"

    def test_increase_volume(self, clf):
        result = clf.classify("increase the volume")
        assert result["action"] == "volume_up"

    def test_volume_down(self, clf):
        result = clf.classify("volume down")
        assert result["action"] == "volume_down"

    def test_lower_volume(self, clf):
        result = clf.classify("lower the volume")
        assert result["action"] == "volume_down"

    def test_mute(self, clf):
        result = clf.classify("mute")
        assert result["action"] == "mute"

    def test_silent(self, clf):
        result = clf.classify("silent")
        assert result["action"] == "mute"

    def test_louder(self, clf):
        result = clf.classify("louder")
        assert result["action"] == "volume_up"

    def test_quieter(self, clf):
        result = clf.classify("quieter")
        assert result["action"] == "volume_down"


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_go_back(self, clf):
        result = clf.classify("go back")
        assert result["action"] == "back"

    def test_press_back(self, clf):
        result = clf.classify("press back")
        assert result["action"] == "back"

    def test_back_standalone(self, clf):
        result = clf.classify("back")
        assert result["action"] == "back"

    def test_go_home(self, clf):
        result = clf.classify("go to home")
        assert result["action"] == "home"

    def test_home_standalone(self, clf):
        result = clf.classify("home")
        assert result["action"] == "home"

    def test_home_screen(self, clf):
        result = clf.classify("home screen")
        assert result["action"] == "home"

    def test_scroll_up(self, clf):
        result = clf.classify("scroll up")
        assert result["action"] == "scroll"
        assert result["parameters"]["direction"] == "up"

    def test_scroll_down(self, clf):
        result = clf.classify("scroll down")
        assert result["action"] == "scroll"
        assert result["parameters"]["direction"] == "down"

    def test_swipe_up(self, clf):
        result = clf.classify("swipe up")
        assert result["action"] == "scroll"

    def test_swipe_down(self, clf):
        result = clf.classify("swipe down")
        assert result["action"] == "scroll"


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

class TestScreenshot:
    def test_take_a_screenshot(self, clf):
        result = clf.classify("take a screenshot")
        assert result["action"] == "take_screenshot"

    def test_capture_screen(self, clf):
        result = clf.classify("capture the screen")
        assert result["action"] == "take_screenshot"

    def test_screenshot_word(self, clf):
        result = clf.classify("screenshot")
        assert result["action"] == "take_screenshot"


# ---------------------------------------------------------------------------
# Multi-action deferral
# ---------------------------------------------------------------------------

class TestMultiActionDeferral:
    def test_and_then_returns_none(self, clf):
        assert clf.classify("turn on wifi and then open camera") is None

    def test_then_connector_returns_none(self, clf):
        assert clf.classify("go back then scroll down") is None

    def test_comma_returns_none(self, clf):
        assert clf.classify("turn off wifi, turn on bluetooth") is None

    def test_single_action_not_deferred(self, clf):
        """Pure single actions should still be classified normally."""
        result = clf.classify("turn on wifi")
        assert result is not None

    def test_and_alone_defers(self, clf):
        assert clf.classify("scroll up and scroll down") is None


# ---------------------------------------------------------------------------
# Unknown commands return None
# ---------------------------------------------------------------------------

class TestUnknownCommands:
    def test_open_camera_returns_none(self, clf):
        """App open commands are not in rule-based classifier scope."""
        assert clf.classify("open camera app") is None

    def test_send_message_returns_none(self, clf):
        assert clf.classify("send a message to mom") is None

    def test_gibberish_returns_none(self, clf):
        assert clf.classify("xyzzy frobble wumpus") is None


# ---------------------------------------------------------------------------
# _build_intent structure
# ---------------------------------------------------------------------------

class TestIntentStructure:
    def test_has_all_required_fields(self, clf):
        result = clf.classify("turn on wifi")
        assert "action" in result
        assert "recipient" in result
        assert "content" in result
        assert "parameters" in result
        assert "confidence" in result

    def test_recipient_is_none(self, clf):
        result = clf.classify("mute")
        assert result["recipient"] is None

    def test_content_is_none(self, clf):
        result = clf.classify("mute")
        assert result["content"] is None

    def test_confidence_is_high(self, clf):
        result = clf.classify("volume up")
        assert result["confidence"] == 0.95

    def test_classifier_metadata_in_parameters(self, clf):
        result = clf.classify("scroll up")
        assert result["parameters"]["classifier"] == "rule_based"
        assert "original_transcript" in result["parameters"]

    def test_original_transcript_preserved(self, clf):
        transcript = "Turn On WiFi please"
        result = clf.classify(transcript)
        assert result["parameters"]["original_transcript"] == transcript


# ---------------------------------------------------------------------------
# _extract_state: enable/disable synonym mapping
# ---------------------------------------------------------------------------

class TestExtractState:
    def test_enable_maps_to_on(self, clf):
        result = clf.classify("enable wifi")
        assert result["parameters"]["state"] == "on"

    def test_disable_maps_to_off(self, clf):
        result = clf.classify("disable wifi")
        assert result["parameters"]["state"] == "off"

    def test_explicit_on_takes_precedence(self, clf):
        result = clf.classify("turn wifi on")
        assert result["parameters"]["state"] == "on"

    def test_explicit_off_takes_precedence(self, clf):
        result = clf.classify("switch wifi off")
        assert result["parameters"]["state"] == "off"

    def test_toggle_no_state(self, clf):
        """Toggle without on/off or enable/disable → state is None → action is toggle_xxx."""
        result = clf.classify("toggle wifi")
        assert result["action"] == "toggle_wifi"
        assert result["parameters"].get("state") is None
