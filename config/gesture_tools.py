"""
Centralized gesture tool definitions — single source of truth for all
agent-usable gestures.

Every gesture AURA can perform is defined here with:
  name                RSG action_type token the LLM must output
  description         internal documentation
  prompt_description  concise line injected into agent system prompts
  needs_target        requires locating a specific UI element on screen
  needs_coords        requires pixel coordinates from the perceiver
  needs_perception    requires a live screenshot / UI tree
  fixed_gesture       FixedGesture — screen-relative coords resolved at
                      runtime; if set the actor skips perception entirely
  examples            sample usages shown in prompts

Auto-derived collections (NO_TARGET_ACTIONS, RSG prompt text, etc.) are
computed from this registry so every consumer stays in sync automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ── FixedGesture ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FixedGesture:
    """
    A gesture whose coordinates are derived from the current screen size —
    no perception step required.

    Coordinate fields ending in _frac are proportions of screen width/height.
    _abs overrides take priority when set (useful for true edge positions).

    Examples
    --------
    Top-edge pull-down (notification shade):
        FixedGesture(start_x_frac=0.5, start_y_abs=2, end_x_frac=0.5,
                     end_y_frac=0.65, duration=500)

    Bottom-edge swipe-up (app drawer):
        FixedGesture(start_x_frac=0.5, start_y_frac=0.95,
                     end_x_frac=0.5, end_y_frac=0.15, duration=450)

    System key (no coords needed):
        FixedGesture(action="back")
    """
    action: str = "swipe"

    # Swipe start position
    start_x_frac: float = 0.5
    start_y_frac: float = 0.0
    start_y_abs: Optional[int] = None   # overrides start_y_frac

    # Swipe end position
    end_x_frac: float = 0.5
    end_y_frac: float = 0.6
    end_y_abs: Optional[int] = None     # overrides end_y_frac

    duration: int = 400

    def resolve(self, sw: int, sh: int) -> Dict[str, Any]:
        """Return a concrete action dict ready for GestureExecutor."""
        if self.action != "swipe":
            # System keys: back, home, press_enter, etc.
            return {"action": self.action}

        sx = int(self.start_x_frac * sw)
        sy = self.start_y_abs if self.start_y_abs is not None else int(self.start_y_frac * sh)
        ex = int(self.end_x_frac * sw)
        ey = self.end_y_abs if self.end_y_abs is not None else int(self.end_y_frac * sh)

        return {
            "action": "swipe",
            "start_x": sx,
            "start_y": sy,
            "end_x": ex,
            "end_y": ey,
            "duration": self.duration,
            "format": "pixels",
        }


# ── GestureTool ───────────────────────────────────────────────────────────────

@dataclass
class GestureTool:
    """Metadata for a single gesture exposed to agents."""
    name: str
    description: str                # internal documentation
    prompt_description: str         # concise line shown in agent system prompts
    needs_target: bool = False      # must locate a specific UI element
    needs_coords: bool = False      # requires pixel coordinates from perceiver
    needs_perception: bool = False  # requires screenshot / UI tree
    fixed_gesture: Optional[FixedGesture] = None  # pre-baked; skips perception
    examples: List[str] = field(default_factory=list)


# ── GESTURE_REGISTRY — single source of truth ─────────────────────────────────

GESTURE_REGISTRY: Dict[str, GestureTool] = {

    # ── Element-targeted gestures (perception + coords required) ──────────────

    "tap": GestureTool(
        name="tap",
        description="Tap a visible UI element identified by label or description",
        prompt_description="tap a UI element visible on screen",
        needs_target=True, needs_coords=True, needs_perception=True,
        examples=["tap 'Add to Cart'", "tap Search button"],
    ),

    "long_press": GestureTool(
        name="long_press",
        description=(
            "Hold ~1 second on a UI element. Triggers context menus, drag handles, "
            "text selection mode, or 'press and hold' targets."
        ),
        prompt_description=(
            "hold ~1s on element — context menu / drag handle / text selection"
        ),
        needs_target=True, needs_coords=True, needs_perception=True,
        examples=["long_press chat message for options", "long_press app icon to drag"],
    ),

    # ── App launch ────────────────────────────────────────────────────────────

    "open_app": GestureTool(
        name="open_app",
        description="Launch an installed app by name via Android intent (package-based, no screen element needed)",
        prompt_description="launch an installed app by name (never tap home-screen icons)",
        needs_target=False, needs_perception=False,
        # needs_target=False: app is launched by package name, not by locating an icon on screen.
        # This prevents the perceiver from running a VLM element-lookup that could select a
        # wrong icon (e.g., Brave) and trigger a bad tap before the package-based launch fires.
        examples=["open_app Amazon", "open_app WhatsApp"],
    ),

    # ── Text input ────────────────────────────────────────────────────────────

    "type": GestureTool(
        name="type",
        description=(
            "Type text into the currently focused field. "
            "target = the exact text to type, NOT the field name."
        ),
        prompt_description=(
            "type text — target is the TEXT TO TYPE (e.g. 'Hello'), "
            "field_hint is the label (e.g. 'Subject')"
        ),
        needs_perception=True,
    ),

    # ── Keyboard control ──────────────────────────────────────────────────────

    "press_enter": GestureTool(
        name="press_enter",
        description="Send the IME Enter / Go / Search key after typing",
        prompt_description="press Enter/Go on keyboard — use after typing a search query",
        fixed_gesture=FixedGesture(action="press_enter"),
    ),

    "dismiss_keyboard": GestureTool(
        name="dismiss_keyboard",
        description="Hide the software keyboard",
        prompt_description=(
            "hide keyboard — use before tapping elements in the lower screen half"
        ),
        fixed_gesture=FixedGesture(action="dismiss_keyboard"),
    ),

    # ── Content scrolling (mid-screen swipes) ─────────────────────────────────
    #
    # These start from the centre of the screen and scroll content within an
    # already-open view. They are NOT the same as edge-swipes used to pull
    # down the notification shade or open the app drawer.

    "scroll_down": GestureTool(
        name="scroll_down",
        description="Scroll page content downward to reveal items below the fold",
        prompt_description=(
            "scroll content DOWN — use BEFORE tapping when target element "
            "is not visible in the current viewport"
        ),
        fixed_gesture=FixedGesture(
            action="swipe",
            start_x_frac=0.5, start_y_frac=0.70,
            end_x_frac=0.5,   end_y_frac=0.30,
            duration=400,
        ),
        examples=["scroll_down to reveal 'Add to Cart'"],
    ),

    "scroll_up": GestureTool(
        name="scroll_up",
        description="Scroll page content upward to reveal items above",
        prompt_description=(
            "scroll content UP — use when the target element is above the current view"
        ),
        fixed_gesture=FixedGesture(
            action="swipe",
            start_x_frac=0.5, start_y_frac=0.30,
            end_x_frac=0.5,   end_y_frac=0.70,
            duration=400,
        ),
    ),

    # ── Screen-edge swipes (special start positions, NOT content scrolls) ─────

    "open_notification_shade": GestureTool(
        name="open_notification_shade",
        description=(
            "Pull down from the very top edge of the screen (y ≈ 0) to open the "
            "notification tray / quick-settings panel. "
            "DIFFERENT from scroll_down — must start at the top bezel."
        ),
        prompt_description=(
            "open notification tray — swipe from TOP EDGE (y≈0) to ~65% screen height. "
            "Use instead of scroll_down when the goal involves notifications or quick tiles."
        ),
        # start_y_abs=2 forces the swipe to begin 2 px from the physical top edge
        fixed_gesture=FixedGesture(
            action="swipe",
            start_x_frac=0.5, start_y_abs=2,
            end_x_frac=0.5,   end_y_frac=0.65,
            duration=500,
        ),
        examples=[
            "open_notification_shade to see incoming alerts",
            "open_notification_shade to access quick-settings tiles",
        ],
    ),

    "open_app_drawer": GestureTool(
        name="open_app_drawer",
        description=(
            "Swipe up from the bottom edge of the home screen to open the app drawer. "
            "Only valid on the launcher / home screen. "
            "DIFFERENT from scroll_up — must start near the bottom bezel."
        ),
        prompt_description=(
            "open app drawer — swipe from BOTTOM EDGE upward (home screen only). "
            "Use when you need to find and launch an app not on the home screen."
        ),
        fixed_gesture=FixedGesture(
            action="swipe",
            start_x_frac=0.5, start_y_frac=0.95,
            end_x_frac=0.5,   end_y_frac=0.15,
            duration=450,
        ),
        examples=["open_app_drawer to browse all installed apps"],
    ),

    # ── Free-form directional swipe (carousels / pagers / browser back) ───────

    "swipe": GestureTool(
        name="swipe",
        description=(
            "Generic directional swipe (up / down / left / right). "
            "Use for horizontal image carousels, story viewers, or the "
            "browser back-gesture — NOT for pulling down the notification shade."
        ),
        prompt_description=(
            "swipe left/right/up/down — carousels, image galleries, story pagers, "
            "browser back gesture"
        ),
        examples=[
            "swipe left on story carousel",
            "swipe right to navigate browser back",
        ],
    ),

    # ── Device navigation ─────────────────────────────────────────────────────

    "back": GestureTool(
        name="back",
        description="Press the hardware / software Back button",
        prompt_description="go back to the previous screen",
        fixed_gesture=FixedGesture(action="back"),
    ),

    "home": GestureTool(
        name="home",
        description="Press the Home button — returns to the launcher",
        prompt_description=(
            "go to device home screen — use when app is in a broken state "
            "or goal requires starting fresh from the launcher"
        ),
        fixed_gesture=FixedGesture(action="home"),
    ),

    # ── Flow control ──────────────────────────────────────────────────────────

    "wait": GestureTool(
        name="wait",
        description="Pause and wait for a screen transition or animation to complete",
        prompt_description="wait for screen transition / animation to settle",
        fixed_gesture=FixedGesture(action="wait"),
    ),

    "ask_user": GestureTool(
        name="ask_user",
        description=(
            "Ask the user a question when the agent cannot proceed without human input "
            "(SIM choice, missing required field, ambiguous commit action)."
        ),
        prompt_description=(
            "ask user — ONLY when SIM/account disambiguation, "
            "a required field value, or explicit commit confirmation is needed"
        ),
    ),

    "stuck": GestureTool(
        name="stuck",
        description="Signal that the agent cannot proceed after exhausting all retries",
        prompt_description="signal irrecoverable failure after all retries exhausted",
    ),

    # ── Mid-task web lookup ───────────────────────────────────────────────────
    #
    # The coordinator intercepts this action before it reaches the actor.
    # Result is injected into running_screen_context so the next RSG call has
    # real-time information (addresses, step-by-step guides, current data).
    # Use SPARINGLY — only when the required fact is NOT on screen.

    "web_search": GestureTool(
        name="web_search",
        description=(
            "Look up real-time facts, addresses, how-to guides, or current data "
            "from the web when the information is not visible on screen. "
            "target = the search query string. "
            "Result is injected as context for the next step — no screen gesture is executed."
        ),
        prompt_description=(
            "look up info from the web — target is the search query. "
            "Use ONLY when a fact, address, or how-to guide is needed that is NOT on screen."
        ),
        needs_target=False, needs_coords=False, needs_perception=False,
        examples=[
            "web_search 'Domino's Pizza Koramangala address'",
            "web_search 'how to enable dark mode in Instagram'",
            "web_search 'current weather Bangalore'",
        ],
    ),
}


# ── Derived helpers (single source of truth) ──────────────────────────────────

def get_no_target_actions() -> Set[str]:
    """
    Return the set of action names that do NOT require locating a UI element.

    Used by the coordinator to skip the perception → locate step.
    Includes legacy aliases emitted by older planner/commander prompts.
    """
    registry_set = {name for name, tool in GESTURE_REGISTRY.items() if not tool.needs_target}
    # Legacy aliases not in the registry (commander/planner may still emit these)
    legacy = {
        "go_back", "go_home",
        "scroll", "scroll_left", "scroll_right",
        "volume_up", "volume_down",
        "none",
        "type_text", "enter_text", "set_text", "input_text",
        "press_search",
    }
    return registry_set | legacy


def get_rsg_actions_prompt() -> str:
    """
    Build the ━━━ AVAILABLE ACTIONS ━━━ block for agent system prompts.

    Output format:
        ━━━ AVAILABLE ACTIONS ━━━
        tap | long_press | open_app | ...

        Action notes:
        - tap: ...
        - long_press: ...
    """
    names = " | ".join(GESTURE_REGISTRY.keys())
    notes = "\n".join(
        f"- {name}: {tool.prompt_description}"
        for name, tool in GESTURE_REGISTRY.items()
    )
    return (
        "━━━ AVAILABLE ACTIONS ━━━\n"
        f"{names}\n\n"
        f"Action notes:\n{notes}"
    )


def resolve_gesture(name: str, sw: int, sh: int) -> Optional[Dict[str, Any]]:
    """
    Resolve a fixed-gesture tool to a concrete action dict.

    Returns:
        Concrete action dict (e.g. {"action": "swipe", "start_x": 540, ...})
        for tools that have a fixed_gesture defined.
        None if the tool requires perception (caller must go through perceiver).
    """
    tool = GESTURE_REGISTRY.get(name)
    if not tool or not tool.fixed_gesture:
        return None
    return tool.fixed_gesture.resolve(sw, sh)
