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

# ── String-based error indicators ─────────────────────────────────────────
# Grouped by category so new entries are easy to find and add.
ERROR_INDICATORS = [
    # App crashes
    "unfortunately",
    "has stopped",
    "isn't responding",
    "keeps stopping",
    "app has stopped",
    "not responding",
    # Connectivity
    "no internet",
    "no connection",
    "network error",
    "connection error",
    "couldn't connect",
    "unable to connect",
    "couldn't reach",
    "check your connection",
    "connection timed out",
    "timed out",
    # Load / server failures
    "couldn't load",
    "failed to load",
    "something went wrong",
    "went wrong",
    "error occurred",
    "request failed",
    "server error",
    "service unavailable",
    "temporarily unavailable",
    "not available",
    # Retry prompts
    "try again",
    "please try again",
    # WebView HTTP errors (appear as inline text on error pages)
    "page not found",
    "404 not found",
    "500 internal",
    "502 bad gateway",
    "503 service",
    # Soft error phrases
    "oops",
    "uh oh",
    "whoops",
]

# ── Structural error signals ───────────────────────────────────────────────
# Class names whose presence strongly suggests a crash/error overlay.
_ERROR_CLASS_FRAGMENTS = [
    "errordialog",
    "crashdialog",
    "alertdialog",
]

# A "retry" button label combined with low content density = error screen.
_RETRY_LABELS = {"retry", "try again", "reload", "refresh", "reconnect"}

# Minimum number of substantive (text-bearing) elements expected on a real
# screen. If the element count is lower AND no "intentionally minimal"
# indicators are present, we treat it as a crash/blank.
_MIN_REAL_SCREEN_ELEMENTS = 4

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
        """
        Return True if the current screen is in an error / crash state.

        Uses three independent detection strategies in priority order:

        1. String match — scan element labels for known error phrases.
           Scans ALL elements (not just top 10) so errors buried in scroll
           containers are also caught.

        2. Structural — class name fragments that signal crash/error dialogs
           (AlertDialog, CrashDialog, etc.).

        3. Low-density + retry button — very few text elements AND at least
           one "retry"-family button label ⟹ network/loading error screen
           even if none of the phrases above matched (e.g. custom branded
           error screens that say "Something broke, tap below" in a graphic).
        """
        if not elements:
            return False

        text_bearing_count = 0
        retry_button_present = False

        for el in elements:
            text = (el.get("text") or "").strip().lower()
            desc = (el.get("contentDescription") or "").strip().lower()
            class_name = (el.get("className") or "").lower()
            combined = f"{text} {desc}"

            # Strategy 1: string match
            if any(ind in combined for ind in ERROR_INDICATORS):
                return True

            # Strategy 2: error/crash dialog class name
            if any(frag in class_name for frag in _ERROR_CLASS_FRAGMENTS):
                return True

            # Accumulators for strategy 3
            label = text or desc
            if label:
                text_bearing_count += 1
                if label in _RETRY_LABELS:
                    retry_button_present = True

        # Strategy 3: sparse screen + retry button
        if retry_button_present and text_bearing_count < _MIN_REAL_SCREEN_ELEMENTS:
            return True

        return False

    async def semantic_verify(self, action_desc: str, elements: List[Dict], success_hint: str = "") -> tuple[bool, str]:
        """
        LLM second-pass: verify semantically that the action produced the expected result.
        Falls back to (True, "no llm") if LLM service is unavailable.

        Returns (passed: bool, reason: str).

        Output contract: VERDICT: PASS / FAIL / PARTIAL
          - PASS   → action succeeded, continue
          - PARTIAL → action partially succeeded (e.g. loading started but not complete); treated
                      as passed=True so the coordinator can proceed rather than retry
          - FAIL   → genuine failure; coordinator should trigger retry ladder
        """
        if not self.llm_service:
            return True, "no llm service"
        if not elements:
            return True, "no elements to check"

        # Build compact element summary (top 15, text + contentDesc only)
        lines = []
        for el in elements[:15]:
            text = (el.get("text") or "").strip()
            desc = (el.get("contentDescription") or "").strip()
            label = text or desc
            if label:
                lines.append(label)

        el_summary = "\n".join(f"- {l}" for l in lines) if lines else "(no text elements)"
        hint_line = f"\nExpected outcome hint: {success_hint}" if success_hint else ""

        # Inject app-specific contextual rules so the verifier knows, e.g.,
        # that a Pause button = music playing = success (not an intermediate state).
        from prompts.dynamic_rules import get_contextual_rules
        screen_ctx = " ".join(lines).lower()
        contextual_rules = get_contextual_rules(screen_ctx)
        rules_section = (
            f"\n\n━━━ APP-SPECIFIC RULES (apply these before deciding) ━━━\n{contextual_rules}"
            if contextual_rules else ""
        )

        prompt = (
            f"You are verifying whether a mobile UI action produced the expected result.\n\n"
            f"ACTION EXECUTED: {action_desc}{hint_line}\n\n"
            f"CURRENT SCREEN ELEMENTS (top 15):\n{el_summary}"
            f"{rules_section}\n\n"
            f"=== CRITICAL: KNOWN FAILURE MODES — OVERRIDE THESE BIASES ===\n"
            f"1. FALSE PASS — You mark PASS because the action technically ran, but the screen\n"
            f"   is still in a loading/animation state (spinner, progress bar, 'Loading…' text).\n"
            f"   FIX: If loading indicators are visible alongside partial results → output PARTIAL.\n"
            f"2. FALSE FAIL — You mark FAIL because a dialog or overlay is visible, but it is a\n"
            f"   routine system permission request or action confirmation (Allow/Deny, OK/Cancel).\n"
            f"   FIX: Standard permission or confirmation dialogs are NOT failures → output PASS.\n"
            f"=== END CRITICAL ===\n\n"
            f"━━━ VERIFICATION CHECKLIST ━━━\n"
            f"① Evidence of completion: sent indicator, new page loaded, item added, setting changed\n"
            f"② Genuine error indicators: app crash, 'failed', 'no internet', 'something went wrong'\n"
            f"   (NOT routine dialogs — see failure mode #2 above)\n"
            f"③ Intermediate state: loading spinner, progress bar, 'Loading…' alongside partial result\n\n"
            f"Respond with EXACTLY one of these three lines:\n"
            f"  VERDICT: PASS   <one sentence of evidence>\n"
            f"  VERDICT: FAIL   <one sentence of evidence>\n"
            f"  VERDICT: PARTIAL   <what succeeded and what still needs to happen>\n"
            f"Examples:\n"
            f"  VERDICT: PASS   'Sent' indicator visible in chat thread.\n"
            f"  VERDICT: FAIL   Error dialog 'Couldn't send message' is blocking the screen.\n"
            f"  VERDICT: PARTIAL   Library tab opened but content is still loading — spinner visible."
        )

        try:
            from concurrent.futures import ThreadPoolExecutor
            from functools import partial as functools_partial
            from prompts import PromptMode, build_aura_agent_prompt
            import re as _re

            _sys = build_aura_agent_prompt(
                agent_name="Verifier", mode=PromptMode.MINIMAL
            )  # G15: MINIMAL boilerplate for sub-agent call
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as ex:
                result = await loop.run_in_executor(
                    ex,
                    functools_partial(
                        self.llm_service.run,
                        prompt,
                        max_tokens=100,
                        caller_agent="verifier",
                        system_prompt=_sys,
                    )
                )
            result = (result or "").strip()

            # Parse structured VERDICT: PASS / FAIL / PARTIAL
            verdict_match = _re.search(r'VERDICT:\s*(PASS|FAIL|PARTIAL)', result, _re.IGNORECASE)
            if verdict_match:
                verdict = verdict_match.group(1).upper()
                # PARTIAL counts as passed — coordinator proceeds, not retries
                passed = verdict in ("PASS", "PARTIAL")
            else:
                # Fallback: legacy YES/NO for model non-compliance
                _clean = _re.sub(r'^[^a-zA-Z]+', '', result)
                passed = _clean.upper().startswith("YES")

            reason = result[:150]
            logger.debug(f"Verifier semantic_verify: passed={passed} — {reason[:80]}")
            return passed, reason
        except Exception as e:
            logger.warning(f"Verifier semantic_verify failed (non-fatal): {e}")
            return True, "llm check failed"
