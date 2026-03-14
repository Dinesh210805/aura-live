"""
Rule-based Intent Classifier for Simple Device Commands.

This module handles simple, deterministic commands without using LLM tokens.
Used as a fast-path before falling back to AI-based classification.
"""

import re
from typing import Any, Dict, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class RuleBasedClassifier:
    """
    Fast rule-based classifier for simple, deterministic device commands.

    Handles common tasks like:
    - System toggles (WiFi, Bluetooth, Flashlight, DND, etc.)
    - Volume controls
    - Navigation (back, home, scroll)
    - Screenshot

    Returns None if command requires AI classification.
    """

    # System control patterns
    FLASHLIGHT_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(flash|flashlight|torch)",
        r"\b(flash|flashlight|torch)\s+(on|off)",
        r"\b(enable|disable)\s+(flash|flashlight|torch)",
    ]

    WIFI_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?wi-?fi",
        r"\bwi-?fi\s+(on|off)",
        r"\b(enable|disable)\s+wi-?fi",
    ]

    BLUETOOTH_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?blue-?tooth",
        r"\bblue-?tooth\s+(on|off)",
        r"\b(enable|disable)\s+blue-?tooth",
    ]

    # DND / Do Not Disturb patterns
    DND_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(dnd|do\s+not\s+disturb)",
        r"\b(dnd|do\s+not\s+disturb)\s+(on|off)",
        r"\b(enable|disable)\s+(dnd|do\s+not\s+disturb)",
        r"\bsilence\s+(notifications?|my\s+phone)",
    ]

    # Airplane Mode patterns
    AIRPLANE_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(airplane|flight)\s*mode",
        r"\b(airplane|flight)\s*mode\s+(on|off)",
        r"\b(enable|disable)\s+(airplane|flight)\s*mode",
    ]

    # Location patterns
    LOCATION_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(location|gps)",
        r"\b(location|gps)\s+(on|off)",
        r"\b(enable|disable)\s+(location|gps)",
    ]

    # Auto-rotate patterns
    ROTATION_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(auto[\s-]?rotat(e|ion)|screen\s+rotation)",
        r"\b(auto[\s-]?rotat(e|ion)|screen\s+rotation)\s+(on|off)",
        r"\b(enable|disable)\s+(auto[\s-]?rotat(e|ion)|screen\s+rotation)",
        r"\block\s+(screen\s+)?rotation",
    ]

    # Mobile Data patterns
    MOBILE_DATA_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(mobile\s+data|cellular|data)",
        r"\b(mobile\s+data|cellular)\s+(on|off)",
        r"\b(enable|disable)\s+(mobile\s+data|cellular|data)",
    ]

    # Hotspot patterns
    HOTSPOT_PATTERNS = [
        r"\b(turn|switch|toggle|enable|disable)\s+(on|off)?\s*(the\s+)?(hot\s*spot|tethering)",
        r"\b(hot\s*spot|tethering)\s+(on|off)",
        r"\b(enable|disable)\s+(hot\s*spot|tethering)",
    ]

    # Brightness patterns
    BRIGHTNESS_UP_PATTERNS = [
        r"\bbrightness\s+up",
        r"\bincrease\s+(the\s+)?brightness",
        r"\braise\s+(the\s+)?brightness",
        r"\bbrighter",
        r"\bmake\s+(the\s+)?screen\s+brighter",
    ]

    BRIGHTNESS_DOWN_PATTERNS = [
        r"\bbrightness\s+down",
        r"\bdecrease\s+(the\s+)?brightness",
        r"\blower\s+(the\s+)?brightness",
        r"\bdimmer",
        r"\bdim\s+(the\s+)?screen",
        r"\bmake\s+(the\s+)?screen\s+dimmer",
    ]

    # Volume patterns
    VOLUME_UP_PATTERNS = [
        r"\bvolume\s+up",
        r"\bincrease\s+(the\s+)?volume",
        r"\braise\s+(the\s+)?volume",
        r"\blouder",
    ]

    VOLUME_DOWN_PATTERNS = [
        r"\bvolume\s+down",
        r"\bdecrease\s+(the\s+)?volume",
        r"\blower\s+(the\s+)?volume",
        r"\bquieter",
    ]

    MUTE_PATTERNS = [
        r"\bmute",
        r"\bsilent",
        r"\bturn\s+off\s+(the\s+)?sound",
    ]

    # Navigation patterns
    BACK_PATTERNS = [
        r"\bgo\s+back",
        r"\bpress\s+back",
        r"\bback\s+button",
        r"^\bback\b$",
    ]

    HOME_PATTERNS = [
        r"\bgo\s+(to\s+)?home",
        r"\bpress\s+home",
        r"\bhome\s+button",
        r"\bhome\s+screen",
        r"^\bhome\b$",  # Match standalone "home"
    ]

    SCROLL_UP_PATTERNS = [
        r"\bscroll\s+up",
        r"\bswipe\s+up",
    ]

    SCROLL_DOWN_PATTERNS = [
        r"\bscroll\s+down",
        r"\bswipe\s+down",
    ]

    # Screenshot pattern
    SCREENSHOT_PATTERNS = [
        r"\btake\s+(a\s+)?screenshot",
        r"\bcapture\s+(the\s+)?screen",
        r"\bscreenshot",
    ]

    # Multi-action detection patterns
    MULTI_ACTION_INDICATORS = re.compile(
        r"\b(and (then )?|then |, and |,(?=\s*\w))",
        re.IGNORECASE
    )

    def __init__(self):
        """Initialize the rule-based classifier."""
        # Compile all patterns for performance
        self.flashlight_regex = [
            re.compile(p, re.IGNORECASE) for p in self.FLASHLIGHT_PATTERNS
        ]
        self.wifi_regex = [re.compile(p, re.IGNORECASE) for p in self.WIFI_PATTERNS]
        self.bluetooth_regex = [
            re.compile(p, re.IGNORECASE) for p in self.BLUETOOTH_PATTERNS
        ]
        self.dnd_regex = [re.compile(p, re.IGNORECASE) for p in self.DND_PATTERNS]
        self.airplane_regex = [re.compile(p, re.IGNORECASE) for p in self.AIRPLANE_PATTERNS]
        self.location_regex = [re.compile(p, re.IGNORECASE) for p in self.LOCATION_PATTERNS]
        self.rotation_regex = [re.compile(p, re.IGNORECASE) for p in self.ROTATION_PATTERNS]
        self.mobile_data_regex = [re.compile(p, re.IGNORECASE) for p in self.MOBILE_DATA_PATTERNS]
        self.hotspot_regex = [re.compile(p, re.IGNORECASE) for p in self.HOTSPOT_PATTERNS]
        self.brightness_up_regex = [re.compile(p, re.IGNORECASE) for p in self.BRIGHTNESS_UP_PATTERNS]
        self.brightness_down_regex = [re.compile(p, re.IGNORECASE) for p in self.BRIGHTNESS_DOWN_PATTERNS]
        self.volume_up_regex = [
            re.compile(p, re.IGNORECASE) for p in self.VOLUME_UP_PATTERNS
        ]
        self.volume_down_regex = [
            re.compile(p, re.IGNORECASE) for p in self.VOLUME_DOWN_PATTERNS
        ]
        self.mute_regex = [re.compile(p, re.IGNORECASE) for p in self.MUTE_PATTERNS]
        self.back_regex = [re.compile(p, re.IGNORECASE) for p in self.BACK_PATTERNS]
        self.home_regex = [re.compile(p, re.IGNORECASE) for p in self.HOME_PATTERNS]
        self.scroll_up_regex = [
            re.compile(p, re.IGNORECASE) for p in self.SCROLL_UP_PATTERNS
        ]
        self.scroll_down_regex = [
            re.compile(p, re.IGNORECASE) for p in self.SCROLL_DOWN_PATTERNS
        ]
        self.screenshot_regex = [
            re.compile(p, re.IGNORECASE) for p in self.SCREENSHOT_PATTERNS
        ]

        logger.info("✅ Rule-based classifier initialized")

    def classify(self, transcript: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to classify using rule-based patterns.

        Args:
            transcript: User's voice command

        Returns:
            Intent dict if matched, None if requires AI classification
        """
        text = transcript.strip().lower()

        # Check for multi-action indicators ("and", "then", commas)
        # If detected, skip rule-based and let LLM handle the full sequence
        if self.MULTI_ACTION_INDICATORS.search(text):
            logger.info(f"⚠️ Multi-action command detected, deferring to LLM: {transcript[:50]}...")
            return None

        # Try each rule category (order matters - more specific first)
        result = (
            self._check_dnd(text, transcript)
            or self._check_airplane(text, transcript)
            or self._check_location(text, transcript)
            or self._check_rotation(text, transcript)
            or self._check_mobile_data(text, transcript)
            or self._check_hotspot(text, transcript)
            or self._check_brightness(text, transcript)
            or self._check_flashlight(text, transcript)
            or self._check_wifi(text, transcript)
            or self._check_bluetooth(text, transcript)
            or self._check_volume(text, transcript)
            or self._check_navigation(text, transcript)
            or self._check_screenshot(text, transcript)
        )

        if result:
            action, state = result
            logger.info(f"✅ Rule-based match: {action} (state: {state})")
            return self._build_intent(action, state, transcript)

        return None

    def _check_dnd(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Do Not Disturb commands."""
        for pattern in self.dnd_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "dnd_on"
                    if state == "on"
                    else "dnd_off" if state == "off" else "toggle_dnd"
                )
                return (action, state)
        return None

    def _check_airplane(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Airplane Mode commands."""
        for pattern in self.airplane_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "airplane_mode_on"
                    if state == "on"
                    else "airplane_mode_off" if state == "off" else "airplane_mode_on"
                )
                return (action, state)
        return None

    def _check_location(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Location/GPS commands."""
        for pattern in self.location_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "location_on"
                    if state == "on"
                    else "location_off" if state == "off" else "toggle_location"
                )
                return (action, state)
        return None

    def _check_rotation(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Auto-rotate commands."""
        for pattern in self.rotation_regex:
            match = pattern.search(text)
            if match:
                # "lock rotation" means turn off auto-rotate
                if "lock" in text:
                    return ("rotation_off", "off")
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "rotation_on"
                    if state == "on"
                    else "rotation_off" if state == "off" else "toggle_rotation"
                )
                return (action, state)
        return None

    def _check_mobile_data(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Mobile Data commands."""
        for pattern in self.mobile_data_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "mobile_data_on"
                    if state == "on"
                    else "mobile_data_off" if state == "off" else "toggle_mobile_data"
                )
                return (action, state)
        return None

    def _check_hotspot(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Hotspot commands."""
        for pattern in self.hotspot_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "hotspot_on"
                    if state == "on"
                    else "hotspot_off" if state == "off" else "toggle_hotspot"
                )
                return (action, state)
        return None

    def _check_brightness(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for brightness commands."""
        for pattern in self.brightness_up_regex:
            if pattern.search(text):
                return ("brightness_up", None)

        for pattern in self.brightness_down_regex:
            if pattern.search(text):
                return ("brightness_down", None)

        return None

    def _check_flashlight(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for flashlight commands."""
        for pattern in self.flashlight_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                return ("control_flashlight", state)
        return None

    def _check_wifi(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for WiFi commands."""
        for pattern in self.wifi_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "wifi_on"
                    if state == "on"
                    else "wifi_off" if state == "off" else "toggle_wifi"
                )
                return (action, state)
        return None

    def _check_bluetooth(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for Bluetooth commands."""
        for pattern in self.bluetooth_regex:
            match = pattern.search(text)
            if match:
                state = self._extract_state(text, ["on", "off"])
                action = (
                    "bluetooth_on"
                    if state == "on"
                    else "bluetooth_off" if state == "off" else "toggle_bluetooth"
                )
                return (action, state)
        return None

    def _check_volume(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for volume commands."""
        for pattern in self.volume_up_regex:
            if pattern.search(text):
                return ("volume_up", None)

        for pattern in self.volume_down_regex:
            if pattern.search(text):
                return ("volume_down", None)

        for pattern in self.mute_regex:
            if pattern.search(text):
                return ("mute", None)

        return None

    def _check_navigation(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for navigation commands."""
        for pattern in self.back_regex:
            if pattern.search(text):
                return ("back", None)

        for pattern in self.home_regex:
            if pattern.search(text):
                return ("home", None)

        for pattern in self.scroll_up_regex:
            if pattern.search(text):
                return ("scroll", "up")

        for pattern in self.scroll_down_regex:
            if pattern.search(text):
                return ("scroll", "down")

        return None

    def _check_screenshot(
        self, text: str, original: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check for screenshot commands."""
        for pattern in self.screenshot_regex:
            if pattern.search(text):
                return ("take_screenshot", None)
        return None

    def _extract_state(self, text: str, valid_states: list) -> Optional[str]:
        """Extract state (on/off) from text, including enable/disable synonyms."""
        # Check for explicit on/off first
        for state in valid_states:
            if state in text:
                return state
        # Check for enable/disable as synonyms
        if "enable" in text:
            return "on"
        if "disable" in text:
            return "off"
        return None

    def _build_intent(
        self, action: str, state: Optional[str], transcript: str
    ) -> Dict[str, Any]:
        """Build intent object from rule match."""
        parameters = {}
        if state:
            parameters["state"] = state

        # Determine direction for scroll
        if action == "scroll" and state:
            parameters["direction"] = state

        # Add classifier metadata to parameters
        parameters["classifier"] = "rule_based"
        parameters["original_transcript"] = transcript

        return {
            "action": action,
            "recipient": None,
            "content": None,
            "parameters": parameters,
            "confidence": 0.95,  # High confidence for rule-based matches
        }


# Singleton instance
_rule_classifier = None


def get_rule_classifier() -> RuleBasedClassifier:
    """Get or create singleton rule-based classifier."""
    global _rule_classifier
    if _rule_classifier is None:
        _rule_classifier = RuleBasedClassifier()
    return _rule_classifier
