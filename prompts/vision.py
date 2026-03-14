"""
Vision & Element Location Prompts - v3.0.0

Prompts for VLM-based UI understanding and element location.

Changes from v2:
- Extracted shared VISUAL_TRUST_RULES constant (was duplicated 5x)
- Added enhanced grounding rules (avatar detection, coordinate validation)
  moved from reactive_step.py rules 21 and 38
"""

from typing import Optional


# =============================================================================
# SHARED VISUAL TRUST RULES (injected into all vision prompts)
# =============================================================================
VISUAL_TRUST_RULES = """━━━ VISUAL TRUST RULES ━━━
Screenshot geometry is ground truth. UI element labels and metadata have bugs and mismatches.
- GHOST CONTAINER: a box that spans most of the screen height or width is NOT a real input
  or button. Ignore it. Look for a smaller, compact box INSIDE it.
- Real input fields are compact rectangles. Buttons have visible text. Containers are large.
- When a label contradicts the visual shape: trust the shape, ignore the label.
- DECORATIVE ELEMENTS: Profile photos, avatars, album art, thumbnails appear in the UI tree
  with coordinates but are NOT interactive targets. If the tree label says "profile photo",
  "avatar", "contact image", or "thumbnail" — skip it. Find the actual interactive zone
  (message input, chat row, button) and target its center.
- UI TREE COORDINATES: element bounds (left, top, right, bottom) are useful for tap positions
  ONLY. Labels, content-desc, and text values are often stale or wrong — especially for
  avatars labeled with contact names, image views with copied descriptions, and full-row
  containers. Always verify: does the coordinate land on what you VISUALLY see as correct?"""


# =============================================================================
# ELEMENT LOCATION PROMPT
# =============================================================================
ELEMENT_LOCATION_PROMPT = """Find the specified element on this Android screen.

TARGET: "{target}"
{context_hint}
SCREEN: {width}x{height}px

━━━ ANALYSIS APPROACH ━━━
1. Identify screen type (home, settings, chat, player, etc.)
2. Look for target using:
   - Text labels (exact or semantic match)
   - Icons (gear=settings, arrow=back, >>=skip)
   - Common positions (nav at bottom, actions at top-right)
3. If multiple candidates, choose most likely by context

━━━ COMMON ICONS ━━━
- Skip/Forward: >>, >, right arrow, "Skip"
- Back: <, ←, left arrow
- Menu: ☰ hamburger, ⋮ three dots
- Profile: 👤 person silhouette
- Search: 🔍 magnifying glass
- Settings: ⚙️ gear/cog
- Send: Paper plane, right arrow (blue/green)
- Like: ❤️ heart, 👍 thumbs up
- Share: ↗️ up-right arrow

{visual_trust_rules}

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "found": true,
  "x_percent": 85.5,
  "y_percent": 12.3,
  "confidence": 0.92,
  "element_type": "button|icon|text|list_item|nav_item|input_field",
  "reasoning": "Why this is the target"
}}

Or if not found:
{{
  "found": false,
  "reason": "What was looked for and why not found",
  "suggestions": ["alternative approach"]
}}"""


# =============================================================================
# ACTION-BASED LOCATION PROMPT
# =============================================================================
ACTION_LOCATION_PROMPT = """Find the element that accomplishes this action.

ACTION: "{action}"
SCREEN: {width}x{height}px

━━━ REASONING ━━━
1. What is user trying to do?
2. What element would accomplish this?
3. Where is that element likely to be?

━━━ ACTION → ELEMENT MAPPING ━━━
- "skip ad" → Skip button, X close, "Skip Ad", >> icon
- "go back" → Back arrow, X close, "Cancel"
- "send message" → Send button, paper plane, arrow (blue/green)
- "open settings" → Gear icon, "Settings" menu
- "like this" → Heart icon, Like button, 👍
- "search" → Magnifying glass, search bar

{visual_trust_rules}

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "found": true,
  "x_percent": 50.0,
  "y_percent": 25.0,
  "confidence": 0.88,
  "element_type": "button",
  "what_found": "Skip button with >> icon",
  "reasoning": "Skip button in top-right, typical for video ads"
}}"""


# =============================================================================
# ELEMENT SELECTION PROMPT (Set-of-Marks)
# =============================================================================
ELEMENT_SELECTION_PROMPT = """Analyzing mobile screenshot with labeled UI regions.
Each region marked with a letter (A, B, C...) in red box.

Available regions: {available_ids}

User wants: "{intent}"

{visual_trust_rules}

Which region matches? Respond with ONLY a single letter (A, B, C...) or NONE.
No explanation."""


# =============================================================================
# SCREEN ANALYSIS PROMPT
# =============================================================================
SCREEN_ANALYSIS_PROMPT = """Analyze this Android screen and provide structured summary.

{visual_trust_rules}

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "app_name": "Instagram|WhatsApp|YouTube|Settings|etc",
  "screen_type": "home|chat|video|settings|search|profile|login|etc",
  "key_elements": [
    {{"type": "button", "description": "Back arrow", "location": "top-left"}},
    {{"type": "input", "description": "Search bar", "location": "top-center"}}
  ],
  "available_actions": ["go back", "search", "scroll", "tap item"],
  "has_modal": false,
  "has_keyboard": false,
  "blocking_overlay": null
}}

Be concise but accurate."""


# =============================================================================
# ORDINAL ITEM LOCATION PROMPT
# =============================================================================
ORDINAL_LOCATION_PROMPT = """Find the {ordinal} {item_type} on this screen.

SCREEN: {width}x{height}px

━━━ INSTRUCTIONS ━━━
1. Find the list/collection of {item_type}s
2. Count from top to bottom (or left to right)
3. Locate item number {index}

{visual_trust_rules}

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "found": true,
  "x_percent": 50.0,
  "y_percent": 35.0,
  "confidence": 0.85,
  "item_description": "Message from John: 'Hey...'",
  "total_visible": 5
}}

Or: {{"found": false, "reason": "Only 2 visible", "total_visible": 2}}"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_vision_prompt(
    prompt_type: str,
    **kwargs,
) -> str:
    """
    Get formatted vision prompt.
    
    Args:
        prompt_type: "element", "action", "selection", "analysis", "ordinal"
        **kwargs: Format arguments for the prompt
    """
    prompts = {
        "element": ELEMENT_LOCATION_PROMPT,
        "action": ACTION_LOCATION_PROMPT,
        "selection": ELEMENT_SELECTION_PROMPT,
        "analysis": SCREEN_ANALYSIS_PROMPT,
        "ordinal": ORDINAL_LOCATION_PROMPT,
    }
    
    template = prompts.get(prompt_type)
    if not template:
        raise ValueError(f"Unknown prompt type: {prompt_type}")
    
    # Add context hint for element location
    if prompt_type == "element" and "action_context" in kwargs:
        kwargs["context_hint"] = f"ACTION CONTEXT: User wants to {kwargs['action_context']}"
    else:
        kwargs.setdefault("context_hint", "")
    
    kwargs.setdefault("visual_trust_rules", VISUAL_TRUST_RULES)
    return template.format(**kwargs)


def get_element_prompt(
    target: str,
    width: int,
    height: int,
    action_context: Optional[str] = None,
) -> str:
    """Convenience function for element location prompt."""
    context_hint = ""
    if action_context:
        context_hint = f"ACTION CONTEXT: User wants to {action_context}"
    
    return ELEMENT_LOCATION_PROMPT.format(
        target=target,
        width=width,
        height=height,
        context_hint=context_hint,
        visual_trust_rules=VISUAL_TRUST_RULES,
    )


def get_action_prompt(action: str, width: int, height: int) -> str:
    """Convenience function for action-based location prompt."""
    return ACTION_LOCATION_PROMPT.format(action=action, width=width, height=height, visual_trust_rules=VISUAL_TRUST_RULES)


def get_ordinal_prompt(
    ordinal: str,
    item_type: str,
    index: int,
    width: int,
    height: int,
) -> str:
    """Convenience function for ordinal item location prompt."""
    return ORDINAL_LOCATION_PROMPT.format(
        ordinal=ordinal,
        item_type=item_type,
        index=index,
        width=width,
        height=height,
        visual_trust_rules=VISUAL_TRUST_RULES,
    )
