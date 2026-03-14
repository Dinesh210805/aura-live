"""
UI Perception Pipeline - Industry-Grade Blueprint Implementation

This package implements the authoritative perception system for AURA,
following the UI Perception Pipeline blueprint.

Includes OmniParser hybrid architecture:
- Layer 1: UI Tree matching (fast, primary)
- Layer 2: CV Detection via YOLOv8 (fallback for WebView/Canvas)
- Layer 3: VLM Semantic Selection (ID-based, no coordinate hallucination)
"""

from perception.models import (
    PerceptionBundle,
    PerceptionModality,
    ScreenshotPayload,
    UITreePayload,
)
from perception.app_classifier import (
    AppCategory,
    classify_app,
    requires_vision_mode,
)

# OmniParser hybrid perception components (lazy-loaded)
# Import these only when needed to avoid heavy dependencies at startup
def get_omniparser_detector():
    """Lazy import of OmniParserDetector to avoid startup cost."""
    from perception.omniparser_detector import OmniParserDetector, Detection, create_detector
    return OmniParserDetector, Detection, create_detector

def get_vlm_selector():
    """Lazy import of VLMSelector."""
    from perception.vlm_selector import VLMSelector, SelectionResult, create_vlm_selector
    return VLMSelector, SelectionResult, create_vlm_selector

def get_perception_pipeline():
    """Lazy import of PerceptionPipeline."""
    from perception.perception_pipeline import (
        PerceptionPipeline, 
        PerceptionConfig, 
        LocateResult,
        create_perception_pipeline,
    )
    return PerceptionPipeline, PerceptionConfig, LocateResult, create_perception_pipeline


__all__ = [
    # Core perception models
    "PerceptionBundle",
    "PerceptionModality",
    "ScreenshotPayload",
    "UITreePayload",
    # App classification
    "AppCategory",
    "classify_app",
    "requires_vision_mode",
    # Lazy loaders for OmniParser components
    "get_omniparser_detector",
    "get_vlm_selector",
    "get_perception_pipeline",
]
