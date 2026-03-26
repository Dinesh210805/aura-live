"""
Perception Pipeline - Three-layer orchestration for UI element location.

This is the main orchestrator implementing the OmniParser hybrid architecture:

Layer 1: UI Tree (Primary - Always First)
    - Uses existing ui_element_finder.py
    - 10-50ms latency, 70-80% success rate
    - Pixel-perfect coordinates from Android Accessibility

Layer 2: CV Detection (Fallback)
    - Uses OmniParserDetector (YOLOv8)
    - 200-400ms on GPU, 2-3s on CPU
    - Detects ALL UI elements geometrically

Layer 3: VLM Selection (Semantic Matching)
    - Uses VLMSelector with Gemini/Claude
    - 300-600ms API latency
    - Selects from CV-detected candidates by ID
    - VLM NEVER generates coordinates!

The key insight: Coordinates always come from deterministic sources
(UI tree or CV). VLM only performs classification among valid options.
"""

import concurrent.futures
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    # Create no-op decorator
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from perception.models import UITreePayload
from utils.perf_tracker import PerfTracker
from perception.omniparser_detector import Detection, OmniParserDetector, create_detector
from perception.vlm_selector import HeuristicSelector, SelectionResult, VLMSelector, create_vlm_selector
from services.vlm import VLMService
from utils.logger import get_logger
from utils.ui_element_finder import find_element, validate_coordinates

logger = get_logger(__name__)


@dataclass
class PerceptionConfig:
    """Configuration for perception pipeline."""
    
    # Layer enables
    ui_tree_enabled: bool = True
    cv_vlm_enabled: bool = True
    
    # UI Tree settings
    ui_tree_min_score: float = 0.5
    ui_tree_prefer_clickable: bool = True
    
    # CV Detector settings
    detector_model_path: Optional[str] = None
    detector_confidence: float = 0.25
    detector_device: str = "auto"
    
    # VLM settings
    vlm_max_tokens: int = 10
    vlm_temperature: float = 0.0
    vlm_timeout: float = 10.0
    
    # Policy gate
    min_confidence: float = 0.70
    validate_bounds: bool = True
    min_box_size: Tuple[int, int] = (10, 10)
    max_retries: int = 2
    
    # Optimization
    cache_detections: bool = True
    resize_for_vlm: bool = True
    max_vlm_dimension: int = 1024
    
    @classmethod
    def from_yaml(cls, path: str = "config/perception_config.yaml") -> "PerceptionConfig":
        """Load config from YAML file."""
        config_path = Path(path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {path}, using defaults")
            return cls()
        
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
        
        perception = data.get("perception", {})
        
        return cls(
            ui_tree_enabled=perception.get("ui_tree_enabled", True),
            cv_vlm_enabled=perception.get("cv_vlm_enabled", True),
            ui_tree_min_score=perception.get("ui_tree", {}).get("min_match_score", 0.5),
            ui_tree_prefer_clickable=perception.get("ui_tree", {}).get("prefer_clickable", True),
            detector_model_path=perception.get("detector", {}).get("model_path"),
            detector_confidence=perception.get("detector", {}).get("confidence_threshold", 0.25),
            detector_device=perception.get("detector", {}).get("device", "auto"),
            vlm_max_tokens=perception.get("vlm", {}).get("max_tokens", 10),
            vlm_temperature=perception.get("vlm", {}).get("temperature", 0.0),
            vlm_timeout=perception.get("vlm", {}).get("timeout_seconds", 10.0),
            min_confidence=perception.get("policy", {}).get("min_confidence", 0.70),
            validate_bounds=perception.get("policy", {}).get("validate_bounds", True),
            min_box_size=tuple(perception.get("policy", {}).get("min_box_size", [10, 10])),
            max_retries=perception.get("policy", {}).get("max_retries", 2),
            cache_detections=perception.get("optimization", {}).get("cache_detections", True),
            resize_for_vlm=perception.get("optimization", {}).get("resize_for_vlm", True),
            max_vlm_dimension=perception.get("optimization", {}).get("max_vlm_dimension", 1024),
        )


@dataclass
class LocateResult:
    """Result of element location attempt."""
    
    success: bool
    coordinates: Optional[Tuple[int, int]] = None
    confidence: float = 0.0
    source: str = ""  # "ui_tree", "cv_vlm", "heuristic"
    element_info: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    latency_ms: float = 0.0
    layer_attempted: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "confidence": self.confidence,
            "source": self.source,
            "element_info": self.element_info,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "layer_attempted": self.layer_attempted,
        }


@dataclass
class PerceptionMetrics:
    """Metrics for perception pipeline performance."""
    
    ui_tree_attempts: int = 0
    ui_tree_successes: int = 0
    cv_vlm_attempts: int = 0
    cv_vlm_successes: int = 0
    heuristic_attempts: int = 0
    heuristic_successes: int = 0
    total_failures: int = 0
    total_latency_ms: float = 0.0
    
    def record_success(self, source: str, latency_ms: float = 0.0):
        """Record a successful location."""
        self.total_latency_ms += latency_ms
        if source == "ui_tree":
            self.ui_tree_successes += 1
        elif source == "cv_vlm":
            self.cv_vlm_successes += 1
        elif source == "heuristic":
            self.heuristic_successes += 1
    
    def record_attempt(self, source: str):
        """Record an attempt."""
        if source == "ui_tree":
            self.ui_tree_attempts += 1
        elif source == "cv_vlm":
            self.cv_vlm_attempts += 1
        elif source == "heuristic":
            self.heuristic_attempts += 1
    
    def record_failure(self):
        """Record a complete failure."""
        self.total_failures += 1
    
    @property
    def ui_tree_success_rate(self) -> float:
        """UI tree success rate."""
        if self.ui_tree_attempts == 0:
            return 0.0
        return self.ui_tree_successes / self.ui_tree_attempts
    
    @property
    def cv_vlm_success_rate(self) -> float:
        """CV+VLM success rate."""
        if self.cv_vlm_attempts == 0:
            return 0.0
        return self.cv_vlm_successes / self.cv_vlm_attempts
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "ui_tree": {
                "attempts": self.ui_tree_attempts,
                "successes": self.ui_tree_successes,
                "success_rate": round(self.ui_tree_success_rate, 3),
            },
            "cv_vlm": {
                "attempts": self.cv_vlm_attempts,
                "successes": self.cv_vlm_successes,
                "success_rate": round(self.cv_vlm_success_rate, 3),
            },
            "heuristic": {
                "attempts": self.heuristic_attempts,
                "successes": self.heuristic_successes,
            },
            "total_failures": self.total_failures,
            "avg_latency_ms": round(
                self.total_latency_ms / max(1, self.ui_tree_successes + self.cv_vlm_successes),
                1
            ),
        }


class PerceptionPipeline:
    """
    Three-layer perception pipeline for UI element location.
    
    This implements the OmniParser hybrid architecture:
    1. UI Tree first (fast, reliable)
    2. CV Detection + VLM Selection (fallback for WebView/Canvas)
    3. Heuristic fallback (last resort)
    
    The VLM never generates coordinates - only selects from CV candidates.
    """
    
    def __init__(
        self,
        vlm_service: VLMService,
        config: Optional[PerceptionConfig] = None,
        detector: Optional[OmniParserDetector] = None,
    ):
        """
        Initialize the perception pipeline.
        
        Args:
            vlm_service: VLMService instance for VLM calls.
            config: Pipeline configuration. Loads from YAML if None.
            detector: OmniParserDetector instance. Creates default if None.
        """
        self.config = config or PerceptionConfig.from_yaml()
        self.vlm_service = vlm_service
        
        # Lazy-init detector (heavy model loading)
        self._detector = detector
        
        # Create VLM selector
        self._vlm_selector: Optional[VLMSelector] = None
        
        # Heuristic fallback
        self._heuristic = HeuristicSelector()
        
        # Metrics tracking
        self.metrics = PerceptionMetrics()
        
        logger.info(
            f"PerceptionPipeline initialized "
            f"(ui_tree={self.config.ui_tree_enabled}, cv_vlm={self.config.cv_vlm_enabled})"
        )
    
    @property
    def detector(self) -> OmniParserDetector:
        """Lazy-init the OmniParser detector."""
        if self._detector is None:
            self._detector = create_detector(
                model_path=self.config.detector_model_path,
                device=self.config.detector_device,
                confidence=self.config.detector_confidence,
            )
        return self._detector
    
    @property
    def vlm_selector(self) -> VLMSelector:
        """Lazy-init the VLM selector."""
        if self._vlm_selector is None:
            self._vlm_selector = create_vlm_selector(self.vlm_service)
        return self._vlm_selector

    def warmup(self) -> None:
        """Pre-load the OmniParser detector and warm up its inference kernels."""
        self.detector.warmup()
    
    def locate_element(
        self,
        intent: str,
        ui_tree: Optional[UITreePayload] = None,
        screenshot: Optional[Union[bytes, str]] = None,
        screen_bounds: Tuple[int, int] = (1080, 2400),
    ) -> LocateResult:
        """
        Locate a UI element matching the user's intent.
        
        Tries layers in order: UI Tree → CV+VLM → Heuristic
        Returns as soon as any layer succeeds.
        
        Args:
            intent: User's intent description (e.g., "play button", "search field").
            ui_tree: UI tree from Android Accessibility (Layer 1 input).
            screenshot: Screenshot as bytes or base64 (Layer 2+3 input).
            screen_bounds: Screen (width, height) for validation.
            
        Returns:
            LocateResult with coordinates and metadata.
        """
        start_time = time.time()
        layers_attempted = []
        
        # Performance tracking for debugging
        perf = PerfTracker(name=f"Perception: {intent[:30]}")
        
        # Layer 1: UI Tree
        if self.config.ui_tree_enabled and ui_tree:
            self.metrics.record_attempt("ui_tree")
            layers_attempted.append("ui_tree")
            
            with perf.track("Layer 1: UI Tree", nodes=len(ui_tree.elements) if ui_tree and ui_tree.elements else 0):
                result = self._try_ui_tree(ui_tree, intent, screen_bounds)
            
            if result.success:
                result.latency_ms = (time.time() - start_time) * 1000
                result.layer_attempted = layers_attempted
                self.metrics.record_success("ui_tree", result.latency_ms)
                perf.log_summary(log_level="debug")
                return result
        
        # Layer 2+3: CV Detection + VLM Selection
        if self.config.cv_vlm_enabled and screenshot:
            self.metrics.record_attempt("cv_vlm")
            layers_attempted.append("cv_vlm")
            
            with perf.track("Layer 2+3: CV+VLM", has_screenshot=bool(screenshot)):
                result = self._try_cv_vlm(screenshot, intent, screen_bounds)
            
            if result.success:
                result.latency_ms = (time.time() - start_time) * 1000
                result.layer_attempted = layers_attempted
                self.metrics.record_success("cv_vlm", result.latency_ms)
                perf.log_summary(log_level="debug")
                return result
        
        # Heuristic fallback (if CV detection ran but VLM failed)
        if self.config.cv_vlm_enabled and screenshot:
            self.metrics.record_attempt("heuristic")
            layers_attempted.append("heuristic")
            
            with perf.track("Layer 4: Heuristic"):
                result = self._try_heuristic(screenshot, intent, screen_bounds)
            
            if result.success:
                result.latency_ms = (time.time() - start_time) * 1000
                result.layer_attempted = layers_attempted
                self.metrics.record_success("heuristic", result.latency_ms)
                perf.log_summary(log_level="debug")
                return result
        
        # All layers failed - log detailed timeline
        self.metrics.record_failure()
        perf.log_summary(log_level="info")  # Log failures at info level
        
        return LocateResult(
            success=False,
            reason="All perception layers failed to locate element",
            latency_ms=(time.time() - start_time) * 1000,
            layer_attempted=layers_attempted,
        )
    
    def _try_ui_tree(
        self,
        ui_tree: UITreePayload,
        intent: str,
        screen_bounds: Tuple[int, int],
    ) -> LocateResult:
        """
        Layer 1: Try to find element in UI tree.
        
        Uses existing ui_element_finder for semantic matching.
        """
        try:
            # Use existing find_element from ui_element_finder.py
            match = find_element(
                elements=ui_tree.elements,
                target=intent,
                min_score=self.config.ui_tree_min_score,
                prefer_clickable=self.config.ui_tree_prefer_clickable,
            )
            
            if match:
                x, y = match["x"], match["y"]
                confidence = match.get("score", 0.8)
                
                # Validate bounds
                if self.config.validate_bounds:
                    is_valid, reason = validate_coordinates(
                        x, y, screen_bounds[0], screen_bounds[1]
                    )
                    if not is_valid:
                        logger.warning(f"UI tree match invalid: {reason}")
                        return LocateResult(
                            success=False,
                            reason=f"Coordinate validation failed: {reason}",
                            source="ui_tree",
                        )
                
                # Check confidence threshold
                if confidence < self.config.min_confidence:
                    logger.info(
                        f"UI tree match below threshold: {confidence:.2f} < {self.config.min_confidence}"
                    )
                    return LocateResult(
                        success=False,
                        reason=f"Confidence too low: {confidence:.2f}",
                        source="ui_tree",
                    )
                
                return LocateResult(
                    success=True,
                    coordinates=(x, y),
                    confidence=confidence,
                    source="ui_tree",
                    element_info={
                        "text": match.get("text", ""),
                        "match_score": match.get("score", 0),
                    },
                )
            
            return LocateResult(
                success=False,
                reason="No matching element in UI tree",
                source="ui_tree",
            )
            
        except Exception as e:
            logger.error(f"UI tree search failed: {e}")
            return LocateResult(
                success=False,
                reason=f"UI tree error: {str(e)}",
                source="ui_tree",
            )
    
    def _try_cv_vlm(
        self,
        screenshot: Union[bytes, str],
        intent: str,
        screen_bounds: Tuple[int, int],
    ) -> LocateResult:
        """
        Layer 2+3: CV Detection + VLM Selection.
        
        1. Run OmniParser detector to find all UI elements
        2. Draw Set-of-Marks visualization
        3. Ask VLM to select the matching element by ID
        4. Return coordinates from the selected detection
        """
        try:
            # Step 1: CV Detection
            detections = self.detector.detect(screenshot, use_cache=self.config.cache_detections)
            
            if not detections:
                return LocateResult(
                    success=False,
                    reason="No UI elements detected by CV",
                    source="cv_vlm",
                )
            
            # Step 2: Draw Set-of-Marks
            annotated = self.detector.draw_set_of_marks(screenshot, detections)
            annotated_b64 = self.detector.annotated_image_to_base64(annotated)

            # Save OmniParser annotated screenshot to HTML log
            try:
                from services.command_logger import get_command_logger
                _log = get_command_logger()
                omni_path = _log.log_screenshot(
                    label=f"omniparser_{str(intent)[:30]}",
                    base64_data=annotated_b64,
                    ext="jpg",
                )
                # Stash path on the logger so PERCEPTION_RESULT can reference it
                _log._last_omniparser_screenshot = omni_path
            except Exception:
                pass

            # Step 3: VLM Selection (with configurable wall-clock timeout — G6)
            try:
                from config.settings import settings as _settings
                _vlm_timeout = _settings.vlm_timeout_seconds
            except Exception:
                _vlm_timeout = 30
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _vlm_pool:
                    _vlm_future = _vlm_pool.submit(
                        self.vlm_selector.select_with_fallback,
                        annotated_image=annotated_b64,
                        detections=detections,
                        intent=intent,
                    )
                    selection = _vlm_future.result(timeout=_vlm_timeout)
            except concurrent.futures.TimeoutError:
                logger.error(
                    f"VLM selection timed out after {_vlm_timeout}s for intent '{intent[:50]}'"
                )
                return LocateResult(
                    success=False,
                    reason=f"VLM selection timed out after {_vlm_timeout}s",
                    source="cv_vlm",
                )

            if not selection.success:
                return LocateResult(
                    success=False,
                    reason=selection.reasoning,
                    source="cv_vlm",
                )
            
            # Step 4: Validate selection
            x, y = selection.coordinates
            
            if self.config.validate_bounds:
                is_valid, reason = validate_coordinates(
                    x, y, screen_bounds[0], screen_bounds[1]
                )
                if not is_valid:
                    logger.warning(f"CV+VLM selection invalid: {reason}")
                    return LocateResult(
                        success=False,
                        reason=f"Coordinate validation failed: {reason}",
                        source="cv_vlm",
                    )
            
            # Validate box size
            if selection.detection:
                box = selection.detection.box
                width = box[2] - box[0]
                height = box[3] - box[1]
                min_w, min_h = self.config.min_box_size
                
                if width < min_w or height < min_h:
                    return LocateResult(
                        success=False,
                        reason=f"Detection too small: {width}x{height}",
                        source="cv_vlm",
                    )
            
            return LocateResult(
                success=True,
                coordinates=(x, y),
                confidence=selection.confidence,
                source="cv_vlm",
                element_info={
                    "selected_id": selection.selected_id,
                    "class_name": selection.detection.class_name if selection.detection else None,
                    "box": list(selection.detection.box) if selection.detection else None,
                    "reasoning": selection.reasoning,
                    "screen_description": selection.screen_description,
                },
            )
            
        except Exception as e:
            logger.error(f"CV+VLM pipeline failed: {e}")
            return LocateResult(
                success=False,
                reason=f"CV+VLM error: {str(e)}",
                source="cv_vlm",
            )
    
    def detect_only(
        self,
        screenshot: Union[bytes, str],
        screen_bounds: Tuple[int, int] = (1080, 2400),
    ) -> list:
        """
        Run OmniParser detector without the VLM selection step.
        Returns raw Detection objects so callers can convert them to element
        dicts and pass to describe_and_locate — avoiding a separate VLM call.
        """
        try:
            return self.detector.detect(screenshot, use_cache=self.config.cache_detections)
        except Exception as e:
            logger.warning(f"detect_only failed: {e}")
            return []

    def _try_heuristic(
        self,
        screenshot: Union[bytes, str],
        intent: str,
        screen_bounds: Tuple[int, int],
    ) -> LocateResult:
        """
        Heuristic fallback when VLM fails.
        
        Uses simple class name and keyword matching.
        """
        try:
            # Reuse cached detections if available
            detections = self.detector.detect(screenshot, use_cache=True)
            
            if not detections:
                return LocateResult(
                    success=False,
                    reason="No detections for heuristic",
                    source="heuristic",
                )
            
            selection = self._heuristic.select(detections, intent)
            
            if selection.success:
                x, y = selection.coordinates
                
                if self.config.validate_bounds:
                    is_valid, _ = validate_coordinates(
                        x, y, screen_bounds[0], screen_bounds[1]
                    )
                    if not is_valid:
                        return LocateResult(
                            success=False,
                            reason="Heuristic selection out of bounds",
                            source="heuristic",
                        )
                
                return LocateResult(
                    success=True,
                    coordinates=(x, y),
                    confidence=selection.confidence,
                    source="heuristic",
                    element_info={
                        "selected_id": selection.selected_id,
                        "reasoning": selection.reasoning,
                    },
                )
            
            return LocateResult(
                success=False,
                reason="Heuristic matching failed",
                source="heuristic",
            )
            
        except Exception as e:
            logger.error(f"Heuristic fallback failed: {e}")
            return LocateResult(
                success=False,
                reason=f"Heuristic error: {str(e)}",
                source="heuristic",
            )
    
    def get_metrics(self) -> Dict:
        """Get pipeline metrics."""
        return self.metrics.to_dict()
    
    def reset_metrics(self):
        """Reset pipeline metrics."""
        self.metrics = PerceptionMetrics()


def create_perception_pipeline(vlm_service: VLMService) -> PerceptionPipeline:
    """
    Factory function to create a perception pipeline with defaults.
    
    Args:
        vlm_service: VLMService instance for VLM calls.
        
    Returns:
        Configured PerceptionPipeline instance.
    """
    return PerceptionPipeline(vlm_service=vlm_service)


def create_default_pipeline(vlm_service: VLMService) -> PerceptionPipeline:
    """Alias for create_perception_pipeline for backward compatibility."""
    return create_perception_pipeline(vlm_service)
