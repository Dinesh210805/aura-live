"""
VLM Selector - Semantic selection from CV-detected candidates.

This is Layer 3 of the perception pipeline. The VLM receives a screenshot
with labeled bounding boxes (Set-of-Marks) and selects which box matches
the user's intent.

CRITICAL: The VLM NEVER generates coordinates. It only selects from
geometrically valid candidates provided by the CV detector (Layer 2).
This eliminates spatial hallucination - a fundamental VLM limitation.
"""

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from perception.omniparser_detector import Detection
from services.vlm import VLMService
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SelectionResult:
    """Result of VLM semantic selection."""
    
    success: bool                                # Whether selection succeeded
    selected_id: Optional[str] = None            # Selected label ID ("A", "B", etc.)
    detection: Optional[Detection] = None        # Full detection data
    coordinates: Optional[Tuple[int, int]] = None  # Center of selected box
    confidence: float = 0.0                      # Selection confidence
    reasoning: str = ""                          # Debug/explanation
    screen_description: str = ""                 # VLM description of the screenshot
    source: str = "vlm_selector"                 # Source identifier
    latency_ms: float = 0.0                      # API call latency
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "selected_id": self.selected_id,
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "screen_description": self.screen_description,
            "source": self.source,
            "latency_ms": self.latency_ms,
            "detection": self.detection.to_dict() if self.detection else None,
        }


class VLMSelector:
    """
    Semantic element selector using Vision-Language Models.
    
    Given a screenshot with labeled UI elements (Set-of-Marks visualization),
    the VLM selects which label corresponds to the user's intent.
    
    This design leverages VLM's strengths (semantic understanding) while
    avoiding its weakness (spatial coordinate prediction).
    """
    
    # Strict selection prompt - shows each region with its description
    SELECTION_PROMPT = """You are analyzing a mobile app screenshot with labeled UI regions.
Each region is marked with a large letter (e.g., A, B, C) inside a red bounding box.

Labeled regions on screen:
{regions_list}

User wants to interact with: "{intent}"

Look at the screenshot and pick the letter whose red box covers the element the user wants.
Respond with JSON only — no extra text:
{{"label": "X", "description": "one sentence describing what this screen shows"}}

Use NONE as the label if no region matches."""

    # Alternative prompt for ambiguous cases
    DETAILED_PROMPT = """Analyze this mobile app screenshot with labeled UI regions.
Each UI element is marked with a large letter ID (A, B, C, etc.) in a red box.

Labeled regions on screen:
{regions_list}

The user wants to: "{intent}"

Choose the labeled region whose red box best covers the element the user wants to interact with.
If multiple match, pick the most likely one. If none match, use NONE.

Respond with JSON only:
{{"label": "X", "description": "one sentence describing what this screen shows"}}"""

    def __init__(
        self,
        vlm_service: VLMService,
        max_tokens: int = 150,
        temperature: float = 0.0,
        timeout: float = 10.0,
        retry_count: int = 1,
    ):
        """
        Initialize the VLM selector.
        
        Args:
            vlm_service: VLMService instance for API calls.
            max_tokens: Max tokens in response (only need 1-2 for letter).
            temperature: Generation temperature (0.0 = deterministic).
            timeout: API timeout in seconds.
            retry_count: Number of retries on failure.
        """
        self.vlm_service = vlm_service
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.retry_count = retry_count
        
        logger.info(
            f"VLMSelector initialized (max_tokens={max_tokens}, "
            f"temperature={temperature}, timeout={timeout}s, "
            f"returns label+description)"
        )
    
    def select(
        self,
        annotated_image: str,  # Base64 encoded
        detections: List[Detection],
        intent: str,
        use_detailed_prompt: bool = False,
    ) -> SelectionResult:
        """
        Select the UI element that matches the user's intent.
        
        Args:
            annotated_image: Base64 encoded screenshot with Set-of-Marks.
            detections: List of detections from OmniParser.
            intent: User's intent description.
            use_detailed_prompt: Use more detailed prompt for ambiguous cases.
            
        Returns:
            SelectionResult with selected element and coordinates.
        """
        start_time = time.time()
        
        if not detections:
            return SelectionResult(
                success=False,
                reasoning="No detections available for selection",
                latency_ms=(time.time() - start_time) * 1000,
            )
        
        # Build per-region description list shown in the prompt.
        # Prefer any OCR/caption label the detector may have; fall back to class_name + position.
        regions_lines = []
        for d in detections:
            ocr_text = (d.label.strip()[:60] if hasattr(d, "label") and d.label else "")
            if ocr_text:
                description = f"{d.class_name}: \"{ocr_text}\""
            else:
                x1, y1, x2, y2 = d.box
                cx, cy = d.center
                description = f"{d.class_name} at ({cx},{cy})"
            regions_lines.append(f"{d.id}. {description}")
        regions_list = "\n".join(regions_lines)
        
        # Build prompt
        prompt_template = self.DETAILED_PROMPT if use_detailed_prompt else self.SELECTION_PROMPT
        prompt = prompt_template.format(
            regions_list=regions_list,
            intent=intent,
        )
        
        # Call VLM with retry
        for attempt in range(self.retry_count + 1):
            try:
                response = self.vlm_service.analyze_image(
                    image_data=annotated_image,
                    prompt=prompt,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    agent="VLMSelector",
                )
                
                # Parse response
                result = self._parse_response(response, detections, intent)
                result.latency_ms = (time.time() - start_time) * 1000
                
                if result.success:
                    logger.info(
                        f"✅ VLM selected '{result.selected_id}' for intent '{intent}' "
                        f"({result.latency_ms:.0f}ms)"
                    )
                else:
                    logger.warning(
                        f"VLM selection failed for '{intent}': {result.reasoning}"
                    )
                
                return result
                
            except Exception as e:
                logger.warning(f"VLM selection attempt {attempt + 1} failed: {e}")
                if attempt == self.retry_count:
                    return SelectionResult(
                        success=False,
                        reasoning=f"VLM API error after {self.retry_count + 1} attempts: {str(e)}",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
        
        # Should not reach here, but just in case
        return SelectionResult(
            success=False,
            reasoning="Unknown error in VLM selection",
            latency_ms=(time.time() - start_time) * 1000,
        )
    
    def _parse_response(
        self,
        response: str,
        detections: List[Detection],
        intent: str,
    ) -> SelectionResult:
        """
        Parse VLM response and validate against available detections.
        
        Args:
            response: Raw VLM response.
            detections: Available detections.
            intent: Original intent for logging.
            
        Returns:
            SelectionResult with parsed selection.
        """
        import json

        screen_description = ""
        selected_id_raw = ""

        # Try JSON parse first (new prompt format)
        try:
            # Strip markdown code fences if present
            json_text = re.sub(r'^```[\w]*\n?|\n?```$', '', response.strip())
            data = json.loads(json_text)
            selected_id_raw = str(data.get("label", "")).strip().upper()
            screen_description = str(data.get("description", "")).strip()
        except (json.JSONDecodeError, AttributeError):
            # Fallback: legacy single-letter parsing
            cleaned = response.strip().upper()
            cleaned = re.sub(r'^(THE\s+ANSWER\s+IS|ANSWER:|REGION:?)\s*', '', cleaned)
            selected_id_raw = cleaned.strip()

        # Check for "NONE"
        if not selected_id_raw or "NONE" in selected_id_raw:
            return SelectionResult(
                success=False,
                reasoning="VLM reported no matching region",
                screen_description=screen_description,
            )

        # Extract letter(s) - match single letter or two-letter combo
        letter_match = re.search(r'\b([A-Z]{1,2})\b', selected_id_raw)

        if not letter_match:
            return SelectionResult(
                success=False,
                reasoning=f"Could not parse letter ID from VLM response: '{response}'",
                screen_description=screen_description,
            )

        selected_id = letter_match.group(1)

        # Find matching detection
        detection = None
        for det in detections:
            if det.id.upper() == selected_id:
                detection = det
                break

        if detection is None:
            available = [d.id for d in detections]
            return SelectionResult(
                success=False,
                selected_id=selected_id,
                reasoning=f"Selected ID '{selected_id}' not in available detections: {available}",
                screen_description=screen_description,
            )

        # Success!
        return SelectionResult(
            success=True,
            selected_id=selected_id,
            detection=detection,
            coordinates=detection.center,
            confidence=detection.confidence,
            reasoning=f"VLM selected {selected_id} ({detection.class_name})",
            screen_description=screen_description,
        )
    
    def select_with_fallback(
        self,
        annotated_image: str,
        detections: List[Detection],
        intent: str,
    ) -> SelectionResult:
        """
        Select with fallback to detailed prompt if first attempt fails.
        
        Args:
            annotated_image: Base64 encoded screenshot with Set-of-Marks.
            detections: List of detections from OmniParser.
            intent: User's intent description.
            
        Returns:
            SelectionResult from best attempt.
        """
        # Try simple prompt first (faster)
        result = self.select(
            annotated_image=annotated_image,
            detections=detections,
            intent=intent,
            use_detailed_prompt=False,
        )
        
        if result.success:
            return result
        
        # Fallback to detailed prompt
        logger.info(f"Retrying VLM selection with detailed prompt for '{intent}'")
        return self.select(
            annotated_image=annotated_image,
            detections=detections,
            intent=intent,
            use_detailed_prompt=True,
        )


class HeuristicSelector:
    """
    Fallback selector using simple heuristics when VLM is unavailable.
    
    Uses text matching, class names, and position to select elements.
    Less accurate than VLM but works without API calls.
    """
    
    def __init__(self):
        logger.info("HeuristicSelector initialized as VLM fallback")
    
    def select(
        self,
        detections: List[Detection],
        intent: str,
    ) -> SelectionResult:
        """
        Select using heuristic matching.
        
        This is a simple fallback when VLM is unavailable.
        Uses class name matching and position-based selection.
        """
        start_time = time.time()
        intent_lower = intent.lower()
        
        # Build keyword mappings
        class_keywords = {
            "button": ["button", "click", "press", "tap", "submit", "send", "ok", "yes", "no", "cancel"],
            "icon": ["icon", "logo", "image", "picture"],
            "text": ["text", "label", "title", "heading"],
            "input": ["input", "text field", "type", "enter", "search", "write"],
            "checkbox": ["checkbox", "check", "tick", "select"],
            "switch": ["switch", "toggle", "on", "off"],
        }
        
        best_detection = None
        best_score = 0.0
        
        for det in detections:
            score = 0.0
            
            # Class name matching
            for class_name, keywords in class_keywords.items():
                if class_name in det.class_name.lower():
                    for kw in keywords:
                        if kw in intent_lower:
                            score += 0.5
                            break
            
            # Confidence boost
            score += det.confidence * 0.3
            
            # Central position boost (for ambiguous cases)
            if score > 0 and det.confidence > 0.5:
                score += 0.1
            
            if score > best_score:
                best_score = score
                best_detection = det
        
        latency = (time.time() - start_time) * 1000
        
        if best_detection and best_score > 0.3:
            return SelectionResult(
                success=True,
                selected_id=best_detection.id,
                detection=best_detection,
                coordinates=best_detection.center,
                confidence=best_score,
                reasoning=f"Heuristic selected {best_detection.id} (score={best_score:.2f})",
                source="heuristic_selector",
                latency_ms=latency,
            )
        
        return SelectionResult(
            success=False,
            reasoning="No heuristic match found",
            source="heuristic_selector",
            latency_ms=latency,
        )


def create_vlm_selector(vlm_service: VLMService) -> VLMSelector:
    """Factory function to create VLMSelector with defaults."""
    return VLMSelector(vlm_service)
