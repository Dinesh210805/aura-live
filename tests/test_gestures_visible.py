"""
Gesture testing with VISIBLE results on real apps.
You'll actually see the gestures working!
"""

import time

import requests

# CONFIGURATION
BACKEND_URL = "http://localhost:8000"
DEVICE_NAME = "OnePlus CPH2661"  # Change to your device name


def send_gesture(gesture_payload, description, wait=3):
    """Send a gesture command via HTTP API."""
    print(f"\n{'='*60}")
    print(f"📤 Test: {description}")

    try:
        response = requests.post(
            f"{BACKEND_URL}/device/commands/queue",
            params={"device_name": DEVICE_NAME, "command_type": "gesture"},
            json=gesture_payload,
            timeout=5,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Queued: {result['command_id']}")
        else:
            print(f"❌ Failed: HTTP {response.status_code}")

    except Exception as e: 
        print(f"❌ Exception: {e}")

    print(f"⏳ Waiting {wait} seconds...")
    print(f"{'='*60}\n")
    time.sleep(wait)


def launch_app(package_name, app_name):
    """Launch an app."""
    print(f"\n🚀 Launching {app_name}...")
    requests.post(
        f"{BACKEND_URL}/device/commands/queue",
        params={"device_name": DEVICE_NAME, "command_type": "launch_app"},
        json={"package_name": package_name},
        timeout=5,
    )
    print("✅ Launch command sent")
    time.sleep(2)


def main():
    """Run visible gesture tests on real apps."""
    print("🚀 AURA Visible Gesture Testing")
    print(f"Backend: {BACKEND_URL}")
    print(f"Device: {DEVICE_NAME}")
    print("\n⚠️  Make sure:")
    print("  1. Backend is running")
    print("  2. Android device connected and polling")
    print("  3. WATCH YOUR PHONE SCREEN - you'll see gestures happen!")
    input("\nPress Enter to start tests...\n")

    # ========================================
    # TEST SEQUENCE 1: Settings App
    # ========================================
    print("\n" + "=" * 60)
    print("TEST SEQUENCE 1: Settings App")
    print("=" * 60)

    launch_app("com.android.settings", "Settings")

    # Scroll down in settings
    send_gesture(
        {
            "gesture_type": "scroll",
            "target": {"type": "direction", "direction": "down", "distance_ratio": 0.6},
            "options": {"duration_ms": 500},
        },
        "Scroll down in Settings (you should see list scroll!)",
        wait=2,
    )

    # Scroll up
    send_gesture(
        {
            "gesture_type": "scroll",
            "target": {"type": "direction", "direction": "up", "distance_ratio": 0.6},
            "options": {"duration_ms": 500},
        },
        "Scroll up in Settings",
        wait=2,
    )

    # Tap on "Network & internet" or similar (top of list)
    send_gesture(
        {
            "gesture_type": "tap",
            "target": {"type": "coordinates", "x": 0.5, "y": 0.25, "normalized": True},
        },
        "Tap near top of Settings (should open a menu!)",
        wait=2,
    )

    # Go back
    send_gesture({"action": "back"}, "Press Back button (legacy format)", wait=1)

    # ========================================
    # TEST SEQUENCE 2: Chrome App
    # ========================================
    print("\n" + "=" * 60)
    print("TEST SEQUENCE 2: Chrome Browser")
    print("=" * 60)

    launch_app("com.android.chrome", "Chrome")
    time.sleep(3)  # Wait for Chrome to fully load

    # Tap address bar (normalized coordinates - top of screen)
    send_gesture(
        {
            "gesture_type": "tap",
            "target": {"type": "coordinates", "x": 0.5, "y": 0.1, "normalized": True},
        },
        "Tap Chrome address bar (should show keyboard!)",
        wait=3,
    )

    # Press back to close keyboard
    send_gesture({"action": "back"}, "Close keyboard", wait=1)

    # Swipe to next tab (if multiple tabs)
    send_gesture(
        {
            "gesture_type": "swipe",
            "target": {"type": "coordinates", "x": 0.8, "y": 0.5, "normalized": True},
            "end_target": {"x": 0.2, "y": 0.5, "normalized": True},
            "options": {"duration_ms": 300},
        },
        "Swipe left (fast swipe)",
        wait=2,
    )

    # ========================================
    # TEST SEQUENCE 3: App Drawer
    # ========================================
    print("\n" + "=" * 60)
    print("TEST SEQUENCE 3: Home Screen & App Drawer")
    print("=" * 60)

    # Go home
    send_gesture({"action": "home"}, "Go to Home screen", wait=2)

    # Swipe up to open app drawer
    send_gesture(
        {
            "gesture_type": "swipe",
            "target": {"type": "coordinates", "x": 0.5, "y": 0.8, "normalized": True},
            "end_target": {"x": 0.5, "y": 0.2, "normalized": True},
            "options": {"duration_ms": 400},
        },
        "Swipe up to open App Drawer (you should see apps!)",
        wait=2,
    )

    # Scroll in app drawer
    send_gesture(
        {
            "gesture_type": "scroll",
            "target": {"type": "direction", "direction": "down"},
        },
        "Scroll down in App Drawer",
        wait=2,
    )

    # Tap to close app drawer (tap outside)
    send_gesture(
        {
            "gesture_type": "tap",
            "target": {"type": "coordinates", "x": 0.1, "y": 0.1, "normalized": True},
        },
        "Tap to close App Drawer",
        wait=2,
    )

    # ========================================
    # TEST SEQUENCE 4: Long Press Test
    # ========================================
    print("\n" + "=" * 60)
    print("TEST SEQUENCE 4: Long Press (Context Menu)")
    print("=" * 60)

    # Long press on home screen (should show widget/wallpaper menu)
    send_gesture(
        {
            "gesture_type": "long_press",
            "target": {"type": "coordinates", "x": 0.5, "y": 0.5, "normalized": True},
            "options": {"hold_ms": 800},
        },
        "Long press on Home screen (should show context menu!)",
        wait=3,
    )

    # Press back to close any menu
    send_gesture({"action": "back"}, "Close any open menu", wait=1)

    # ========================================
    # FINAL: Return to AURA app
    # ========================================
    print("\n" + "=" * 60)
    print("FINAL: Return to AURA app")
    print("=" * 60)

    launch_app("com.aura.aura_ui.debug", "AURA")

    print("\n" + "=" * 60)
    print("✅ All visible tests completed!")
    print("=" * 60)
    print("\n📊 What you should have seen:")
    print("  ✅ Settings app scrolling up and down")
    print("  ✅ Settings menu opening when tapped")
    print("  ✅ Chrome address bar activating")
    print("  ✅ App drawer opening and scrolling")
    print("  ✅ Long press showing home screen context menu")
    print("\nIf you saw these, gestures are working perfectly! 🎉")


if __name__ == "__main__":
    main()