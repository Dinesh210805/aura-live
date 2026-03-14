"""
UI Tree Viewer - Fetches and displays the current screen's UI tree.

Usage:
    python scripts/view_ui_tree.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ui_tree_service import get_ui_tree_service
from services.real_accessibility import real_accessibility_service
from utils.logger import get_logger

logger = get_logger(__name__)


def format_element(elem: dict, indent: int = 0) -> str:
    """Format a single UI element for display."""
    prefix = "  " * indent
    text = elem.get("text") or ""
    desc = elem.get("contentDescription") or ""
    cls = (elem.get("className") or "").split(".")[-1]  # Short class name
    res_id = (elem.get("resourceId") or "").split("/")[-1]
    clickable = elem.get("clickable", False)
    scrollable = elem.get("scrollable", False)
    editable = elem.get("isEditable", False) or "EditText" in (elem.get("className") or "")

    bounds = elem.get("bounds", {})
    if isinstance(bounds, dict):
        cx = bounds.get("centerX", 0)
        cy = bounds.get("centerY", 0)
        l, t, r, b = bounds.get("left", 0), bounds.get("top", 0), bounds.get("right", 0), bounds.get("bottom", 0)
        bounds_str = f"[{l},{t},{r},{b}] center=({cx},{cy})"
    else:
        bounds_str = str(bounds)

    # Build display label
    label = text or desc or res_id or cls
    flags = []
    if clickable:
        flags.append("CLICK")
    if scrollable:
        flags.append("SCROLL")
    if editable:
        flags.append("EDIT")
    flags_str = f" [{','.join(flags)}]" if flags else ""

    line = f"{prefix}├─ [{cls}] \"{label}\"{flags_str}  {bounds_str}"
    if text and desc:
        line += f"  (desc: \"{desc}\")"
    if res_id and res_id != label:
        line += f"  (id: {res_id})"
    return line


async def fetch_and_display():
    """Fetch UI tree from connected device and display it."""
    # Check device connection
    connected = real_accessibility_service.is_device_connected()
    has_ws = real_accessibility_service.has_websocket()
    
    print("=" * 80)
    print("  AURA UI Tree Viewer")
    print("=" * 80)
    print(f"  Device connected: {connected}")
    print(f"  WebSocket ready:  {has_ws}")
    
    if not connected or not has_ws:
        print("\n❌ Device not connected or WebSocket not available.")
        print("   Make sure the server is running and phone is connected.")
        print("\n   Falling back to HTTP API at http://localhost:8000...")
        await fetch_via_http()
        return

    # Request UI tree
    ui_tree_service = get_ui_tree_service()
    print("\n📱 Requesting UI tree from device...")
    
    ui_tree = await ui_tree_service.request_ui_tree("viewer-001", "UI tree viewer")
    
    if ui_tree is None:
        print("❌ Failed to get UI tree (timeout or error)")
        return
    
    display_ui_tree(ui_tree.elements, ui_tree.screen_width, ui_tree.screen_height)


async def fetch_via_http():
    """Fetch UI tree via the running server's HTTP API."""
    try:
        import httpx
    except ImportError:
        print("   Installing httpx...")
        os.system(f"{sys.executable} -m pip install httpx -q")
        import httpx

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient(timeout=15) as client:
        # Step 0: Check device connection status
        try:
            resp = await client.get(f"{base_url}/device/status")
            if resp.status_code == 200:
                status_data = resp.json()
                connected = status_data.get("connected", False)
                print(f"   Device connected: {connected}")
                print(f"   Screen: {status_data.get('screen_width', '?')}x{status_data.get('screen_height', '?')}")
                if not connected:
                    print("\n   ❌ Phone is NOT connected via the AURA app.")
                    print("   Please ensure:")
                    print("     1. AURA app is open on your phone")
                    print("     2. WebSocket connection is established")
                    print("     3. Accessibility Service is enabled")
                    return
        except Exception as e:
            print(f"   ⚠️ Cannot reach server: {e}")
            return

        # Step 1: Request fresh UI capture from device
        try:
            print(f"\n   POST {base_url}/device/request-ui (requesting fresh capture)...")
            resp = await client.post(f"{base_url}/device/request-ui")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ {data.get('message', 'UI capture received')}")
            else:
                print(f"   ⚠️ Status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ /device/request-ui failed: {e}")

        # Step 2: Get the UI snapshot (screenshot + elements)
        try:
            print(f"   GET {base_url}/device/ui-snapshot")
            resp = await client.get(f"{base_url}/device/ui-snapshot")
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                width = data.get("screen_width", 0)
                height = data.get("screen_height", 0)
                display_ui_tree(elements, width, height)
                return
            else:
                print(f"   ⚠️ Status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ /device/ui-snapshot failed: {e}")

        # Fallback: accessibility endpoint
        try:
            print(f"   GET {base_url}/accessibility/current-ui")
            resp = await client.get(f"{base_url}/accessibility/current-ui")
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", data.get("ui_elements", []))
                width = data.get("screen_width", 0)
                height = data.get("screen_height", 0)
                display_ui_tree(elements, width, height)
                return
            else:
                print(f"   ⚠️ Status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ /accessibility/current-ui failed: {e}")

    print("\n❌ Could not retrieve UI tree from any endpoint.")


def display_ui_tree(elements: list, screen_width: int = 0, screen_height: int = 0):
    """Display the UI tree elements."""
    if not elements:
        print("\n⚠️ UI tree is EMPTY (0 elements)")
        print("   This means the accessibility tree has no visible nodes.")
        print("   The screen may contain WebView/Canvas content (like Amazon product cards)")
        print("   that requires OmniParser+VLM to detect.")
        return

    print(f"\n📐 Screen: {screen_width}x{screen_height}")
    print(f"📦 Total elements: {len(elements)}")

    # Stats
    clickable = sum(1 for e in elements if e.get("clickable"))
    scrollable = sum(1 for e in elements if e.get("scrollable"))
    with_text = sum(1 for e in elements if e.get("text"))
    with_desc = sum(1 for e in elements if e.get("contentDescription"))
    editable = sum(1 for e in elements if e.get("isEditable") or "EditText" in (e.get("className") or ""))

    print(f"   Clickable: {clickable} | Scrollable: {scrollable} | Editable: {editable}")
    print(f"   With text: {with_text} | With description: {with_desc}")
    
    # Package name from root
    if elements:
        pkg = elements[0].get("packageName", "unknown")
        print(f"   Package: {pkg}")

    print("\n" + "─" * 80)
    print("  UI TREE HIERARCHY")
    print("─" * 80)

    for i, elem in enumerate(elements):
        print(format_element(elem, indent=0))

    # Also dump raw JSON for debugging
    print("\n" + "─" * 80)
    print("  RAW JSON (first 5 elements)")
    print("─" * 80)
    for elem in elements[:5]:
        print(json.dumps(elem, indent=2, ensure_ascii=False))
        print()


async def fetch_via_ws_service():
    """Fetch UI tree through the server's WebSocket-based UITreeService via a direct API call."""
    try:
        import httpx
    except ImportError:
        os.system(f"{sys.executable} -m pip install httpx -q")
        import httpx

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient(timeout=15) as client:
        # Check device status
        try:
            resp = await client.get(f"{base_url}/device/status")
            if resp.status_code == 200:
                status_data = resp.json()
                connected = status_data.get("connected", False)
                print(f"  Device connected: {connected}")
                print(f"  Screen: {status_data.get('screen_width', '?')}x{status_data.get('screen_height', '?')}")
                if not connected:
                    print("\n  ❌ Phone is NOT connected. Open AURA app and connect.")
                    return
        except Exception as e:
            print(f"  ❌ Cannot reach server at {base_url}: {e}")
            return

        # Use the debug perception endpoint to get fresh UI tree via WebSocket
        print("\n  📱 Requesting UI tree via WebSocket service...")
        try:
            resp = await client.get(f"{base_url}/api/v1/debug/perception", timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                ui_tree_data = data.get("ui_tree") or data.get("last_bundle", {}).get("ui_tree")
                if ui_tree_data:
                    elements = ui_tree_data.get("elements", [])
                    width = ui_tree_data.get("screen_width", 0)
                    height = ui_tree_data.get("screen_height", 0)
                    if elements:
                        display_ui_tree(elements, width, height)
                        return
                print(f"  Debug perception data: {json.dumps(data, indent=2)[:1500]}")
        except Exception as e:
            print(f"  ⚠️ /debug/perception: {e}")

        # Fallback: use task execute endpoint to run a perception-only command
        print("\n  Trying /device/ui-snapshot (cached data)...")
        try:
            resp = await client.get(f"{base_url}/device/ui-snapshot", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                width = data.get("screen_width", 0)
                height = data.get("screen_height", 0)
                if elements:
                    display_ui_tree(elements, width, height)
                    return
                else:
                    print("  ⚠️ UI snapshot has 0 elements")
                    print("  This often means Android hasn't pushed UI data yet.")
                    print("  Try interacting with the phone screen, then run again.")
        except Exception as e:
            print(f"  ⚠️ /device/ui-snapshot: {e}")

    print("\n  ❌ Could not retrieve UI tree. The device may need a screen interaction first.")


if __name__ == "__main__":
    print("=" * 80)
    print("  AURA UI Tree Viewer")
    print("=" * 80)
    asyncio.run(fetch_via_ws_service())
