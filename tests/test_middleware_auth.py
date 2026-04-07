"""
Unit tests for middleware/auth.py.

Tests cover:
- Development mode: require_api_key=False → returns "development-mode" without checking key
- Missing server config: require_api_key=True, device_api_key=None → HTTP 500
- Invalid key: correct format but wrong value → HTTP 401
- Missing key (None header): → HTTP 401
- Valid key: correct value → returns key unchanged
- Timing safety: uses secrets.compare_digest so direct equality would also work for a test

Must patch `middleware.auth.settings` (the module-level bound instance),
not `get_settings()`, because the binding happens at import time.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helper: build a mock settings object
# ---------------------------------------------------------------------------

def _settings(require_api_key: bool = True, device_api_key: str | None = "secret-key"):
    s = MagicMock()
    s.require_api_key = require_api_key
    s.device_api_key = device_api_key
    # Make getattr work for dynamic attribute access in verify_api_key
    if device_api_key is None:
        del s.device_api_key
        s.__getattr__ = lambda self, name: None
    return s


# We must import AFTER defining the helper, to capture the module-level `settings` attr
import middleware.auth as auth_module
from middleware.auth import verify_api_key


# ---------------------------------------------------------------------------
# Development mode
# ---------------------------------------------------------------------------

class TestDevMode:
    def test_dev_mode_returns_development_mode_string(self):
        mock_settings = MagicMock()
        mock_settings.require_api_key = False
        with patch.object(auth_module, "settings", mock_settings):
            result = verify_api_key(x_api_key=None)
        assert result == "development-mode"

    def test_dev_mode_ignores_provided_key(self):
        mock_settings = MagicMock()
        mock_settings.require_api_key = False
        with patch.object(auth_module, "settings", mock_settings):
            result = verify_api_key(x_api_key="any-key")
        assert result == "development-mode"


# ---------------------------------------------------------------------------
# Missing server config (HTTP 500)
# ---------------------------------------------------------------------------

class TestMissingServerConfig:
    def test_no_device_api_key_raises_500(self):
        mock_settings = MagicMock()
        mock_settings.require_api_key = True
        # getattr(settings, "device_api_key", None) should return None/falsy
        type(mock_settings).device_api_key = property(lambda self: None)
        with patch.object(auth_module, "settings", mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key="some-key")
        assert exc_info.value.status_code == 500

    def test_empty_device_api_key_raises_500(self):
        mock_settings = MagicMock()
        mock_settings.require_api_key = True
        type(mock_settings).device_api_key = property(lambda self: "")
        with patch.object(auth_module, "settings", mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key="some-key")
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Invalid key (HTTP 401)
# ---------------------------------------------------------------------------

class TestInvalidKey:
    def _make_settings(self):
        s = MagicMock()
        s.require_api_key = True
        type(s).device_api_key = property(lambda self: "correct-secret")
        return s

    def test_wrong_key_raises_401(self):
        with patch.object(auth_module, "settings", self._make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key="wrong-key")
        assert exc_info.value.status_code == 401

    def test_missing_key_raises_401(self):
        """x_api_key=None (header not provided)."""
        with patch.object(auth_module, "settings", self._make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key=None)
        assert exc_info.value.status_code == 401

    def test_empty_key_raises_401(self):
        with patch.object(auth_module, "settings", self._make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key="")
        assert exc_info.value.status_code == 401

    def test_401_has_www_authenticate_header(self):
        with patch.object(auth_module, "settings", self._make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(x_api_key="bad")
        assert "WWW-Authenticate" in exc_info.value.headers


# ---------------------------------------------------------------------------
# Valid key
# ---------------------------------------------------------------------------

class TestValidKey:
    def test_correct_key_returned(self):
        s = MagicMock()
        s.require_api_key = True
        type(s).device_api_key = property(lambda self: "correct-secret")
        with patch.object(auth_module, "settings", s):
            result = verify_api_key(x_api_key="correct-secret")
        assert result == "correct-secret"
