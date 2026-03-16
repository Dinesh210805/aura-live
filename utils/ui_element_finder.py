"""
UI Element Finder Utility.

Provides reliable element finding from UI tree data.
Uses text matching, content description, resource ID patterns,
and semantic understanding of common UI elements.
"""

from typing import Any, Dict, List, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

# All known className substrings that identify an interactive input field.
# Covers: standard Android views, Gmail RecipientEditTextView, React Native,
# Flutter (semantic bridge), search bars, OTP/PIN inputs, custom text fields.
_INPUT_CLASS_KEYWORDS: tuple = (
    "edittext", "textinput", "autocomplete", "multiautocomplete",
    "recipient", "searchview", "searchedittext", "searchbar",
    "pinview", "otpview", "codeview", "codeinput", "codeentry",
    "passwordinput", "passwordview", "amountinput", "phoneinput",
    "emailinput", "textfield", "clearableedittext", "floatinglabel",
)

_NULL_INPUT_TYPES = frozenset({0, "0", "none", "TYPE_NULL", "TYPE_CLASS_NULL"})


def is_input_element(el: dict) -> bool:
    """
    Return True if this accessibility element is an interactive input field.

    Uses three independent signals so any one is sufficient:
      1. editable / isEditable attribute set by the framework
      2. inputType non-zero/non-null (OS-level signal, set even on custom views)
      3. className substring match against known input view types

    Works across any Android app, framework, or custom View subclass.
    """
    if el.get("editable") or el.get("isEditable"):
        return True
    input_type = el.get("inputType")
    if input_type is not None and input_type not in _NULL_INPUT_TYPES:
        return True
    cls = (el.get("className") or "").lower()
    return any(kw in cls for kw in _INPUT_CLASS_KEYWORDS)


def element_display_label(el: dict) -> str:
    """
    Return the best human-readable label for a UI element.

    For input fields with no text/contentDescription, falls back to
    hint/hintText (the placeholder) so empty-but-labelled fields like
    Gmail's To / Subject fields are never silent in LLM hint strings.
    """
    label = (el.get("text") or el.get("contentDescription") or "").strip()
    if not label and is_input_element(el):
        placeholder = (el.get("hint") or el.get("hintText") or "").strip()
        if placeholder:
            return f"[placeholder: {placeholder}]"
    return label

# Semantic aliases - what users might say vs what the UI might contain
SEMANTIC_ALIASES = {
    # Profile/Account related
    "profile": ["profile", "account", "me", "my profile", "user", "avatar"],
    "my profile": ["profile", "account", "me", "you", "avatar"],
    "account": ["account", "profile", "settings", "my account"],
    
    # Navigation
    "home": ["home", "feed", "main", "start"],
    "back": ["back", "return", "previous", "navigate up"],
    "search": ["search", "find", "explore", "discover"],
    "menu": ["menu", "more", "options", "hamburger", "overflow"],
    "settings": ["settings", "preferences", "config", "gear", "cog"],
    
    # Social/Communication
    "send": ["send", "submit", "post", "share"],
    "like": ["like", "love", "heart", "favorite"],
    "comment": ["comment", "reply", "respond"],
    "share": ["share", "send to", "forward"],
    "follow": ["follow", "subscribe", "add"],
    "message": ["message", "chat", "dm", "direct message", "inbox"],
    
    # Media
    "camera": ["camera", "photo", "capture", "take picture"],
    "gallery": ["gallery", "photos", "images", "albums"],
    "video": ["video", "reels", "shorts", "watch"],
    
    # App-specific common elements
    "stories": ["stories", "story", "status"],
    "reels": ["reels", "shorts", "video"],
    "notifications": ["notifications", "alerts", "bell", "inbox"],
    "explore": ["explore", "discover", "search", "browse"],
    
    # Music/Playlist related (Spotify, YouTube Music, etc.)
    "liked songs": ["liked songs", "liked music", "favorite songs", "favorites", "your likes", "my likes", "liked", "favourite songs", "favourite music"],
    "playlist": ["playlist", "my playlist", "playlists", "your playlists"],
    "library": ["library", "your library", "my library", "collection", "media library"],
    "play": ["play", "start", "resume", "unpause", "play music"],
    "home": ["home", "feed", "main", "start", "home screen", "home tab"],
    "search spotify": ["search", "find", "explore", "discover", "search spotify"],
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    return text.lower().strip()


def get_semantic_matches(target: str) -> List[str]:
    """Get list of semantic variants for a target."""
    target_lower = normalize_text(target)
    
    # Check if target matches any alias category
    for category, aliases in SEMANTIC_ALIASES.items():
        if target_lower in aliases or target_lower == category:
            return aliases
    
    # Also check if any alias contains the target
    for category, aliases in SEMANTIC_ALIASES.items():
        for alias in aliases:
            if target_lower in alias or alias in target_lower:
                return aliases
    
    # No semantic match, return just the target
    return [target_lower]


def calculate_match_score(element: Dict[str, Any], target: str) -> float:
    """
    Calculate match score between element and target description.
    
    Uses semantic understanding to match user intent with UI elements.
    Returns score 0.0-1.0 where higher is better match.
    """
    if not target:
        return 0.0
    
    target_lower = normalize_text(target)
    
    # Get semantic variants
    search_terms = get_semantic_matches(target)
    
    # Extract element properties
    text = normalize_text(element.get("text", ""))
    content_desc = normalize_text(element.get("contentDescription", ""))
    resource_id = normalize_text(element.get("resourceId", ""))
    class_name = normalize_text(element.get("className", ""))
    hint = normalize_text(element.get("hint", ""))
    
    best_score = 0.0
    
    for term in search_terms:
        # Exact text match = highest score
        if term == text:
            best_score = max(best_score, 1.0)
        elif term == content_desc:
            best_score = max(best_score, 0.95)
        elif term == hint:
            best_score = max(best_score, 0.90)
        
        # Contains match
        elif term in text:
            best_score = max(best_score, 0.85)
        elif term in content_desc:
            best_score = max(best_score, 0.80)
        elif text and text in term:
            best_score = max(best_score, 0.70)
        elif content_desc and content_desc in term:
            best_score = max(best_score, 0.65)
        
        # Resource ID match (e.g., "bottom_nav_profile" matches "profile")
        elif term.replace(" ", "_") in resource_id or term.replace(" ", "") in resource_id:
            best_score = max(best_score, 0.75)
        
        # Partial resource ID match
        elif any(word in resource_id for word in term.split()):
            best_score = max(best_score, 0.55)
    
    # Class name hints (button, edittext, etc.)
    if "button" in target_lower and "button" in class_name:
        if text or content_desc:
            best_score = max(best_score, 0.40)
    if "edit" in target_lower or "input" in target_lower or "text field" in target_lower:
        if "edittext" in class_name or "textinputedittext" in class_name:
            best_score = max(best_score, 0.50)
    
    # Penalize contentDescription-only matches when the element has visible text
    # that contradicts the target.  Example: Gmail's "Help me write" AI button
    # carries contentDescription="Message body" — we must not treat it as the
    # compose body EditText.
    if best_score >= 0.85 and text:
        text_matches = any(
            term == text or term in text or text in term
            for term in search_terms
        )
        if not text_matches:
            best_score = min(best_score, 0.60)

    return best_score


def get_element_center(element: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Get center coordinates of an element from its bounds."""
    bounds = element.get("bounds", {})
    
    if isinstance(bounds, str):
        # Android string format: "[left,top][right,bottom]"
        import re
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if match:
            left, top, right, bottom = [int(x) for x in match.groups()]
            if right > left and bottom > top:
                center_x = (left + right) // 2
                center_y = (top + bottom) // 2
                return (center_x, center_y)
    
    elif isinstance(bounds, dict):
        # Dict format: {left, top, right, bottom}
        left = bounds.get("left", 0)
        top = bounds.get("top", 0)
        right = bounds.get("right", 0)
        bottom = bounds.get("bottom", 0)
        
        # Also check for centerX/centerY if provided
        if "centerX" in bounds and "centerY" in bounds:
            return (bounds["centerX"], bounds["centerY"])
        
        if right > left and bottom > top:
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2
            return (center_x, center_y)
    
    elif isinstance(bounds, list) and len(bounds) >= 4:
        # List format: [left, top, right, bottom]
        left, top, right, bottom = bounds[:4]
        if right > left and bottom > top:
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2
            return (center_x, center_y)
    
    return None


def find_element(
    elements: List[Dict[str, Any]],
    target: str,
    min_score: float = 0.5,
    prefer_clickable: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Find best matching element from UI tree.
    
    Args:
        elements: List of UI elements from perception bundle
        target: Text/description to search for
        min_score: Minimum match score (0.0-1.0)
        prefer_clickable: Prefer clickable elements over non-clickable
        
    Returns:
        Best matching element with coordinates, or None
    """
    if not elements or not target:
        return None
    
    best_match = None
    best_score = 0.0
    
    # Track top candidates for debugging
    candidates = []
    
    for elem in elements:
        score = calculate_match_score(elem, target)
        
        # Boost score for clickable elements
        if prefer_clickable and elem.get("clickable", False):
            score += 0.1
        
        # Boost for enabled elements
        if elem.get("enabled", True):
            score += 0.05
        
        if score > best_score and score >= min_score:
            # Verify we can get coordinates
            center = get_element_center(elem)
            if center:
                best_score = score
                best_match = {
                    "element": elem,
                    "x": center[0],
                    "y": center[1],
                    "score": score,
                    "text": elem.get("text") or elem.get("contentDescription") or "",
                }
        
        # Track top candidates for debug logging
        if score >= 0.3:  # Only log reasonable candidates
            candidates.append({
                "text": elem.get("text") or elem.get("contentDescription") or "[no text]",
                "score": score,
                "clickable": elem.get("clickable", False)
            })
    
    if best_match:
        logger.info(
            f"✅ Found element '{target}' at ({best_match['x']}, {best_match['y']}) "
            f"score={best_score:.2f}, text='{best_match['text'][:30]}'"
        )
    else:
        # Log top candidates to help debug why match failed
        logger.warning(f"❌ Element '{target}' not found (min_score={min_score})")
        if candidates:
            top_candidates = sorted(candidates, key=lambda c: c["score"], reverse=True)[:3]
            logger.warning(f"   Top candidates:")
            for cand in top_candidates:
                logger.warning(f"     - '{cand['text'][:30]}' (score={cand['score']:.2f}, clickable={cand['clickable']})")
    
    return best_match


def find_editable_element(elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the first editable text field on screen."""
    for elem in elements:
        class_name = normalize_text(elem.get("className", ""))
        is_editable = elem.get("editable", False) or elem.get("isEditable", False)
        
        if is_editable or "edittext" in class_name or "textinputedittext" in class_name:
            center = get_element_center(elem)
            if center:
                logger.info(f"✅ Found editable field at ({center[0]}, {center[1]})")
                return {
                    "element": elem,
                    "x": center[0],
                    "y": center[1],
                    "score": 1.0,
                    "text": elem.get("text", ""),
                }
    
    logger.warning("❌ No editable element found")
    return None


def find_scrollable_element(elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find a scrollable container on screen."""
    for elem in elements:
        is_scrollable = elem.get("scrollable", False) or elem.get("isScrollable", False)
        class_name = normalize_text(elem.get("className", ""))
        
        if is_scrollable or "recyclerview" in class_name or "scrollview" in class_name:
            center = get_element_center(elem)
            if center:
                logger.info(f"✅ Found scrollable at ({center[0]}, {center[1]})")
                return {
                    "element": elem,
                    "x": center[0],
                    "y": center[1],
                    "score": 1.0,
                }
    
    return None


def validate_coordinates(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    status_bar_height: int = 80,
    nav_bar_height: int = 140,
) -> Tuple[bool, str]:
    """
    Validate that coordinates are safe to tap.
    
    Args:
        x, y: Tap coordinates
        screen_width, screen_height: Screen dimensions
        status_bar_height: Height of status bar (unsafe zone)
        nav_bar_height: Height of navigation bar (unsafe zone)
        
    Returns:
        (is_valid, reason) tuple
    """
    if x < 0 or y < 0:
        return False, "Negative coordinates"
    
    if x > screen_width:
        return False, f"X ({x}) exceeds screen width ({screen_width})"
    
    if y > screen_height:
        return False, f"Y ({y}) exceeds screen height ({screen_height})"
    
    # Check status bar (top unsafe zone)
    if y < status_bar_height:
        return False, f"Y ({y}) is in status bar zone (0-{status_bar_height})"
    
    # Check navigation bar (bottom unsafe zone)
    safe_bottom = screen_height - nav_bar_height
    if y > safe_bottom:
        return False, f"Y ({y}) is in nav bar zone ({safe_bottom}-{screen_height})"
    
    return True, "Valid"


def adjust_to_safe_zone(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    status_bar_height: int = 80,
    nav_bar_height: int = 140,
) -> Tuple[int, int]:
    """
    Adjust coordinates to nearest safe zone if they're in unsafe areas.
    """
    # Clamp X
    x = max(10, min(x, screen_width - 10))
    
    # Adjust Y for status bar
    if y < status_bar_height:
        y = status_bar_height + 10
    
    # Adjust Y for nav bar
    safe_bottom = screen_height - nav_bar_height
    if y > safe_bottom:
        y = safe_bottom - 10
    
    return x, y


def _associate_sibling_labels(elements) -> dict:
    """Map unlabeled editable element indices to their sibling TextView label.

    Android forms commonly use a sibling TextView (same row, to the left) as the
    visible label for an EditText, rather than nesting it in a parent with the
    field. When an EditText has no text, content-description, or hint, this
    function scans for a non-editable element with text in the same Y band
    (|center_y delta| < 80 px) that ends to the left of the field
    (right <= field_left + 60 px).

    Returns a dict: {element_index: inferred_label_text}
    """
    def _get(el, *keys, default=None):
        is_dict = isinstance(el, dict)
        for k in keys:
            v = el.get(k) if is_dict else getattr(el, k, None)
            if v is not None:
                return v
        return default

    def _bounds(el):
        b = _get(el, "bounds")
        if isinstance(b, dict):
            return b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0)
        if isinstance(b, (list, tuple)) and len(b) >= 4:
            return b[0], b[1], b[2], b[3]
        return None

    def _is_editable(el):
        if _get(el, "isEditable", "editable"):
            return True
        cls = str(_get(el, "className", "element_type", "class") or "").split(".")[-1].lower()
        return any(kw in cls for kw in _INPUT_CLASS_KEYWORDS)

    # Collect non-editable elements that carry text (potential field labels)
    label_candidates = []
    for el in elements:
        if _is_editable(el):
            continue
        text = (_get(el, "text") or "").strip()
        if not text:
            continue
        b = _bounds(el)
        if b:
            label_candidates.append((*b, text))  # (left, top, right, bottom, text)

    if not label_candidates:
        return {}

    label_map = {}
    for i, el in enumerate(elements):
        if not _is_editable(el):
            continue
        if (_get(el, "text") or "").strip():
            continue
        if (_get(el, "contentDescription", "content_description") or "").strip():
            continue
        if (_get(el, "hint", "hintText") or "").strip():
            continue
        b = _bounds(el)
        if not b:
            continue
        el_left, el_top, el_right, el_bottom = b
        el_center_y = (el_top + el_bottom) / 2
        for lx1, lt, lx2, lb, ltext in label_candidates:
            lcy = (lt + lb) / 2
            if abs(lcy - el_center_y) < 80 and lx2 <= el_left + 60:
                label_map[i] = ltext
                break

    return label_map


# AURA's own package names — filter these from the UI tree so the agent
# never sees its own overlay elements mixed in with the target app's UI.
_AURA_PACKAGES = {
    "com.aura.aura_ui",
    "com.aura.aura_ui.debug",
    "com.aura.aura_ui.feature",
    "com.aura.aura_ui.feature.debug",
}


def _is_aura_element(el) -> bool:
    """Return True if this element belongs to AURA's own overlay."""
    is_dict = isinstance(el, dict)
    pkg = (el.get("packageName") or el.get("package") or "") if is_dict \
          else (getattr(el, "packageName", None) or getattr(el, "package", None) or "")
    return str(pkg) in _AURA_PACKAGES


def format_ui_tree(elements) -> str:
    """Format UI tree elements into a rich reference string for VLM/LLM prompts.

    Surfaces resource-id, bounds, text, content-desc, hint, class, clickable,
    enabled, focused, scrollable, editable, checked, selected, password, package
    so VLM agents can make accurate element selection and state-aware decisions.

    Handles raw Android dicts, Pydantic UIElement objects, and RealUIElement dataclasses.
    AURA's own overlay elements are stripped so the agent only sees the target app.
    """
    if not elements:
        return "No UI tree data available."

    # Strip AURA's own overlay elements before anything else
    filtered = [e for e in elements if not _is_aura_element(e)]
    if not filtered:
        return "No UI tree data available."

    label_map = _associate_sibling_labels(filtered)
    lines = []
    for i, el in enumerate(filtered):
        is_dict = isinstance(el, dict)

        def _g(*keys, _el=el, _is_dict=is_dict, default=None):
            for k in keys:
                v = _el.get(k) if _is_dict else getattr(_el, k, None)
                if v is not None:
                    return v
            return default

        # Class — strip package prefix
        raw_cls = _g("className", "element_type", "class") or "View"
        cls = str(raw_cls).split(".")[-1]

        # Labels
        text = (_g("text") or "").strip()
        cd   = (_g("contentDescription", "content_description") or "").strip()
        hint = (_g("hint", "hintText") or "").strip()

        # Resource ID — strip "package:id/" prefix
        raw_rid = _g("viewId", "resourceId", "resource_id", "element_id") or ""
        rid = str(raw_rid).split("/")[-1] if raw_rid else ""

        # Package (last dotted segment)
        pkg = (_g("packageName", "package") or "").split(".")[-1]

        # Bounds → "[x1,y1→x2,y2]"
        bounds_raw = _g("bounds")
        bounds_str = ""
        if isinstance(bounds_raw, dict):
            l = bounds_raw.get("left", 0)
            t = bounds_raw.get("top", 0)
            r = bounds_raw.get("right", 0)
            b = bounds_raw.get("bottom", 0)
            bounds_str = f"[{l},{t}→{r},{b}]"
        elif isinstance(bounds_raw, (list, tuple)) and len(bounds_raw) >= 4:
            bounds_str = f"[{bounds_raw[0]},{bounds_raw[1]}→{bounds_raw[2]},{bounds_raw[3]}]"

        # Boolean flags
        clickable  = bool(_g("isClickable",  "clickable")  or False)
        enabled    = bool(_g("isEnabled",    "enabled",    default=True))
        focused    = bool(_g("focused",      "isFocused")  or False)
        scrollable = bool(_g("isScrollable", "scrollable") or False)
        editable   = bool(_g("isEditable",   "editable")   or False)
        if not editable:
            editable = any(kw in cls.lower() for kw in _INPUT_CLASS_KEYWORDS)
        checked    = bool(_g("checked",   "isChecked")  or False)
        selected   = bool(_g("selected",  "isSelected") or False)
        password   = bool(_g("password",  "isPassword") or False)

        # Primary label: text > content-desc > hint > sibling-inferred label
        if text:
            primary = f"'{text[:60]}'"
        elif cd:
            primary = f"cd='{cd[:60]}'"
        elif hint:
            primary = f"hint='{hint[:60]}'"
        elif label_map.get(i):
            primary = f"field:'{label_map[i][:40]}'"
        else:
            primary = "''"

        # Active flags only (DISABLED flagged when enabled=False)
        flags = []
        if clickable:   flags.append("CLICK")
        if not enabled: flags.append("DISABLED")
        if focused:     flags.append("FOCUSED")
        if editable:    flags.append("EDIT")
        if scrollable:  flags.append("SCROLL")
        if checked:     flags.append("CHECKED")
        if selected:    flags.append("SELECTED")
        if password:    flags.append("PWD")

        parts = [f"[{i + 1}] {cls}", primary]
        if rid:        parts.append(f"id={rid}")
        if bounds_str: parts.append(f"bounds={bounds_str}")
        if flags:      parts.append(" ".join(flags))
        # Append secondary labels when text was shown as primary
        if text and cd:   parts.append(f"cd='{cd[:40]}'")
        if text and hint: parts.append(f"hint='{hint[:40]}'")
        if pkg:        parts.append(f"pkg={pkg}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)
