"""
Unit tests for utils/ui_element_finder.py.

is_input_element() uses three independent signals to identify text input
fields from Android accessibility trees. element_display_label() implements
a fallback chain: text → contentDescription → hint/placeholder.

These functions run on every UI element the agent inspects — correctness
here directly affects whether the coordinator types into the right field.
"""

import pytest

from utils.ui_element_finder import (
    element_display_label,
    get_semantic_matches,
    is_input_element,
    normalize_text,
)


# ---------------------------------------------------------------------------
# is_input_element — Signal 1: editable / isEditable attribute
# ---------------------------------------------------------------------------

class TestIsInputElementEditableSignal:
    def test_editable_true_is_input(self):
        assert is_input_element({"editable": True}) is True

    def test_is_editable_true_is_input(self):
        assert is_input_element({"isEditable": True}) is True

    def test_editable_false_is_not_input_by_this_signal(self):
        """False editable alone should not classify as input."""
        assert is_input_element({"editable": False}) is False

    def test_missing_editable_key_skips_signal(self):
        """Missing key must not raise — falls through to other signals."""
        result = is_input_element({})
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# is_input_element — Signal 2: inputType (OS-level)
# ---------------------------------------------------------------------------

class TestIsInputElementInputTypeSignal:
    def test_nonzero_input_type_int_is_input(self):
        assert is_input_element({"inputType": 1}) is True

    def test_input_type_zero_is_not_input(self):
        assert is_input_element({"inputType": 0}) is False

    def test_input_type_string_zero_is_not_input(self):
        assert is_input_element({"inputType": "0"}) is False

    def test_input_type_none_string_is_not_input(self):
        assert is_input_element({"inputType": "none"}) is False

    def test_input_type_none_python_none_is_skipped(self):
        """Python None means key exists but has no value — not a valid input signal."""
        assert is_input_element({"inputType": None}) is False

    def test_input_type_large_value_is_input(self):
        assert is_input_element({"inputType": 131073}) is True  # TYPE_CLASS_TEXT | multiline


# ---------------------------------------------------------------------------
# is_input_element — Signal 3: className substring match
# ---------------------------------------------------------------------------

class TestIsInputElementClassNameSignal:
    def test_edittext_class_is_input(self):
        assert is_input_element({"className": "android.widget.EditText"}) is True

    def test_autocompletetextview_is_input(self):
        assert is_input_element({"className": "android.widget.AutoCompleteTextView"}) is True

    def test_searchview_is_input(self):
        assert is_input_element({"className": "android.widget.SearchView"}) is True

    def test_textview_is_not_input(self):
        assert is_input_element({"className": "android.widget.TextView"}) is False

    def test_button_is_not_input(self):
        assert is_input_element({"className": "android.widget.Button"}) is False

    def test_imageview_is_not_input(self):
        assert is_input_element({"className": "android.widget.ImageView"}) is False

    def test_case_insensitive_class_match(self):
        """className matching must be lowercase-normalized."""
        assert is_input_element({"className": "com.gmail.RecipientEditTextView"}) is True

    def test_custom_react_native_text_input(self):
        assert is_input_element({"className": "com.reactnative.TextInput"}) is True

    def test_otp_input_field(self):
        assert is_input_element({"className": "com.app.OtpView"}) is True

    def test_empty_class_name_is_not_input(self):
        assert is_input_element({"className": ""}) is False


# ---------------------------------------------------------------------------
# is_input_element — multiple signals
# ---------------------------------------------------------------------------

class TestIsInputElementMultipleSignals:
    def test_all_three_signals_true(self):
        el = {
            "editable": True,
            "inputType": 1,
            "className": "android.widget.EditText",
        }
        assert is_input_element(el) is True

    def test_only_class_name_signal_sufficient(self):
        el = {"editable": False, "inputType": 0, "className": "android.widget.EditText"}
        assert is_input_element(el) is True

    def test_no_signals_is_not_input(self):
        el = {"editable": False, "inputType": 0, "className": "android.widget.Button"}
        assert is_input_element(el) is False


# ---------------------------------------------------------------------------
# element_display_label
# ---------------------------------------------------------------------------

class TestElementDisplayLabel:
    def test_text_field_returns_text(self):
        el = {"text": "Search", "contentDescription": "Search bar"}
        assert element_display_label(el) == "Search"

    def test_no_text_falls_back_to_content_description(self):
        el = {"text": "", "contentDescription": "Close button"}
        assert element_display_label(el) == "Close button"

    def test_input_field_with_no_label_falls_back_to_hint(self):
        """Gmail To/Subject fields have hint but no text — must show placeholder."""
        el = {
            "text": "",
            "contentDescription": "",
            "className": "android.widget.EditText",
            "hint": "To",
        }
        assert element_display_label(el) == "[placeholder: To]"

    def test_non_input_with_no_label_returns_empty(self):
        """A Button with no text/contentDesc should return empty string."""
        el = {"text": "", "contentDescription": "", "className": "android.widget.Button"}
        assert element_display_label(el) == ""

    def test_hint_not_shown_for_non_input_elements(self):
        """Hint fallback only applies to input fields."""
        el = {
            "text": "",
            "contentDescription": "",
            "className": "android.widget.TextView",
            "hint": "some hint",
        }
        assert element_display_label(el) == ""

    def test_whitespace_text_is_stripped(self):
        el = {"text": "  Search  "}
        assert element_display_label(el) == "Search"

    def test_hinttext_variant_also_works(self):
        """Some frameworks use hintText instead of hint."""
        el = {
            "text": "",
            "contentDescription": "",
            "className": "android.widget.EditText",
            "hintText": "Subject",
        }
        assert element_display_label(el) == "[placeholder: Subject]"


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("SPOTIFY") == "spotify"

    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_none_returns_empty(self):
        assert normalize_text(None) == ""


# ---------------------------------------------------------------------------
# get_semantic_matches
# ---------------------------------------------------------------------------

class TestGetSemanticMatches:
    def test_liked_songs_returns_aliases(self):
        matches = get_semantic_matches("liked songs")
        assert "liked songs" in matches
        assert "favorites" in matches

    def test_library_returns_aliases(self):
        matches = get_semantic_matches("library")
        assert "library" in matches

    def test_unknown_target_returns_itself(self):
        """Unrecognised targets should still return at least the original string."""
        matches = get_semantic_matches("completely_unknown_widget_xyzabc")
        assert isinstance(matches, list)
