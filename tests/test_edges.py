"""
Unit tests for LangGraph routing edges in aura_graph/edges.py.

Each edge function takes a TaskState dict and returns a Literal string.
These tests cover every branch that determines which node runs next —
a wrong route silently bypasses perception, coordinator, or error handling.

Strategy: build minimal TaskState dicts with only the fields each function reads.
No mocking needed — edges are pure functions over dicts.
"""

import pytest
from unittest.mock import patch

# Patch settings before importing edges so _SETTINGS is set from our mock
from unittest.mock import MagicMock

_mock_settings = MagicMock()
_mock_settings.use_universal_agent = True

with patch("config.settings.get_settings", return_value=_mock_settings):
    from aura_graph.edges import (
        route_from_start,
        should_continue_after_error_handling,
        should_continue_after_intent_parsing,
        should_continue_after_perception,
        should_continue_after_speak,
        should_continue_after_stt,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**kwargs) -> dict:
    """Build a minimal TaskState-like dict from kwargs."""
    return kwargs


# ---------------------------------------------------------------------------
# route_from_start
# ---------------------------------------------------------------------------

class TestRouteFromStart:
    def test_text_input_with_transcript_routes_to_parse_intent(self):
        state = _state(input_type="text", transcript="open spotify")
        assert route_from_start(state) == "parse_intent"

    def test_streaming_input_with_streaming_transcript(self):
        state = _state(input_type="streaming", streaming_transcript="play music")
        assert route_from_start(state) == "parse_intent"

    def test_text_input_without_transcript_falls_through_to_stt(self):
        """Text type but no transcript yet → default to stt."""
        state = _state(input_type="text")
        assert route_from_start(state) == "stt"

    def test_audio_input_routes_to_stt(self):
        state = _state(input_type="audio")
        assert route_from_start(state) == "stt"

    def test_unknown_input_type_defaults_to_stt(self):
        state = _state(input_type="fax_machine")
        assert route_from_start(state) == "stt"

    def test_missing_input_type_defaults_to_stt(self):
        state = _state()
        assert route_from_start(state) == "stt"


# ---------------------------------------------------------------------------
# should_continue_after_stt
# ---------------------------------------------------------------------------

class TestAfterStt:
    def test_valid_transcript_routes_to_parse_intent(self):
        state = _state(transcript="open settings")
        assert should_continue_after_stt(state) == "parse_intent"

    def test_stt_failed_status_routes_to_error_handler(self):
        state = _state(transcript="", status="stt_failed")
        assert should_continue_after_stt(state) == "error_handler"

    def test_empty_transcript_routes_to_error_handler(self):
        state = _state(transcript="")
        assert should_continue_after_stt(state) == "error_handler"

    def test_whitespace_only_transcript_routes_to_error_handler(self):
        state = _state(transcript="   ")
        assert should_continue_after_stt(state) == "error_handler"

    def test_single_char_transcript_routes_to_error_handler(self):
        """Single character is not meaningful speech."""
        state = _state(transcript="a")
        assert should_continue_after_stt(state) == "error_handler"

    def test_streaming_transcript_also_accepted(self):
        state = _state(streaming_transcript="turn off wifi")
        assert should_continue_after_stt(state) == "parse_intent"


# ---------------------------------------------------------------------------
# should_continue_after_intent_parsing
# ---------------------------------------------------------------------------

class TestAfterIntentParsing:
    def test_blocked_status_routes_to_speak(self):
        state = _state(
            status="blocked",
            intent={"action": "delete_all_data", "confidence": 0.9},
            transcript="",
        )
        assert should_continue_after_intent_parsing(state) == "speak"

    def test_intent_failed_routes_to_error_handler(self):
        state = _state(status="intent_failed", intent=None, transcript="")
        assert should_continue_after_intent_parsing(state) == "error_handler"

    def test_missing_intent_routes_to_error_handler(self):
        state = _state(status="ok", intent=None, transcript="")
        assert should_continue_after_intent_parsing(state) == "error_handler"

    def test_low_confidence_below_03_routes_to_error_handler(self):
        state = _state(
            status="ok",
            intent={"action": "tap", "confidence": 0.2, "parameters": {}},
            transcript="do something",
        )
        assert should_continue_after_intent_parsing(state) == "error_handler"

    def test_conversational_action_routes_to_speak(self):
        state = _state(
            status="ok",
            intent={"action": "greet", "confidence": 0.95, "parameters": {}},
            transcript="hello",
        )
        assert should_continue_after_intent_parsing(state) == "speak"

    def test_conversational_transcript_keyword_routes_to_speak(self):
        """'hello' in transcript triggers conversational path even if action differs."""
        state = _state(
            status="ok",
            intent={"action": "unknown_action", "confidence": 0.8, "parameters": {}},
            transcript="hello there",
        )
        assert should_continue_after_intent_parsing(state) == "speak"

    def test_web_search_action_routes_to_web_search(self):
        state = _state(
            status="ok",
            intent={"action": "web_search", "confidence": 0.9, "parameters": {}},
            transcript="what is the weather today",
        )
        assert should_continue_after_intent_parsing(state) == "web_search"

    def test_delegate_to_planner_flag_routes_to_coordinator(self):
        state = _state(
            status="ok",
            intent={
                "action": "general_interaction",
                "confidence": 0.85,
                "delegate_to_planner": True,
                "parameters": {},
            },
            transcript="open youtube search cat videos and play the first one",
        )
        assert should_continue_after_intent_parsing(state) == "coordinator"

    def test_multi_step_transcript_with_and_routes_to_coordinator(self):
        state = _state(
            status="ok",
            intent={"action": "open_app", "confidence": 0.9, "parameters": {}},
            transcript="open spotify and play liked songs",
        )
        assert should_continue_after_intent_parsing(state) == "coordinator"

    def test_no_ui_action_routes_to_coordinator(self):
        """NO_UI actions skip perception entirely."""
        state = _state(
            status="ok",
            intent={"action": "go_home", "confidence": 0.9, "parameters": {}},
            transcript="go home",
        )
        assert should_continue_after_intent_parsing(state) == "coordinator"


# ---------------------------------------------------------------------------
# should_continue_after_perception
# ---------------------------------------------------------------------------

class TestAfterPerception:
    def test_perception_failed_status_routes_to_error_handler(self):
        state = _state(
            status="perception_failed",
            perception_bundle=None,
            intent={"action": "tap", "parameters": {}},
        )
        assert should_continue_after_perception(state) == "error_handler"

    def test_missing_bundle_routes_to_error_handler(self):
        state = _state(
            status="ok",
            perception_bundle=None,
            intent={"action": "tap", "parameters": {}},
        )
        assert should_continue_after_perception(state) == "error_handler"

    def test_screen_reading_action_routes_to_speak(self):
        bundle = object()  # non-None sentinel
        state = _state(
            status="ok",
            perception_bundle=bundle,
            intent={"action": "read_screen", "parameters": {}},
        )
        assert should_continue_after_perception(state) == "speak"

    def test_normal_action_with_bundle_routes_to_coordinator(self):
        bundle = object()
        state = _state(
            status="ok",
            perception_bundle=bundle,
            intent={"action": "tap", "parameters": {"x": 100}},
        )
        assert should_continue_after_perception(state) == "coordinator"

    def test_describe_screen_routes_to_speak(self):
        bundle = object()
        state = _state(
            status="ok",
            perception_bundle=bundle,
            intent={"action": "describe_screen", "parameters": {}},
        )
        assert should_continue_after_perception(state) == "speak"


# ---------------------------------------------------------------------------
# should_continue_after_speak
# ---------------------------------------------------------------------------

class TestAfterSpeak:
    def test_always_ends(self):
        """Speak is always terminal — no matter what state contains."""
        assert should_continue_after_speak(_state()) == "__end__"
        assert should_continue_after_speak(_state(status="failed")) == "__end__"


# ---------------------------------------------------------------------------
# should_continue_after_error_handling
# ---------------------------------------------------------------------------

class TestAfterErrorHandling:
    def test_perception_failed_within_retries_routes_to_perception(self):
        state = _state(
            status="perception_failed",
            retry_count=0,
            max_retries=3,
            intent={"action": "tap"},
        )
        assert should_continue_after_error_handling(state) == "perception"

    def test_perception_failed_exceeds_retries_routes_to_speak(self):
        state = _state(
            status="perception_failed",
            retry_count=3,
            max_retries=3,
            intent={"action": "tap"},
        )
        assert should_continue_after_error_handling(state) == "speak"

    def test_non_perception_error_routes_to_speak(self):
        state = _state(
            status="stt_failed",
            retry_count=0,
            max_retries=3,
            intent={"action": "tap"},
        )
        assert should_continue_after_error_handling(state) == "speak"

    def test_no_ui_action_never_retries_perception(self):
        """go_home with perception_failed → speak (not perception retry)."""
        state = _state(
            status="perception_failed",
            retry_count=0,
            max_retries=3,
            intent={"action": "go_home"},
        )
        assert should_continue_after_error_handling(state) == "speak"
