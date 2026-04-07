"""
Unit tests for models/gestures.py.

Tests cover:
- TapAction: valid construction, coordinate validation (ge=0), optional field defaults,
  extra fields forbidden, confidence range, negative x/y rejection
- SwipeAction: valid construction, all coordinate fields required (x1/y1/x2/y2 ge=0),
  duration default, extra fields forbidden
- TypeAction: valid construction, text min_length=1, empty text rejection,
  extra fields forbidden
- LongPressAction: valid construction, coordinate validation, duration default,
  extra fields forbidden

No I/O or external calls are made.
"""

import pytest
from pydantic import ValidationError

from models.gestures import LongPressAction, SwipeAction, TapAction, TypeAction


# ---------------------------------------------------------------------------
# TapAction
# ---------------------------------------------------------------------------

class TestTapActionValid:
    def test_minimal_tap(self):
        t = TapAction(action="tap", x=100, y=200)
        assert t.x == 100
        assert t.y == 200
        assert t.action == "tap"

    def test_click_alias(self):
        t = TapAction(action="click", x=0, y=0)
        assert t.action == "click"

    def test_defaults_applied(self):
        t = TapAction(action="tap", x=50, y=50)
        assert t.format == "pixels"
        assert t.step == 1
        assert t.timeout == 5.0
        assert t.max_retries == 2
        assert t.confidence == 0.0
        assert t.description == ""
        assert t.snapshot_id == ""

    def test_custom_fields(self):
        t = TapAction(
            action="tap", x=300, y=400,
            step=3, timeout=10.0, max_retries=5,
            confidence=0.9, description="tap OK button", snapshot_id="snap_123"
        )
        assert t.step == 3
        assert t.timeout == 10.0
        assert t.max_retries == 5
        assert t.confidence == 0.9
        assert t.description == "tap OK button"
        assert t.snapshot_id == "snap_123"

    def test_zero_coordinates_valid(self):
        t = TapAction(action="tap", x=0, y=0)
        assert t.x == 0 and t.y == 0


class TestTapActionInvalid:
    def test_negative_x_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=-1, y=100)

    def test_negative_y_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=-1)

    def test_invalid_action_literal(self):
        with pytest.raises(ValidationError):
            TapAction(action="swipe", x=100, y=100)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=100, unknown_field="value")

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=100, confidence=1.5)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=100, confidence=-0.1)

    def test_step_zero_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=100, step=0)

    def test_timeout_zero_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100, y=100, timeout=0)

    def test_missing_x_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", y=100)

    def test_missing_y_rejected(self):
        with pytest.raises(ValidationError):
            TapAction(action="tap", x=100)


# ---------------------------------------------------------------------------
# SwipeAction
# ---------------------------------------------------------------------------

class TestSwipeActionValid:
    def test_minimal_swipe(self):
        s = SwipeAction(action="swipe", x1=0, y1=500, x2=0, y2=100)
        assert s.x1 == 0
        assert s.y2 == 100

    def test_scroll_alias(self):
        s = SwipeAction(action="scroll", x1=100, y1=600, x2=100, y2=200)
        assert s.action == "scroll"

    def test_defaults(self):
        s = SwipeAction(action="swipe", x1=10, y1=10, x2=50, y2=50)
        assert s.duration == 300
        assert s.format == "pixels"
        assert s.step == 1
        assert s.timeout == 3.0

    def test_zero_coordinates_valid(self):
        s = SwipeAction(action="swipe", x1=0, y1=0, x2=0, y2=0)
        assert s.x1 == 0


class TestSwipeActionInvalid:
    def test_negative_x1_rejected(self):
        with pytest.raises(ValidationError):
            SwipeAction(action="swipe", x1=-1, y1=0, x2=100, y2=100)

    def test_negative_y2_rejected(self):
        with pytest.raises(ValidationError):
            SwipeAction(action="swipe", x1=0, y1=0, x2=100, y2=-5)

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            SwipeAction(action="tap", x1=0, y1=0, x2=100, y2=100)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            SwipeAction(action="swipe", x1=0, y1=0, x2=100, y2=100, unexpected="oops")

    def test_missing_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            SwipeAction(action="swipe", x1=0, y1=0)  # x2, y2 missing


# ---------------------------------------------------------------------------
# TypeAction
# ---------------------------------------------------------------------------

class TestTypeActionValid:
    def test_type_action(self):
        t = TypeAction(action="type", text="hello world")
        assert t.text == "hello world"

    def test_type_text_alias(self):
        t = TypeAction(action="type_text", text="abc")
        assert t.action == "type_text"

    def test_input_alias(self):
        t = TypeAction(action="input", text="data")
        assert t.action == "input"

    def test_single_character_text(self):
        t = TypeAction(action="type", text="a")
        assert t.text == "a"

    def test_defaults(self):
        t = TypeAction(action="type", text="hello")
        assert t.step == 1
        assert t.timeout == 5.0
        assert t.max_retries == 2


class TestTypeActionInvalid:
    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            TypeAction(action="type", text="")

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            TypeAction(action="tap", text="hello")

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            TypeAction(action="type", text="hello", extra="nope")

    def test_missing_text_rejected(self):
        with pytest.raises(ValidationError):
            TypeAction(action="type")


# ---------------------------------------------------------------------------
# LongPressAction
# ---------------------------------------------------------------------------

class TestLongPressActionValid:
    def test_minimal_long_press(self):
        lp = LongPressAction(action="long_press", x=150, y=300)
        assert lp.x == 150
        assert lp.y == 300

    def test_long_tap_alias(self):
        lp = LongPressAction(action="long_tap", x=100, y=200)
        assert lp.action == "long_tap"

    def test_defaults(self):
        lp = LongPressAction(action="long_press", x=100, y=200)
        assert lp.duration == 1000
        assert lp.format == "pixels"
        assert lp.step == 1
        assert lp.timeout == 5.0
        assert lp.max_retries == 2

    def test_custom_duration(self):
        lp = LongPressAction(action="long_press", x=100, y=200, duration=2000)
        assert lp.duration == 2000

    def test_zero_coordinates_valid(self):
        lp = LongPressAction(action="long_press", x=0, y=0)
        assert lp.x == 0


class TestLongPressActionInvalid:
    def test_negative_x_rejected(self):
        with pytest.raises(ValidationError):
            LongPressAction(action="long_press", x=-10, y=100)

    def test_negative_y_rejected(self):
        with pytest.raises(ValidationError):
            LongPressAction(action="long_press", x=100, y=-5)

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            LongPressAction(action="swipe", x=100, y=100)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            LongPressAction(action="long_press", x=100, y=100, bogus=True)

    def test_missing_x_rejected(self):
        with pytest.raises(ValidationError):
            LongPressAction(action="long_press", y=100)
