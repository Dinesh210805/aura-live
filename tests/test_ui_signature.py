"""
Unit tests for services/ui_signature.py.

Tests cover:
- compute_ui_signature: determinism, empty input, dict vs list input
- Zone weighting: STATUS/HEADER elements excluded below weight 0.5 when screen_height given
- Different UI data → different signatures
- signatures_differ: empty sig treated as different, identical sigs return False
- compute_content_signature: text-bearing class filtering, empty/None input
- compute_lightweight_signature: dict and list formats, 8-char output
"""

import pytest

from services.ui_signature import (
    compute_content_signature,
    compute_lightweight_signature,
    compute_ui_signature,
    signatures_differ,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _element(class_name="android.widget.TextView", text="Hello", top=300, left=0, right=500, bottom=350, clickable=False):
    return {
        "className": class_name,
        "text": text,
        "contentDescription": "",
        "clickable": clickable,
        "focusable": False,
        "top": top,
        "left": left,
        "right": right,
        "bottom": bottom,
    }


def _tree_node(class_name="android.view.ViewGroup", text="", children=None):
    node = {
        "className": class_name,
        "text": text,
        "contentDescription": "",
        "clickable": False,
        "focusable": False,
        "children": children or [],
    }
    return node


# ---------------------------------------------------------------------------
# compute_ui_signature — basic behaviour
# ---------------------------------------------------------------------------

class TestComputeUiSignatureBasic:
    def test_empty_none_returns_empty(self):
        assert compute_ui_signature(None) == ""

    def test_empty_list_returns_empty(self):
        assert compute_ui_signature([]) == ""

    def test_returns_16_char_hex(self):
        sig = compute_ui_signature([_element()])
        assert len(sig) == 16
        assert all(c in "0123456789abcdef" for c in sig)

    def test_deterministic_list_input(self):
        elements = [_element(text="Login"), _element(text="Password", top=400)]
        sig1 = compute_ui_signature(elements)
        sig2 = compute_ui_signature(elements)
        assert sig1 == sig2

    def test_deterministic_dict_input(self):
        tree = _tree_node(children=[_tree_node(class_name="android.widget.Button", text="OK")])
        sig1 = compute_ui_signature(tree)
        sig2 = compute_ui_signature(tree)
        assert sig1 == sig2

    def test_different_text_gives_different_sig(self):
        sig_a = compute_ui_signature([_element(text="Screen A")])
        sig_b = compute_ui_signature([_element(text="Screen B")])
        assert sig_a != sig_b

    def test_different_class_gives_different_sig(self):
        sig_a = compute_ui_signature([_element(class_name="android.widget.TextView")])
        sig_b = compute_ui_signature([_element(class_name="android.widget.Button")])
        assert sig_a != sig_b

    def test_dict_and_list_may_differ(self):
        """Dict (tree) and list (flat) paths use different extraction logic — just verify both return non-empty."""
        tree = _tree_node(children=[_tree_node(text="Child")])
        elements = [_element(text="Child")]
        sig_tree = compute_ui_signature(tree)
        sig_list = compute_ui_signature(elements)
        assert sig_tree != ""
        assert sig_list != ""


# ---------------------------------------------------------------------------
# Zone weighting with screen_height
# ---------------------------------------------------------------------------

class TestZoneWeighting:
    """
    STATUS (top < 5% of screen_height) has weight 0.1 — excluded (< 0.5).
    NAV_BAR (top > 85%) has weight 0.2 — excluded.
    HEADER (5-15%) has weight 0.5 — included (>= 0.5).
    CONTENT (15-85%) has weight 3.0 — always included.
    """

    SCREEN_HEIGHT = 1000

    def test_status_element_excluded(self):
        """Element in top 5% (STATUS zone, weight 0.1) should be excluded."""
        status_elem = _element(text="12:00 PM battery 80%", top=10)  # top/1000 = 0.01
        content_elem = _element(text="Content", top=300)
        # With status elem excluded, sig should match content-only
        sig_with_status = compute_ui_signature([status_elem, content_elem], screen_height=self.SCREEN_HEIGHT)
        sig_content_only = compute_ui_signature([content_elem], screen_height=self.SCREEN_HEIGHT)
        assert sig_with_status == sig_content_only

    def test_nav_bar_element_excluded(self):
        """Element in bottom 15% (NAV_BAR zone, weight 0.2) should be excluded."""
        nav_elem = _element(text="Home Back Recent", top=900)  # top/1000 = 0.90
        content_elem = _element(text="Content", top=300)
        sig_with_nav = compute_ui_signature([nav_elem, content_elem], screen_height=self.SCREEN_HEIGHT)
        sig_content_only = compute_ui_signature([content_elem], screen_height=self.SCREEN_HEIGHT)
        assert sig_with_nav == sig_content_only

    def test_content_zone_included(self):
        """Elements in content zone (15-85%) are always included."""
        content_elem = _element(text="Main Content", top=500)
        sig = compute_ui_signature([content_elem], screen_height=self.SCREEN_HEIGHT)
        assert sig != ""

    def test_no_screen_height_includes_all_elements(self):
        """Without screen_height, status bar element is included in hash."""
        status_elem = _element(text="StatusBar", top=10)
        content_elem = _element(text="Content", top=300)
        sig_all = compute_ui_signature([status_elem, content_elem])
        sig_content_only = compute_ui_signature([content_elem])
        # They differ because zone exclusion doesn't apply without screen_height
        assert sig_all != sig_content_only


# ---------------------------------------------------------------------------
# signatures_differ
# ---------------------------------------------------------------------------

class TestSignaturesDiffer:
    def test_empty_sig1_returns_true(self):
        assert signatures_differ("", "abc123") is True

    def test_empty_sig2_returns_true(self):
        assert signatures_differ("abc123", "") is True

    def test_both_empty_returns_true(self):
        assert signatures_differ("", "") is True

    def test_identical_sigs_returns_false(self):
        sig = compute_ui_signature([_element(text="Same")])
        assert signatures_differ(sig, sig) is False

    def test_different_sigs_returns_true(self):
        sig_a = compute_ui_signature([_element(text="A")])
        sig_b = compute_ui_signature([_element(text="B")])
        assert signatures_differ(sig_a, sig_b) is True


# ---------------------------------------------------------------------------
# compute_content_signature
# ---------------------------------------------------------------------------

class TestComputeContentSignature:
    def test_none_input_returns_empty(self):
        assert compute_content_signature(None) == ""

    def test_empty_list_returns_empty(self):
        assert compute_content_signature([]) == ""

    def test_textview_included(self):
        elements = [{"className": "android.widget.TextView", "text": "Hello", "contentDescription": ""}]
        sig = compute_content_signature(elements)
        assert len(sig) == 16

    def test_button_included(self):
        elements = [{"className": "android.widget.Button", "text": "Submit", "contentDescription": ""}]
        sig = compute_content_signature(elements)
        assert sig != ""

    def test_layout_container_excluded(self):
        """Pure layout containers don't carry text-bearing class names."""
        layout_only = [{"className": "android.widget.LinearLayout", "text": "", "contentDescription": ""}]
        assert compute_content_signature(layout_only) == ""

    def test_text_change_detected(self):
        """Same class, different text → different signature."""
        before = [{"className": "android.widget.TextView", "text": "0", "contentDescription": ""}]
        after = [{"className": "android.widget.TextView", "text": "42", "contentDescription": ""}]
        assert compute_content_signature(before) != compute_content_signature(after)

    def test_edittext_included(self):
        elements = [{"className": "android.widget.EditText", "text": "user@example.com", "contentDescription": ""}]
        sig = compute_content_signature(elements)
        assert sig != ""

    def test_uses_content_description_fallback(self):
        """If text is empty but contentDescription is set, it should be included."""
        elements = [{"className": "android.widget.Button", "text": "", "contentDescription": "Search"}]
        sig = compute_content_signature(elements)
        assert sig != ""

    def test_elements_with_no_text_or_desc_excluded(self):
        """Elements with empty text AND empty contentDescription don't contribute."""
        elements = [{"className": "android.widget.CheckBox", "text": "", "contentDescription": ""}]
        assert compute_content_signature(elements) == ""

    def test_deterministic(self):
        elements = [
            {"className": "android.widget.TextView", "text": "Hello", "contentDescription": ""},
            {"className": "android.widget.Button", "text": "OK", "contentDescription": ""},
        ]
        assert compute_content_signature(elements) == compute_content_signature(elements)


# ---------------------------------------------------------------------------
# compute_lightweight_signature
# ---------------------------------------------------------------------------

class TestComputeLightweightSignature:
    def test_none_returns_empty(self):
        assert compute_lightweight_signature(None) == ""

    def test_empty_list_returns_empty(self):
        assert compute_lightweight_signature([]) == ""

    def test_returns_8_char_hex(self):
        sig = compute_lightweight_signature([_element()])
        assert len(sig) == 8
        assert all(c in "0123456789abcdef" for c in sig)

    def test_dict_returns_8_char_hex(self):
        tree = _tree_node(children=[_tree_node(text="Child")])
        sig = compute_lightweight_signature(tree)
        assert len(sig) == 8

    def test_list_deterministic(self):
        elements = [_element(text="Test"), _element(text="Two")]
        assert compute_lightweight_signature(elements) == compute_lightweight_signature(elements)

    def test_dict_deterministic(self):
        tree = _tree_node(children=[_tree_node(class_name="android.widget.Button")])
        assert compute_lightweight_signature(tree) == compute_lightweight_signature(tree)

    def test_different_element_count_different_sig(self):
        one = [_element()]
        two = [_element(), _element(text="Second")]
        assert compute_lightweight_signature(one) != compute_lightweight_signature(two)

    def test_different_root_class_different_sig(self):
        tree_a = _tree_node(class_name="android.widget.FrameLayout")
        tree_b = _tree_node(class_name="android.widget.LinearLayout")
        assert compute_lightweight_signature(tree_a) != compute_lightweight_signature(tree_b)
