"""
Gesture Sequence Test Suite - REAL WebSocket Execution

Tests gestures using the actual WebSocket connection to Android device.
Watch your device screen - you'll see each gesture execute in real-time!

IMPORTANT: 
1. Backend must be running (python main.py)
2. AURA app must be open on device and connected via WebSocket
"""

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, ".")

from services.real_accessibility import real_accessibility_service
from utils.logger import get_logger

logger = get_logger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_WAIT = 1.5  # Seconds between gestures


@dataclass
class GestureStep:
    """A single step in a gesture sequence."""
    name: str
    gesture: Dict[str, Any]
    wait_after: float = DEFAULT_WAIT
    description: str = ""


@dataclass
class TestResult:
    """Result of a gesture test."""
    step_name: str
    success: bool
    command_id: Optional[str] = None
    error: Optional[str] = None
    response_time_ms: float = 0


# =============================================================================
# GESTURE HELPERS - Build gestures in the format real_accessibility expects
# =============================================================================

def make_tap(x: int, y: int) -> Dict[str, Any]:
    """Create a tap gesture with pixel coordinates."""
    return {
        "action": "tap",
        "x": x,
        "y": y,
        "format": "pixels"
    }


def make_swipe(x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> Dict[str, Any]:
    """Create a swipe gesture with pixel coordinates."""
    return {
        "action": "swipe",
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "duration": duration,
        "format": "pixels"
    }


def make_scroll(direction: str) -> Dict[str, Any]:
    """Create a scroll gesture."""
    return {
        "action": f"scroll_{direction}"
    }


def make_long_press(x: int, y: int, duration: int = 800) -> Dict[str, Any]:
    """Create a long press gesture."""
    return {
        "action": "long_press",
        "x": x,
        "y": y,
        "duration": duration,
        "format": "pixels"
    }


# =============================================================================
# GESTURE EXECUTION - REAL WEBSOCKET
# =============================================================================

async def execute_gesture(gesture: Dict[str, Any], step_name: str) -> TestResult:
    """Execute a single gesture via WebSocket (the REAL way)."""
    start = time.perf_counter()
    
    try:
        # Use the real accessibility service that sends via WebSocket
        result = await real_accessibility_service.execute_gesture(gesture)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        if result.get("success"):
            return TestResult(
                step_name=step_name,
                success=True,
                command_id=result.get("command_id"),
                response_time_ms=elapsed
            )
        else:
            return TestResult(
                step_name=step_name,
                success=False,
                error=result.get("error", "Unknown error"),
                response_time_ms=elapsed
            )
            
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return TestResult(
            step_name=step_name,
            success=False,
            error=str(e),
            response_time_ms=elapsed
        )


async def check_connection() -> bool:
    """Check if device is connected via WebSocket."""
    connected = real_accessibility_service.is_device_connected()
    device = real_accessibility_service.connected_device
    
    if connected:
        print(f"   ✅ Connected to: {device}")
        return True
    else:
        print("   ❌ No device connected!")
        print("   Make sure:")
        print("      1. Backend is running (python main.py)")
        print("      2. AURA app is open on device")
        print("      3. Device shows 'Connected' status")
        return False


async def launch_app(package_name: str, app_name: str):
    """Launch an app on the device."""
    print(f"\n🚀 Launching {app_name}...")
    try:
        result = await real_accessibility_service.launch_app(package_name)
        if result.get("success"):
            print(f"   ✅ {app_name} launched")
        else:
            print(f"   ❌ Failed: {result.get('error')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    await asyncio.sleep(2.0)


async def press_button(button: str):
    """Press a system button (back, home, recent_apps)."""
    print(f"   🔘 Pressing {button}...")
    try:
        result = await real_accessibility_service.execute_gesture({"action": button})
        if not result.get("success"):
            print(f"      ⚠️ {result.get('error')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    await asyncio.sleep(1.0)


# =============================================================================
# TEST SEQUENCES (using pixel coordinates for 1080x2400 screen)
# =============================================================================

# Screen dimensions - adjust for your device
SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2400


def build_scroll_test() -> List[GestureStep]:
    """Test scroll gestures."""
    return [
        GestureStep(
            name="Scroll Down",
            gesture=make_scroll("down"),
            description="Scroll down"
        ),
        GestureStep(
            name="Scroll Down Again",
            gesture=make_scroll("down"),
            description="Scroll down more"
        ),
        GestureStep(
            name="Scroll Up",
            gesture=make_scroll("up"),
            description="Scroll back up"
        ),
    ]


def build_swipe_test() -> List[GestureStep]:
    """Test swipe gestures with pixel coordinates."""
    mid_x = SCREEN_WIDTH // 2
    mid_y = SCREEN_HEIGHT // 2
    
    return [
        GestureStep(
            name="Swipe Left",
            gesture=make_swipe(900, mid_y, 180, mid_y, 300),
            description="Swipe left across middle"
        ),
        GestureStep(
            name="Swipe Right",
            gesture=make_swipe(180, mid_y, 900, mid_y, 300),
            description="Swipe right across middle"
        ),
        GestureStep(
            name="Swipe Up",
            gesture=make_swipe(mid_x, 1800, mid_x, 600, 400),
            description="Swipe up"
        ),
        GestureStep(
            name="Swipe Down",
            gesture=make_swipe(mid_x, 600, mid_x, 1800, 400),
            description="Swipe down"
        ),
    ]


def build_tap_test() -> List[GestureStep]:
    """Test tap gestures at different screen positions."""
    return [
        GestureStep(
            name="Tap Center",
            gesture=make_tap(540, 1200),
            description="Tap center of screen"
        ),
        GestureStep(
            name="Tap Top Area",
            gesture=make_tap(540, 400),
            description="Tap upper area"
        ),
        GestureStep(
            name="Tap Bottom Area",
            gesture=make_tap(540, 2000),
            description="Tap lower area"
        ),
    ]


def build_long_press_test() -> List[GestureStep]:
    """Test long press gesture."""
    return [
        GestureStep(
            name="Long Press Center",
            gesture=make_long_press(540, 1200, 800),
            wait_after=2.5,
            description="Long press center (should show context menu on home)"
        ),
    ]


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_sequence(sequence_name: str, steps: List[GestureStep]) -> List[TestResult]:
    """Run a sequence of gesture steps."""
    print(f"\n{'='*60}")
    print(f"📋 {sequence_name}")
    print(f"{'='*60}")
    
    results = []
    
    for i, step in enumerate(steps, 1):
        print(f"\n   [{i}/{len(steps)}] {step.name}")
        if step.description:
            print(f"       {step.description}")
        
        result = await execute_gesture(step.gesture, step.name)
        results.append(result)
        
        if result.success:
            print(f"       ✅ Executed ({result.response_time_ms:.0f}ms)")
        else:
            print(f"       ❌ Failed: {result.error}")
        
        await asyncio.sleep(step.wait_after)
    
    return results


async def run_all_tests():
    """Run complete gesture test suite."""
    print("\n" + "="*60)
    print("🎯 AURA Gesture Test Suite (WebSocket)")
    print("="*60)
    
    print("\n📡 Checking device connection...")
    if not await check_connection():
        return
    
    print("\n⚠️  Watch your device screen!")
    print("   You'll see each gesture execute in real-time.")
    
    input("\n   Press Enter to start tests...\n")
    
    all_results = []
    
    # Test 1: Scroll in Settings
    await launch_app("com.android.settings", "Settings")
    results = await run_sequence("TEST 1: Scroll Gestures", build_scroll_test())
    all_results.extend(results)
    await press_button("home")
    
    # Test 2: Swipe on Home Screen
    await asyncio.sleep(1.0)
    results = await run_sequence("TEST 2: Swipe Gestures", build_swipe_test())
    all_results.extend(results)
    await press_button("home")
    
    # Test 3: Tap in Settings
    await launch_app("com.android.settings", "Settings")
    results = await run_sequence("TEST 3: Tap Gestures", build_tap_test())
    all_results.extend(results)
    await press_button("home")
    
    # Test 4: Long Press on Home
    await asyncio.sleep(1.0)
    results = await run_sequence("TEST 4: Long Press", build_long_press_test())
    all_results.extend(results)
    await press_button("back")
    await press_button("home")
    
    # Print summary
    print_summary(all_results)


def print_summary(results: List[TestResult]):
    """Print test summary."""
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total = len(results)
    avg_time = sum(r.response_time_ms for r in results) / total if total > 0 else 0
    
    print(f"\n   Total: {total} gestures")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏱️  Avg Response: {avg_time:.0f}ms")
    
    if failed > 0:
        print("\n   Failed tests:")
        for r in results:
            if not r.success:
                print(f"      - {r.step_name}: {r.error}")
    
    print("\n" + "="*60)
    if failed == 0:
        print("🎉 All gestures executed successfully!")
    else:
        print(f"⚠️  {failed} gesture(s) failed")
    print("="*60 + "\n")


# =============================================================================
# QUICK TESTS
# =============================================================================

async def run_quick_test():
    """Quick test - just a few gestures."""
    print("\n🚀 Quick Gesture Test (WebSocket)")
    print("="*40)
    
    print("\n📡 Checking connection...")
    if not await check_connection():
        return
    
    steps = [
        GestureStep("Back", {"action": "back"}, description="Press back"),
        GestureStep("Home", {"action": "home"}, description="Press home"),
        GestureStep("Scroll Down", make_scroll("down"), description="Scroll"),
        GestureStep("Tap Center", make_tap(540, 1200), description="Tap center"),
    ]
    
    await run_sequence("Quick Test", steps)


async def run_single_gesture(gesture_type: str):
    """Run a single gesture for debugging."""
    print(f"\n🔧 Single Gesture Test: {gesture_type}")
    print("="*40)
    
    print("\n📡 Checking connection...")
    if not await check_connection():
        return
    
    gestures = {
        "tap": make_tap(540, 1200),
        "swipe": make_swipe(540, 1800, 540, 600, 300),
        "scroll_down": make_scroll("down"),
        "scroll_up": make_scroll("up"),
        "back": {"action": "back"},
        "home": {"action": "home"},
        "long_press": make_long_press(540, 1200, 800),
    }
    
    if gesture_type not in gestures:
        print(f"   ❌ Unknown gesture: {gesture_type}")
        print(f"   Available: {list(gestures.keys())}")
        return
    
    gesture = gestures[gesture_type]
    print(f"\n   Executing: {gesture}")
    
    result = await execute_gesture(gesture, gesture_type)
    
    if result.success:
        print(f"   ✅ Success ({result.response_time_ms:.0f}ms)")
    else:
        print(f"   ❌ Failed: {result.error}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AURA Gesture Test Suite (WebSocket)")
    parser.add_argument(
        "--test", 
        choices=["all", "quick", "tap", "swipe", "scroll_down", "scroll_up", "back", "home", "long_press"],
        default="quick",
        help="Which test to run (default: quick)"
    )
    
    args = parser.parse_args()
    
    if args.test == "all":
        asyncio.run(run_all_tests())
    elif args.test == "quick":
        asyncio.run(run_quick_test())
    else:
        asyncio.run(run_single_gesture(args.test))
