"""
SimulatedDevice — mock Android device state machine for integration tests.

No real ADB/WebSocket/LLM connections. Transitions through screen states based
on actions and returns realistic PerceptionBundles so the full agent logic
(Coordinator, PerceiverAgent, VerifierAgent) can be exercised in-process.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from perception.models import (
    PerceptionBundle,
    PerceptionModality,
    ScreenMeta,
    ScreenshotPayload,
    UITreePayload,
)

SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 1920

# Minimal 1×1 PNG so bundle.screenshot is not None for WebView screens
_MOCK_SCREENSHOT_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    "DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# ---------------------------------------------------------------------------
# Screen definitions
# ---------------------------------------------------------------------------
# Each screen has:
#   elements      – accessibility UI tree (flat list of element dicts)
#   webview       – True if classified as WebView by _classify_screen()
#   visual_description – VLM text returned when skip_description=False

_KEYBOARD_KEYS = [
    {
        "className": "android.widget.Button",
        "text": c,
        "contentDescription": c,
        "clickable": True,
        "focusable": True,
        "left": 10 + i * 95,
        "top": 1400,
        "right": 90 + i * 95,
        "bottom": 1500,
    }
    for i, c in enumerate("QWERTYUIOPA")  # 11 keys so keyboard_keys > 10
]

SCREENS: Dict[str, Dict[str, Any]] = {
    "launcher": {
        "elements": [
            {
                "className": "android.widget.FrameLayout",
                "packageName": "com.android.launcher3",
                "text": "",
                "contentDescription": "Home screen",
                "clickable": False,
                "focusable": False,
                "left": 0, "top": 0, "right": SCREEN_WIDTH, "bottom": SCREEN_HEIGHT,
            },
            {
                "className": "android.widget.TextView",
                "text": "Amazon",
                "contentDescription": "Amazon",
                "clickable": True,
                "focusable": True,
                "left": 100, "top": 400, "right": 250, "bottom": 500,
            },
        ],
        "webview": False,
        "visual_description": None,
    },
    "amazon_home": {
        "elements": [
            {
                "className": "android.view.View",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "",
                "contentDescription": "Amazon",
                "clickable": False,
                "focusable": False,
                "left": 0, "top": 0, "right": SCREEN_WIDTH, "bottom": SCREEN_HEIGHT,
            },
            {
                "className": "android.widget.EditText",
                "text": "Search Amazon",
                "contentDescription": "Search Amazon",
                "clickable": True,
                "focusable": True,
                "left": 50, "top": 150, "right": 1030, "bottom": 230,
            },
        ],
        "webview": False,
        "visual_description": None,
    },
    "amazon_search_empty": {
        "elements": [
            {
                "className": "android.widget.EditText",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "",
                "contentDescription": "Search Amazon",
                "clickable": True,
                "focusable": True,
                "left": 50, "top": 150, "right": 1030, "bottom": 230,
            },
            *_KEYBOARD_KEYS,
        ],
        "webview": False,
        "visual_description": None,
    },
    "amazon_search_typed": {
        "elements": [
            {
                "className": "android.widget.EditText",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "iPhone 17 Pro",
                "contentDescription": "Search Amazon",
                "clickable": True,
                "focusable": True,
                "left": 50, "top": 150, "right": 1030, "bottom": 230,
            },
            *_KEYBOARD_KEYS,
        ],
        "webview": False,
        "visual_description": None,
    },
    "amazon_results": {
        "elements": [
            {
                "className": "android.webkit.WebView",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "",
                "contentDescription": "Amazon search results",
                "clickable": False,
                "focusable": False,
                "left": 0, "top": 0, "right": SCREEN_WIDTH, "bottom": SCREEN_HEIGHT,
            },
        ],
        "webview": True,
        "visual_description": (
            "Amazon search results page showing iPhone 17 Pro listings. "
            "Multiple product cards visible with prices and ratings. "
            "First card: 'iPhone 17 Pro 256GB' at $999."
        ),
    },
    "product_detail": {
        "elements": [
            {
                "className": "android.webkit.WebView",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "",
                "contentDescription": "iPhone 17 Pro product detail",
                "clickable": False,
                "focusable": False,
                "left": 0, "top": 0, "right": SCREEN_WIDTH, "bottom": SCREEN_HEIGHT,
            },
        ],
        "webview": True,
        "visual_description": (
            "iPhone 17 Pro product detail page. Shows product images, "
            "price $999 and 'Add to Cart' button visible at bottom."
        ),
    },
    "cart_confirmed": {
        "elements": [
            {
                "className": "android.view.View",
                "packageName": "com.amazon.mShop.android.shopping",
                "text": "Added to Cart",
                "contentDescription": "Added to Cart",
                "clickable": False,
                "focusable": False,
                "left": 200, "top": 300, "right": 880, "bottom": 420,
            },
            {
                "className": "android.widget.Button",
                "text": "View Cart",
                "contentDescription": "View Cart",
                "clickable": True,
                "focusable": True,
                "left": 50, "top": 700, "right": 500, "bottom": 800,
            },
        ],
        "webview": False,
        "visual_description": None,
    },
}

# ---------------------------------------------------------------------------
# State transitions
# (from_state, action_type, target_hint_or_None, to_state)
# target_hint is checked as substring of target (case-insensitive).
# None means "any target" (including None).
# ---------------------------------------------------------------------------
TRANSITIONS: List[Tuple[str, str, Optional[str], str]] = [
    ("launcher",            "open_app",    "amazon", "amazon_home"),
    ("amazon_home",         "tap",         None,     "amazon_search_empty"),
    ("amazon_search_empty", "type",        None,     "amazon_search_typed"),
    ("amazon_search_typed", "press_enter", None,     "amazon_results"),
    ("amazon_results",      "tap",         None,     "product_detail"),
    ("product_detail",      "tap",         None,     "cart_confirmed"),
]


class SimulatedDevice:
    """
    Mock Android device that transitions through screen states on actions.

    Provides make_perception_call() and apply_action() as AsyncMock side
    effects so the full agent loop runs without real hardware or APIs.
    """

    def __init__(self, initial_state: str = "launcher"):
        self.current_state = initial_state
        # Log every perception request for test assertions
        self.perception_calls: List[Dict[str, Any]] = []
        self.action_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Perception                                                           #
    # ------------------------------------------------------------------ #

    def get_bundle(
        self,
        force_screenshot: bool = False,
        skip_description: bool = True,
    ) -> PerceptionBundle:
        """Build a PerceptionBundle reflecting the current screen state."""
        screen = SCREENS[self.current_state]
        ts = int(time.time() * 1000)

        ui_tree = UITreePayload(
            elements=screen["elements"],
            screen_width=SCREEN_WIDTH,
            screen_height=SCREEN_HEIGHT,
            timestamp=ts,
        )

        # Include screenshot for WebView screens (VisualLocator check needs it)
        screenshot = None
        if screen["webview"] or force_screenshot:
            screenshot = ScreenshotPayload(
                screenshot_base64=_MOCK_SCREENSHOT_B64,
                screen_width=SCREEN_WIDTH,
                screen_height=SCREEN_HEIGHT,
                timestamp=ts,
            )

        visual_description = (
            screen["visual_description"]
            if (not skip_description and screen["webview"])
            else None
        )

        return PerceptionBundle(
            modality=PerceptionModality.HYBRID,
            ui_tree=ui_tree,
            screenshot=screenshot,
            screen_meta=ScreenMeta(width=SCREEN_WIDTH, height=SCREEN_HEIGHT),
            visual_description=visual_description,
        )

    async def make_perception_call(
        self,
        intent: Optional[Dict[str, Any]] = None,
        action_type: str = "UI_ACTION",
        execution_history: Any = None,
        retry_context: Any = None,
        app_category: Any = None,
        force_screenshot: bool = False,
        skip_description: bool = True,
    ) -> PerceptionBundle:
        """AsyncMock-compatible wrapper that logs the call then returns a bundle."""
        self.perception_calls.append({
            "action_type": action_type,
            "force_screenshot": force_screenshot,
            "skip_description": skip_description,
            "device_state": self.current_state,
        })
        return self.get_bundle(
            force_screenshot=force_screenshot,
            skip_description=skip_description,
        )

    # ------------------------------------------------------------------ #
    # Action execution                                                     #
    # ------------------------------------------------------------------ #

    def apply_action(
        self,
        action_type: str,
        target: Optional[str] = None,
    ) -> bool:
        """Advance device state. Returns True regardless (gestures always succeed)."""
        target_lower = (target or "").lower()
        for (from_state, act, hint, to_state) in TRANSITIONS:
            if from_state != self.current_state:
                continue
            if act != action_type:
                continue
            if hint is None or hint in target_lower:
                self.action_log.append({
                    "from": self.current_state,
                    "action_type": action_type,
                    "target": target,
                    "to": to_state,
                })
                self.current_state = to_state
                return True
        # No matching transition — action has no effect (device stays put)
        self.action_log.append({
            "from": self.current_state,
            "action_type": action_type,
            "target": target,
            "to": self.current_state,
        })
        return True
