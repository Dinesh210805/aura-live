"""
Unit tests for ReflexionService._goal_key() in services/reflexion_service.py.

_goal_key() is a static method that normalises a free-text goal string into a
stable storage key. The key determines which lesson pool a future retry reads
from — a wrong bucket silently injects irrelevant lessons into the next attempt.

Tests cover:
- Action bucket detection for all major verbs
- Per-app scoping (spotify lessons must not contaminate youtube pool)
- No-app fallback (bucket name only)
- Unknown goal slug fallback (first 3 words)
- Edge cases: empty string, single word, mixed case
"""

import pytest

from services.reflexion_service import ReflexionService

# Alias for brevity
_goal_key = ReflexionService._goal_key


# ---------------------------------------------------------------------------
# Action bucket — media
# ---------------------------------------------------------------------------

class TestPlayMediaBucket:
    def test_play_spotify(self):
        assert _goal_key("play liked songs in spotify") == "play_media__spotify"

    def test_play_youtube(self):
        assert _goal_key("play a video on youtube") == "play_media__youtube"

    def test_listen_spotify(self):
        assert _goal_key("listen to music on spotify") == "play_media__spotify"

    def test_watch_netflix(self):
        assert _goal_key("watch a movie on netflix") == "play_media__netflix"

    def test_stream_no_app(self):
        """'stream' matches play_media; no known app → no app suffix."""
        assert _goal_key("stream some videos") == "play_media"

    def test_music_keyword(self):
        assert _goal_key("play some music") == "play_media"

    def test_podcast_keyword(self):
        assert _goal_key("play a podcast on spotify") == "play_media__spotify"


# ---------------------------------------------------------------------------
# Action bucket — open_app (must precede send_message in bucket order)
# ---------------------------------------------------------------------------

class TestOpenAppBucket:
    def test_open_whatsapp(self):
        assert _goal_key("open whatsapp") == "open_app__whatsapp"

    def test_launch_camera(self):
        assert _goal_key("launch camera") == "open_app__camera"

    def test_start_settings(self):
        assert _goal_key("start settings") == "open_app__settings"

    def test_open_with_no_known_app(self):
        """'open' verb matches, but app not in _APP_NAMES."""
        assert _goal_key("open some random app") == "open_app"


# ---------------------------------------------------------------------------
# Action bucket — send_message
# ---------------------------------------------------------------------------

class TestSendMessageBucket:
    def test_send_message_to_john(self):
        """No app name in text → no app suffix."""
        assert _goal_key("send message to john") == "send_message"

    def test_text_whatsapp(self):
        assert _goal_key("text mom on whatsapp") == "send_message__whatsapp"

    def test_sms_keyword(self):
        assert _goal_key("sms contact number") == "send_message"


# ---------------------------------------------------------------------------
# Action bucket — search
# ---------------------------------------------------------------------------

class TestSearchBucket:
    def test_search_maps(self):
        assert _goal_key("search for restaurants on maps") == "search__maps"

    def test_find_no_app(self):
        assert _goal_key("find the nearest pharmacy") == "search"

    def test_google_verb(self):
        assert _goal_key("google the weather today") == "search"

    def test_browse_chrome(self):
        assert _goal_key("browse something on chrome") == "search__chrome"


# ---------------------------------------------------------------------------
# Action bucket — navigate
# ---------------------------------------------------------------------------

class TestNavigateBucket:
    def test_navigate_to_work(self):
        assert _goal_key("navigate to work on maps") == "navigate__maps"

    def test_directions_no_app(self):
        assert _goal_key("get directions to the airport") == "navigate"

    def test_route_maps(self):
        # "find" would hit the search bucket; use a phrase without search keywords
        assert _goal_key("get route on maps") == "navigate__maps"


# ---------------------------------------------------------------------------
# Action bucket — settings
# ---------------------------------------------------------------------------

class TestSettingsBucket:
    def test_toggle_wifi(self):
        assert _goal_key("toggle wifi off") == "settings"

    def test_turn_on_bluetooth(self):
        assert _goal_key("turn on bluetooth") == "settings"

    def test_volume_up(self):
        assert _goal_key("volume up please") == "settings"


# ---------------------------------------------------------------------------
# Action bucket — make_call
# ---------------------------------------------------------------------------

class TestMakeCallBucket:
    def test_call_mom(self):
        assert _goal_key("call mom") == "make_call"

    def test_dial_number(self):
        assert _goal_key("dial 9876543210") == "make_call"


# ---------------------------------------------------------------------------
# App isolation — same bucket, different apps → different keys
# ---------------------------------------------------------------------------

class TestAppIsolation:
    def test_spotify_and_youtube_are_distinct(self):
        k1 = _goal_key("play music on spotify")
        k2 = _goal_key("play music on youtube")
        assert k1 != k2

    def test_same_goal_same_app_is_identical(self):
        assert _goal_key("play liked songs in spotify") == _goal_key("play liked songs in spotify")

    def test_whatsapp_and_telegram_are_distinct(self):
        k1 = _goal_key("send message via whatsapp")
        k2 = _goal_key("send message via telegram")
        assert k1 != k2


# ---------------------------------------------------------------------------
# Fallback slug for unknown goals
# ---------------------------------------------------------------------------

class TestFallbackSlug:
    def test_unrecognised_goal_uses_first_three_words(self):
        key = _goal_key("flip the donut configuration")
        assert key == "flip_the_donut"

    def test_unrecognised_goal_with_known_app_appends_app(self):
        key = _goal_key("flip the donut on spotify")
        assert key == "flip_the_donut__spotify"

    def test_single_word_goal(self):
        key = _goal_key("frobnicate")
        assert key == "frobnicate"

    def test_empty_string_returns_unknown(self):
        key = _goal_key("")
        assert key == "unknown"


# ---------------------------------------------------------------------------
# Case and whitespace normalisation
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_uppercase_goal_still_matches_bucket(self):
        assert _goal_key("PLAY MUSIC ON SPOTIFY") == "play_media__spotify"

    def test_mixed_case(self):
        assert _goal_key("Open WhatsApp") == "open_app__whatsapp"

    def test_leading_trailing_whitespace_ignored(self):
        assert _goal_key("  play music  ") == "play_media"

    def test_key_contains_no_spaces(self):
        """Storage keys must be filesystem-safe: no spaces."""
        key = _goal_key("play liked songs in spotify")
        assert " " not in key
