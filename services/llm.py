"""
Large Language Model (LLM) service wrapper.

This module provides a unified interface for interacting with different
LLM providers (Groq, Gemini, NVIDIA NIM) with automatic fallback and error handling.
"""

from typing import Any, Optional

import groq

try:
    from google import genai
    from google.genai import types as genai_types

    GEMINI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Google GenAI not available: {e}")
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

from config.settings import Settings
from utils.exceptions import ModelProviderError
from utils.logger import get_logger
from utils.token_tracker import token_tracker
from services.command_logger import get_command_logger

logger = get_logger(__name__)


class LLMService:
    """
    Service class for Large Language Model operations.

    Provides a unified interface for text generation using different
    LLM providers with automatic fallback and error handling.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the LLM service with configuration settings.

        Args:
            settings: Application settings containing API keys and model configs.
        """
        self.settings = settings
        self.groq_client: Optional[groq.Groq] = None
        self.gemini_client: Optional[Any] = None
        self.nvidia_client: Optional[Any] = None

        # Initialize clients based on available API keys
        self._initialize_clients()

        logger.info(
            f"LLMService initialized with default provider: {self.settings.default_llm_provider}"
        )

    def _initialize_clients(self) -> None:
        """Initialize AI provider clients based on available API keys."""
        # Initialize Groq client
        if self.settings.groq_api_key and self.settings.groq_api_key != "gsk_...":
            try:
                self.groq_client = groq.Groq(api_key=self.settings.groq_api_key)
                logger.debug("Groq client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}")

        # Initialize Gemini client if it may be used (default providers, planning provider, or fallback)
        if (
            GEMINI_AVAILABLE
            and (
                self.settings.default_llm_provider == "gemini"
                or self.settings.default_vlm_provider == "gemini"
                or self.settings.planning_provider == "gemini"
                or self.settings.enable_provider_fallback
            )
            and self.settings.gemini_api_key
            and self.settings.gemini_api_key != "..."
        ):
            try:
                self.gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
                logger.debug("Gemini client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        elif not GEMINI_AVAILABLE:
            logger.warning(
                "Gemini LLM not available - google-genai package not installed properly"
            )

        # Initialize NVIDIA NIM client
        if (
            self.settings.nvidia_api_key
            and (
                self.settings.default_llm_provider == "nvidia"
                or self.settings.default_vlm_provider == "nvidia"
                or self.settings.planning_provider == "nvidia"
                or self.settings.enable_provider_fallback
            )
        ):
            try:
                from services.nvidia_nim import get_nvidia_client
                self.nvidia_client = get_nvidia_client(self.settings.nvidia_api_key)
                if self.nvidia_client:
                    logger.debug("NVIDIA NIM client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NVIDIA NIM client: {e}")

    def run(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using the specified or default LLM provider.

        Args:
            prompt: Input text prompt for the model.
            provider: Override default provider ('groq' or 'gemini').
            model: Override default model name.
            **kwargs: Additional parameters passed to the model.

        Returns:
            Generated text response from the model.

        Raises:
            ModelProviderError: If all available providers fail.
        """
        target_provider = provider or self.settings.default_llm_provider
        target_model = model or self.settings.default_llm_model

        # Guard against mismatched provider/model strings coming from env overrides
        target_model = self._normalize_model_for_provider(target_provider, target_model)

        logger.info(
            f"Running LLM with provider: {target_provider}, model: {target_model}"
        )

        # Try the specified provider first
        try:
            response = self._call_provider(
                target_provider, target_model, prompt, **kwargs
            )
            logger.debug(f"LLM response generated successfully using {target_provider}")
            return response
        except ModelProviderError as e:
            logger.warning(f"Primary provider {target_provider} failed: {e}")

            # If fallback is enabled, try alternative providers
            if self.settings.enable_provider_fallback:
                fallback_providers = [p for p in ["groq", "nvidia", "gemini"] if p != target_provider]

                for fallback_provider in fallback_providers:
                    try:
                        logger.info(f"Attempting fallback to {fallback_provider}")

                        # Use provider-appropriate model
                        if fallback_provider == "groq":
                            fallback_model = self.settings.llm_fallback_model or self.settings.default_llm_model
                        elif fallback_provider == "gemini":
                            fallback_model = self.settings.planning_fallback_model or self.settings.fallback_vlm_model
                        else:  # nvidia
                            fallback_model = self.settings.planning_model
                        fallback_model = self._normalize_model_for_provider(
                            fallback_provider, fallback_model
                        )

                        response = self._call_provider(
                            fallback_provider, fallback_model, prompt, **kwargs
                        )
                        logger.info(
                            f"✅ Fallback to {fallback_provider} succeeded with model {fallback_model}"
                        )
                        return response
                    except ModelProviderError as fallback_error:
                        logger.warning(
                            f"Fallback provider {fallback_provider} failed: {fallback_error}"
                        )
                        continue

            # If all providers fail, raise the original error
            raise e

    def _call_provider(
        self, provider: str, model: str, prompt: str, **kwargs: Any
    ) -> str:
        """
        Call a specific LLM provider with error handling.

        Args:
            provider: Provider name ('groq' or 'gemini').
            model: Model name to use.
            prompt: Input prompt.
            **kwargs: Additional model parameters.

        Returns:
            Generated text response.

        Raises:
            ModelProviderError: If the provider call fails.
        """
        try:
            if provider == "groq":
                return self._call_groq(model, prompt, **kwargs)
            elif provider == "gemini":
                return self._call_gemini(model, prompt, **kwargs)
            elif provider == "nvidia":
                return self._call_nvidia(model, prompt, **kwargs)
            else:
                raise ModelProviderError(
                    f"Unsupported provider: {provider}",
                    provider=provider,
                    error_code="UNSUPPORTED_PROVIDER",
                )
        except Exception as e:
            if isinstance(e, ModelProviderError):
                raise e

            error_msg = f"Provider {provider} failed: {str(e)}"
            logger.error(error_msg, exc_info=True if logger.level <= 10 else False)
            raise ModelProviderError(
                error_msg,
                provider=provider,
                model=model,
                error_code="PROVIDER_CALL_FAILED",
                context={"original_error": str(e), "error_type": type(e).__name__},
            )

    def _call_groq(self, model: str, prompt: str, **kwargs: Any) -> str:
        """
        Call Groq LLM provider.

        Args:
            model: Groq model name.
            prompt: Input prompt.
            **kwargs: Additional parameters.

        Returns:
            Generated text response.

        Raises:
            ModelProviderError: If Groq call fails.
        """
        if not self.groq_client:
            raise ModelProviderError(
                "Groq client not initialized. Check API key configuration.",
                provider="groq",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        try:
            # Remove NVIDIA-specific parameters that Groq doesn't support
            kwargs.pop("thinking", None)
            
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("tools", None)
            
            create_params = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }

            create_params.update(kwargs)
            response = self.groq_client.chat.completions.create(**create_params)

            response_text = response.choices[0].message.content

            # Log token usage
            token_usage = None
            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                token_usage = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                }
                logger.info(
                    f"📊 LLM Token Usage - Prompt: {usage.prompt_tokens}, "
                    f"Completion: {usage.completion_tokens}, "
                    f"Total: {usage.total_tokens}"
                )
                # Track in global tracker
                token_tracker.track(
                    agent="llm_service",
                    model_type="llm",
                    provider="groq",
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                )
            
            # Log LLM call to command logger
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response_text,
                provider="groq",
                model=model,
                token_usage=token_usage,
                metadata={"kwargs": kwargs}
            )

            return response_text
        except Exception as e:
            raise ModelProviderError(
                f"Groq API call failed: {str(e)}",
                provider="groq",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _call_gemini(self, model: str, prompt: str, **kwargs: Any) -> str:
        """
        Call Gemini LLM provider.

        Args:
            model: Gemini model name.
            prompt: Input prompt.
            **kwargs: Additional parameters.

        Returns:
            Generated text response.

        Raises:
            ModelProviderError: If Gemini call fails.
        """
        if not self.gemini_client:
            raise ModelProviderError(
                "Gemini client not initialized. Check API key configuration.",
                provider="gemini",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        try:
            config_params = {}
            if "max_tokens" in kwargs:
                config_params["max_output_tokens"] = kwargs.pop("max_tokens")
            if "temperature" in kwargs:
                config_params["temperature"] = kwargs.pop("temperature")
            if "top_p" in kwargs:
                config_params["top_p"] = kwargs.pop("top_p")
            # Strip Groq-specific parameters
            kwargs.pop("response_format", None)
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("tools", None)

            # Create config object if we have parameters
            config = None
            if config_params and genai_types is not None:
                config = genai_types.GenerateContentConfig(**config_params)

            response = self.gemini_client.models.generate_content(
                model=model, contents=prompt, config=config
            )
            
            response_text = response.text

            # Log token usage (Gemini uses usage_metadata)
            token_usage = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = response.usage_metadata
                token_usage = {
                    "prompt_tokens": usage.prompt_token_count,
                    "completion_tokens": usage.candidates_token_count,
                    "total_tokens": usage.total_token_count
                }
                logger.info(
                    f"📊 LLM Token Usage (Gemini) - Prompt: {usage.prompt_token_count}, "
                    f"Completion: {usage.candidates_token_count}, "
                    f"Total: {usage.total_token_count}"
                )
                # Track in global tracker
                token_tracker.track(
                    agent="llm_service",
                    model_type="llm",
                    provider="gemini",
                    model=model,
                    prompt_tokens=usage.prompt_token_count,
                    completion_tokens=usage.candidates_token_count,
                    total_tokens=usage.total_token_count,
                )
            
            # Log LLM call to command logger
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response_text,
                provider="gemini",
                model=model,
                token_usage=token_usage,
                metadata={"config_params": config_params}
            )

            return response_text
        except Exception as e:
            raise ModelProviderError(
                f"Gemini API call failed: {str(e)}",
                provider="gemini",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _call_nvidia(self, model: str, prompt: str, **kwargs: Any) -> str:
        """Call NVIDIA NIM LLM provider via OpenAI-compatible API."""
        if not self.nvidia_client:
            raise ModelProviderError(
                "NVIDIA NIM client not initialized. Check NVIDIA_API_KEY.",
                provider="nvidia",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        try:
            from services.nvidia_nim import call_nvidia_chat

            # Strip provider prefix if present (e.g., "nvidia/model-name" -> "model-name")
            actual_model = model.split("/")[1] if "/" in model else model

            # Strip Groq-specific parameters that NVIDIA NIM doesn't support
            kwargs.pop("response_format", None)
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("tools", None)

            # Extract thinking params if present
            thinking = kwargs.pop("thinking", None)
            # nemotron-3-nano-30b-a3b returns None in plain chat — always use thinking
            if not thinking and "nemotron-3-nano" in actual_model:
                thinking = {"budget_tokens": 1024}
            if thinking:
                from services.nvidia_nim import call_nvidia_reasoning
                response_text = call_nvidia_reasoning(
                    self.nvidia_client, actual_model, prompt,
                    budget_tokens=thinking.get("budget_tokens", 2048),
                    **kwargs,
                )
            else:
                response_text = call_nvidia_chat(
                    self.nvidia_client, actual_model, prompt, **kwargs
                )

            # Log to command logger
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response_text,
                provider="nvidia",
                model=model,
                metadata={"kwargs": kwargs},
            )

            return response_text
        except Exception as e:
            if isinstance(e, ModelProviderError):
                raise e
            raise ModelProviderError(
                f"NVIDIA NIM API call failed: {str(e)}",
                provider="nvidia",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _normalize_model_for_provider(self, provider: str, model: str) -> str:
        """Ensure the model string matches the provider (handles bad env overrides)."""
        if not model:
            return model

        provider_lower = (provider or "").lower()
        model_str = str(model)

        # Groq models should not be used with Gemini provider
        if provider_lower == "gemini" and (model_str.startswith("groq/") or model_str.startswith("llama") or model_str.startswith("nvidia/") or model_str.startswith("meta/")):
            corrected = self.settings.planning_fallback_model
            logger.warning(
                f"Model '{model_str}' incompatible with provider gemini; using '{corrected}'"
            )
            return corrected

        # Gemini/NVIDIA models should not be used with Groq provider
        if provider_lower == "groq" and (model_str.startswith("gemini") or model_str.startswith("nvidia/") or model_str.startswith("meta/")):
            corrected = self.settings.default_llm_model
            logger.warning(
                f"Model '{model_str}' incompatible with provider groq; using '{corrected}'"
            )
            return corrected

        # Groq/Gemini models should not be used with NVIDIA provider
        if provider_lower == "nvidia" and (model_str.startswith("gemini") or model_str.startswith("llama-") or model_str.startswith("groq/")):
            corrected = self.settings.planning_model
            logger.warning(
                f"Model '{model_str}' incompatible with provider nvidia; using '{corrected}'"
            )
            return corrected

        return model_str
