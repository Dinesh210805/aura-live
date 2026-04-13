"""
AURA MCP Server — exposes Android device control as MCP tools.

Style B: granular tools (Agent-Piloted Mode)

  Perception:
  - perceive_screen()           → full pipeline: screenshot + YOLO + SoM labels
  - get_screenshot()            → raw screenshot only (fast, no perception)
  - get_ui_tree()               → raw accessibility UI tree (all fields, unfiltered)
  - get_annotated_screenshot()  → screenshot + OmniParser bounding-box annotations
  - omniparser_detect()         → YOLOv8 detection on a provided screenshot

  Tap / press gestures:
  - tap()                       → tap by SoM label or (x, y)
  - long_press()                → long-press (default 1s hold)
  - double_tap()                → double-tap at coordinates

  Text input:
  - type_text()                 → type text into the focused field

  Scroll / swipe:
  - scroll_up(), scroll_down(), scroll_left(), scroll_right()  → directional scroll
  - scroll_to()                 → scroll within specific coordinates
  - swipe()                     → free-form swipe between two points

  System buttons:
  - press_back(), press_home(), press_enter()
  - open_recent_apps()
  - volume_up(), volume_down(), mute()

  App / device:
  - lookup_app()                → resolve app name → package name
  - launch_app()                → launch app by package name (intent-based)
  - get_device_status()         → connection check
  - validate_action()           → OPA policy pre-check
  - watch_device_events()       → observe device events

  Legacy catch-all (prefer specific tools above):
  - execute_gesture()           → generic gesture dispatcher

Style A: black box (added in Task 3.x)
  - execute_android_task()      → full AURA pipeline (Groq/Gemini internally)

Run MCP server (separate process from FastAPI):
  python aura_mcp_server.py          ← stdio transport (for Claude Code)

PREREQUISITE: AURA FastAPI server must be running first (python main.py).
The MCP server delegates perception and gesture execution to services that
connect to the Android device via WebSocket — it is NOT standalone.

Configure in Claude Code (~/.claude.json or project .claude/mcp.json):
  {
    "mcpServers": {
      "aura": {
        "command": "python",
        "args": ["aura_mcp_server.py"],
        "cwd": "/path/to/aura-live"
      }
    }
  }
"""

import asyncio
import base64
import datetime
import html
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from config.settings import settings
from services.event_bus import DeviceEvent, get_event_bus
from services.gesture_executor import GestureExecutor
from services.perception_controller import get_perception_controller
from services.policy_engine import ActionContext, PolicyEngine
from agents.actor_agent import ActorAgent

mcp = FastMCP(settings.mcp_server_name)

# ── REST base URL (FastAPI server must be running) ──────────────────────────
_AURA_BASE = "http://127.0.0.1:8000"

# ── Module-level singletons (lazy-init) ─────────────────────────────────────
_actor: Optional[ActorAgent] = None
_policy: Optional[PolicyEngine] = None
_mcp_graph: Optional[Any] = None


def _get_mcp_graph() -> Any:
    """Lazily compile the AURA LangGraph for use in this MCP process."""
    global _mcp_graph
    if _mcp_graph is None:
        from aura_graph.graph import compile_aura_graph
        from langgraph.checkpoint.memory import MemorySaver
        _mcp_graph = compile_aura_graph(checkpointer=MemorySaver())
    return _mcp_graph


def _get_actor() -> ActorAgent:
    global _actor
    if _actor is None:
        _actor = ActorAgent(gesture_executor=GestureExecutor())
    return _actor


def _get_policy() -> PolicyEngine:
    global _policy
    if _policy is None:
        _policy = PolicyEngine()
    return _policy


# ── MCP Brain Logger ─────────────────────────────────────────────────────────
# Writes structured logs matching AURA's CommandLogger format:
#   logs/mcp_brain_YYYYMMDD_HHMMSS.html  (dark-theme interactive)
#   logs/mcp_brain_YYYYMMDD_HHMMSS.txt   (plain text)
#   logs/mcp_brain_YYYYMMDD_HHMMSS.log   (terminal capture)

_ENTRY_COLORS = {
    "TOOL_CALL":  "#4fc3f7",   # light blue
    "PERCEPTION": "#81c784",   # green
    "GESTURE":    "#ffb74d",   # orange
    "APP_LAUNCH": "#ce93d8",   # purple
    "WEB_SEARCH": "#4db6ac",   # teal
    "RESULT":     "#a5d6a7",   # light green
    "ERROR":      "#ef5350",   # red
    "INFO":       "#90caf9",   # blue
}

_HTML_HEADER = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AURA MCP Brain Log</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Courier New',monospace; font-size:13px; padding:20px; }}
    .entry {{ margin:4px 0; padding:6px 10px; border-radius:4px; background:#16213e; border-left:4px solid #4fc3f7; }}
  .ts {{ color:#78909c; margin-right:10px; }}
    .level {{ font-weight:bold; color:#4fc3f7; margin-right:10px; min-width:80px; display:inline-block; }}
  .module {{ color:#90caf9; margin-right:10px; }}
  .msg {{ color:#e0e0e0; }}
  pre {{ margin:4px 0 0 0; color:#b0bec5; white-space:pre-wrap; }}
</style>
</head>
<body>
<h2 style="color:#4fc3f7">AURA MCP Brain Session — {session_id}</h2>
<p style="color:#78909c">Started: {started}</p>
<hr style="border-color:#2a2a4a">
"""

_HTML_ENTRY = """<div class="entry" style="border-left-color:{color}">
  <span class="ts">{ts}</span>
  <span class="level" style="color:{color}">{level}</span>
  <span class="module">{module}</span>
  <span class="msg">{message}</span>
  {detail_block}
</div>
"""


class MCPBrainLogger:
    """Writes structured brain-mode logs in the same style as CommandLogger."""

    def __init__(self):
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_id = f"mcp_{ts}"
        self._html_path = logs_dir / f"{self._session_id}.html"
        self._txt_path = logs_dir / f"{self._session_id}.txt"
        self._log_path = logs_dir / f"{self._session_id}.log"

        started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Bootstrap HTML
        self._html_path.write_text(
            _HTML_HEADER.format(session_id=self._session_id, started=started),
            encoding="utf-8",
        )
        # Bootstrap txt/log
        header_line = f"═══ AURA MCP Brain Session {self._session_id} — {started} ═══\n"
        self._txt_path.write_text(header_line, encoding="utf-8")
        self._log_path.write_text(header_line, encoding="utf-8")

    def _append(self, level: str, module: str, message: str, detail: str = "") -> None:
        now = datetime.datetime.now()
        ts = now.strftime("%H:%M:%S")
        color = _ENTRY_COLORS.get(level, "#e0e0e0")

        # ── HTML ──────────────────────────────────────────────────
        detail_block = ""
        if detail:
            escaped = html.escape(detail[:2000])  # cap to keep file manageable
            detail_block = f"<pre>{escaped}</pre>"
        html_entry = _HTML_ENTRY.format(
            color=color,
            ts=ts,
            level=level,
            module=html.escape(module),
            message=html.escape(message),
            detail_block=detail_block,
        )
        with open(self._html_path, "a", encoding="utf-8") as f:
            f.write(html_entry)

        # ── TXT / LOG ──────────────────────────────────────────────
        txt_line = f"{ts} │ {level:<12} │ {module:<30} │ {message}\n"
        if detail:
            for line in detail.split("\n")[:20]:
                txt_line += f"          │               │                                │   {line}\n"
        with open(self._txt_path, "a", encoding="utf-8") as f:
            f.write(txt_line)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(txt_line)

    def tool_call(self, tool: str, params: dict) -> None:
        import json
        self._append("TOOL_CALL", "mcp.brain", f"→ {tool}", json.dumps(params, indent=2, default=str))

    def result(self, tool: str, result: Any) -> None:
        import json
        msg = f"← {tool}"
        detail = json.dumps(result, indent=2, default=str) if isinstance(result, dict) else str(result)
        self._append("RESULT", "mcp.brain", msg, detail[:1000])

    def gesture(self, gesture_type: str, target: str, success: bool) -> None:
        status = "✓" if success else "✗"
        self._append("GESTURE", "mcp.gesture", f"{status} {gesture_type} → {target}")

    def perception(self, elements: int, has_screenshot: bool) -> None:
        self._append("PERCEPTION", "mcp.perceive", f"elements={elements} screenshot={has_screenshot}")

    def app_launch(self, package_name: str, success: bool) -> None:
        status = "✓" if success else "✗"
        self._append("APP_LAUNCH", "mcp.launch", f"{status} {package_name}")

    def web_search(self, query: str, result_count: int) -> None:
        self._append("WEB_SEARCH", "mcp.search", f"'{query}' → {result_count} results")

    def error(self, tool: str, error: str) -> None:
        self._append("ERROR", f"mcp.{tool}", f"ERROR: {error}")

    def info(self, message: str) -> None:
        self._append("INFO", "mcp.brain", message)

    @property
    def log_path(self) -> str:
        return str(self._html_path)


# Single session logger (one per MCP process lifetime)
_brain_logger: Optional[MCPBrainLogger] = None


def _get_brain_logger() -> MCPBrainLogger:
    global _brain_logger
    if _brain_logger is None:
        _brain_logger = MCPBrainLogger()
    return _brain_logger


# ── Tools ────────────────────────────────────────────────────────────────────

def _is_device_disconnect_error(exc: Exception) -> bool:
    """Return True if the exception is caused by no device being connected."""
    msg = str(exc).lower()
    return any(kw in msg for kw in ("no device", "not connected", "device not connected", "device disconnected"))


def _device_disconnected_response(tool: str, detail: str = "") -> dict:
    """Return a structured error dict Claude can branch on without crashing."""
    return {
        "error": "device_disconnected",
        "connected": False,
        "message": (
            "No Android device connected. "
            "Ask the user to open the AURA app and ensure it shows 'Connected'."
        ),
        "detail": detail,
        "tool": tool,
    }


@mcp.tool()
async def get_device_status() -> dict:
    """
    Check whether an Android device is currently connected to AURA.

    Call this:
    - Before starting any multi-step task sequence
    - After any tool returns {"error": "device_disconnected"}
    - When watch_device_events returns a "device_disconnected" event

    Returns:
        connected: bool — True if device is online and ready
        device_name: str — device identifier (empty if disconnected)
        screen_width: int
        screen_height: int
        has_screenshot: bool — whether a recent screenshot is cached
        ui_elements_available: bool — whether UI tree data is cached
        error: str | None — set only if the status check itself failed
    """
    log = _get_brain_logger()
    log.tool_call("get_device_status", {})

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_AURA_BASE}/device/status")

        if resp.status_code == 200:
            data = resp.json()
            log.result("get_device_status", data)
            return {
                "connected": data.get("connected", False),
                "device_name": data.get("device_name") or "",
                "screen_width": data.get("screen_width", 1080),
                "screen_height": data.get("screen_height", 1920),
                "has_screenshot": data.get("last_screenshot", False),
                "ui_elements_available": data.get("ui_elements_available", False),
                "error": None,
            }
        else:
            err = f"HTTP {resp.status_code}"
            log.error("get_device_status", err)
            return {"connected": False, "device_name": "", "error": err}

    except Exception as e:
        log.error("get_device_status", str(e))
        return {"connected": False, "device_name": "", "error": str(e)}


@mcp.tool()
async def perceive_screen() -> dict:
    """
    Capture a fresh screenshot and UI analysis of the connected Android device.

    Returns a dict with:
      screenshot_base64: str — PNG encoded as base64
      screen_width: int
      screen_height: int
      som_elements: list[dict] — each has {label, description, bounds, type, clickable}
      ui_summary: str — natural language description of current screen
      snapshot_id: str — ID for this perception snapshot

    On device disconnection, returns:
      {"error": "device_disconnected", "connected": false, "message": "..."}
      → Call get_device_status() to confirm, then wait for the user to reconnect.
    """
    log = _get_brain_logger()
    log.tool_call("perceive_screen", {})

    try:
        controller = get_perception_controller()
        bundle = await controller.request_perception(
            intent="observe current screen state",
            action_type="observe",
            execution_history=[],
            retry_context=None,
            app_category=None,
            force_screenshot=True,
            skip_description=False,
            goal=None,
            subgoal_hint=None,
            recent_steps=[],
        )
    except Exception as exc:
        log.error("perceive_screen", str(exc))
        if _is_device_disconnect_error(exc):
            return _device_disconnected_response("perceive_screen", str(exc))
        # For other errors also return structured dict so Claude doesn't crash
        return {"error": "perception_failed", "message": str(exc), "connected": None}

    elements = []
    if bundle.ui_tree and bundle.ui_tree.elements:
        for el in bundle.ui_tree.elements:
            elements.append({
                "label": getattr(el, "som_label", None),
                "description": getattr(el, "content_desc", "") or getattr(el, "text", ""),
                "type": getattr(el, "class_name", ""),
                "bounds": getattr(el, "bounds", None),
                "clickable": getattr(el, "clickable", False),
            })

    screenshot_b64 = None
    width = 0
    height = 0
    if bundle.screenshot:
        screenshot_b64 = bundle.screenshot.screenshot_base64
        width = bundle.screenshot.screen_width
        height = bundle.screenshot.screen_height
    elif bundle.screen_meta:
        width = bundle.screen_meta.width
        height = bundle.screen_meta.height

    log.perception(len(elements), screenshot_b64 is not None)

    result = {
        "screenshot_base64": screenshot_b64,
        "screen_width": width,
        "screen_height": height,
        "som_elements": elements,
        "ui_summary": bundle.visual_description or "",
        "snapshot_id": bundle.snapshot_id,
        "error": None,
    }
    log.result("perceive_screen", {k: v for k, v in result.items() if k != "screenshot_base64"})
    return result


@mcp.tool()
async def execute_gesture(
    gesture_type: str,
    target: str = "",
    params: dict = {},
) -> dict:
    """
    Execute a gesture on the connected Android device.

    Args:
        gesture_type: "tap" | "type" | "swipe" | "scroll" | "back" | "home"
        target: SoM label (e.g. "A3"), element description, or text to type.
        params: optional extra parameters:
          tap:   {"x": int, "y": int} — use coordinates directly
          type:  {"focus_x": int, "focus_y": int} — tap field FIRST, then type.
                 When provided, a tap is executed at (focus_x, focus_y) before typing.
          swipe: {"direction": "up" | "down" | "left" | "right"}

    Returns:
        success: bool
        action_type: str
        duration_ms: float
        error: str | None
        details: dict

    Note: To launch an app, use launch_app() instead — it's faster (intent-based,
    no UI navigation required).
    """
    log = _get_brain_logger()
    log.tool_call("execute_gesture", {"gesture_type": gesture_type, "target": target, "params": params})

    # ── Tap-before-type: if typing and focus coordinates provided ────────────
    if gesture_type == "type" and ("focus_x" in params or "focus_y" in params):
        focus_x = int(params.get("focus_x", 0))
        focus_y = int(params.get("focus_y", 0))
        if focus_x > 0 and focus_y > 0:
            log.info(f"Tap-before-type: tapping ({focus_x}, {focus_y}) before typing")
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    await client.post(
                        f"{_AURA_BASE}/accessibility/execute-gesture",
                        json={"action": "tap", "x": focus_x, "y": focus_y, "duration": 150},
                    )
                    await asyncio.sleep(0.3)  # let keyboard/focus settle
                except Exception as tap_err:
                    log.error("execute_gesture", f"Pre-tap failed: {tap_err}")

    actor = _get_actor()

    coordinates = None
    if gesture_type == "tap" and "x" in params and "y" in params:
        coordinates = (int(params["x"]), int(params["y"]))

    try:
        result = await actor.execute(
            action_type=gesture_type,
            target=target or None,
            coordinates=coordinates,
            parameters=params or None,
        )
    except Exception as exc:
        log.error("execute_gesture", str(exc))
        if _is_device_disconnect_error(exc):
            return _device_disconnected_response("execute_gesture", str(exc))
        return {"success": False, "error": str(exc), "action_type": gesture_type, "duration_ms": 0.0, "details": {}}

    log.gesture(gesture_type, target, result.success)

    # Also surface device-disconnected as a structured error when the actor
    # returns success=False with a "not connected" error message
    if not result.success and result.error and _is_device_disconnect_error(Exception(result.error)):
        log.error("execute_gesture", result.error)
        return _device_disconnected_response("execute_gesture", result.error)

    await get_event_bus().publish(DeviceEvent(
        event_type="gesture_executed",
        source="mcp",
        client_id="mcp_client",
        payload={
            "gesture_type": gesture_type,
            "target": target,
            "success": result.success,
            "error": result.error,
        },
        timestamp=time.time(),
    ))

    out = {
        "success": result.success,
        "action_type": result.action_type,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "details": result.details or {},
    }
    log.result("execute_gesture", out)
    return out


@mcp.tool()
async def lookup_app(app_name: str) -> dict:
    """
    Look up an app by name in the device app inventory.

    Returns the package name and metadata needed to launch the app directly.
    Always call this before launch_app() when you only have a human-readable
    app name (e.g. "Spotify", "WhatsApp", "Chrome").

    Args:
        app_name: Human-readable app name (case-insensitive, supports synonyms
                  like "insta" → Instagram, "gpt" → ChatGPT)

    Returns:
        found: bool
        package_name: str — Android package name (e.g. "com.spotify.music")
        app_name: str — exact name as installed on device
        deep_links: list[str] — supported deep link schemes
        all_candidates: list[str] — additional matching package names (priority order)
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("lookup_app", {"app_name": app_name})

    try:
        from utils.app_inventory_utils import get_app_inventory_manager
        mgr = get_app_inventory_manager()

        app_info = mgr.find_app_by_name(app_name)
        candidates = mgr.get_package_candidates(app_name)

        if app_info:
            result = {
                "found": True,
                "package_name": app_info.get("package_name", ""),
                "app_name": app_info.get("app_name", ""),
                "deep_links": app_info.get("deep_links", []),
                "all_candidates": candidates,
                "error": None,
            }
        else:
            result = {
                "found": False,
                "package_name": "",
                "app_name": app_name,
                "deep_links": [],
                "all_candidates": candidates,
                "error": f"App '{app_name}' not found in device inventory",
            }

        log.result("lookup_app", result)
        return result

    except Exception as e:
        log.error("lookup_app", str(e))
        return {
            "found": False,
            "package_name": "",
            "app_name": app_name,
            "deep_links": [],
            "all_candidates": [],
            "error": str(e),
        }


@mcp.tool()
async def launch_app(package_name: str, deep_link_uri: str = "") -> dict:
    """
    Launch an Android app directly by package name via intent.

    Much faster than navigating the UI — the OS opens the app instantly.
    Always prefer this over tapping app icons in the launcher.

    Workflow:
      1. Call lookup_app(app_name) to get the package_name
      2. Call launch_app(package_name) to open it

    Args:
        package_name: Android package name (e.g. "com.spotify.music").
                      Use lookup_app() first if you only have the app name.
        deep_link_uri: Optional deep link URI (e.g. "spotify://playlist/37i9dQZF").
                       Leave empty for a normal app launch.

    Returns:
        success: bool
        package_name: str
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("launch_app", {"package_name": package_name, "deep_link_uri": deep_link_uri})

    try:
        payload: dict = {"package_name": package_name}
        if deep_link_uri:
            payload["deep_link_uri"] = deep_link_uri

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_AURA_BASE}/accessibility/launch-app",
                json=payload,
            )

        if resp.status_code == 200:
            data = resp.json()
            log.app_launch(package_name, data.get("success", False))
            log.result("launch_app", data)
            return {
                "success": data.get("success", False),
                "package_name": package_name,
                "error": None,
            }
        else:
            err = resp.json().get("detail", f"HTTP {resp.status_code}")
            log.app_launch(package_name, False)
            log.error("launch_app", err)
            return {"success": False, "package_name": package_name, "error": err}

    except Exception as e:
        log.error("launch_app", str(e))
        return {"success": False, "package_name": package_name, "error": str(e)}


@mcp.tool()
async def omniparser_detect(
    screenshot_b64: str,
    screen_width: int = 1080,
    screen_height: int = 1920,
    confidence: float = 0.3,
    include_annotated_image: bool = False,
) -> dict:
    """
    Run OmniParser (YOLOv8) on a screenshot to detect UI elements.

    Use this when the screen contains WebView, Canvas, or game UI where
    the standard UI tree (perceive_screen) has no clickable elements.
    OmniParser assigns Set-of-Marks labels (A1, A2...) to each detected element.

    The VLM uses these labels to select elements without hallucinating coordinates.
    Never use raw (x, y) pixel coordinates from this output directly — use them
    only as inputs to execute_gesture with explicit coordinates.

    Args:
        screenshot_b64: Base64-encoded PNG screenshot (from perceive_screen)
        screen_width: Screen width in pixels (default 1080)
        screen_height: Screen height in pixels (default 1920)
        confidence: Detection confidence threshold 0-1 (default 0.3)
        include_annotated_image: Return annotated SoM image (default False)

    Returns:
        elements_detected: int
        detections: list of {label, description, bounds, confidence, center_x, center_y}
        annotated_image_b64: str | None — annotated image if requested
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("omniparser_detect", {
        "screen_width": screen_width,
        "screen_height": screen_height,
        "confidence": confidence,
        "include_annotated_image": include_annotated_image,
    })

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_AURA_BASE}/perception/omniparser-detect",
                json={
                    "screenshot_b64": screenshot_b64,
                    "screen_width": screen_width,
                    "screen_height": screen_height,
                    "confidence": confidence,
                    "include_annotated_image": include_annotated_image,
                },
            )

        if resp.status_code == 200:
            data = resp.json()
            log.perception(data.get("elements_detected", 0), True)
            log.result("omniparser_detect", {
                "elements_detected": data.get("elements_detected"),
                "detections": data.get("detections", [])[:5],  # cap for log readability
            })
            return data
        else:
            err = resp.json().get("detail", f"HTTP {resp.status_code}")
            log.error("omniparser_detect", err)
            return {"elements_detected": 0, "detections": [], "error": err}

    except Exception as e:
        log.error("omniparser_detect", str(e))
        return {"elements_detected": 0, "detections": [], "error": str(e)}


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> dict:
    """
    Search the web for real-time information using Tavily.

    Use this when:
    - You need current information (weather, news, prices)
    - The user asks a factual question that requires up-to-date data
    - You need to look up an app's deep link URI or content URL

    Requires TAVILY_API_KEY in the server's .env file.

    Args:
        query: Search query string
        max_results: Reserved for future use (Tavily answer mode returns a single synthesized string)

    Returns:
        success: bool
        results: list — empty; use `answer` field instead
        answer: str — Tavily's pre-synthesized answer ready for direct use or TTS
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("web_search", {"query": query, "max_results": max_results})

    try:
        from services.web_search import get_web_search_service
        svc = get_web_search_service()

        if not svc.available:
            return {
                "success": False,
                "results": [],
                "answer": "",
                "error": "Web search unavailable — set TAVILY_API_KEY in .env",
            }

        # search() returns a pre-synthesized answer string (ideal for TTS / direct use)
        answer = await svc.search(query)

        log.web_search(query, 1 if answer else 0)
        log.result("web_search", {"answer": answer[:200]})
        return {
            "success": True,
            "results": [],
            "answer": answer,
            "error": None,
        }

    except Exception as e:
        log.error("web_search", str(e))
        return {"success": False, "results": [], "answer": "", "error": str(e)}


@mcp.tool()
async def validate_action(gesture_type: str, target: str = "") -> dict:
    """
    Check whether an action is permitted by AURA's OPA safety policies.
    Call this before execute_gesture when unsure if an action is safe.

    Args:
        gesture_type: The action type to validate (e.g. "tap", "open_app")
        target: The target element label or app name

    Returns:
        allowed: bool — True if action is permitted
        reason: str — explanation if blocked, empty string if allowed
        requires_confirmation: bool — True if action needs user confirmation
    """
    log = _get_brain_logger()
    log.tool_call("validate_action", {"gesture_type": gesture_type, "target": target})

    policy = _get_policy()

    context = ActionContext(
        action_type=gesture_type,
        target=target or None,
    )
    decision = await policy.evaluate(context)

    result = {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "requires_confirmation": decision.requires_confirmation,
    }
    log.result("validate_action", result)
    return result


async def _poll_device_status_once() -> Optional[bool]:
    """
    Query FastAPI /device/status.  Returns True if connected, False if disconnected,
    None if the HTTP call itself failed (FastAPI not reachable).
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{_AURA_BASE}/device/status")
        if resp.status_code == 200:
            return resp.json().get("connected", False)
        return None
    except Exception:
        return None


@mcp.tool()
async def watch_device_events(timeout_seconds: int = 30) -> list:
    """
    Observe events happening on the device for the specified duration.
    Returns a list of events (voice commands, gestures, screen changes).

    Also polls the FastAPI server every 5 s so that device connection/disconnection
    events are always surfaced — even though the MCP process and the FastAPI process
    have separate event buses.

    Args:
        timeout_seconds: how long to listen before returning (default 30)

    Returns:
        List of event dicts with keys: event_type, source, payload, timestamp
        Special event types:
          "device_disconnected" — Android app dropped the WebSocket connection
          "device_reconnected"  — Android app reconnected after a drop
    """
    log = _get_brain_logger()
    log.tool_call("watch_device_events", {"timeout_seconds": timeout_seconds})

    bus = get_event_bus()
    queue = bus.subscribe("mcp_watcher")

    events = []
    # Track the last known connection state so we can detect transitions
    last_connected: Optional[bool] = await _poll_device_status_once()
    _POLL_INTERVAL = 5.0  # seconds between status polls

    try:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_seconds
        next_poll = loop.time() + _POLL_INTERVAL

        while True:
            now = loop.time()
            if now >= deadline:
                break

            # How long until the next scheduled poll or deadline, whichever is sooner
            wait_until = min(next_poll, deadline)
            remaining_wait = max(0.0, wait_until - loop.time())

            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining_wait)
                events.append({
                    "event_type": event.event_type,
                    "source": event.source,
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                })
            except asyncio.TimeoutError:
                pass  # normal — time to poll

            # Poll FastAPI for authoritative device status
            if loop.time() >= next_poll:
                next_poll = loop.time() + _POLL_INTERVAL
                current_connected = await _poll_device_status_once()

                if current_connected is not None:
                    if last_connected is True and current_connected is False:
                        synthetic = {
                            "event_type": "device_disconnected",
                            "source": "mcp_status_poll",
                            "payload": {"connected": False, "message": "Android device lost connection"},
                            "timestamp": time.time(),
                        }
                        events.append(synthetic)
                        log.info("device_disconnected — detected via status poll")
                    elif last_connected is False and current_connected is True:
                        synthetic = {
                            "event_type": "device_reconnected",
                            "source": "mcp_status_poll",
                            "payload": {"connected": True, "message": "Android device reconnected"},
                            "timestamp": time.time(),
                        }
                        events.append(synthetic)
                        log.info("device_reconnected — detected via status poll")
                    last_connected = current_connected
    finally:
        bus.unsubscribe("mcp_watcher")

    log.result("watch_device_events", {"events_captured": len(events)})
    return events


@mcp.tool()
async def execute_android_task(utterance: str) -> dict:
    """
    Execute a full natural-language command on the Android device using the
    complete AURA pipeline (perception → planning → gesture execution → response).

    Use this when you want AURA to autonomously handle a task end-to-end.
    Use perceive_screen / execute_gesture for step-by-step granular control instead.

    Args:
        utterance: The command in plain English, e.g. "Open Spotify and play Liked Songs"

    Returns:
        success: bool — True if task completed without errors
        response_text: str — AURA's natural-language response
        steps_taken: int — number of gestures executed
        error: str | None — error message if task failed, None otherwise
    """
    log = _get_brain_logger()
    log.tool_call("execute_android_task", {"utterance": utterance})

    graph = _get_mcp_graph()

    from aura_graph.graph import execute_aura_task_from_text
    result = await execute_aura_task_from_text(
        app=graph,
        text_input=utterance,
        thread_id="mcp-session",
        track_workflow=True,
    )

    succeeded = result.get("status") not in ("failed", "error")
    response = (
        result.get("spoken_response")
        or result.get("feedback_message")
        or ("Task completed." if succeeded else "Task failed.")
    )

    await get_event_bus().publish(DeviceEvent(
        event_type="task_executed",
        source="mcp",
        client_id="mcp_client",
        payload={
            "utterance": utterance,
            "success": succeeded,
            "steps_taken": len(result.get("executed_steps", [])),
        },
        timestamp=time.time(),
    ))

    out = {
        "success": succeeded,
        "response_text": response,
        "steps_taken": len(result.get("executed_steps", [])),
        "error": result.get("error_message") if not succeeded else None,
    }
    log.result("execute_android_task", out)
    return out


# ── Private gesture helper ────────────────────────────────────────────────────

async def _call_gesture(
    tool_name: str,
    action_type: str,
    target: Optional[str] = None,
    coordinates: Optional[tuple] = None,
    parameters: Optional[dict] = None,
) -> dict:
    """
    Shared private helper for all dedicated gesture tools.

    Executes via ActorAgent, publishes the event, returns a structured result.
    Handles disconnect detection uniformly so each tool doesn't repeat it.
    """
    log = _get_brain_logger()
    actor = _get_actor()

    try:
        result = await actor.execute(
            action_type=action_type,
            target=target,
            coordinates=coordinates,
            parameters=parameters,
        )
    except Exception as exc:
        log.error(tool_name, str(exc))
        if _is_device_disconnect_error(exc):
            return _device_disconnected_response(tool_name, str(exc))
        return {"success": False, "error": str(exc), "action_type": action_type, "duration_ms": 0.0, "details": {}}

    log.gesture(action_type, target or "", result.success)

    if not result.success and result.error and _is_device_disconnect_error(Exception(result.error)):
        log.error(tool_name, result.error)
        return _device_disconnected_response(tool_name, result.error)

    await get_event_bus().publish(DeviceEvent(
        event_type="gesture_executed",
        source="mcp",
        client_id="mcp_client",
        payload={"gesture_type": action_type, "target": target, "success": result.success, "error": result.error},
        timestamp=time.time(),
    ))

    out = {
        "success": result.success,
        "action_type": result.action_type,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "details": result.details or {},
    }
    log.result(tool_name, out)
    return out


# ── Raw perception tools ──────────────────────────────────────────────────────

@mcp.tool()
async def get_screenshot() -> dict:
    """
    Capture a plain screenshot from the connected Android device.

    Faster and cheaper than perceive_screen() — no YOLO, no VLM, no SoM labels.
    Use when you only need a visual frame (e.g. before passing to get_annotated_screenshot).

    Returns:
        screenshot_base64: str — PNG encoded as base64
        screen_width: int
        screen_height: int
        timestamp: int — capture timestamp (ms)
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("get_screenshot", {})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_AURA_BASE}/accessibility/screenshot")

        if resp.status_code == 200:
            data = resp.json()
            out = {
                "screenshot_base64": data.get("screenshot", ""),
                "screen_width": data.get("width", 1080),
                "screen_height": data.get("height", 1920),
                "timestamp": data.get("timestamp", 0),
                "error": None,
            }
            log.result("get_screenshot", {k: v for k, v in out.items() if k != "screenshot_base64"})
            return out
        elif resp.status_code == 503:
            return _device_disconnected_response("get_screenshot", resp.json().get("detail", ""))
        else:
            err = resp.json().get("detail", f"HTTP {resp.status_code}")
            log.error("get_screenshot", err)
            return {"screenshot_base64": None, "error": err}

    except Exception as e:
        log.error("get_screenshot", str(e))
        if _is_device_disconnect_error(e):
            return _device_disconnected_response("get_screenshot", str(e))
        return {"screenshot_base64": None, "error": str(e)}


@mcp.tool()
async def get_ui_tree() -> dict:
    """
    Fetch the raw unfiltered accessibility UI tree from the connected Android device.

    Unlike perceive_screen() (which runs YOLO + VLM and returns flattened SoM elements),
    this returns the full accessibility tree with every element field: resourceId,
    className, text, contentDescription, bounds, clickable, scrollable, editable,
    focused, enabled, actions, packageName.

    Use this when you need precise element targeting by resourceId, or when you want
    to inspect the full hierarchy before deciding what to tap.

    Warning: Some apps (games, media players with DRM) block the accessibility tree.
    In that case, validation_failed=True is returned — use get_screenshot() or
    get_annotated_screenshot() instead for those apps.

    Returns:
        validation_failed: bool — True if app blocks accessibility
        elements: list[dict] — full element list (empty when validation_failed)
        element_count: int
        screen_width: int
        screen_height: int
        orientation: str
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("get_ui_tree", {})

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{_AURA_BASE}/device/ui-tree")

        if resp.status_code == 200:
            data = resp.json()
            log.result("get_ui_tree", {
                "element_count": data.get("element_count", 0),
                "validation_failed": data.get("validation_failed", False),
            })
            data["error"] = None
            return data
        elif resp.status_code in (503, 400):
            return _device_disconnected_response("get_ui_tree", resp.json().get("detail", ""))
        elif resp.status_code == 504:
            return {"validation_failed": False, "elements": [], "element_count": 0, "error": "timeout — device did not send UI tree within 15s"}
        else:
            err = resp.json().get("detail", f"HTTP {resp.status_code}")
            log.error("get_ui_tree", err)
            return {"validation_failed": False, "elements": [], "element_count": 0, "error": err}

    except Exception as e:
        log.error("get_ui_tree", str(e))
        if _is_device_disconnect_error(e):
            return _device_disconnected_response("get_ui_tree", str(e))
        return {"validation_failed": False, "elements": [], "element_count": 0, "error": str(e)}


@mcp.tool()
async def get_annotated_screenshot() -> dict:
    """
    Capture a screenshot and annotate it with OmniParser YOLOv8 element detection.

    Convenience wrapper: automatically grabs a fresh screenshot then runs it through
    the OmniParser detection pipeline. Use when dealing with WebView, Canvas, or
    game-like UIs where the accessibility tree is unavailable or unhelpful.

    Returns:
        screenshot_base64: str — annotated PNG encoded as base64 (with bounding boxes)
        screen_width: int
        screen_height: int
        elements_detected: int
        detections: list[dict] — each has {label, bbox, confidence, element_type}
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("get_annotated_screenshot", {})

    # Step 1: get raw screenshot
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            sc_resp = await client.get(f"{_AURA_BASE}/accessibility/screenshot")

        if sc_resp.status_code != 200:
            if sc_resp.status_code == 503:
                return _device_disconnected_response("get_annotated_screenshot")
            return {"elements_detected": 0, "detections": [], "error": f"Screenshot failed: HTTP {sc_resp.status_code}"}

        sc_data = sc_resp.json()
        screenshot_b64 = sc_data.get("screenshot", "")
        width = sc_data.get("width", 1080)
        height = sc_data.get("height", 1920)

    except Exception as e:
        log.error("get_annotated_screenshot", f"screenshot step: {e}")
        if _is_device_disconnect_error(e):
            return _device_disconnected_response("get_annotated_screenshot", str(e))
        return {"elements_detected": 0, "detections": [], "error": str(e)}

    # Step 2: run OmniParser on the screenshot
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            om_resp = await client.post(
                f"{_AURA_BASE}/perception/omniparser-detect",
                json={"screenshot_b64": screenshot_b64, "screen_width": width, "screen_height": height},
            )

        if om_resp.status_code == 200:
            data = om_resp.json()
            data["screenshot_base64"] = screenshot_b64
            data["screen_width"] = width
            data["screen_height"] = height
            data["error"] = None
            log.result("get_annotated_screenshot", {"elements_detected": data.get("elements_detected", 0)})
            return data
        else:
            err = om_resp.json().get("detail", f"HTTP {om_resp.status_code}")
            log.error("get_annotated_screenshot", err)
            return {"screenshot_base64": screenshot_b64, "screen_width": width, "screen_height": height, "elements_detected": 0, "detections": [], "error": err}

    except Exception as e:
        log.error("get_annotated_screenshot", f"omniparser step: {e}")
        return {"screenshot_base64": screenshot_b64, "screen_width": width, "screen_height": height, "elements_detected": 0, "detections": [], "error": str(e)}


# ── Individual gesture tools ──────────────────────────────────────────────────

@mcp.tool()
async def tap(
    target: str = "",
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> dict:
    """
    Tap a UI element on the connected Android device.

    Provide EITHER:
      - target: SoM label from perceive_screen (e.g. "A3") or element description
      - x + y: exact screen coordinates (pixels)

    Returns:
        success: bool
        duration_ms: float
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("tap", {"target": target, "x": x, "y": y})
    coords = (x, y) if x is not None and y is not None else None
    return await _call_gesture("tap", "tap", target=target or None, coordinates=coords)


@mcp.tool()
async def long_press(
    target: str = "",
    x: Optional[int] = None,
    y: Optional[int] = None,
    duration_ms: int = 1000,
) -> dict:
    """
    Long-press a UI element on the connected Android device.

    Useful for context menus, drag initiation, widget placement, and text selection.

    Args:
        target: SoM label (e.g. "B2") or element description
        x, y: exact screen coordinates (use instead of target)
        duration_ms: how long to hold the press (default 1000ms = 1 second)

    Returns:
        success: bool
        duration_ms: float
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("long_press", {"target": target, "x": x, "y": y, "duration_ms": duration_ms})
    coords = (x, y) if x is not None and y is not None else None
    return await _call_gesture(
        "long_press", "long_press",
        target=target or None,
        coordinates=coords,
        parameters={"duration": duration_ms},
    )


@mcp.tool()
async def double_tap(
    target: str = "",
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> dict:
    """
    Double-tap a UI element on the connected Android device.

    Use for zooming in on maps/images, activating double-tap shortcuts, or
    selecting words in text editors.

    Args:
        target: SoM label (e.g. "C1") or element description
        x, y: exact screen coordinates (use instead of target)

    Returns:
        success: bool
        duration_ms: float
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("double_tap", {"target": target, "x": x, "y": y})

    # double_tap is not yet dispatched by the actor's gesture_executor.
    # Route directly through the HTTP endpoint as a workaround.
    tap_x = x
    tap_y = y

    # If a SoM label/description was given, ask the actor for resolved coordinates
    # by doing a dry-run; fall back to HTTP with whatever we have.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_AURA_BASE}/accessibility/execute-gesture",
                json={
                    "action": "double_tap",
                    "x": tap_x,
                    "y": tap_y,
                    "duration": 100,
                },
            )
        if resp.status_code == 200:
            out = {"success": True, "action_type": "double_tap", "duration_ms": 100.0, "error": None, "details": {}}
            log.result("double_tap", out)
            return out
        elif resp.status_code in (503, 400):
            return _device_disconnected_response("double_tap", resp.json().get("detail", ""))
        else:
            err = resp.json().get("detail", f"HTTP {resp.status_code}")
            log.error("double_tap", err)
            return {"success": False, "action_type": "double_tap", "duration_ms": 0.0, "error": err, "details": {}}
    except Exception as e:
        log.error("double_tap", str(e))
        if _is_device_disconnect_error(e):
            return _device_disconnected_response("double_tap", str(e))
        return {"success": False, "action_type": "double_tap", "duration_ms": 0.0, "error": str(e), "details": {}}


@mcp.tool()
async def type_text(
    text: str,
    auto_submit: bool = False,
) -> dict:
    """
    Type text into the currently focused input field on the Android device.

    The field must already be focused (tapped) before calling this tool.
    If the field is not focused, use tap() on it first.

    Args:
        text: The text to type. Supports Unicode characters.
        auto_submit: If True, sends Enter/Return after typing (submits forms, searches).

    Returns:
        success: bool
        duration_ms: float
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("type_text", {"text": text[:80], "auto_submit": auto_submit})
    result = await _call_gesture("type_text", "type", target=text, parameters={"auto_submit": auto_submit})
    return result


@mcp.tool()
async def scroll_up(amount: int = 300) -> dict:
    """
    Scroll UP on the current screen (reveals content below the fold).

    Args:
        amount: scroll distance in pixels (default 300 — about one visible screen)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("scroll_up", {"amount": amount})
    return await _call_gesture("scroll_up", "scroll", parameters={"direction": "up", "amount": amount})


@mcp.tool()
async def scroll_down(amount: int = 300) -> dict:
    """
    Scroll DOWN on the current screen (reveals content above).

    Args:
        amount: scroll distance in pixels (default 300)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("scroll_down", {"amount": amount})
    return await _call_gesture("scroll_down", "scroll", parameters={"direction": "down", "amount": amount})


@mcp.tool()
async def scroll_left(amount: int = 300) -> dict:
    """
    Scroll LEFT (swipe right-to-left) — reveals content to the right.

    Use for horizontal carousels, tab sliders, or horizontal lists.

    Args:
        amount: scroll distance in pixels (default 300)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("scroll_left", {"amount": amount})
    return await _call_gesture("scroll_left", "scroll", parameters={"direction": "left", "amount": amount})


@mcp.tool()
async def scroll_right(amount: int = 300) -> dict:
    """
    Scroll RIGHT (swipe left-to-right) — reveals content to the left.

    Use for horizontal carousels, tab sliders, or navigating back in pagers.

    Args:
        amount: scroll distance in pixels (default 300)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("scroll_right", {"amount": amount})
    return await _call_gesture("scroll_right", "scroll", parameters={"direction": "right", "amount": amount})


@mcp.tool()
async def scroll_to(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
) -> dict:
    """
    Scroll within a specific area of the screen using precise coordinates.

    Use this when you need to scroll INSIDE a particular list/container rather
    than the whole screen. Specify start and end points of the scroll gesture.

    Example — scroll down inside a list that starts at y=400:
        scroll_to(x1=540, y1=1000, x2=540, y2=400, duration_ms=400)

    Args:
        x1, y1: start coordinate of the scroll gesture
        x2, y2: end coordinate of the scroll gesture
        duration_ms: scroll speed (longer = slower, smoother; default 300ms)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("scroll_to", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms})
    return await _call_gesture(
        "scroll_to", "swipe",
        coordinates=(x1, y1),
        parameters={"x2": x2, "y2": y2, "duration": duration_ms},
    )


@mcp.tool()
async def swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
) -> dict:
    """
    Perform a free-form swipe gesture between two screen coordinates.

    Use for:
      - Pull-to-refresh (swipe down from top)
      - Dismiss notifications (swipe right)
      - Navigation gestures (swipe from edge)
      - Any gesture that is not a simple directional scroll

    Args:
        x1, y1: start coordinate
        x2, y2: end coordinate
        duration_ms: gesture duration (shorter = faster fling; default 300ms)

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms})
    return await _call_gesture(
        "swipe", "swipe",
        coordinates=(x1, y1),
        parameters={"x2": x2, "y2": y2, "duration": duration_ms},
    )


# ── System / hardware button tools ───────────────────────────────────────────

@mcp.tool()
async def press_back() -> dict:
    """
    Press the Android BACK button.

    Navigates to the previous screen, closes dialogs, or exits the current app
    if already at the root activity.

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("press_back", {})
    return await _call_gesture("press_back", "back")


@mcp.tool()
async def press_home() -> dict:
    """
    Press the Android HOME button.

    Sends the current app to the background and returns to the launcher.

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("press_home", {})
    return await _call_gesture("press_home", "home")


@mcp.tool()
async def press_enter() -> dict:
    """
    Press the ENTER / Return key on the Android soft keyboard.

    Use after type_text() when you want to submit a search, confirm a form,
    or move to the next field without using auto_submit=True.

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("press_enter", {})
    return await _call_gesture("press_enter", "press_enter")


@mcp.tool()
async def open_recent_apps() -> dict:
    """
    Open the Android Recent Apps overview (task switcher).

    Use to:
      - Switch to a recently used app without launching it fresh
      - Check what apps are currently open
      - Close apps by swiping them away in the overview

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("open_recent_apps", {})
    return await _call_gesture("open_recent_apps", "recent_apps")


@mcp.tool()
async def volume_up() -> dict:
    """
    Press the hardware VOLUME UP button on the Android device.

    Increases media/ringer volume by one step.

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("volume_up", {})
    return await _call_gesture("volume_up", "volume_up")


@mcp.tool()
async def volume_down() -> dict:
    """
    Press the hardware VOLUME DOWN button on the Android device.

    Decreases media/ringer volume by one step.

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("volume_down", {})
    return await _call_gesture("volume_down", "volume_down")


@mcp.tool()
async def mute() -> dict:
    """
    Mute the Android device (sets volume to 0 / silent mode).

    Returns:
        success: bool
        error: str | None
    """
    log = _get_brain_logger()
    log.tool_call("mute", {})
    return await _call_gesture("mute", "mute")


if __name__ == "__main__":
    logger_inst = _get_brain_logger()
    logger_inst.info(f"MCP Brain session started — log: {logger_inst.log_path}")
    mcp.run()
