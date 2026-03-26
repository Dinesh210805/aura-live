"""
Centralized action type definitions for AURA.

METADATA-DRIVEN ARCHITECTURE
============================
Single source of truth using ActionMeta dataclass.
All lists are auto-generated from metadata - no manual sync needed.

Add new action → Define once in ACTION_REGISTRY → All lists update automatically.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ActionMeta:
    """
    Metadata for an action type.
    
    Attributes:
        needs_ui: Requires UI tree/perception analysis
        needs_coords: Requires pixel coordinates from Navigator
        needs_perception: Requires perception bundle (screenshot/UI tree)
        is_dangerous: Requires user confirmation
        is_conversational: Just responds, no device action
        required_fields: Fields that must be present in intent
        opens_panel: Opens settings panel (requires user tap on Android 10+)
    """
    needs_ui: bool = False
    needs_coords: bool = False
    needs_perception: bool = False
    is_dangerous: bool = False
    is_conversational: bool = False
    required_fields: tuple = ()
    opens_panel: bool = False  # Android 10+ security: can't directly toggle, opens panel


# =============================================================================
# ACTION REGISTRY - Single Source of Truth
# =============================================================================
# Add new actions HERE - all lists auto-generate from this registry

ACTION_REGISTRY: Dict[str, ActionMeta] = {
    # =========================================================================
    # UI INTERACTION ACTIONS (need perception + coordinates)
    # =========================================================================
    "tap": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "click": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "swipe": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "long_press": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "type": ActionMeta(needs_ui=True, needs_coords=False, needs_perception=True),
    
    # =========================================================================
    # SCROLL (needs perception for screen dimensions, but not specific element)
    # =========================================================================
    "scroll": ActionMeta(needs_ui=False, needs_coords=False, needs_perception=True),
    
    # =========================================================================
    # APP LAUNCHING (no UI needed - uses package names/deep links)
    # =========================================================================
    "open_app": ActionMeta(required_fields=("recipient",)),
    "launch_app": ActionMeta(required_fields=("recipient",)),
    "start_app": ActionMeta(required_fields=("recipient",)),
    
    # =========================================================================
    # COMMUNICATION (no UI - uses deep links/intents)
    # =========================================================================
    "send_message": ActionMeta(required_fields=("recipient", "content")),
    "send_whatsapp": ActionMeta(required_fields=("recipient", "content")),
    "send_sms": ActionMeta(required_fields=("recipient", "content")),
    "send_email": ActionMeta(required_fields=("recipient",)),
    "call": ActionMeta(required_fields=("recipient",)),
    "make_call": ActionMeta(required_fields=("recipient",)),
    "dial": ActionMeta(required_fields=("recipient",)),
    "video_call": ActionMeta(required_fields=("recipient",)),
    
    # =========================================================================
    # SYSTEM TOGGLES (no UI - direct system APIs)
    # Note: WiFi/Bluetooth on Android 10+ open settings panel (opens_panel=True)
    # =========================================================================
    "wifi_on": ActionMeta(opens_panel=True),
    "wifi_off": ActionMeta(opens_panel=True),
    "toggle_wifi": ActionMeta(opens_panel=True),
    "bluetooth_on": ActionMeta(opens_panel=True),
    "bluetooth_off": ActionMeta(opens_panel=True),
    "toggle_bluetooth": ActionMeta(opens_panel=True),
    "volume_up": ActionMeta(),
    "volume_down": ActionMeta(),
    "mute": ActionMeta(),
    "unmute": ActionMeta(),
    "brightness_up": ActionMeta(),
    "brightness_down": ActionMeta(),
    "airplane_mode_on": ActionMeta(opens_panel=True),
    "airplane_mode_off": ActionMeta(opens_panel=True),
    "rotation_lock_on": ActionMeta(),
    "rotation_lock_off": ActionMeta(),
    # Do Not Disturb (direct API works with notification access permission)
    "dnd_on": ActionMeta(),
    "dnd_off": ActionMeta(),
    "do_not_disturb_on": ActionMeta(),
    "do_not_disturb_off": ActionMeta(),
    "toggle_dnd": ActionMeta(),
    "toggle_do_not_disturb": ActionMeta(),
    # Auto-Rotate (direct API with Settings.System)
    "rotation_on": ActionMeta(),
    "rotation_off": ActionMeta(),
    "auto_rotate_on": ActionMeta(),
    "auto_rotate_off": ActionMeta(),
    "toggle_rotation": ActionMeta(),
    "toggle_auto_rotate": ActionMeta(),
    # Battery Saver (opens settings panel)
    "battery_saver_on": ActionMeta(opens_panel=True),
    "battery_saver_off": ActionMeta(opens_panel=True),
    "power_saver_on": ActionMeta(opens_panel=True),
    "power_saver_off": ActionMeta(opens_panel=True),
    # Dark Mode (opens settings)
    "dark_mode_on": ActionMeta(opens_panel=True),
    "dark_mode_off": ActionMeta(opens_panel=True),
    "toggle_dark_mode": ActionMeta(opens_panel=True),
    # Location Services (opens settings)
    "location_on": ActionMeta(opens_panel=True),
    "location_off": ActionMeta(opens_panel=True),
    "toggle_location": ActionMeta(opens_panel=True),
    # Mobile Data (opens settings panel on Android 10+)
    "mobile_data_on": ActionMeta(opens_panel=True),
    "mobile_data_off": ActionMeta(opens_panel=True),
    "data_on": ActionMeta(opens_panel=True),
    "data_off": ActionMeta(opens_panel=True),
    "toggle_mobile_data": ActionMeta(opens_panel=True),
    "toggle_data": ActionMeta(opens_panel=True),
    # Hotspot (opens settings)
    "hotspot_on": ActionMeta(opens_panel=True),
    "hotspot_off": ActionMeta(opens_panel=True),
    "toggle_hotspot": ActionMeta(opens_panel=True),
    # NFC (opens settings)
    "nfc_on": ActionMeta(opens_panel=True),
    "nfc_off": ActionMeta(opens_panel=True),
    "toggle_nfc": ActionMeta(opens_panel=True),
    # Settings Panels (by definition they open panels)
    "open_settings": ActionMeta(opens_panel=True),
    "open_wifi_settings": ActionMeta(opens_panel=True),
    "open_bluetooth_settings": ActionMeta(opens_panel=True),
    
    # =========================================================================
    # FLASHLIGHT/TORCH (no UI)
    # =========================================================================
    "control_torch": ActionMeta(),
    "control_flashlight": ActionMeta(),
    "toggle_flashlight": ActionMeta(),
    "flashlight_on": ActionMeta(),
    "flashlight_off": ActionMeta(),
    
    # =========================================================================
    # DEVICE NAVIGATION (no UI - system buttons)
    # =========================================================================
    "back": ActionMeta(),
    "home": ActionMeta(),
    "recent_apps": ActionMeta(),
    "press": ActionMeta(),
    "go_back": ActionMeta(),
    "go_home": ActionMeta(),
    
    # =========================================================================
    # KEYBOARD CONTROL (no UI - system keyevents)
    # =========================================================================
    "dismiss_keyboard": ActionMeta(),
    "restore_keyboard": ActionMeta(),
    "press_enter": ActionMeta(),
    "press_search": ActionMeta(),
    
    # =========================================================================
    # WAIT (pause for screen transition)
    # =========================================================================
    "wait": ActionMeta(),

    # =========================================================================
    # SCREENSHOT (no UI)
    # =========================================================================
    "screenshot": ActionMeta(),
    "take_screenshot": ActionMeta(),
    
    # =========================================================================
    # SEARCH & NAVIGATION
    # =========================================================================
    "search": ActionMeta(required_fields=("content",)),
    "navigate_to": ActionMeta(required_fields=("recipient",)),
    
    # =========================================================================
    # SCREEN READING (needs perception, but no coords)
    # =========================================================================
    "read_screen": ActionMeta(needs_perception=True),
    "describe": ActionMeta(needs_perception=True),
    
    # =========================================================================
    # APP-SPECIFIC ACTIONS (need intelligent UI reasoning)
    # These require understanding app UI layout and multi-step navigation
    # =========================================================================
    "play_song": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "play_music": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "play_video": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "find_content": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "open_section": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "navigate_app": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    "app_action": ActionMeta(needs_ui=True, needs_coords=True, needs_perception=True),
    
    # =========================================================================
    # CONVERSATIONAL (no device action)
    # =========================================================================
    "greeting": ActionMeta(is_conversational=True),
    "greet": ActionMeta(is_conversational=True),
    "greetings": ActionMeta(is_conversational=True),
    "hello": ActionMeta(is_conversational=True),
    "hi": ActionMeta(is_conversational=True),
    "help": ActionMeta(is_conversational=True),
    "general_interaction": ActionMeta(is_conversational=True),
    "general_query": ActionMeta(is_conversational=True),
    "provide_help": ActionMeta(is_conversational=True),
    "none": ActionMeta(is_conversational=True),
    "status": ActionMeta(is_conversational=True),
    "thanks": ActionMeta(is_conversational=True),
    "goodbye": ActionMeta(is_conversational=True),
    "chitchat": ActionMeta(is_conversational=True),
    "conversation": ActionMeta(is_conversational=True),
    
    # =========================================================================
    # HUMAN-IN-THE-LOOP (ask user questions during execution)
    # =========================================================================
    "ask_user": ActionMeta(),
    
    # =========================================================================
    # DANGEROUS ACTIONS (require confirmation)
    # =========================================================================
    "delete": ActionMeta(is_dangerous=True),
    "remove": ActionMeta(is_dangerous=True),
    "uninstall": ActionMeta(is_dangerous=True),
    "factory_reset": ActionMeta(is_dangerous=True),
    "format": ActionMeta(is_dangerous=True),
    "clear_data": ActionMeta(is_dangerous=True),
    "send_money": ActionMeta(is_dangerous=True),
    "purchase": ActionMeta(is_dangerous=True),
    "transfer": ActionMeta(is_dangerous=True),
}


# =============================================================================
# AUTO-GENERATED LISTS (for backward compatibility)
# =============================================================================
# These are computed from ACTION_REGISTRY - DO NOT EDIT MANUALLY

def _get_actions_where(**criteria) -> List[str]:
    """Get actions matching all criteria."""
    result = []
    for action, meta in ACTION_REGISTRY.items():
        match = all(
            getattr(meta, attr) == value 
            for attr, value in criteria.items()
        )
        if match:
            result.append(action)
    return result


# NO_UI_ACTIONS: Actions that don't need perception at all
NO_UI_ACTIONS: List[str] = [
    action for action, meta in ACTION_REGISTRY.items()
    if not meta.needs_ui and not meta.needs_perception and not meta.is_conversational
]

# NO_SCREEN_ACTIONS: Actions that don't need screen data  
NO_SCREEN_ACTIONS: List[str] = [
    action for action, meta in ACTION_REGISTRY.items()
    if not meta.needs_perception and not meta.is_conversational
]

# SIMPLE_DEVICE_ACTIONS: Actions that execute without UI analysis
SIMPLE_DEVICE_ACTIONS: List[str] = [
    action for action, meta in ACTION_REGISTRY.items()
    if not meta.needs_ui and not meta.is_conversational and not meta.is_dangerous
]

# VISUAL_ACTIONS: Actions that require UI analysis
VISUAL_ACTIONS: List[str] = _get_actions_where(needs_ui=True)

# COORDINATE_REQUIRING_ACTIONS: Actions that need pixel coordinates
COORDINATE_REQUIRING_ACTIONS: List[str] = _get_actions_where(needs_coords=True)

# CONVERSATIONAL_ACTIONS: Actions that just respond
CONVERSATIONAL_ACTIONS: List[str] = _get_actions_where(is_conversational=True)

# DANGEROUS_ACTIONS: Actions requiring confirmation
DANGEROUS_ACTIONS: List[str] = _get_actions_where(is_dangerous=True)

# VALID_ACTIONS: All known action types
VALID_ACTIONS: List[str] = list(ACTION_REGISTRY.keys())

# REQUIRED_FIELDS: Fields required for specific actions
REQUIRED_FIELDS: Dict[str, List[str]] = {
    action: list(meta.required_fields)
    for action, meta in ACTION_REGISTRY.items()
    if meta.required_fields
}


# =============================================================================
# HELPER FUNCTIONS (new API)
# =============================================================================

def get_action_meta(action: str) -> Optional[ActionMeta]:
    """Get metadata for an action type."""
    return ACTION_REGISTRY.get(action)


def needs_perception(action: str) -> bool:
    """Check if action needs perception bundle."""
    meta = ACTION_REGISTRY.get(action)
    return meta.needs_perception if meta else False


def needs_coordinates(action: str) -> bool:
    """Check if action needs pixel coordinates."""
    meta = ACTION_REGISTRY.get(action)
    return meta.needs_coords if meta else False


def needs_ui_analysis(action: str) -> bool:
    """Check if action needs UI tree analysis."""
    meta = ACTION_REGISTRY.get(action)
    return meta.needs_ui if meta else False


def is_dangerous(action: str) -> bool:
    """Check if action requires user confirmation."""
    meta = ACTION_REGISTRY.get(action)
    return meta.is_dangerous if meta else False


def is_conversational(action: str) -> bool:
    """Check if action is conversational (no device action)."""
    meta = ACTION_REGISTRY.get(action)
    return meta.is_conversational if meta else False


def is_valid_action(action: str) -> bool:
    """Check if action is known/valid."""
    return action in ACTION_REGISTRY


def get_required_fields(action: str) -> List[str]:
    """Get required fields for an action."""
    meta = ACTION_REGISTRY.get(action)
    return list(meta.required_fields) if meta and meta.required_fields else []


def opens_settings_panel(action: str) -> bool:
    """
    Check if action opens a settings panel instead of directly toggling.
    
    Android 10+ security restrictions prevent direct WiFi/Bluetooth/etc toggling.
    These actions open the relevant settings panel for the user to tap.
    """
    meta = ACTION_REGISTRY.get(action)
    return meta.opens_panel if meta else False
