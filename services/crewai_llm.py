"""
CrewAI LLM integration supporting multiple providers.

This module provides LLM integration for CrewAI agents with support for:
- Groq (groq/* and openai/* models hosted on Groq)
- Gemini (gemini/* models)

Automatically selects the correct API key based on model prefix.
"""

import os

from crewai import LLM

from services.llm import LLMService
from utils.logger import get_logger

logger = get_logger(__name__)


def create_crewai_llm(llm_service: LLMService) -> LLM:
    """
    Create a CrewAI-compatible LLM instance supporting both Groq and Gemini.

    Automatically selects the correct API key based on model prefix:
    - groq/* models use GROQ_API_KEY
    - gemini/* models use GEMINI_API_KEY

    Args:
        llm_service: Our configured LLM service (used to get settings).

    Returns:
        CrewAI LLM instance configured for the specified provider.
    """
    try:
        model = llm_service.settings.crewai_model

        # Determine provider from model prefix
        is_gemini = model.startswith("gemini/")

        # Select appropriate API key
        # openai/* models on Groq and groq/* models both use GROQ_API_KEY
        if is_gemini:
            api_key = llm_service.settings.gemini_api_key
            if not api_key or api_key.startswith("AIza") is False:
                logger.error(
                    "❌ GEMINI_API_KEY is not properly configured in .env file!"
                )
                raise ValueError("GEMINI_API_KEY not configured - check .env file")
            os.environ["GEMINI_API_KEY"] = api_key
            logger.info(f"Using Gemini API key for model: {model}")
        else:  # Default to Groq
            api_key = llm_service.settings.groq_api_key
            if not api_key or api_key == "gsk_...":
                logger.error("❌ GROQ_API_KEY is not properly configured in .env file!")
                raise ValueError("GROQ_API_KEY not configured - check .env file")
            os.environ["GROQ_API_KEY"] = api_key
            logger.info(f"Using Groq API key for model: {model}")

        # Remove conflicting keys from environment
        for key in ["OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_ORG_ID"]:
            if key in os.environ:
                del os.environ[key]
                logger.debug(f"Removed {key} from environment")

        # Create LLM instance with appropriate configuration
        llm = LLM(
            model=model,
            temperature=0.3,
            max_tokens=512,  # Reduced from 2048 for 80% token savings (actual usage: 10-150 tokens)
            top_p=0.9,
            stop=None,
            stream=False,
            api_key=api_key,
            timeout=60.0,
            base_url=None,
        )

        logger.info(
            f"✅ CrewAI LLM configured with {model} (API key length: {len(api_key)})"
        )
        logger.debug(f"LLM Model: {model}, max_tokens: 512, temperature: 0.3")
        return llm

    except Exception as e:
        logger.error(f"Failed to create CrewAI LLM: {e}")

        # Try fallback configuration
        try:
            fallback_llm = LLM(
                model=llm_service.settings.crewai_model,
                api_key=api_key,
            )
            logger.warning("Using fallback LLM configuration")
            return fallback_llm
        except Exception as fallback_error:
            logger.error(f"Fallback LLM creation also failed: {fallback_error}")
            raise
