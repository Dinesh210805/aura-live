"""
Prompt Guard — lightweight safety screening for voice command inputs.

Uses Llama Prompt Guard 2 86M via Groq to detect prompt injection
and jailbreak attempts. Runs BEFORE CommanderAgent receives transcribed text.

Gracefully skips if Groq API key is not configured.
"""

from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class PromptGuard:
    """Screen voice inputs for unsafe content via Llama Prompt Guard 2 on Groq."""

    MODEL = "meta-llama/llama-prompt-guard-2-86m"

    # Labels returned by Prompt Guard 2 86M
    SAFE_LABELS = {"benign", "safe"}
    UNSAFE_LABELS = {"injection", "jailbreak", "unsafe"}

    def __init__(self, client: Optional[object] = None, model: Optional[str] = None) -> None:
        self.client = client
        self.model = model or self.MODEL
        if not self.client:
            logger.warning(
                "PromptGuard initialized without client — safety checks disabled"
            )

    @property
    def available(self) -> bool:
        return self.client is not None

    def is_safe(self, user_input: str) -> Tuple[bool, float]:
        """Return (is_safe, confidence). Defaults to safe on failure."""
        if not self.client:
            return True, 0.5

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": user_input}],
                max_tokens=20,
                temperature=0.0,
            )
            result = response.choices[0].message.content.strip().lower()
            # Prompt Guard 2 86M returns "BENIGN", "INJECTION", or "JAILBREAK"
            # Llama Guard 4 returns "safe" or "unsafe" — handle both
            is_safe = any(label in result for label in self.SAFE_LABELS)
            is_unsafe = any(label in result for label in self.UNSAFE_LABELS)
            if is_safe:
                return True, 1.0
            if is_unsafe:
                logger.warning(f"PromptGuard classification: {result}")
                return False, 1.0
            # Unknown label — default to safe to avoid false blocks
            logger.warning(f"PromptGuard unknown response: '{result}', defaulting to safe")
            return True, 0.3
        except Exception as e:
            logger.warning(f"PromptGuard check failed — defaulting to safe: {e}")
            return True, 0.5

    def check_or_raise(self, user_input: str) -> str:
        """Return input unchanged if safe, raise ValueError if flagged."""
        safe, confidence = self.is_safe(user_input)
        if not safe:
            logger.warning(f"🚫 PromptGuard blocked input (confidence={confidence})")
            raise ValueError(
                "[PromptGuard] Input flagged as potential injection attempt. Blocked."
            )
        return user_input


_prompt_guard: Optional[PromptGuard] = None


def get_prompt_guard() -> PromptGuard:
    """Get the singleton PromptGuard instance."""
    global _prompt_guard
    if _prompt_guard is None:
        _prompt_guard = PromptGuard()
    return _prompt_guard


def initialize_prompt_guard(client: Optional[object] = None, model: Optional[str] = None) -> PromptGuard:
    """Initialize the singleton PromptGuard with a Groq client."""
    global _prompt_guard
    _prompt_guard = PromptGuard(client, model=model)
    return _prompt_guard
