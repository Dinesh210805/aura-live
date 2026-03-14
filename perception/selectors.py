"""
Modality selection logic - Deterministic decision making.

Implements the dynamic modality selection logic from the blueprint.
"""

from typing import Dict, List, Optional

from perception.models import PerceptionModality
from utils.logger import get_logger
from config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Visual keywords that indicate vision is needed
VISUAL_KEYWORDS = {
    "color", "icon", "image", "picture", "photo", "logo",
    "first", "second", "third", "top", "bottom", "left", "right",
    "above", "below", "beside", "next to", "profile", "avatar", "thumbnail"
}

# Standard UI patterns that work well with UI tree
UI_TREE_FRIENDLY_PATTERNS = {"button", "form", "list", "recycler", "text_field", "checkbox", "radio"}


def select_modality(
    intent: Dict,
    ui_tree_available: bool = True,
    screenshot_available: bool = True,
    previous_failure: bool = False,
    app_category: Optional[str] = None,
    package_name: Optional[str] = None,
) -> PerceptionModality:
    """
    Select perception modality based on intent and context.

    Decision logic:
    - Standard buttons / forms → UI_TREE
    - Lists / recyclers → UI_TREE
    - Icons / image buttons → VISION
    - Canvas / custom UI → VISION
    - Ambiguous layouts → HYBRID
    - Retry after failure → HYBRID

    Args:
        intent: Parsed intent object
        ui_tree_available: Whether UI tree is available
        screenshot_available: Whether screenshot capture is available
        previous_failure: Whether previous execution failed
        app_category: App category if known (deprecated, use package_name)
        package_name: Android package name for classification

    Returns:
        Selected perception modality
    """
    action = intent.get("action", "").lower()
    recipient = (intent.get("recipient") or "").lower()
    content = (intent.get("content") or "").lower()
    parameters = intent.get("parameters", {})
    
    # Combine all text for keyword detection
    combined_text = f"{action} {recipient} {content} {parameters}".lower()

    # Retry after failure → HYBRID
    if previous_failure:
        logger.info("🔄 Previous failure detected → selecting HYBRID modality")
        return PerceptionModality.HYBRID

    # HYBRID default: If both available and mode is hybrid, prefer HYBRID for full context
    if ui_tree_available and screenshot_available and settings.default_perception_modality == "hybrid":
        # Check if app is in fast perception list (where UI_TREE is sufficient)
        if package_name and package_name in settings.fast_perception_apps:
            logger.info(f"📋 Package '{package_name}' in fast perception list → using UI_TREE")
            return PerceptionModality.UI_TREE
        
        # Otherwise default to HYBRID for maximum context
        logger.info("🎯 Both screenshot and UI tree available → defaulting to HYBRID mode")
        return PerceptionModality.HYBRID

    # NOTE: App-based vision mode detection removed - Android's UITreeValidator 
    # dynamically detects when UI tree is garbage and signals requires_vision=true.
    # This is more accurate than hardcoded package lists.

    # Visual keywords → VISION or HYBRID
    has_visual_keywords = any(keyword in combined_text for keyword in VISUAL_KEYWORDS)
    if has_visual_keywords:
        logger.info("👁️ Visual keywords detected → selecting VISION modality")
        if screenshot_available:
            # If UI tree also available and action is ambiguous, use HYBRID
            if ui_tree_available and _is_ambiguous_action(action):
                return PerceptionModality.HYBRID
            return PerceptionModality.VISION
        elif ui_tree_available:
            logger.warning("⚠️ Vision preferred but screenshot unavailable, using UI_TREE")
            return PerceptionModality.UI_TREE
        else:
            raise ValueError("Visual keywords detected but no perception data available")

    # Standard UI patterns → Only use UI_TREE if mode is explicitly "auto" or "ui_tree"
    # Otherwise defer to HYBRID default (already handled above)
    if settings.default_perception_modality in ["auto", "ui_tree"]:
        if _is_standard_ui_action(action, recipient, content):
            logger.info("📋 Standard UI action + auto/ui_tree mode → selecting UI_TREE modality")
            if ui_tree_available:
                return PerceptionModality.UI_TREE
            elif screenshot_available:
                logger.warning("⚠️ UI tree preferred but unavailable, falling back to VISION")
                return PerceptionModality.VISION
            else:
                raise ValueError("Standard UI action but no perception data available")

    # Ambiguous → HYBRID if both available, otherwise best available
    if ui_tree_available and screenshot_available:
        logger.info("🤔 Ambiguous action → selecting HYBRID modality")
        return PerceptionModality.HYBRID
    elif ui_tree_available:
        return PerceptionModality.UI_TREE
    elif screenshot_available:
        return PerceptionModality.VISION
    else:
        logger.error(
            f"❌ No perception data available: ui_tree={ui_tree_available}, "
            f"screenshot={screenshot_available}. Device may not be connected via WebSocket."
        )
        raise ValueError(
            "No perception data available - device may not be connected via WebSocket. "
            "Please ensure the AURA app is open and connected to the server."
        )


def _is_ambiguous_action(action: str) -> bool:
    """Check if action is ambiguous and might benefit from hybrid approach."""
    ambiguous_actions = {
        "tap", "click", "open", "navigate", "find", "select", "choose"
    }
    return action in ambiguous_actions


def _is_standard_ui_action(action: str, recipient: str, content: str) -> bool:
    """Check if action targets standard UI elements (buttons, forms, lists)."""
    standard_actions = {
        "send_message", "open_app", "fill_form", "submit", "select_option",
        "scroll", "navigate", "search"
    }
    
    # Check if action is standard
    if action in standard_actions:
        return True
    
    # Check for standard UI patterns in recipient/content
    standard_patterns = {"button", "form", "list", "menu", "dialog", "field"}
    combined = f"{recipient} {content}".lower()
    return any(pattern in combined for pattern in standard_patterns)
