"""
Unit tests for perception/validators.py — detect_permission_dialog().

Tests cover:
- None input → (False, None)
- Empty elements list → (False, None)
- System package + matching permission text → (True, dialog_type)
- System package alone (no matching text) → (False, None)
- Matching permission text alone (no system package) → (False, None)
- screen_capture dialog type detection (cast/record indicators)
- overlay dialog type detection (draw over other apps)
- unknown_system dialog type fallback
- Case insensitivity of text matching

UITreePayload is constructed directly (no mocking needed).
"""

import pytest

from perception.models import UITreePayload
from perception.validators import detect_permission_dialog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _elem(package: str = "", text: str = "", content_desc: str = ""):
    return {
        "packageName": package,
        "text": text,
        "contentDescription": content_desc,
        "clickable": False,
    }


def _tree(*elements) -> UITreePayload:
    return UITreePayload(elements=list(elements), screen_width=1080, screen_height=2400, timestamp=0)


# ---------------------------------------------------------------------------
# Null / empty cases
# ---------------------------------------------------------------------------

class TestNullAndEmpty:
    def test_none_input_returns_false_none(self):
        is_dialog, dialog_type = detect_permission_dialog(None)
        assert is_dialog is False
        assert dialog_type is None

    def test_empty_elements_returns_false_none(self):
        tree = _tree()
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is False
        assert dialog_type is None


# ---------------------------------------------------------------------------
# System package requirement
# ---------------------------------------------------------------------------

class TestSystemPackageRequirement:
    def test_system_package_alone_not_detected(self):
        """System package without permission text should NOT fire."""
        tree = _tree(_elem(package="com.android.systemui", text="Normal status bar"))
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is False

    def test_permission_text_alone_not_detected(self):
        """Permission text without system package should NOT fire."""
        tree = _tree(_elem(package="com.example.myapp", text="Cast your screen?"))
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is False

    def test_both_required_for_detection(self):
        """Both system package AND permission text needed."""
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Cast your screen?"),
        )
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is True


# ---------------------------------------------------------------------------
# dialog_type: screen_capture
# ---------------------------------------------------------------------------

class TestScreenCaptureType:
    def test_cast_your_screen(self):
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Cast your screen?"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "screen_capture"

    def test_screen_capture_text(self):
        tree = _tree(
            _elem(package="com.android.permissioncontroller"),
            _elem(text="Screen capture"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "screen_capture"

    def test_record_screen_text(self):
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Record screen"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "screen_capture"

    def test_start_now_button_with_system_package(self):
        """'start now' alone maps to unknown_system since it's not in screen_capture list."""
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Start now"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "unknown_system"


# ---------------------------------------------------------------------------
# dialog_type: overlay
# ---------------------------------------------------------------------------

class TestOverlayType:
    def test_draw_over_other_apps(self):
        tree = _tree(
            _elem(package="com.android.permissioncontroller"),
            _elem(text="Draw over other apps"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "overlay"

    def test_allow_display_over_other_apps(self):
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Allow display over other apps"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "overlay"


# ---------------------------------------------------------------------------
# dialog_type: unknown_system
# ---------------------------------------------------------------------------

class TestUnknownSystemType:
    def test_sensitive_information_text(self):
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="Sensitive information"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "unknown_system"

    def test_will_be_able_to_see_everything(self):
        tree = _tree(
            _elem(package="android"),
            _elem(text="will be able to see everything"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "unknown_system"


# ---------------------------------------------------------------------------
# contentDescription fallback
# ---------------------------------------------------------------------------

class TestContentDescriptionMatching:
    def test_permission_text_in_content_desc(self):
        """Text can be in contentDescription instead of text field."""
        tree = _tree(
            _elem(package="com.android.systemui"),
            _elem(text="", content_desc="Cast your screen?"),
        )
        is_dialog, dialog_type = detect_permission_dialog(tree)
        assert is_dialog is True
        assert dialog_type == "screen_capture"


# ---------------------------------------------------------------------------
# Known system packages
# ---------------------------------------------------------------------------

class TestKnownSystemPackages:
    @pytest.mark.parametrize("pkg", [
        "com.android.systemui",
        "com.android.permissioncontroller",
        "com.google.android.permissioncontroller",
        "android",
    ])
    def test_all_system_packages_recognized(self, pkg):
        tree = _tree(
            _elem(package=pkg),
            _elem(text="Record or cast"),
        )
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is True


# ---------------------------------------------------------------------------
# Normal screen detection
# ---------------------------------------------------------------------------

class TestNormalScreenNotDetected:
    def test_regular_app_not_detected(self):
        tree = _tree(
            _elem(package="com.spotify.music", text="Now Playing"),
            _elem(package="com.spotify.music", text="Like"),
        )
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is False

    def test_system_settings_non_permission_not_detected(self):
        tree = _tree(
            _elem(package="com.android.settings", text="Wi-Fi"),
            _elem(package="com.android.settings", text="Bluetooth"),
        )
        is_dialog, _ = detect_permission_dialog(tree)
        assert is_dialog is False
