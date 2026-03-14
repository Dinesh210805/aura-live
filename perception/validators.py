"""
Perception validators - Freshness & integrity checks.

Validates perception data according to blueprint rules.
"""

import time
from typing import Optional, Tuple

from perception.models import PerceptionBundle, UITreePayload
from utils.logger import get_logger

logger = get_logger(__name__)

# Safety thresholds
MIN_NODE_COUNT = 3  # Minimum nodes required for valid UI tree
MAX_BUNDLE_AGE_SECONDS = 2.0  # Bundle invalid after 2 seconds
INVALID_BOUNDS_THRESHOLD = 0.9  # If >90% nodes have invalid bounds, reject tree

# App categories that should not use UI tree
CANVAS_APP_CATEGORIES = {"game", "camera", "map", "canvas", "drawing"}

# Permission dialog detection patterns
PERMISSION_DIALOG_INDICATORS = {
    # MediaProjection permission dialog markers
    "texts": [
        "cast your screen?",
        "start now",
        "start recording",
        "screen capture",
        "record screen",
        "record or cast",
        "everything on your screen",
        "will be able to see everything",
        "sensitive information",
        "allow display over other apps",
        "draw over other apps",
    ],
    # System UI packages that show permission dialogs
    "system_packages": [
        "com.android.systemui",
        "com.android.permissioncontroller",
        "com.google.android.permissioncontroller",
        "android",
    ],
}


def detect_permission_dialog(ui_tree: Optional[UITreePayload]) -> Tuple[bool, Optional[str]]:
    """
    Detect if the current screen shows a system permission dialog.
    
    This detects MediaProjection permission dialogs ("Cast your screen?"),
    overlay permission dialogs, and similar system prompts that the agent
    should NOT interact with.
    
    Args:
        ui_tree: UI tree payload to analyze
        
    Returns:
        Tuple of (is_permission_dialog, dialog_type)
        dialog_type examples: "screen_capture", "overlay", "unknown_system"
    """
    if ui_tree is None or not ui_tree.elements:
        return False, None
    
    detected_texts = []
    is_system_package = False
    
    for element in ui_tree.elements:
        # Check package name
        package = element.get("packageName", "").lower()
        if any(sp in package for sp in PERMISSION_DIALOG_INDICATORS["system_packages"]):
            is_system_package = True
        
        # Check text content
        text = (element.get("text", "") or "").lower()
        content_desc = (element.get("contentDescription", "") or "").lower()
        combined_text = f"{text} {content_desc}"
        
        for pattern in PERMISSION_DIALOG_INDICATORS["texts"]:
            if pattern in combined_text:
                detected_texts.append(pattern)
    
    # Decision logic: system package + permission-related text = permission dialog
    if is_system_package and detected_texts:
        # Determine dialog type
        if any(p in detected_texts for p in ["cast your screen?", "screen capture", "record screen"]):
            dialog_type = "screen_capture"
        elif any(p in detected_texts for p in ["allow display over other apps", "draw over other apps"]):
            dialog_type = "overlay"
        else:
            dialog_type = "unknown_system"
        
        logger.info(
            f"🚫 Permission dialog detected: type={dialog_type}, "
            f"indicators={detected_texts[:3]}"
        )
        return True, dialog_type
    
    return False, None


def validate_bundle_freshness(bundle: PerceptionBundle) -> bool:
    """
    Validate that perception bundle is fresh.

    Args:
        bundle: Perception bundle to validate

    Returns:
        True if bundle is fresh, False if stale
    """
    age = bundle.get_age_seconds()
    if age > MAX_BUNDLE_AGE_SECONDS:
        logger.warning(
            f"❌ Bundle stale: age={age:.2f}s, threshold={MAX_BUNDLE_AGE_SECONDS}s, "
            f"snapshot_id={bundle.snapshot_id}"
        )
        return False
    return True


def validate_ui_tree(ui_tree: Optional[UITreePayload]) -> tuple[bool, Optional[str]]:
    """
    Validate UI tree according to blueprint rejection conditions.

    UI Tree is discarded if:
    - Root node is null
    - All nodes lack valid bounds
    - Node count < safety threshold
    - App category is canvas / game / map / camera
    - Tree is unchanged after a UI_ACTION (handled separately)

    Args:
        ui_tree: UI tree payload to validate

    Returns:
        (is_valid, rejection_reason)
    """
    if ui_tree is None:
        return False, "UI tree is None"

    elements = ui_tree.elements
    if not elements:
        return False, "UI tree has no elements"

    # Check node count threshold
    if len(elements) < MIN_NODE_COUNT:
        return (
            False,
            f"UI tree has too few nodes: {len(elements)} < {MIN_NODE_COUNT}",
        )

    # Check for valid bounds
    nodes_with_valid_bounds = 0
    for element in elements:
        bounds = element.get("bounds", {})
        if isinstance(bounds, dict):
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = bounds.get("right", 0)
            bottom = bounds.get("bottom", 0)
            if right > left and bottom > top:
                nodes_with_valid_bounds += 1
        elif isinstance(bounds, list) and len(bounds) >= 4:
            left, top, right, bottom = bounds[:4]
            if right > left and bottom > top:
                nodes_with_valid_bounds += 1

    valid_bounds_ratio = nodes_with_valid_bounds / len(elements)
    if valid_bounds_ratio < (1.0 - INVALID_BOUNDS_THRESHOLD):
        return (
            False,
            f"Too many nodes have invalid bounds: {valid_bounds_ratio:.2%} valid",
        )

    # Check app category (if available)
    # This would need to be passed separately or extracted from elements
    # For now, we'll skip this check as it requires app context

    return True, None


def validate_screenshot(
    screenshot: Optional["ScreenshotPayload"],
) -> tuple[bool, Optional[str]]:
    """
    Validate screenshot integrity.

    Args:
        screenshot: Screenshot payload to validate

    Returns:
        (is_valid, rejection_reason)
    """
    import base64
    
    if screenshot is None:
        return False, "Screenshot is None"

    if not screenshot.screenshot_base64:
        return False, "Screenshot data is empty"

    # Check minimum size (1x1 PNG is ~100 bytes base64)
    if len(screenshot.screenshot_base64) < 100:
        return False, f"Screenshot too small: {len(screenshot.screenshot_base64)} bytes"

    # Check dimensions
    if screenshot.screen_width <= 0 or screenshot.screen_height <= 0:
        return False, f"Invalid screen dimensions: {screenshot.screen_width}x{screenshot.screen_height}"

    # Validate base64 decodability
    try:
        decoded = base64.b64decode(screenshot.screenshot_base64)
        if len(decoded) < 50:  # Minimum reasonable image size
            return False, f"Decoded screenshot too small: {len(decoded)} bytes"
        
        # Check for common image headers (JPEG starts with FFD8, PNG with 89504E47)
        if not (decoded[:2] == b'\xff\xd8' or decoded[:4] == b'\x89PNG'):
            logger.warning(f"Screenshot may not be a valid image: header bytes {decoded[:4].hex()}")
    except Exception as e:
        return False, f"Base64 decode failed: {str(e)}"

    return True, None


def validate_bundle_integrity(bundle: PerceptionBundle) -> tuple[bool, Optional[str]]:
    """
    Validate overall bundle integrity.

    Args:
        bundle: Perception bundle to validate

    Returns:
        (is_valid, rejection_reason)
    """
    # Check freshness
    if not validate_bundle_freshness(bundle):
        return False, "Bundle is stale"

    # Validate based on modality
    if bundle.modality == "ui_tree":
        is_valid, reason = validate_ui_tree(bundle.ui_tree)
        if not is_valid:
            return False, f"UI tree validation failed: {reason}"
    elif bundle.modality == "vision":
        is_valid, reason = validate_screenshot(bundle.screenshot)
        if not is_valid:
            return False, f"Screenshot validation failed: {reason}"
    elif bundle.modality == "hybrid":
        # Both must be valid for hybrid
        ui_valid, ui_reason = validate_ui_tree(bundle.ui_tree)
        screenshot_valid, screenshot_reason = validate_screenshot(bundle.screenshot)

        if not ui_valid and not screenshot_valid:
            return False, f"Both UI tree and screenshot invalid: UI={ui_reason}, Screenshot={screenshot_reason}"
        elif not ui_valid:
            logger.warning(f"⚠️ UI tree invalid in hybrid mode: {ui_reason}, falling back to vision-only")
        elif not screenshot_valid:
            logger.warning(f"⚠️ Screenshot invalid in hybrid mode: {screenshot_reason}, falling back to UI-tree-only")

    return True, None
