"""
Get UI Elements - Simple script to fetch and display current screen UI elements.

Usage:
    python tools/get_ui_elements.py
"""

import requests
import sys
from pathlib import Path

# Backend API configuration
BACKEND_URL = "http://localhost:8000"
API_ENDPOINT = f"{BACKEND_URL}/api/v1/device/ui-elements"


def get_current_ui_elements():
    """Fetch and display UI elements from current screen via HTTP API."""
    
    try:
        print("📋 Requesting UI elements from backend API...")
        response = requests.get(API_ENDPOINT, timeout=10)
        
        if response.status_code == 503:
            print("❌ ERROR: Device not connected!")
            print("   Please ensure:")
            print("   1. Android app is running")
            print("   2. Backend server is started (python main.py)")
            print("   3. Device is connected via WebSocket")
            return None
        
        if response.status_code != 200:
            print(f"❌ ERROR: API request failed (HTTP {response.status_code})")
            print(f"   {response.json().get('detail', 'Unknown error')}")
            return None
        
        data = response.json()
        
        if not data.get("success"):
            print(f"❌ ERROR: {data.get('error', 'Failed to get UI elements')}")
            return None
        
        elements = data.get("elements", [])
        
        print(f"✅ Received {data.get('total_count', 0)} UI elements")
        print(f"📱 Screen: {data.get('screen_width')}x{data.get('screen_height')}")
        print(f"📦 Current app: {data.get('current_app', 'Unknown')}")
        print()
        
        # Display elements
        print("=" * 100)
        print("UI ELEMENTS ON CURRENT SCREEN")
        print("=" * 100)
        print()
        
        for idx, element in enumerate(elements, 1):
            # Build flags string (handle both snake_case and camelCase)
            flags = []
            if element.get("clickable") or element.get("isClickable"):
                flags.append("CLICKABLE")
            if element.get("scrollable") or element.get("isScrollable"):
                flags.append("SCROLLABLE")
            if element.get("editable") or element.get("isEditable"):
                flags.append("EDITABLE")
            
            flags_str = f"[{', '.join(flags)}]" if flags else "[NONE]"
            
            # Get label (text or content description)
            label = element.get("text") or element.get("contentDescription") or "(no label)"
            if len(label) > 50:
                label = label[:47] + "..."
            
            # Get bounds
            bounds = element.get("bounds", {})
            x = bounds.get("centerX", 0)
            y = bounds.get("centerY", 0)
            width = bounds.get("width", 0)
            height = bounds.get("height", 0)
            
            # Get className (try both formats)
            class_name = element.get("className") or element.get("class_name") or "Unknown"
            if class_name != "Unknown":
                class_name = class_name.split(".")[-1]  # Simplify to last part
            
            # Display element info
            print(f"Element #{idx}")
            print(f"  Label:       {label}")
            print(f"  Type:        {class_name}")
            print(f"  Flags:       {flags_str}")
            print(f"  Position:    ({x}, {y})")
            print(f"  Size:        {width}x{height}")
            
            resource_id = element.get("resourceId") or element.get("viewId")
            if resource_id:
                print(f"  Resource ID: {resource_id}")
            
            print()
        
        # Summary statistics
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Total elements:      {data.get('total_count', 0)}")
        print(f"Clickable:          {data.get('clickable_count', 0)}")
        print(f"Scrollable:         {data.get('scrollable_count', 0)}")
        print(f"Editable:           {data.get('editable_count', 0)}")
        print()
        
        return elements
        
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to backend server!")
        print("   Please ensure backend is running:")
        print("   python main.py")
        return None
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out!")
        print("   Backend server may be overloaded or unresponsive")
        return None
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return None


if __name__ == "__main__":
    print()
    print("🔍 UI ELEMENTS INSPECTOR")
    print("=" * 100)
    print()
    
    get_current_ui_elements()
