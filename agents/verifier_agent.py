"""
Verifier Agent â€” Post-action state capture and error screen detection.

Goal verification (did the action succeed?) is handled by
ReactiveStepGenerator.generate_next_step(), which assesses the result
in the same VLM call that proposes the next step.
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from services.ui_signature import compute_ui_signature
from utils.logger import get_logger

if TYPE_CHECKING:
    from services.llm import LLMService
    from services.perception_controller import PerceptionController

logger = get_logger(__name__)

# Action-type-aware stabilization delays (seconds).
# ADB returns success when the command is *sent*, not when the UI settles.
# Android animations run 300-500ms; navigations/loads take longer.
ACTION_SETTLE_DELAYS = {
    "tap": 0.8,
    "click": 0.8,
    "press": 0.8,
    "long_press": 0.7,
    "double_tap": 0.8,
    "scroll": 0.5,
    "scroll_down": 0.5,
    "scroll_up": 0.5,
    "swipe": 0.5,
    "type": 0.3,
    "input": 0.3,
    "type_text": 0.3,
    "back": 1.0,
    "home": 1.0,
    "open_app": 3.0,
    "launch_app": 3.0,
}
DEFAULT_STABILIZE_DELAY = 0.8


def get_settle_delay(action_type: str | None = None) -> float:
    """Return the appropriate stabilization delay for an action type."""
    if not action_type:
        return DEFAULT_STABILIZE_DELAY
    return ACTION_SETTLE_DELAYS.get(action_type.lower(), DEFAULT_STABILIZE_DELAY)

ERROR_INDICATORS = [
    "page not found",
    "couldn't load",
    "couldn't connect",
    "network error",
    "try again",
    "something went wrong",
    "no internet",
    "connection error",
    "unfortunately",
    "has stopped",
    "isn't responding",
    "no connection",
]

class VerifierAgent:
    """Captures post-action state and detects error screens."""

    def __init__(self, perception_controller: "PerceptionController", llm_service: Optional["LLMService"] = None):
        self.perception_controller = perception_controller
        self.llm_service = llm_service

    async def capture_post_state(self, intent: Dict[str, Any], action_type: str | None = None) -> Tuple[Any, str, List]:
        """
        Wait for UI to stabilise, then capture post-action screen state.

        Args:
            intent: Current intent dict.
            action_type: The action just executed (tap, scroll, etc.) — used to
                         pick an appropriate settle delay.

        Returns:
            (bundle, post_signature, elements)
        """
        delay = get_settle_delay(action_type)
        logger.debug(f"Verifier: waiting {delay}s for UI to settle after '{action_type or 'unknown'}'")
        await asyncio.sleep(delay)
        bundle = await self.perception_controller.request_perception(
            intent=intent,
            action_type="verify",
            force_screenshot=True,
        )
        elements: List[Dict] = []
        screen_height = None
        if bundle.ui_tree and hasattr(bundle.ui_tree, "elements"):
            elements = bundle.ui_tree.elements or []
            screen_height = getattr(bundle.ui_tree, "screen_height", None)
        post_signature = compute_ui_signature(elements, screen_height=screen_height)
        return bundle, post_signature, elements

    def is_error_screen(self, elements: List[Dict]) -> bool:
        """Return True if any of the first 10 elements signal an error state."""
        for el in elements[:10]:
            combined = (
                f"{(el.get('text') or '').lower()} "
                f"{(el.get('contentDescription') or '').lower()}"
            )
            if any(ind in combined for ind in ERROR_INDICATORS):
                return True
        return False

    async def semantic_verify(self, action_desc: str, elements: List[Dict], success_hint: str = "") -> tuple[bool, str]:
        """
        LLM second-pass: verify semantically that the action produced the expected result.
        Falls back to (True, "no llm") if LLM service is unavailable.

        Returns (passed: bool, reason: str).
        """
        if not self.llm_service:
            return True, "no llm service"
        if not elements:
            return True, "no elements to check"

        # Build a compact element summary (top 15, text + contentDesc only)
        lines = []
        for el in elements[:15]:
            text = (el.get("text") or "").strip()
            desc = (el.get("contentDescription") or "").strip()
            label = text or desc
            if label:
                lines.append(label)

        el_summary = "\n".join(f"- {l}" for l in lines) if lines else "(no text elements)"
        hint_line = f"\nExpected outcome: {success_hint}" if success_hint else ""

        prompt = (
            f"Action just executed: {action_desc}{hint_line}\n\n"
            f"Current screen elements:\n{el_summary}\n\n"
            f"Did this action succeed based on the screen state? "
            f"Answer YES or NO followed by one sentence reason."
        )

        try:
            from concurrent.futures import ThreadPoolExecutor
            from functools import partial
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as ex:
                result = await loop.run_in_executor(
                    ex,
                    partial(self.llm_service.run, prompt, max_tokens=60)
                )
            result = (result or "").strip().upper()
            passed = result.startswith("YES")
            reason = result[:120]
            logger.debug(f"Verifier semantic_verify: {passed} — {reason[:60]}")
            return passed, reason
        except Exception as e:
            logger.warning(f"Verifier semantic_verify failed (non-fatal): {e}")
            return True, "llm check failed"
