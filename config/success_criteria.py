"""
Success criteria registry for action validation.

Maps action types to their expected success criteria for post-action validation.
"""

from dataclasses import replace

from aura_graph.agent_state import SuccessCriteria


# Default criteria for actions that change UI
UI_CHANGE_CRITERIA = SuccessCriteria(ui_changed=True)

# For actions that navigate away from current element
NAVIGATION_CRITERIA = SuccessCriteria(ui_changed=True, target_element_gone=True)

# For input actions (keyboard shows, text appears)
INPUT_CRITERIA = SuccessCriteria(ui_changed=True)

# For no-UI actions (volume, brightness, etc.)
NO_UI_CRITERIA = SuccessCriteria(ui_changed=False)


SUCCESS_CRITERIA_REGISTRY: dict[str, SuccessCriteria] = {
    # Tap actions - expect UI to change
    "tap": UI_CHANGE_CRITERIA,
    "double_tap": UI_CHANGE_CRITERIA,
    "long_press": UI_CHANGE_CRITERIA,
    
    # Navigation - element should disappear
    "click": NAVIGATION_CRITERIA,
    "open_app": SuccessCriteria(ui_changed=True, target_screen_reached=""),
    "go_back": UI_CHANGE_CRITERIA,
    "go_home": SuccessCriteria(ui_changed=True, target_screen_reached="launcher"),
    
    # Input actions
    "type": INPUT_CRITERIA,
    "type_text": INPUT_CRITERIA,
    "enter_text": INPUT_CRITERIA,
    "set_text": INPUT_CRITERIA,
    "input_text": INPUT_CRITERIA,
    
    # Scroll actions - UI changes but may be subtle
    "scroll": SuccessCriteria(ui_changed=True),
    "scroll_up": SuccessCriteria(ui_changed=True),
    "scroll_down": SuccessCriteria(ui_changed=True),
    "scroll_left": SuccessCriteria(ui_changed=True),
    "scroll_right": SuccessCriteria(ui_changed=True),
    "swipe": SuccessCriteria(ui_changed=True),
    
    # System actions - no UI tree change expected
    "volume_up": NO_UI_CRITERIA,
    "volume_down": NO_UI_CRITERIA,
    "mute": NO_UI_CRITERIA,
    "unmute": NO_UI_CRITERIA,
    "brightness_up": NO_UI_CRITERIA,
    "brightness_down": NO_UI_CRITERIA,
    "take_screenshot": NO_UI_CRITERIA,
    
    # Communication - may open app
    "call": SuccessCriteria(ui_changed=True),
    "send_sms": SuccessCriteria(ui_changed=True),
    "send_whatsapp": SuccessCriteria(ui_changed=True),
    
    # Status queries - no change expected
    "get_time": NO_UI_CRITERIA,
    "get_battery": NO_UI_CRITERIA,
    "get_weather": NO_UI_CRITERIA,
    "read_screen": NO_UI_CRITERIA,
    "read_notifications": NO_UI_CRITERIA,
    
    # Toggle actions - UI may show indicator
    "toggle_wifi": SuccessCriteria(ui_changed=False),
    "toggle_bluetooth": SuccessCriteria(ui_changed=False),
    "toggle_airplane_mode": SuccessCriteria(ui_changed=False),
    "toggle_flashlight": NO_UI_CRITERIA,
    
    # Wait action
    "wait": NO_UI_CRITERIA,
    "none": NO_UI_CRITERIA,

    # Keyboard actions — keyboard may not appear in the accessibility tree as
    # a separate node, so dismissing it does not always change the UI signature.
    # Treat as always-successful once the gesture is acknowledged.
    "dismiss_keyboard": NO_UI_CRITERIA,

    # Key press actions - submit search, etc.
    "press_enter": UI_CHANGE_CRITERIA,
    "press_search": UI_CHANGE_CRITERIA,
}


def get_success_criteria(action_type: str) -> SuccessCriteria:
    """
    Get success criteria for an action type.
    
    Returns a fresh copy so callers can safely mutate without
    affecting other subgoals that share the same action type.
    """
    return replace(SUCCESS_CRITERIA_REGISTRY.get(action_type, UI_CHANGE_CRITERIA))
