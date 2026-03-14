"""
Screen State Detection Prompts - v1.0.0

NEW: Dedicated prompts for detecting special screen states.
Helps agent understand context before taking action.
"""

from typing import Dict, Any, Optional


# =============================================================================
# SCREEN STATE DETECTION PROMPT
# =============================================================================
SCREEN_STATE_PROMPT = """Analyze this screen's current state.

━━━ POSSIBLE STATES ━━━

**NORMAL**: Regular app content, ready for interaction

**LOADING**: 
- Spinner/progress indicator
- Skeleton placeholders
- "Loading..." text
→ Action: wait

**ERROR**:
- "Something went wrong"
- "Error", "Failed"
- Retry/refresh buttons
→ Action: tap retry or go back

**PERMISSION**:
- "Allow access to..."
- Allow/Deny buttons
- Camera, microphone, location requests
→ Action: tap Allow or Deny based on goal

**CRASH**:
- "App stopped"
- "Not responding"
- Force close dialog
→ Action: tap OK, restart app

**KEYBOARD**:
- Virtual keyboard visible
- Input field focused
- "Paste", "Select all" visible
→ Action: ready to type

**DIALOG**:
- Modal popup
- Confirmation dialog
- Action sheet/bottom sheet
→ Action: respond to dialog or dismiss

**NOTIFICATION_SHADE**:
- Quick settings (WiFi, Bluetooth, etc.)
- Notification list
- System UI overlay
→ Action: press HOME or swipe to dismiss

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "state": "NORMAL|LOADING|ERROR|PERMISSION|CRASH|KEYBOARD|DIALOG|NOTIFICATION_SHADE",
  "confidence": 0.9,
  "details": "Brief description of what's shown",
  "action_needed": "wait|tap_allow|tap_deny|tap_retry|restart|dismiss|type|none",
  "blocking": true|false
}}"""


# =============================================================================
# QUICK STATE INDICATORS (Rule-based, no LLM)
# =============================================================================
STATE_INDICATORS = {
    "notification_shade": [
        "wi-fi", "wifi", "bluetooth", "mobile data", "airplane",
        "edit quick settings", "flashlight", "auto-rotate",
        "do not disturb", "battery saver", "hotspot"
    ],
    "permission": [
        "allow access", "permission", "allow", "deny",
        "enable", "grant access", "needs access"
    ],
    "dialog": [
        "cancel", "ok", "dismiss", "got it", "not now",
        "skip", "continue", "confirm"
    ],
    "error": [
        "something went wrong", "error", "failed", "retry",
        "try again", "couldn't load", "no connection"
    ],
    "loading": [
        "loading", "please wait", "fetching"
    ],
    "keyboard": [
        "paste", "select all", "auto-fill", "clipboard"
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def detect_screen_state_prompt() -> str:
    """Get the screen state detection prompt."""
    return SCREEN_STATE_PROMPT


def detect_state_from_text(texts: list[str], package_name: str = "") -> Optional[Dict[str, Any]]:
    """
    Quick rule-based state detection from UI text.
    
    Use before VLM call for common cases.
    
    Args:
        texts: List of visible text elements (lowercased)
        package_name: Current app package name
    
    Returns:
        State dict if detected, None otherwise
    """
    combined = " ".join(texts).lower()
    
    # Check for notification shade first (highest priority)
    is_systemui = package_name and "systemui" in package_name.lower()
    shade_matches = sum(1 for ind in STATE_INDICATORS["notification_shade"] if ind in combined)
    
    if is_systemui and shade_matches >= 2:
        return {
            "state": "NOTIFICATION_SHADE",
            "confidence": 0.95,
            "details": "Quick settings or notification shade detected",
            "action_needed": "dismiss",
            "blocking": True,
        }
    
    # Check for permission dialogs
    if sum(1 for ind in STATE_INDICATORS["permission"] if ind in combined) >= 2:
        return {
            "state": "PERMISSION",
            "confidence": 0.85,
            "details": "Permission dialog detected",
            "action_needed": "tap_allow",  # Default to allow
            "blocking": True,
        }
    
    # Check for keyboard
    keyboard_matches = sum(1 for ind in STATE_INDICATORS["keyboard"] if ind in combined)
    if keyboard_matches >= 2:
        return {
            "state": "KEYBOARD",
            "confidence": 0.9,
            "details": "Keyboard context menu visible",
            "action_needed": "type",
            "blocking": False,
        }
    
    # Check for error state
    if sum(1 for ind in STATE_INDICATORS["error"] if ind in combined) >= 2:
        return {
            "state": "ERROR",
            "confidence": 0.8,
            "details": "Error state detected",
            "action_needed": "tap_retry",
            "blocking": True,
        }
    
    # Check for generic dialog
    if sum(1 for ind in STATE_INDICATORS["dialog"] if ind in combined) >= 2:
        return {
            "state": "DIALOG",
            "confidence": 0.7,
            "details": "Dialog or popup detected",
            "action_needed": "dismiss",
            "blocking": True,
        }
    
    return None


def get_blocking_state_action(state: str) -> str:
    """Get recommended action for a blocking state."""
    actions = {
        "NOTIFICATION_SHADE": "Press HOME button to dismiss",
        "PERMISSION": "Tap Allow or Deny based on your goal",
        "DIALOG": "Respond to dialog or tap outside to dismiss",
        "ERROR": "Tap Retry or go back",
        "CRASH": "Tap OK and restart the app",
        "LOADING": "Wait for loading to complete",
    }
    return actions.get(state, "No action needed")
