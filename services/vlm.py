"""
Vision-Language Model (VLM) service wrapper.

This module provides a unified interface for analyzing images with text prompts
using different VLM providers (Gemini, Groq, NVIDIA NIM) with automatic fallback.
"""

import base64
from io import BytesIO
from typing import Any, Optional, Union

import groq

# Enable Google GenAI for superior vision capabilities
try:
    from google import genai
    from google.genai import types as genai_types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

from PIL import Image  # noqa: E402

from config.settings import Settings  # noqa: E402
from utils.exceptions import ModelProviderError  # noqa: E402
from utils.logger import get_logger  # noqa: E402
from utils.token_tracker import token_tracker  # noqa: E402
from services.command_logger import get_command_logger  # noqa: E402

logger = get_logger(__name__)


class VLMService:
    """
    Service class for Vision-Language Model operations.

    Provides a unified interface for image analysis using different
    VLM providers with automatic fallback and error handling.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the VLM service with configuration settings.

        Args:
            settings: Application settings containing API keys and model configs.
        """
        self.settings = settings
        self.groq_client: Optional[groq.Groq] = None
        self.gemini_client: Optional[Any] = None
        self.nvidia_client: Optional[Any] = None

        # Provider-specific model mappings
        self.provider_models = self._build_provider_models()

        # Initialize clients based on available API keys
        self._initialize_clients()

        logger.info(
            f"VLMService initialized with default provider: {self.settings.default_vlm_provider}"
        )

    def _initialize_clients(self) -> None:
        """Initialize VLM provider clients based on available API keys."""
        # Initialize Groq client (for potential future VLM support)
        if self.settings.groq_api_key and self.settings.groq_api_key != "gsk_...":
            try:
                self.groq_client = groq.Groq(api_key=self.settings.groq_api_key)
                logger.debug("Groq VLM client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq VLM client: {e}")

        # Initialize Gemini client
        if (
            GEMINI_AVAILABLE
            and self.settings.gemini_api_key
            and self.settings.gemini_api_key != "..."
        ):
            try:
                self.gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
                logger.debug("Gemini VLM client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini VLM client: {e}")
        elif not GEMINI_AVAILABLE:
            logger.warning(
                "Gemini VLM not available - google-genai package not installed properly"
            )

        # Initialize NVIDIA NIM client
        if self.settings.nvidia_api_key and (
            self.settings.default_vlm_provider == "nvidia"
            or self.settings.enable_provider_fallback
        ):
            try:
                from services.nvidia_nim import get_nvidia_client
                self.nvidia_client = get_nvidia_client(self.settings.nvidia_api_key)
                if self.nvidia_client:
                    logger.debug("NVIDIA NIM VLM client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NVIDIA NIM VLM client: {e}")

    def _build_provider_models(self) -> dict:
        """
        Map each provider to its correct model.

        The primary provider always uses default_vlm_model.
        Non-primary providers use fallback_vlm_model so that each provider
        calls a model it actually supports, regardless of which is primary.
        The vlm_secondary_model is reserved for NVIDIA NIM (not Groq/Gemini).
        """
        primary = self.settings.default_vlm_provider
        models: dict[str, str] = {}
        for provider in ("gemini", "groq", "nvidia"):
            if provider == primary:
                models[provider] = self.settings.default_vlm_model
            elif provider == "nvidia":
                # NVIDIA always uses vlm_secondary_model (its own model family)
                models[provider] = self.settings.vlm_secondary_model
            else:
                # The other non-primary provider (groq or gemini) uses fallback_vlm_model
                models[provider] = self.settings.fallback_vlm_model
        return models

    def analyze_image(
        self,
        image_data: Union[bytes, str, Image.Image],
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> str:
        """
        Analyze an image with a text prompt using the specified or default VLM provider.

        Args:
            image_data: Image data as bytes, file path string, or PIL Image.
            prompt: Text prompt describing what to analyze in the image.
            provider: Override default provider ('groq' or 'gemini').
            model: Override default model name.
            **kwargs: Additional parameters passed to the VLM service.

        Returns:
            Analysis result from the vision-language model.

        Raises:
            ModelProviderError: If all available providers fail.
        """
        target_provider = provider or self.settings.default_vlm_provider
        target_model = model or self.settings.default_vlm_model

        logger.info(
            f"Analyzing image with provider: {target_provider}, model: {target_model}"
        )

        # Try the specified provider first
        try:
            result = self._call_provider(
                target_provider, target_model, image_data, prompt,
                system_prompt=system_prompt, **kwargs
            )
            logger.debug(f"Image analyzed successfully using {target_provider}")
            return result
        except ModelProviderError as e:
            logger.warning(f"Primary VLM provider {target_provider} failed: {e}")

            # If fallback is enabled, try alternative providers
            if self.settings.enable_provider_fallback:
                fallback_providers = [p for p in ["nvidia", "gemini", "groq"] if p != target_provider]

                for fallback_provider in fallback_providers:
                    try:
                        logger.info(f"Attempting VLM fallback to {fallback_provider}")
                        # Use provider-specific model for fallback
                        fallback_model = self.provider_models.get(
                            fallback_provider, target_model
                        )
                        result = self._call_provider(
                            fallback_provider,
                            fallback_model,
                            image_data,
                            prompt,
                            system_prompt=system_prompt,
                            **kwargs,
                        )
                        logger.info(
                            f"VLM fallback to {fallback_provider} successful with model {fallback_model}"
                        )
                        return result
                    except ModelProviderError as fallback_error:
                        logger.warning(
                            f"VLM fallback provider {fallback_provider} failed: {fallback_error}"
                        )
                        continue

            # If all providers fail, raise the original error
            raise e

    def analyze_two_images(
        self,
        before_b64: str,
        after_b64: str,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Analyze two images together (before/after comparison).
        Passes both images in a single VLM call for delta detection.
        """
        target_provider = provider or self.settings.default_vlm_provider
        target_model = model or self.settings.default_vlm_model

        try:
            if target_provider == "groq":
                return self._call_groq_two_images(target_model, before_b64, after_b64, prompt, temperature=temperature)
            elif target_provider == "gemini":
                return self._call_gemini_two_images(target_model, before_b64, after_b64, prompt, temperature=temperature)
        except Exception as e:
            logger.warning(f"VLM two-image call failed ({e}), falling back to after-image only")
            return self.analyze_image(after_b64, prompt, provider=provider, model=model, temperature=temperature)

    def _call_groq_two_images(self, model: str, before_b64: str, after_b64: str, prompt: str, temperature: float = 0.1) -> str:
        if not self.groq_client:
            raise ModelProviderError("Groq client not initialized", provider="groq",
                                     error_code="CLIENT_NOT_INITIALIZED")
        response = self.groq_client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            max_tokens=512,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _call_gemini_two_images(self, model: str, before_b64: str, after_b64: str, prompt: str, temperature: float = 0.1) -> str:
        if not self.gemini_client:
            raise ModelProviderError("Gemini client not initialized", provider="gemini",
                                     error_code="CLIENT_NOT_INITIALIZED")
        parts = [
            genai_types.Part.from_bytes(data=base64.b64decode(before_b64), mime_type="image/jpeg"),
            genai_types.Part.from_bytes(data=base64.b64decode(after_b64), mime_type="image/jpeg"),
            genai_types.Part.from_text(text=prompt),
        ]
        config = genai_types.GenerateContentConfig(temperature=temperature) if genai_types is not None else None
        response = self.gemini_client.models.generate_content(
            model=model,
            contents=genai_types.Content(role="user", parts=parts),
            config=config,
        )
        return response.text or ""

    def _call_provider(
        self,
        provider: str,
        model: str,
        image_data: Union[bytes, str, Image.Image],
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """
        Call a specific VLM provider with error handling.

        Args:
            provider: Provider name ('groq' or 'gemini').
            model: Model name to use.
            image_data: Image data to analyze.
            prompt: Analysis prompt.
            **kwargs: Additional parameters.

        Returns:
            Analysis result.

        Raises:
            ModelProviderError: If the provider call fails.
        """
        try:
            # Extract agent name before forwarding kwargs to provider APIs
            _caller_agent = kwargs.pop("agent", None)
            if provider == "gemini":
                return self._call_gemini(model, image_data, prompt, _caller_agent=_caller_agent, **kwargs)
            elif provider == "groq":
                return self._call_groq(model, image_data, prompt, _caller_agent=_caller_agent, **kwargs)
            elif provider == "nvidia":
                return self._call_nvidia(model, image_data, prompt, _caller_agent=_caller_agent, **kwargs)
            else:
                raise ModelProviderError(
                    f"Unsupported VLM provider: {provider}",
                    provider=provider,
                    error_code="UNSUPPORTED_PROVIDER",
                )
        except Exception as e:
            if isinstance(e, ModelProviderError):
                raise e

            raise ModelProviderError(
                f"VLM provider {provider} failed: {str(e)}",
                provider=provider,
                model=model,
                error_code="PROVIDER_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _call_gemini(
        self,
        model: str,
        image_data: Union[bytes, str, Image.Image],
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """
        Call Gemini VLM provider.

        Args:
            model: Gemini VLM model name.
            image_data: Image data in various formats.
            prompt: Analysis prompt.
            **kwargs: Additional parameters.

        Returns:
            Analysis result.

        Raises:
            ModelProviderError: If Gemini VLM call fails.
        """
        if not self.gemini_client:
            raise ModelProviderError(
                "Gemini VLM client not initialized. Check API key configuration.",
                provider="gemini",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        _caller_agent = kwargs.pop("_caller_agent", None)
        # Strip kwargs that Gemini generate_content() does not accept
        system_prompt = kwargs.pop("system_prompt", "")
        # temperature / max_tokens must go into GenerateContentConfig, not as top-level kwargs
        _temperature = kwargs.pop("temperature", None)
        _max_tokens = kwargs.pop("max_tokens", None)

        try:
            # Convert image data to PIL Image if needed
            image = self._prepare_image_for_gemini(image_data)

            # Save VLM input image to HTML log
            _vlm_screenshot_path = ""
            try:
                import base64 as _b64
                _cmd = get_command_logger()
                if isinstance(image_data, bytes):
                    _vlm_screenshot_path = _cmd.log_screenshot("vlm_input_gemini", _b64.b64encode(image_data).decode())
                elif isinstance(image_data, str):
                    # image_data is base64 — log it directly (not a file path)
                    _vlm_screenshot_path = _cmd.log_screenshot("vlm_input_gemini", image_data)
                elif hasattr(image_data, "width"):
                    from io import BytesIO as _BIO
                    _buf = _BIO()
                    image_data.save(_buf, format="PNG")
                    _vlm_screenshot_path = _cmd.log_screenshot("vlm_input_gemini", _b64.b64encode(_buf.getvalue()).decode())
                else:
                    _vlm_screenshot_path = ""
            except Exception:
                _vlm_screenshot_path = ""

            # Generate content with image and prompt
            # The new Google GenAI SDK accepts PIL Images directly
            # Build optional GenerateContentConfig for supported params
            _gen_config = None
            if _temperature is not None or _max_tokens is not None or system_prompt:
                try:
                    from google.genai import types as _gtypes
                    _cfg_kwargs: dict = {}
                    if _temperature is not None:
                        _cfg_kwargs["temperature"] = _temperature
                    if _max_tokens is not None:
                        _cfg_kwargs["max_output_tokens"] = _max_tokens
                    if system_prompt:
                        _cfg_kwargs["system_instruction"] = system_prompt
                    _gen_config = _gtypes.GenerateContentConfig(**_cfg_kwargs)
                except Exception:
                    pass  # Config construction is best-effort

            response = self.gemini_client.models.generate_content(
                model=model,
                contents=[prompt, image],
                config=_gen_config,
                **{k: v for k, v in kwargs.items() if k not in ("config",)},
            )

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
                    f"📊 VLM Token Usage (Gemini) - Prompt: {usage.prompt_token_count}, "
                    f"Completion: {usage.candidates_token_count}, "
                    f"Total: {usage.total_token_count}"
                )
                # Track in global tracker
                token_tracker.track(
                    agent="vlm_service",
                    model_type="vlm",
                    provider="gemini",
                    model=model,
                    prompt_tokens=usage.prompt_token_count,
                    completion_tokens=usage.candidates_token_count,
                    total_tokens=usage.total_token_count,
                )
            
            # Log VLM call to command logger
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response.text or "",
                provider="gemini",
                model=model,
                agent=_caller_agent,
                token_usage=token_usage,
                is_vlm=True,
                metadata={
                    "has_image": True,
                    "image_type": "bytes" if isinstance(image_data, bytes) else ("file_path" if isinstance(image_data, str) else "pil_image"),
                    "image_size_bytes": len(image_data) if isinstance(image_data, bytes) else None,
                    "image_path": image_data if isinstance(image_data, str) else None,
                    "image_dimensions": f"{image_data.width}x{image_data.height}" if hasattr(image_data, "width") else None,
                    "screenshot_saved_path": _vlm_screenshot_path,
                }
            )

            return response.text or ""
        except Exception as e:
            raise ModelProviderError(
                f"Gemini VLM API call failed: {str(e)}",
                provider="gemini",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _call_groq(
        self,
        model: str,
        image_data: Union[bytes, str, Image.Image],
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """
        Call Groq VLM provider with vision model support and intelligent fallback.

        Args:
            model: Groq VLM model name (e.g., 'meta-llama/llama-4-scout-17b-16e-instruct').
            image_data: Image data in various formats.
            prompt: Analysis prompt.
            **kwargs: Additional parameters.

        Returns:
            Analysis result.

        Raises:
            ModelProviderError: If Groq VLM call fails.
        """
        if not self.groq_client:
            raise ModelProviderError(
                "Groq VLM client not initialized. Check API key configuration.",
                provider="groq",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        _caller_agent = kwargs.pop("_caller_agent", None)
        system_prompt = kwargs.pop("system_prompt", "")

        # Convert image data to base64 format required by Groq
        base64_image = self._prepare_image_for_groq(image_data)

        # Save VLM input image to HTML log
        _vlm_screenshot_path = ""
        try:
            _vlm_screenshot_path = get_command_logger().log_screenshot(
                label="vlm_input_groq",
                base64_data=base64_image,
                ext="jpg",
            )
        except Exception:
            pass

        try:
            # System message carries static rules (cached by Groq at 50% token cost).
            # User message carries the dynamic context (screenshot + screen data).
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            })

            # Make the API call with vision model
            chat_completion = self.groq_client.chat.completions.create(
                messages=messages,
                model=model,
                max_tokens=kwargs.get("max_tokens", 512),
                temperature=kwargs.get("temperature", 0.2),
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k not in ["max_tokens", "temperature", "thinking"]
                },
            )

            # Log token usage
            token_usage = None
            if hasattr(chat_completion, "usage") and chat_completion.usage:
                usage = chat_completion.usage
                token_usage = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                }
                logger.info(
                    f"📊 VLM Token Usage - Prompt: {usage.prompt_tokens}, "
                    f"Completion: {usage.completion_tokens}, "
                    f"Total: {usage.total_tokens}"
                )
                # Track in global tracker
                token_tracker.track(
                    agent="vlm_service",
                    model_type="vlm",
                    provider="groq",
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                )
            
            response_text = chat_completion.choices[0].message.content
            
            # Log VLM call to command logger
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response_text,
                provider="groq",
                model=model,
                agent=_caller_agent,
                token_usage=token_usage,
                is_vlm=True,
                metadata={
                    "has_image": True,
                    "image_type": "bytes" if isinstance(image_data, bytes) else ("file_path" if isinstance(image_data, str) else "pil_image"),
                    "image_size_bytes": len(image_data) if isinstance(image_data, bytes) else None,
                    "image_path": image_data if isinstance(image_data, str) else None,
                    "image_dimensions": f"{image_data.width}x{image_data.height}" if hasattr(image_data, "width") else None,
                    "screenshot_saved_path": _vlm_screenshot_path,
                }
            )

            return response_text

        except Exception as e:
            raise ModelProviderError(
                f"Groq VLM API call failed: {str(e)}",
                provider="groq",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _call_nvidia(
        self,
        model: str,
        image_data: Union[bytes, str, Image.Image],
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """Call NVIDIA NIM VLM provider with base64-encoded image."""
        if not self.nvidia_client:
            raise ModelProviderError(
                "NVIDIA NIM VLM client not initialized. Check NVIDIA_API_KEY.",
                provider="nvidia",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        _caller_agent = kwargs.pop("_caller_agent", None)

        try:
            # Reuse Groq's base64 preparation (same format)
            base64_image = self._prepare_image_for_groq(image_data)

            # Save VLM input image to HTML log
            _vlm_screenshot_path = ""
            try:
                _vlm_screenshot_path = get_command_logger().log_screenshot(
                    label="vlm_input_nvidia",
                    base64_data=base64_image,
                    ext="jpg",
                )
            except Exception:
                pass

            # Strip provider prefix if present (e.g., "nvidia/model-name" -> "model-name")
            actual_model = model.split("/")[1] if "/" in model else model

            from services.nvidia_nim import call_nvidia_vision
            response_text = call_nvidia_vision(
                self.nvidia_client, actual_model, base64_image, prompt, **kwargs
            )

            # Log VLM call
            cmd_logger = get_command_logger()
            cmd_logger.log_llm_call(
                prompt=prompt,
                response=response_text,
                provider="nvidia",
                model=model,
                agent=_caller_agent,
                is_vlm=True,
                metadata={
                    "has_image": True,
                    "image_type": "bytes" if isinstance(image_data, bytes) else ("file_path" if isinstance(image_data, str) else "pil_image"),
                    "image_size_bytes": len(image_data) if isinstance(image_data, bytes) else None,
                    "image_path": image_data if isinstance(image_data, str) else None,
                    "image_dimensions": f"{image_data.width}x{image_data.height}" if hasattr(image_data, "width") else None,
                    "screenshot_saved_path": _vlm_screenshot_path,
                },
            )

            return response_text
        except Exception as e:
            if isinstance(e, ModelProviderError):
                raise e
            raise ModelProviderError(
                f"NVIDIA NIM VLM API call failed: {str(e)}",
                provider="nvidia",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _prepare_image_for_gemini(
        self, image_data: Union[bytes, str, Image.Image]
    ) -> Image.Image:
        """
        Prepare image data for Gemini API consumption.

        Args:
            image_data: Image in various formats.

        Returns:
            PIL Image object ready for Gemini API.

        Raises:
            ModelProviderError: If image preparation fails.
        """
        try:
            if isinstance(image_data, Image.Image):
                return image_data
            elif isinstance(image_data, bytes):
                # Convert bytes to PIL Image
                return Image.open(BytesIO(image_data))
            elif isinstance(image_data, str):
                # Check if it's base64, URL, or file path
                if image_data.startswith("data:image"):
                    # Data URL format
                    base64_data = image_data.split(",")[1]
                    image_bytes = base64.b64decode(base64_data)
                    return Image.open(BytesIO(image_bytes))
                elif image_data.startswith(("http://", "https://")):
                    # URL - download it (with SSRF protection)
                    import requests
                    from utils.url_validation import validate_image_url

                    validate_image_url(image_data)
                    response = requests.get(image_data, timeout=10)
                    response.raise_for_status()
                    return Image.open(BytesIO(response.content))
                else:
                    # Try base64 first (any length), then file path
                    try:
                        image_bytes = base64.b64decode(image_data)
                        return Image.open(BytesIO(image_bytes))
                    except Exception:
                        # Not valid base64 image, try as file path
                        import os

                        if os.path.exists(image_data):
                            return Image.open(image_data)
                        else:
                            raise ValueError(
                                "Invalid image data: not valid base64 or existing file"
                            )
            else:
                raise ValueError(f"Unsupported image data type: {type(image_data)}")
        except Exception as e:
            raise ModelProviderError(
                f"Failed to prepare image for Gemini: {str(e)}",
                provider="gemini",
                error_code="IMAGE_PREPARATION_FAILED",
                context={"original_error": str(e)},
            )

    def _prepare_image_for_groq(
        self, image_data: Union[bytes, str, Image.Image]
    ) -> str:
        """
        Prepare image data for Groq API consumption (base64 encoding).

        Args:
            image_data: Image in various formats (URL, file path, bytes, or PIL Image).

        Returns:
            Base64 encoded string ready for Groq VLM API.

        Raises:
            ModelProviderError: If image preparation fails.
        """
        try:
            # Convert to PIL Image first
            if isinstance(image_data, Image.Image):
                pil_image = image_data
            elif isinstance(image_data, bytes):
                pil_image = Image.open(BytesIO(image_data))
            elif isinstance(image_data, str):
                # Check if it's already base64 data, URL, or file path
                if image_data.startswith("data:image"):
                    # Data URL format: data:image/png;base64,iVBORw0KGgo...
                    base64_data = image_data.split(",")[1]
                    image_bytes = base64.b64decode(base64_data)
                    pil_image = Image.open(BytesIO(image_bytes))
                elif image_data.startswith(("http://", "https://")):
                    # Download image from URL (with SSRF protection)
                    import requests
                    from utils.url_validation import validate_image_url

                    validate_image_url(image_data)
                    response = requests.get(image_data, timeout=10)
                    response.raise_for_status()
                    pil_image = Image.open(BytesIO(response.content))
                else:
                    # Try base64 first (any length), then file path
                    try:
                        image_bytes = base64.b64decode(image_data)
                        pil_image = Image.open(BytesIO(image_bytes))
                    except Exception:
                        # Not valid base64 image, try as file path
                        import os

                        if os.path.exists(image_data):
                            pil_image = Image.open(image_data)
                        else:
                            raise ValueError(
                                "Invalid image data: not valid base64 or existing file"
                            )
            else:
                raise ValueError(f"Unsupported image data type: {type(image_data)}")

            # Convert PIL Image to base64
            buffered = BytesIO()

            # Convert to RGB if necessary (for JPEG compatibility)
            if pil_image.mode in ("RGBA", "P"):
                pil_image = pil_image.convert("RGB")

            # Downscale to reduce TTFT — image encoding dominates VLM latency
            max_dim = 1024
            w, h = pil_image.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                pil_image = pil_image.resize(
                    (int(w * scale), int(h * scale)), Image.LANCZOS
                )

            # Save as JPEG and encode to base64
            pil_image.save(buffered, format="JPEG", quality=95)
            img_bytes = buffered.getvalue()

            return base64.b64encode(img_bytes).decode("utf-8")

        except Exception as e:
            raise ModelProviderError(
                f"Failed to prepare image for Groq: {str(e)}",
                provider="groq",
                error_code="IMAGE_PREPARATION_FAILED",
                context={"original_error": str(e)},
            )
