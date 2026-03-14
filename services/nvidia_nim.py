"""
NVIDIA NIM client factory and helpers.

Provides OpenAI-compatible client for NVIDIA NIM API endpoints.
Supports LLM, vision (base64 images), and reasoning with thinking toggle.
"""

import base64
import os
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI

from utils.logger import get_logger

logger = get_logger(__name__)

NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

_nvidia_client: Optional[OpenAI] = None


def get_nvidia_client(api_key: Optional[str] = None) -> Optional[OpenAI]:
    """Get or create a singleton NVIDIA NIM client."""
    global _nvidia_client
    if _nvidia_client is not None:
        return _nvidia_client

    key = api_key or os.environ.get("NVIDIA_API_KEY")
    if not key:
        logger.warning("NVIDIA_API_KEY not set — NVIDIA NIM provider unavailable")
        return None

    try:
        _nvidia_client = OpenAI(
            base_url=NVIDIA_NIM_BASE_URL, api_key=key, timeout=30.0
        )
        logger.debug("NVIDIA NIM client initialized successfully")
        return _nvidia_client
    except Exception as e:
        logger.warning(f"Failed to initialize NVIDIA NIM client: {e}")
        return None


def encode_image_to_base64(image_data: Union[bytes, str]) -> str:
    """Encode image bytes or file path to base64 string."""
    if isinstance(image_data, str):
        with open(image_data, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return base64.b64encode(image_data).decode("utf-8")


def call_nvidia_chat(
    client: OpenAI,
    model: str,
    prompt: str,
    **kwargs: Any,
) -> str:
    """Call NVIDIA NIM chat completion."""
    messages = kwargs.pop("messages", None) or [{"role": "user", "content": prompt}]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content


def call_nvidia_vision(
    client: OpenAI,
    model: str,
    image_b64: str,
    prompt: str,
    **kwargs: Any,
) -> str:
    """Call NVIDIA NIM vision model with a base64-encoded image."""
    max_tokens = kwargs.pop("max_tokens", 1024)
    temperature = kwargs.pop("temperature", 0.2)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    return response.choices[0].message.content


def call_nvidia_reasoning(
    client: OpenAI,
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    budget_tokens: int = 2048,
    **kwargs: Any,
) -> str:
    """Call NVIDIA NIM with thinking/reasoning mode enabled."""
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    max_tokens = kwargs.pop("max_tokens", 4096)
    temperature = kwargs.pop("temperature", 0.1)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body={
            "thinking": {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            }
        },
        **kwargs,
    )
    return response.choices[0].message.content
