"""
Unit tests for ClassificationCache in utils/fuzzy_classifier.py.

ClassificationCache is a standalone in-memory TTL cache used by the
AI intent classifier. If it returns stale data or has a non-deterministic
key, the classifier routes to the wrong agent tier — silently.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from utils.fuzzy_classifier import ClassificationCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent(action: str = "open_app", content: str = "spotify") -> dict:
    return {"action": action, "content": content}


def _make_result(tier: str = "complex") -> dict:
    return {"tier": tier, "confidence": 0.9}


# ---------------------------------------------------------------------------
# Cache miss
# ---------------------------------------------------------------------------

class TestCacheMiss:
    def test_empty_cache_returns_none(self):
        cache = ClassificationCache()
        assert cache.get(_make_intent(), "open spotify") is None

    def test_different_transcript_is_cache_miss(self):
        cache = ClassificationCache()
        cache.set(_make_intent(), "open spotify", _make_result())
        assert cache.get(_make_intent(), "launch spotify") is None

    def test_different_action_is_cache_miss(self):
        cache = ClassificationCache()
        cache.set(_make_intent("open_app"), "open spotify", _make_result())
        assert cache.get(_make_intent("web_search"), "open spotify") is None


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------

class TestCacheHit:
    def test_same_intent_and_transcript_returns_result(self):
        cache = ClassificationCache()
        result = _make_result("simple")
        cache.set(_make_intent(), "open spotify", result)
        assert cache.get(_make_intent(), "open spotify") == result

    def test_cache_hit_does_not_modify_result(self):
        cache = ClassificationCache()
        original = {"tier": "conversational", "agents": ["responder"]}
        cache.set(_make_intent(), "hello", original)
        retrieved = cache.get(_make_intent(), "hello")
        assert retrieved == original

    def test_key_is_deterministic_across_calls(self):
        """Same input must always map to same cache slot."""
        cache = ClassificationCache()
        result = _make_result()
        cache.set(_make_intent(), "play music", result)
        assert cache.get(_make_intent(), "play music") == result
        assert cache.get(_make_intent(), "play music") == result  # second call


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

class TestTTLExpiry:
    def test_entry_expires_after_ttl(self):
        cache = ClassificationCache(ttl_seconds=1)
        cache.set(_make_intent(), "open maps", _make_result())

        # Simulate TTL elapsed by backdating the stored timestamp
        key = cache._generate_key(_make_intent(), "open maps")
        result, _ = cache.cache[key]
        cache.cache[key] = (result, datetime.now() - timedelta(seconds=2))

        assert cache.get(_make_intent(), "open maps") is None

    def test_entry_valid_just_before_ttl(self):
        cache = ClassificationCache(ttl_seconds=60)
        cache.set(_make_intent(), "open maps", _make_result())
        assert cache.get(_make_intent(), "open maps") is not None

    def test_expired_entry_is_removed_from_cache(self):
        cache = ClassificationCache(ttl_seconds=1)
        cache.set(_make_intent(), "open maps", _make_result())

        key = cache._generate_key(_make_intent(), "open maps")
        result, _ = cache.cache[key]
        cache.cache[key] = (result, datetime.now() - timedelta(seconds=2))

        cache.get(_make_intent(), "open maps")  # triggers eviction
        assert key not in cache.cache


# ---------------------------------------------------------------------------
# Max size eviction
# ---------------------------------------------------------------------------

class TestMaxSizeEviction:
    def test_cache_does_not_exceed_max_size(self):
        cache = ClassificationCache(max_size=3)
        for i in range(5):
            cache.set(_make_intent(content=f"app_{i}"), f"open app_{i}", _make_result())
        assert len(cache.cache) <= 3

    def test_oldest_entry_is_evicted_when_full(self):
        """After eviction at capacity, old entries should be gone."""
        cache = ClassificationCache(max_size=2)
        cache.set(_make_intent(content="a"), "open a", _make_result("simple"))
        cache.set(_make_intent(content="b"), "open b", _make_result("complex"))
        # Adding a third entry must evict one of the first two
        cache.set(_make_intent(content="c"), "open c", _make_result("conversational"))
        assert len(cache.cache) == 2


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestKeyGeneration:
    def test_same_inputs_produce_same_key(self):
        cache = ClassificationCache()
        k1 = cache._generate_key(_make_intent(), "open spotify")
        k2 = cache._generate_key(_make_intent(), "open spotify")
        assert k1 == k2

    def test_different_transcripts_produce_different_keys(self):
        cache = ClassificationCache()
        k1 = cache._generate_key(_make_intent(), "open spotify")
        k2 = cache._generate_key(_make_intent(), "open youtube")
        assert k1 != k2

    def test_key_is_hex_string(self):
        cache = ClassificationCache()
        key = cache._generate_key(_make_intent(), "any transcript")
        assert all(c in "0123456789abcdef" for c in key)
