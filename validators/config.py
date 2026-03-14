"""Configuration validation."""

from config.settings import get_settings
from utils.exceptions import ConfigurationError
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def validate_configuration() -> None:
    """
    Validate critical configuration.

    Raises:
        ConfigurationError: If configuration is invalid
    """
    try:
        # Check required API keys
        if not settings.groq_api_key and settings.default_llm_provider == "groq":
            raise ConfigurationError("Groq API key required when using Groq provider")

        if not settings.gemini_api_key and settings.default_vlm_provider == "gemini":
            raise ConfigurationError(
                "Gemini API key required when using Gemini provider"
            )

        # Check NVIDIA API key when nvidia is configured as any provider
        nvidia_providers = [
            settings.default_vlm_provider,
            settings.default_llm_provider,
            settings.planning_provider,
        ]
        if "nvidia" in nvidia_providers and not settings.nvidia_api_key:
            logger.warning(
                "⚠️ NVIDIA_API_KEY not configured but nvidia is set as a provider. "
                "NVIDIA NIM calls will fail — falling back to other providers."
            )

        # Check security settings in production
        if settings.environment == "production":
            if not getattr(settings, "device_api_key", None):
                logger.warning(" No device API key configured for production!")

            if "*" in getattr(settings, "cors_origins", ["*"]):
                logger.warning(" CORS allows all origins in production!")

        logger.info(" Configuration validation completed")

    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise ConfigurationError(f"Invalid configuration: {e}")
