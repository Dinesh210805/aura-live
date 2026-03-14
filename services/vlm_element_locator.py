"""
VLM Element Locator Service.

Vision-first element location using VLM for semantic understanding.
Replaces brittle text matching with intelligent visual reasoning.
"""

import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from prompts import get_element_prompt, get_action_prompt, get_ordinal_prompt, SCREEN_ANALYSIS_PROMPT
from services.vlm import VLMService
from utils.logger import get_logger

if TYPE_CHECKING:
    from perception.models import PerceptionBundle

logger = get_logger(__name__)


class VLMElementLocator:
    """
    Intelligent element location using Vision-Language Model.
    
    Uses visual reasoning to find UI elements by their semantic meaning,
    not just text matching. Understands icons, visual patterns, and
    common app UI conventions.
    """

    def __init__(self, vlm_service: VLMService):
        self.vlm_service = vlm_service
        
        # Confidence threshold for accepting VLM results
        self.min_confidence = 0.6
    
    def _validate_and_clamp_coordinates(
        self, 
        x: int, 
        y: int, 
        screen_width: int, 
        screen_height: int,
        margin: int = 18,
    ) -> tuple[int, int, bool]:
        """
        Validate coordinates are within screen bounds and clamp if needed.
        
        Args:
            x, y: Raw coordinates from VLM
            screen_width, screen_height: Screen dimensions
            margin: Safety margin from edges to avoid edge taps
            
        Returns:
            (x, y, was_clamped) tuple with validated coordinates
        """
        original_x, original_y = x, y
        was_clamped = False
        
        # Check for obviously invalid coordinates
        if x < 0 or y < 0 or x > screen_width or y > screen_height:
            logger.warning(f"⚠️ VLM returned out-of-bounds coordinates: ({x}, {y}) for screen {screen_width}x{screen_height}")
            was_clamped = True
        
        # Clamp to valid range with margin
        x = max(margin, min(x, screen_width - margin))
        y = max(margin, min(y, screen_height - margin))
        
        if was_clamped:
            logger.info(f"📍 Clamped coordinates: ({original_x}, {original_y}) → ({x}, {y})")
        
        return x, y, was_clamped
    
    def locate_element(
        self,
        screenshot_b64: str,
        target_description: str,
        screen_width: int,
        screen_height: int,
        action_context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Locate an element using visual reasoning.
        
        Args:
            screenshot_b64: Base64 encoded screenshot
            target_description: What to find (e.g., "skip button", "send icon", "profile")
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            action_context: Optional context about intended action (e.g., "skip ad", "send message")
        
        Returns:
            Dict with x, y, confidence, reasoning, element_type or None if not found
        """
        if not screenshot_b64 or len(screenshot_b64) < 1000:
            logger.warning("Screenshot too small for visual location")
            return None
        
        # Build context-aware prompt using centralized template
        prompt = get_element_prompt(
            target=target_description,
            width=screen_width,
            height=screen_height,
            action_context=action_context,
        )

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="VLMElementLocator")
            parsed = self._parse_json_response(result)
            
            if parsed and parsed.get("found"):
                x = int((parsed["x_percent"] / 100) * screen_width)
                y = int((parsed["y_percent"] / 100) * screen_height)
                
                # Validate and clamp coordinates to screen bounds
                x, y, was_clamped = self._validate_and_clamp_coordinates(
                    x, y, screen_width, screen_height
                )
                
                confidence = parsed.get("confidence", 0.7)
                
                # Reduce confidence if coordinates were clamped (VLM was inaccurate)
                if was_clamped:
                    confidence = min(confidence, 0.5)
                    logger.warning(f"Reduced confidence to {confidence:.2f} due to coordinate clamping")
                
                if confidence < self.min_confidence:
                    logger.warning(
                        f"VLM found '{target_description}' but confidence too low: {confidence:.2f}"
                    )
                    return None
                
                logger.info(
                    f"✅ VLM located '{target_description}' at ({x}, {y}) "
                    f"confidence={confidence:.2f}, type={parsed.get('element_type', 'unknown')}"
                )
                logger.debug(f"   Reasoning: {parsed.get('reasoning', 'N/A')}")
                
                return {
                    "x": x,
                    "y": y,
                    "confidence": confidence,
                    "element_type": parsed.get("element_type", "unknown"),
                    "reasoning": parsed.get("reasoning", ""),
                    "source": "vlm",
                }
            else:
                reason = parsed.get("reason", "not found") if parsed else "VLM parse error"
                logger.warning(f"❌ VLM could not find '{target_description}': {reason}")
                return None
                
        except Exception as e:
            logger.error(f"VLM element location failed: {e}")
            return None

    def locate_for_action(
        self,
        screenshot_b64: str,
        action: str,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the element that would accomplish a specific action.
        
        More intelligent than locate_element - understands intent.
        
        Examples:
            action="skip this ad" -> finds skip button, X button, countdown timer, etc.
            action="go back" -> finds back arrow, X, close button, etc.
            action="send the message" -> finds send button, paper plane icon, etc.
        """
        # Use centralized action location prompt
        prompt = get_action_prompt(
            action=action,
            width=screen_width,
            height=screen_height,
        )

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="VLMElementLocator")
            parsed = self._parse_json_response(result)
            
            if parsed and parsed.get("found"):
                x = int((parsed["x_percent"] / 100) * screen_width)
                y = int((parsed["y_percent"] / 100) * screen_height)
                
                # Validate and clamp coordinates
                x, y, was_clamped = self._validate_and_clamp_coordinates(
                    x, y, screen_width, screen_height
                )
                
                confidence = parsed.get("confidence", 0.7)
                if was_clamped:
                    confidence = min(confidence, 0.5)
                
                logger.info(
                    f"✅ VLM found element for action '{action}': "
                    f"{parsed.get('what_found', 'element')} at ({x}, {y})"
                )
                
                return {
                    "x": x,
                    "y": y,
                    "confidence": confidence,
                    "element_type": parsed.get("element_type", "unknown"),
                    "what_found": parsed.get("what_found", ""),
                    "reasoning": parsed.get("reasoning", ""),
                    "source": "vlm_action",
                }
            else:
                reason = parsed.get("reason", "unknown") if parsed else "parse error"
                suggestions = parsed.get("suggestions", []) if parsed else []
                logger.warning(f"❌ Cannot accomplish '{action}': {reason}")
                if suggestions:
                    logger.info(f"   Suggestions: {suggestions}")
                return None
                
        except Exception as e:
            logger.error(f"VLM action location failed: {e}")
            return None

    def locate_ordinal_item(
        self,
        screenshot_b64: str,
        item_type: str,
        ordinal: int,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the Nth item of a type on screen.
        
        Args:
            item_type: Type of items to count (e.g., "message", "contact", "notification")
            ordinal: Which item (1=first, 2=second, etc.)
        
        Examples:
            locate_ordinal_item(..., "message", 3) -> 3rd message in list
            locate_ordinal_item(..., "search result", 1) -> first search result
        """
        ordinal_word = self._ordinal_to_word(ordinal)
        
        # Use centralized ordinal location prompt
        prompt = get_ordinal_prompt(
            ordinal=ordinal_word,
            item_type=item_type,
            index=ordinal,
            width=screen_width,
            height=screen_height,
        )

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="VLMElementLocator")
            parsed = self._parse_json_response(result)
            
            if parsed and parsed.get("found"):
                x = int((parsed["x_percent"] / 100) * screen_width)
                y = int((parsed["y_percent"] / 100) * screen_height)
                
                # Validate and clamp coordinates
                x, y, was_clamped = self._validate_and_clamp_coordinates(
                    x, y, screen_width, screen_height
                )
                
                confidence = parsed.get("confidence", 0.7)
                if was_clamped:
                    confidence = min(confidence, 0.5)
                
                logger.info(
                    f"✅ VLM found {ordinal_word} {item_type} at ({x}, {y}): "
                    f"{parsed.get('item_description', '')[:50]}"
                )
                
                return {
                    "x": x,
                    "y": y,
                    "confidence": confidence,
                    "item_description": parsed.get("item_description", ""),
                    "total_visible": parsed.get("total_visible", 0),
                    "source": "vlm_ordinal",
                }
            else:
                reason = parsed.get("reason", "not found") if parsed else "parse error"
                total = parsed.get("total_visible", "?") if parsed else "?"
                logger.warning(f"❌ Could not find {ordinal_word} {item_type}: {reason}")
                return None
                
        except Exception as e:
            logger.error(f"VLM ordinal location failed: {e}")
            return None

    def verify_element(
        self,
        screenshot_b64: str,
        x: int,
        y: int,
        expected_element: str,
        screen_width: int,
        screen_height: int,
    ) -> Dict[str, Any]:
        """
        Verify that an element at coordinates matches expectation.
        
        Used for post-action verification.
        
        Returns:
            Dict with 'matches' (bool), 'confidence', 'actual_element', 'reasoning'
        """
        x_percent = (x / screen_width) * 100
        y_percent = (y / screen_height) * 100
        
        prompt = f"""Look at the element at approximately ({x_percent:.1f}%, {y_percent:.1f}%) on this screen.

EXPECTED: "{expected_element}"

Is the element at this position what we expected?

OUTPUT FORMAT (JSON only):
{{
  "matches": true,
  "confidence": 0.9,
  "actual_element": "Send button (paper plane icon)",
  "reasoning": "Found send button icon at specified location, matches expectation"
}}

Or if different:
{{
  "matches": false,
  "confidence": 0.85,
  "actual_element": "Voice message button",
  "reasoning": "Found microphone icon, not send button"
}}

RESPOND ONLY WITH JSON."""

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="VLMElementLocator")
            parsed = self._parse_json_response(result)
            
            if parsed:
                matches = parsed.get("matches", False)
                logger.info(
                    f"🔍 Verification: expected='{expected_element}', "
                    f"actual='{parsed.get('actual_element', '?')}', "
                    f"matches={matches}"
                )
                return {
                    "matches": matches,
                    "confidence": parsed.get("confidence", 0.5),
                    "actual_element": parsed.get("actual_element", "unknown"),
                    "reasoning": parsed.get("reasoning", ""),
                }
            
            return {"matches": False, "confidence": 0, "actual_element": "error", "reasoning": "Parse failed"}
            
        except Exception as e:
            logger.error(f"VLM verification failed: {e}")
            return {"matches": False, "confidence": 0, "actual_element": "error", "reasoning": str(e)}

    def analyze_screen(
        self,
        screenshot_b64: str,
        screen_width: int,
        screen_height: int,
    ) -> Dict[str, Any]:
        """
        Get high-level understanding of current screen.
        
        Returns:
            Dict with app_name, screen_type, key_elements, available_actions
        """
        prompt = """Analyze this Android screen and provide a structured summary.

OUTPUT FORMAT (JSON only):
{
  "app_name": "Instagram|WhatsApp|YouTube|Settings|etc",
  "screen_type": "home_feed|chat|video_player|settings|search|profile|login|etc",
  "key_elements": [
    {"type": "button", "description": "Back arrow", "location": "top-left"},
    {"type": "input", "description": "Search bar", "location": "top-center"},
    {"type": "list", "description": "Message list", "location": "center"}
  ],
  "available_actions": ["go back", "search", "scroll down", "tap message"],
  "has_modal": false,
  "has_keyboard": false
}

Be concise but accurate. RESPOND ONLY WITH JSON."""

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="VLMElementLocator")
            parsed = self._parse_json_response(result)
            
            if parsed:
                logger.info(
                    f"📱 Screen: {parsed.get('app_name', '?')} - {parsed.get('screen_type', '?')}"
                )
                return parsed
            
            return {"app_name": "unknown", "screen_type": "unknown", "key_elements": [], "available_actions": []}
            
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return {"app_name": "unknown", "screen_type": "unknown", "key_elements": [], "available_actions": []}

    def locate_from_bundle(
        self,
        bundle: "PerceptionBundle",
        target_description: str,
        action_context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Convenience method to locate element from PerceptionBundle.
        """
        target_lower = (target_description or "").strip().lower()

        # 1) Prefer deterministic UI-tree bounds when available.
        if target_lower and bundle.ui_tree and getattr(bundle.ui_tree, "elements", None):
            best_match: Optional[Dict[str, Any]] = None
            best_score = 0.0

            for elem in bundle.ui_tree.elements:
                text = (elem.get("text") or "").strip().lower()
                content_desc = (elem.get("contentDescription") or "").strip().lower()
                resource_id = (elem.get("resourceId") or "").strip().lower()

                score = 0.0
                if target_lower and target_lower == text:
                    score = 1.0
                elif target_lower and (target_lower in text or target_lower in content_desc):
                    score = 0.8
                elif (text and text in target_lower) or (content_desc and content_desc in target_lower):
                    score = 0.6
                elif target_lower and target_lower.replace(" ", "_") in resource_id:
                    score = 0.7

                if score > best_score:
                    best_score = score
                    best_match = elem

            if best_match and best_score >= 0.55:
                bounds = best_match.get("bounds", {})
                left = top = right = bottom = 0

                if isinstance(bounds, dict) and bounds:
                    left = int(bounds.get("left", 0) or 0)
                    top = int(bounds.get("top", 0) or 0)
                    right = int(bounds.get("right", 0) or 0)
                    bottom = int(bounds.get("bottom", 0) or 0)
                elif isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                    left, top, right, bottom = (int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3]))

                if right > left and bottom > top:
                    x = (left + right) // 2
                    y = (top + bottom) // 2
                    logger.info(
                        f"✅ UI tree located '{target_description}' at ({x}, {y}) confidence={best_score:.2f}"
                    )
                    return {
                        "x": x,
                        "y": y,
                        "confidence": best_score,
                        "element_type": "ui_tree",
                        "reasoning": "Matched element in UI tree and used bounds center",
                        "source": "ui_tree",
                    }

        # 2) Fall back to VLM screenshot-based location.
        if not bundle.screenshot or not bundle.screenshot.screenshot_base64:
            logger.warning("No screenshot in bundle for VLM location")
            return None
        
        return self.locate_element(
            screenshot_b64=bundle.screenshot.screenshot_base64,
            target_description=target_description,
            screen_width=bundle.screen_meta.width,
            screen_height=bundle.screen_meta.height,
            action_context=action_context,
        )

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from VLM response, handling markdown code blocks."""
        if not response:
            return None
        
        text = response.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse VLM JSON: {e}")
            logger.debug(f"Raw response: {response[:200]}")
            return None

    def _ordinal_to_word(self, n: int) -> str:
        """Convert number to ordinal word."""
        ordinals = {
            1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
            6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"
        }
        return ordinals.get(n, f"{n}th")
