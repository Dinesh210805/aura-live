"""
App Category Classifier - Detect app types for modality selection.

DEPRECATED: This module previously contained hardcoded package lists for 
games/cameras/maps. That approach was removed because:

1. Lists can never be complete (thousands of apps exist)
2. Some listed apps (Instagram, Spotify) actually have good UI trees
3. Android-side UITreeValidator already detects bad trees dynamically
   and signals requires_vision=true when tree is garbage

Now we rely on DYNAMIC detection:
- Android validates UI tree quality (node count, bounds ratio)
- If tree is garbage → Android sends requires_vision=true
- Python perception_controller handles that signal

The classify_app() function is kept for backward compatibility but
always returns STANDARD with requires_vision=False. The actual
vision detection happens via Android's validation response.
"""

from enum import Enum
from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class AppCategory(str, Enum):
    """App category for modality selection."""
    
    STANDARD = "standard"  # Normal UI apps - UI tree works well
    GAME = "game"  # Games - canvas rendering, no accessibility
    CAMERA = "camera"  # Camera apps - real-time viewfinder
    MAP = "map"  # Map apps - canvas/tile rendering
    VIDEO = "video"  # Video players - media surface
    CANVAS = "canvas"  # Drawing/editing apps
    UNKNOWN = "unknown"


def classify_app(package_name: Optional[str]) -> Tuple[AppCategory, bool]:
    """
    Classify app by package name.
    
    NOTE: This now always returns STANDARD. Actual vision-required detection
    happens dynamically via Android's UITreeValidator which checks tree quality.
    
    Args:
        package_name: Android package name (e.g., "com.google.android.apps.maps")
    
    Returns:
        Tuple of (AppCategory, requires_vision)
        - Always (STANDARD, False) now - dynamic detection handles vision apps
    """
    if not package_name:
        return AppCategory.UNKNOWN, False
    
    # Dynamic detection via Android validator is preferred
    # The validator checks actual tree quality, not package names
    return AppCategory.STANDARD, False


def requires_vision_mode(package_name: Optional[str]) -> bool:
    """
    Quick check if app requires vision-only mode.
    
    NOTE: Always returns False now. Actual detection happens via
    Android's UITreeValidator which checks tree quality dynamically.
    
    Args:
        package_name: Android package name
    
    Returns:
        Always False - dynamic detection handles this
    """
    return False


def get_cached_category(package_name: Optional[str]) -> Tuple[AppCategory, bool]:
    """
    Get app category (simplified - no caching needed since always returns STANDARD).
    
    Args:
        package_name: Android package name
    
    Returns:
        Tuple of (AppCategory, requires_vision)
    """
    return classify_app(package_name)


def clear_classifier_cache():
    """Clear the classifier cache (no-op now)."""
    pass
