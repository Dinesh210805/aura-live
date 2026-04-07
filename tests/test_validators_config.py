"""
Unit tests for validators/config.py.

Tests cover:
- Groq key missing + groq provider → raises ConfigurationError
- Gemini key missing + gemini provider → raises ConfigurationError
- NVIDIA key missing + nvidia as any provider → logs warning, does NOT raise
- Production env + no device_api_key → logs warning, does NOT raise
- Production env + wildcard CORS → logs warning, does NOT raise
- Valid full config (all keys present) → no exception raised

Must patch `validators.config.settings` (module-level bound instance).
"""

from unittest.mock import MagicMock, patch

import pytest

import validators.config as config_module
from utils.exceptions import ConfigurationError
from validators.config import validate_configuration


# ---------------------------------------------------------------------------
# Helper: build a mock settings object with sensible defaults
# ---------------------------------------------------------------------------

def _settings(
    groq_api_key="groq-key",
    gemini_api_key="gemini-key",
    nvidia_api_key="nvidia-key",
    default_llm_provider="groq",
    default_vlm_provider="groq",
    planning_provider="groq",
    environment="development",
    device_api_key="dev-api-key",
    cors_origins=None,
):
    s = MagicMock()
    s.groq_api_key = groq_api_key
    s.gemini_api_key = gemini_api_key
    s.nvidia_api_key = nvidia_api_key
    s.default_llm_provider = default_llm_provider
    s.default_vlm_provider = default_vlm_provider
    s.planning_provider = planning_provider
    s.environment = environment
    type(s).device_api_key = property(lambda self: device_api_key)
    type(s).cors_origins = property(lambda self: cors_origins or ["http://localhost"])
    return s


# ---------------------------------------------------------------------------
# Groq key missing
# ---------------------------------------------------------------------------

class TestGroqKeyRequired:
    def test_missing_groq_key_with_groq_provider_raises(self):
        s = _settings(groq_api_key=None, default_llm_provider="groq")
        with patch.object(config_module, "settings", s):
            with pytest.raises(ConfigurationError, match="[Gg]roq"):
                validate_configuration()

    def test_missing_groq_key_with_non_groq_provider_ok(self):
        """Groq key missing but provider is gemini → no error."""
        s = _settings(groq_api_key=None, default_llm_provider="gemini")
        with patch.object(config_module, "settings", s):
            validate_configuration()  # Should not raise


# ---------------------------------------------------------------------------
# Gemini key missing
# ---------------------------------------------------------------------------

class TestGeminiKeyRequired:
    def test_missing_gemini_key_with_gemini_vlm_provider_raises(self):
        s = _settings(gemini_api_key=None, default_vlm_provider="gemini")
        with patch.object(config_module, "settings", s):
            with pytest.raises(ConfigurationError, match="[Gg]emini"):
                validate_configuration()

    def test_missing_gemini_key_with_non_gemini_provider_ok(self):
        s = _settings(gemini_api_key=None, default_vlm_provider="groq")
        with patch.object(config_module, "settings", s):
            validate_configuration()  # Should not raise


# ---------------------------------------------------------------------------
# NVIDIA key missing → warning, not exception
# ---------------------------------------------------------------------------

class TestNvidiaKeyWarning:
    def test_nvidia_vlm_provider_no_key_warns_not_raises(self):
        s = _settings(nvidia_api_key=None, default_vlm_provider="nvidia")
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()  # Should not raise
                assert mock_warn.called

    def test_nvidia_llm_provider_no_key_warns_not_raises(self):
        s = _settings(nvidia_api_key=None, default_llm_provider="nvidia")
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()
                assert mock_warn.called

    def test_nvidia_planning_provider_no_key_warns_not_raises(self):
        s = _settings(nvidia_api_key=None, planning_provider="nvidia")
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()
                assert mock_warn.called


# ---------------------------------------------------------------------------
# Production security warnings (not exceptions)
# ---------------------------------------------------------------------------

class TestProductionWarnings:
    def test_production_no_device_api_key_warns(self):
        s = _settings(environment="production", device_api_key=None)
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()  # Should not raise
                assert mock_warn.called

    def test_production_wildcard_cors_warns(self):
        s = _settings(environment="production", cors_origins=["*"])
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()
                assert mock_warn.called

    def test_development_env_no_warnings_for_security(self):
        s = _settings(environment="development", device_api_key=None, cors_origins=["*"])
        with patch.object(config_module, "settings", s):
            with patch.object(config_module.logger, "warning") as mock_warn:
                validate_configuration()
                # No security warnings for development env
                security_warnings = [
                    call for call in mock_warn.call_args_list
                    if "production" in str(call).lower() or "api key" in str(call).lower()
                ]
                assert len(security_warnings) == 0


# ---------------------------------------------------------------------------
# Valid full configuration
# ---------------------------------------------------------------------------

class TestValidConfiguration:
    def test_all_keys_present_no_exception(self):
        s = _settings(
            groq_api_key="valid-groq",
            gemini_api_key="valid-gemini",
            nvidia_api_key="valid-nvidia",
            default_llm_provider="groq",
            default_vlm_provider="gemini",
        )
        with patch.object(config_module, "settings", s):
            validate_configuration()  # Should not raise

    def test_groq_only_config_ok(self):
        s = _settings(
            groq_api_key="valid-groq",
            gemini_api_key=None,
            default_llm_provider="groq",
            default_vlm_provider="groq",
        )
        with patch.object(config_module, "settings", s):
            validate_configuration()
