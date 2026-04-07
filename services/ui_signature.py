"""
UI signature generation for state tracking and loop detection.

Generates stable hashes from UI tree state to detect:
- Same screen loops (stuck on same UI)
- UI changes after actions (validation)
"""

import hashlib
import json
from typing import Optional, Any, List, Union


def compute_ui_signature(
    ui_data: Optional[Union[dict, List[dict]]],
    screen_height: Optional[int] = None,
) -> str:
    """
    Compute a stable hash signature from UI tree or elements list.
    
    Extracts key structural elements to create a fingerprint that:
    - Changes when meaningful UI changes occur
    - Stays stable for minor variations (resource IDs, exact coordinates)
    - Weights content-zone elements higher than status/nav bars when screen_height is provided
    
    Args:
        ui_data: The UI tree payload (dict with children) or elements list (List[dict])
        screen_height: Device screen height in pixels. Enables zone weighting when provided.
        
    Returns:
        Hex digest string representing UI state, or empty string if no data
    """
    if not ui_data:
        return ""
    
    # Handle list of elements (flat format from UITreePayload.elements)
    if isinstance(ui_data, list):
        features = _extract_features_from_list(ui_data, screen_height=screen_height)
    else:
        # Handle dict (tree format with children)
        features = _extract_features(ui_data)
    
    # Create deterministic JSON representation
    features_json = json.dumps(features, sort_keys=True)
    
    return hashlib.md5(features_json.encode()).hexdigest()[:16]


def _extract_features_from_list(
    elements: List[dict],
    max_elements: int = 20,
    screen_height: Optional[int] = None,
) -> dict:
    """
    Extract structural features from flat UI elements list.
    
    When screen_height is provided, applies zone weighting:
    - STATUS zone (top 5%): weight 0.1 — clock, battery changes don't matter
    - HEADER zone (5-15%): weight 0.5
    - CONTENT zone (15-85%): weight 3.0 — most important for change detection
    - NAV_BAR zone (85-100%): weight 0.2 — bottom nav rarely changes
    Elements with weight < 0.5 are excluded from the signature.
    """
    included_elements = []

    for elem in elements[:max_elements]:
        if not isinstance(elem, dict):
            continue

        # Zone weighting: skip low-weight elements
        if screen_height:
            bounds = _get_bounds_from_element(elem)
            top = bounds.get("top", 0) if bounds else 0
            zone = _get_zone(top, screen_height)
            weight = _ZONE_WEIGHTS.get(zone, 1.0)
            if weight < 0.5:
                continue

        elem_features = {
            "class": _get_short_class(elem.get("className", "")),
            "text": _truncate(elem.get("text", ""), 50),
            "desc": _truncate(elem.get("contentDescription", ""), 30),
            "click": elem.get("clickable", elem.get("isClickable", False)),
            "focus": elem.get("focusable", elem.get("isFocusable", False)),
        }
        
        # Include bounds for position
        bounds = _get_bounds_from_element(elem)
        if bounds:
            elem_features["bounds"] = _quantize_bounds(bounds)
        
        included_elements.append(elem_features)

    return {
        "element_count": len(included_elements),
        "elements": included_elements,
    }


def _get_bounds_from_element(elem: dict) -> Optional[dict]:
    """Extract bounds from element in various formats."""
    # Try standard format
    if "left" in elem and "top" in elem:
        return {
            "left": elem.get("left", 0),
            "top": elem.get("top", 0),
            "right": elem.get("right", 0),
            "bottom": elem.get("bottom", 0),
        }
    # Try visibleBounds or boundsInScreen format
    return elem.get("visibleBounds") or elem.get("boundsInScreen")


def _extract_features(node: dict, depth: int = 0, max_depth: int = 5) -> dict:
    """
    Recursively extract structural features from UI tree node.
    
    Focuses on:
    - Node types (class names)
    - Text content (truncated)
    - Clickable/focusable state
    - Tree structure (depth-limited)
    """
    if depth > max_depth:
        return {"truncated": True}
    
    features = {
        "class": _get_short_class(node.get("className", "")),
        "text": _truncate(node.get("text", ""), 50),
        "desc": _truncate(node.get("contentDescription", ""), 30),
        "click": node.get("clickable", False),
        "focus": node.get("focusable", False),
    }
    
    # Include visible bounds as rough position indicator
    bounds = node.get("visibleBounds") or node.get("boundsInScreen")
    if bounds:
        # Quantize to reduce noise from minor position changes
        features["bounds"] = _quantize_bounds(bounds)
    
    # Recurse into children
    children = node.get("children", [])
    if children:
        features["children"] = [
            _extract_features(child, depth + 1, max_depth)
            for child in children[:10]  # Limit children to prevent explosion
        ]
    
    return features


def _get_short_class(class_name: str) -> str:
    """Extract short class name from fully qualified name."""
    if not class_name:
        return ""
    parts = class_name.split(".")
    return parts[-1] if parts else class_name


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max length."""
    if not text:
        return ""
    text = str(text).strip()
    return text[:max_len] if len(text) > max_len else text


def _quantize_bounds(bounds: dict) -> tuple:
    """
    Quantize bounds to reduce sensitivity to minor position changes.
    
    Divides coordinates by 50 to create coarse position buckets.
    """
    quantize = lambda x: int(x // 50) * 50 if x else 0
    return (
        quantize(bounds.get("left", 0)),
        quantize(bounds.get("top", 0)),
        quantize(bounds.get("right", 0)),
        quantize(bounds.get("bottom", 0)),
    )


# Zone weights for content-aware signature weighting
_ZONE_WEIGHTS = {"STATUS": 0.1, "HEADER": 0.5, "CONTENT": 3.0, "NAV_BAR": 0.2}


def _get_zone(top: int, screen_height: int) -> str:
    """Classify an element into a screen zone by its top coordinate."""
    if screen_height <= 0:
        return "CONTENT"
    ratio = top / screen_height
    if ratio < 0.05:
        return "STATUS"
    if ratio < 0.15:
        return "HEADER"
    if ratio < 0.85:
        return "CONTENT"
    return "NAV_BAR"


def signatures_differ(sig1: str, sig2: str) -> bool:
    """Check if two signatures represent different UI states."""
    if not sig1 or not sig2:
        return True  # Treat missing signatures as different
    return sig1 != sig2


def compute_content_signature(elements: Optional[List[dict]]) -> str:
    """
    Content-aware signature that hashes the *text values* of every
    display/input element regardless of position in the element list.

    Complements ``compute_ui_signature`` which only inspects the first
    20 elements for structural features.  Use-cases where the structural
    signature stays identical but this one changes:

    - Calculator display: "1" → "1+" → "1+1"  (text of a single TextView)
    - Search results count: "24 results" → "12 results"
    - Form validation message appearing below a field
    - Any EditText whose content changes after a type action

    Only captures elements whose ``className`` suggests they carry visible
    text (TextView, EditText, TextInputEditText, CheckedTextView, etc.).
    Pure layout containers are excluded to keep the hash stable against
    irrelevant hierarchy shifts.

    Returns:
        16-char hex digest, or empty string if no text-bearing elements.
    """
    if not elements:
        return ""

    _TEXT_CLASS_FRAGMENTS = {
        "textview", "edittext", "textinput", "checkedtext",
        "button",  # buttons often show dynamic labels (e.g. "Add to cart" → "Added")
        "chip", "radiobutton", "checkbox", "switch",
        "autocomplete",
    }

    tokens: list = []
    for el in elements:
        class_name = (el.get("className") or "").lower()
        if not any(frag in class_name for frag in _TEXT_CLASS_FRAGMENTS):
            continue
        text = (el.get("text") or "").strip()
        desc = (el.get("contentDescription") or "").strip()
        label = text or desc
        if label:
            tokens.append(label[:80])   # cap per-element to avoid runaway input

    if not tokens:
        return ""

    return hashlib.md5("|".join(tokens).encode()).hexdigest()[:16]


def compute_lightweight_signature(ui_data: Optional[Union[dict, List[dict]]]) -> str:
    """
    Compute a very fast, lightweight signature.
    
    Only looks at top-level structure for quick comparisons.
    Use when full signature computation is too slow.
    """
    if not ui_data:
        return ""
    
    # Handle list of elements (flat format)
    if isinstance(ui_data, list):
        element_classes = [_get_short_class(e.get("className", "")) for e in ui_data[:5] if isinstance(e, dict)]
        features = {
            "element_count": len(ui_data),
            "top_elements": element_classes,
        }
    else:
        # Handle dict (tree format with children)
        children = ui_data.get("children", [])
        child_classes = [_get_short_class(c.get("className", "")) for c in children[:5]]
        
        features = {
            "root": _get_short_class(ui_data.get("className", "")),
            "child_count": len(children),
            "top_children": child_classes,
        }
    
    return hashlib.md5(json.dumps(features, sort_keys=True).encode()).hexdigest()[:8]
