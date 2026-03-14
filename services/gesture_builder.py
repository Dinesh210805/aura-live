"""
Gesture command builder service.

Converts high-level actions into JSON gesture commands for Android device.
"""

import time
from typing import Any, Dict

from utils.logger import get_logger

logger = get_logger(__name__)


def _generate_command_id(prefix: str = "cmd") -> str:
    """Generate unique command ID with timestamp."""
    timestamp = int(time.time() * 1000)
    return f"{prefix}_{timestamp}"


def _validate_coordinates(x: float, y: float, normalized: bool) -> None:
    """Validate coordinate values are in valid range."""
    if normalized:
        if not (0.0 <= x <= 1.0):
            raise ValueError(f"Normalized x coordinate must be 0.0-1.0, got {x}")
        if not (0.0 <= y <= 1.0):
            raise ValueError(f"Normalized y coordinate must be 0.0-1.0, got {y}")
    else:
        if x < 0 or y < 0:
            raise ValueError(f"Absolute coordinates must be >= 0, got ({x}, {y})")


def _normalize_direction(direction: str) -> str:
    """Normalize direction string to lowercase."""
    normalized = direction.lower().strip()
    valid_directions = ["up", "down", "left", "right"]
    if normalized not in valid_directions:
        raise ValueError(
            f"Direction must be one of {valid_directions}, got '{direction}'"
        )
    return normalized


def build_tap(
    x: float,
    y: float,
    normalized: bool = True,
    duration_ms: int = 100,
    retry_count: int = 2,
) -> Dict[str, Any]:
    """
    Build tap gesture command.

    Args:
        x: X coordinate (0.0-1.0 if normalized, pixels if not)
        y: Y coordinate (0.0-1.0 if normalized, pixels if not)
        normalized: Whether coordinates are normalized (default: True)
        duration_ms: Tap duration in milliseconds
        retry_count: Number of retry attempts

    Returns:
        Gesture command dict ready for command queue

    Example:
        >>> build_tap(0.5, 0.5)
        {
            "command_id": "cmd_tap_1702584245123",
            "gesture_type": "tap",
            "target": {
                "type": "coordinates",
                "x": 0.5,
                "y": 0.5,
                "normalized": True
            },
            "options": {
                "duration_ms": 100,
                "retry_count": 2
            }
        }
    """
    _validate_coordinates(x, y, normalized)

    command = {
        "command_id": _generate_command_id("cmd_tap"),
        "gesture_type": "tap",
        "target": {"type": "coordinates", "x": x, "y": y, "normalized": normalized},
        "options": {"duration_ms": duration_ms, "retry_count": retry_count},
    }

    logger.debug(
        f"Built tap gesture: ({x}, {y}), normalized={normalized}, duration={duration_ms}ms"
    )
    return command


def build_tap_element(
    text: str = None,
    resource_id: str = None,
    content_desc: str = None,
    index: int = 0,
    duration_ms: int = 100,
) -> Dict[str, Any]:
    """
    Build tap on UI element command.

    Args:
        text: Text content to search for (case-insensitive contains match)
        resource_id: Resource ID to search for (case-insensitive contains match)
        content_desc: Content description to search for
        index: Which match to use if multiple found (default: 0 = first)
        duration_ms: Tap duration

    Returns:
        Gesture command dict

    Example:
        >>> build_tap_element(text="Settings")
        {
            "command_id": "cmd_tap_elem_1702584245123",
            "gesture_type": "tap",
            "target": {
                "type": "ui_element",
                "text": "Settings",
                "index": 0
            }
        }
    """
    if not any([text, resource_id, content_desc]):
        raise ValueError(
            "At least one of text, resource_id, or content_desc must be provided"
        )

    target = {"type": "ui_element", "index": index}

    if text:
        target["text"] = text
    if resource_id:
        target["resource_id"] = resource_id
    if content_desc:
        target["content_desc"] = content_desc

    command = {
        "command_id": _generate_command_id("cmd_tap_elem"),
        "gesture_type": "tap",
        "target": target,
        "options": {"duration_ms": duration_ms},
    }

    logger.debug(
        f"Built tap element gesture: text={text}, resource_id={resource_id}, index={index}"
    )
    return command


def build_swipe(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    normalized: bool = True,
    duration_ms: int = 400,
) -> Dict[str, Any]:
    """
    Build swipe gesture command.

    Args:
        start_x: Starting X coordinate
        start_y: Starting Y coordinate
        end_x: Ending X coordinate
        end_y: Ending Y coordinate
        normalized: Whether coordinates are normalized
        duration_ms: Swipe duration (affects speed)

    Returns:
        Gesture command dict

    Example:
        >>> build_swipe(0.8, 0.5, 0.2, 0.5)  # Swipe left
        {
            "command_id": "cmd_swipe_1702584245123",
            "gesture_type": "swipe",
            "target": {
                "type": "coordinates",
                "x": 0.8,
                "y": 0.5,
                "normalized": True
            },
            "end_target": {
                "x": 0.2,
                "y": 0.5,
                "normalized": True
            },
            "options": {
                "duration_ms": 400
            }
        }
    """
    _validate_coordinates(start_x, start_y, normalized)
    _validate_coordinates(end_x, end_y, normalized)

    command = {
        "command_id": _generate_command_id("cmd_swipe"),
        "gesture_type": "swipe",
        "target": {
            "type": "coordinates",
            "x": start_x,
            "y": start_y,
            "normalized": normalized,
        },
        "end_target": {"x": end_x, "y": end_y, "normalized": normalized},
        "options": {"duration_ms": duration_ms},
    }

    logger.debug(
        f"Built swipe gesture: ({start_x}, {start_y}) → ({end_x}, {end_y}), duration={duration_ms}ms"
    )
    return command


def build_scroll(
    direction: str, distance_ratio: float = 0.5, duration_ms: int = 500
) -> Dict[str, Any]:
    """
    Build scroll gesture command.

    Args:
        direction: "up", "down", "left", or "right"
        distance_ratio: How far to scroll (0.0-1.0, default: 0.5 = half screen)
        duration_ms: Scroll duration (affects speed)

    Returns:
        Gesture command dict

    Example:
        >>> build_scroll("down")
        {
            "command_id": "cmd_scroll_1702584245123",
            "gesture_type": "scroll",
            "target": {
                "type": "direction",
                "direction": "down",
                "distance_ratio": 0.5
            },
            "options": {
                "duration_ms": 500
            }
        }
    """
    direction = _normalize_direction(direction)

    if not (0.0 <= distance_ratio <= 1.0):
        raise ValueError(f"distance_ratio must be 0.0-1.0, got {distance_ratio}")

    command = {
        "command_id": _generate_command_id("cmd_scroll"),
        "gesture_type": "scroll",
        "target": {
            "type": "direction",
            "direction": direction,
            "distance_ratio": distance_ratio,
        },
        "options": {"duration_ms": duration_ms},
    }

    logger.debug(
        f"Built scroll gesture: direction={direction}, distance={distance_ratio}, duration={duration_ms}ms"
    )
    return command


def build_long_press(
    x: float,
    y: float,
    normalized: bool = True,
    hold_ms: int = 600,
    duration_ms: int = 100,
) -> Dict[str, Any]:
    """
    Build long press gesture command.

    Args:
        x: X coordinate
        y: Y coordinate
        normalized: Whether coordinates are normalized
        hold_ms: How long to hold (default: 600ms)
        duration_ms: Initial touch duration

    Returns:
        Gesture command dict

    Example:
        >>> build_long_press(0.5, 0.5, hold_ms=800)
        {
            "command_id": "cmd_lp_1702584245123",
            "gesture_type": "long_press",
            "target": {
                "type": "coordinates",
                "x": 0.5,
                "y": 0.5,
                "normalized": True
            },
            "options": {
                "duration_ms": 100,
                "hold_ms": 800
            }
        }
    """
    _validate_coordinates(x, y, normalized)

    command = {
        "command_id": _generate_command_id("cmd_lp"),
        "gesture_type": "long_press",
        "target": {"type": "coordinates", "x": x, "y": y, "normalized": normalized},
        "options": {"duration_ms": duration_ms, "hold_ms": hold_ms},
    }

    logger.debug(
        f"Built long press gesture: ({x}, {y}), hold={hold_ms}ms, duration={duration_ms}ms"
    )
    return command


# Convenience functions for common gestures
def build_swipe_left(
    y: float = 0.5, normalized: bool = True, duration_ms: int = 400
) -> Dict[str, Any]:
    """Build swipe left gesture at specified y position."""
    return build_swipe(0.8, y, 0.2, y, normalized, duration_ms)


def build_swipe_right(
    y: float = 0.5, normalized: bool = True, duration_ms: int = 400
) -> Dict[str, Any]:
    """Build swipe right gesture at specified y position."""
    return build_swipe(0.2, y, 0.8, y, normalized, duration_ms)


def build_swipe_up(
    x: float = 0.5, normalized: bool = True, duration_ms: int = 400
) -> Dict[str, Any]:
    """Build swipe up gesture at specified x position."""
    return build_swipe(x, 0.8, x, 0.2, normalized, duration_ms)


def build_swipe_down(
    x: float = 0.5, normalized: bool = True, duration_ms: int = 400
) -> Dict[str, Any]:
    """Build swipe down gesture at specified x position."""
    return build_swipe(x, 0.2, x, 0.8, normalized, duration_ms)


def build_back_button() -> Dict[str, Any]:
    """
    Build BACK button press command using Android keyevent.
    
    This uses Android keyevent 4 (KEYCODE_BACK) which is the proper way
    to trigger back navigation. Do NOT use swipe gestures for back navigation.
    
    Returns:
        System action command dict
        
    Example:
        >>> build_back_button()
        {
            "command_id": "cmd_back_1702584245123",
            "gesture_type": "system_action",
            "action": "back",
            "method": "keyevent",
            "keycode": 4
        }
        
    Note:
        Android side must implement this as:
        - Runtime.getRuntime().exec("input keyevent 4")
        - OR getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK)
        - NOT as a swipe gesture
    """
    command = {
        "command_id": _generate_command_id("cmd_back"),
        "gesture_type": "system_action",
        "action": "back",
        "method": "keyevent",
        "keycode": 4,  # KEYCODE_BACK
    }
    
    logger.debug("Built BACK button press (keyevent 4)")
    return command


def build_home_button() -> Dict[str, Any]:
    """
    Build HOME button press command using Android keyevent.
    
    This uses Android keyevent 3 (KEYCODE_HOME) which is the proper way
    to return to the home screen.
    
    Returns:
        System action command dict
        
    Example:
        >>> build_home_button()
        {
            "command_id": "cmd_home_1702584245123",
            "gesture_type": "system_action",
            "action": "home",
            "method": "keyevent",
            "keycode": 3
        }
        
    Note:
        Android side must implement this as:
        - Runtime.getRuntime().exec("input keyevent 3")
        - OR performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
    """
    command = {
        "command_id": _generate_command_id("cmd_home"),
        "gesture_type": "system_action",
        "action": "home",
        "method": "keyevent",
        "keycode": 3,  # KEYCODE_HOME
    }
    
    logger.debug("Built HOME button press (keyevent 3)")
    return command


def build_recent_apps_button() -> Dict[str, Any]:
    """
    Build RECENT APPS button press command.
    
    This uses Android GLOBAL_ACTION_RECENTS to show recent apps.
    
    Returns:
        System action command dict
        
    Example:
        >>> build_recent_apps_button()
        {
            "command_id": "cmd_recent_1702584245123",
            "gesture_type": "system_action",
            "action": "recent_apps",
            "method": "global_action"
        }
    """
    command = {
        "command_id": _generate_command_id("cmd_recent"),
        "gesture_type": "system_action",
        "action": "recent_apps",
        "method": "global_action",
    }
    
    logger.debug("Built RECENT APPS button press")
    return command


def build_dismiss_keyboard() -> Dict[str, Any]:
    """
    Build dismiss keyboard command using tapping outside the keyboard area.
    
    Uses a tap at the top of the screen to defocus the input field and dismiss
    the keyboard, avoiding BACK which navigates away from the current screen.
    
    Returns:
        System action command dict
    """
    command = {
        "command_id": _generate_command_id("cmd_dismiss_kb"),
        "gesture_type": "system_action",
        "action": "dismiss_keyboard",
        "method": "keyevent",
        "keycode": 111,  # KEYCODE_ESCAPE
    }
    
    logger.debug("Built DISMISS KEYBOARD (keyevent ESCAPE 111)")
    return command


def build_restore_keyboard() -> Dict[str, Any]:
    """Build command to restore normal keyboard behaviour after automation."""
    command = {
        "command_id": _generate_command_id("cmd_restore_kb"),
        "gesture_type": "system_action",
        "action": "restore_keyboard",
    }
    logger.debug("Built RESTORE KEYBOARD")
    return command


def build_press_enter() -> Dict[str, Any]:
    """
    Build Enter key press command (submits search, sends message, etc.).
    
    Uses Android KEYCODE_ENTER (66) to trigger the keyboard's action button.
    
    Returns:
        System action command dict
    """
    command = {
        "command_id": _generate_command_id("cmd_enter"),
        "gesture_type": "system_action",
        "action": "press_enter",
        "method": "keyevent",
        "keycode": 66,  # KEYCODE_ENTER
    }
    
    logger.debug("Built PRESS ENTER (keyevent 66)")
    return command


def build_press_search() -> Dict[str, Any]:
    """
    Build Search key press command for search IME action.
    
    Uses Android KEYCODE_SEARCH (84) to trigger search on the keyboard.
    
    Returns:
        System action command dict
    """
    command = {
        "command_id": _generate_command_id("cmd_search"),
        "gesture_type": "system_action",
        "action": "press_search",
        "method": "keyevent",
        "keycode": 84,  # KEYCODE_SEARCH
    }
    
    logger.debug("Built PRESS SEARCH (keyevent 84)")
    return command
