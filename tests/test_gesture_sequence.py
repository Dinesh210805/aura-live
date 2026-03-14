"""
Gesture Sequence Test Suite

Tests a complete series of gestures using REAL WebSocket execution.
Watch your device screen - you'll see each gesture execute in real-time!

IMPORTANT: Backend must be running and device connected via AURA app.
"""

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

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
        await real_accessibility_service.execute_gesture({"action": button})
    except Exception as e:
        print(f"   ❌ Error: {e}")
    await asyncio.sleep(1.0)


# =============================================================================
# TEST SEQUENCES
# =============================================================================

def build_navigation_test() -> List[GestureStep]:
    """Test sequence for basic navigation gestures."""
    return [
        GestureStep(
            name="Scroll Down",
            gesture=build_scroll("down", distance_ratio=0.5),
            description="Scroll down half screen"
        ),
        GestureStep(
            name="Scroll Down Again",
            gesture=build_scroll("down", distance_ratio=0.6),
            description="Scroll down more"
        ),
        GestureStep(
            name="Scroll Up",
            gesture=build_scroll("up", distance_ratio=0.4),
            description="Scroll back up"
        ),
        GestureStep(
            name="Tap Center",
            gesture=build_tap(0.5, 0.5),
            description="Tap center of screen"
        ),
    ]


def build_swipe_test() -> List[GestureStep]:
    """Test sequence for swipe gestures."""
    return [
        GestureStep(
            name="Swipe Left",
            gesture=build_swipe_left(y=0.5),
            description="Swipe left at middle"
        ),
        GestureStep(
            name="Swipe Right",
            gesture=build_swipe_right(y=0.5),
            description="Swipe right to go back"
        ),
        GestureStep(
            name="Swipe Up",
            gesture=build_swipe_up(x=0.5),
            description="Swipe up"
        ),
        GestureStep(
            name="Swipe Down",
            gesture=build_swipe_down(x=0.5),
            description="Swipe down"
        ),
        GestureStep(
            name="Diagonal Swipe",
            gesture=build_swipe(0.2, 0.8, 0.8, 0.2, duration_ms=500),
            description="Diagonal swipe bottom-left to top-right"
        ),
    ]


def build_tap_test() -> List[GestureStep]:
    """Test sequence for tap gestures."""
    return [
        GestureStep(
            name="Tap Top Left",
            gesture=build_tap(0.1, 0.1),
            description="Tap top-left corner"
        ),
        GestureStep(
            name="Tap Top Right", 
            gesture=build_tap(0.9, 0.1),
            description="Tap top-right corner"
        ),
        GestureStep(
            name="Tap Center",
            gesture=build_tap(0.5, 0.5),
            description="Tap center"
        ),
        GestureStep(
            name="Tap Bottom Center",
            gesture=build_tap(0.5, 0.9),
            description="Tap bottom center"
        ),
    ]


def build_long_press_test() -> List[GestureStep]:
    """Test sequence for long press gestures."""
    return [
        GestureStep(
            name="Long Press Center",
            gesture=build_long_press(0.5, 0.5, hold_ms=800),
            wait_after=3.0,
            description="Long press center (800ms hold)"
        ),
        GestureStep(
            name="Long Press Short",
            gesture=build_long_press(0.5, 0.3, hold_ms=500),
            wait_after=2.0,
            description="Short long press (500ms)"
        ),
    ]


def build_app_drawer_test() -> List[GestureStep]:
    """Test opening and navigating app drawer."""
    return [
        GestureStep(
            name="Open App Drawer",
            gesture=build_swipe(0.5, 0.9, 0.5, 0.3, duration_ms=400),
            wait_after=2.5,
            description="Swipe up from bottom to open app drawer"
        ),
        GestureStep(
            name="Scroll Apps Down",
            gesture=build_scroll("down", distance_ratio=0.5),
            description="Scroll through apps"
        ),
        GestureStep(
            name="Scroll Apps Down More",
            gesture=build_scroll("down", distance_ratio=0.5),
            description="Keep scrolling"
        ),
        GestureStep(
            name="Scroll Apps Up",
            gesture=build_scroll("up", distance_ratio=0.7),
            description="Scroll back up"
        ),
    ]


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_sequence(
    client: httpx.AsyncClient,
    sequence_name: str,
    steps: List[GestureStep]
) -> List[TestResult]:
    """Run a sequence of gesture steps."""
    print(f"\n{'='*60}")
    print(f"📋 {sequence_name}")
    print(f"{'='*60}")
    
    results = []
    
    for i, step in enumerate(steps, 1):
        print(f"\n   [{i}/{len(steps)}] {step.name}")
        if step.description:
            print(f"       {step.description}")
        
        result = await execute_gesture(client, step.gesture, step.name)
        results.append(result)
        
        if result.success:
            print(f"       ✅ Queued ({result.response_time_ms:.0f}ms)")
        else:
            print(f"       ❌ Failed: {result.error}")
        
        await asyncio.sleep(step.wait_after)
    
    return results


async def run_all_tests():
    """Run complete gesture test suite."""
    print("\n" + "="*60)
    print("🎯 AURA Gesture Sequence Test Suite")
    print("="*60)
    print(f"\n📡 Backend: {BACKEND_URL}")
    print(f"📱 Device: {DEVICE_NAME}")
    print("\n⚠️  Watch your device screen!")
    print("   You'll see each gesture execute in real-time.")
    
    input("\n   Press Enter to start tests...\n")
    
    all_results = []
    
    async with httpx.AsyncClient() as client:
        # Test 1: Settings App Navigation
        await launch_app(client, "com.android.settings", "Settings")
        results = await run_sequence(
            client, 
            "TEST 1: Settings Navigation",
            build_navigation_test()
        )
        all_results.extend(results)
        await press_button(client, "back")
        await press_button(client, "home")
        
        # Test 2: Home Screen Swipes
        await asyncio.sleep(1.0)
        results = await run_sequence(
            client,
            "TEST 2: Home Screen Swipes", 
            build_swipe_test()
        )
        all_results.extend(results)
        await press_button(client, "home")
        
        # Test 3: Tap Positions
        await launch_app(client, "com.android.settings", "Settings")
        results = await run_sequence(
            client,
            "TEST 3: Tap Positions",
            build_tap_test()
        )
        all_results.extend(results)
        await press_button(client, "home")
        
        # Test 4: Long Press
        await asyncio.sleep(1.0)
        results = await run_sequence(
            client,
            "TEST 4: Long Press (Context Menu)",
            build_long_press_test()
        )
        all_results.extend(results)
        await press_button(client, "back")
        await press_button(client, "home")
        
        # Test 5: App Drawer
        await asyncio.sleep(1.0)
        results = await run_sequence(
            client,
            "TEST 5: App Drawer Navigation",
            build_app_drawer_test()
        )
        all_results.extend(results)
        await press_button(client, "home")
    
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
        print(f"⚠️  {failed} gesture(s) failed - check device connection")
    print("="*60 + "\n")


# =============================================================================
# INDIVIDUAL TEST RUNNERS
# =============================================================================

async def run_quick_test():
    """Quick test - just scrolls and taps."""
    print("\n🚀 Quick Gesture Test")
    print("="*40)
    
    async with httpx.AsyncClient() as client:
        steps = [
            GestureStep("Scroll Down", build_scroll("down")),
            GestureStep("Scroll Up", build_scroll("up")),
            GestureStep("Tap Center", build_tap(0.5, 0.5)),
        ]
        await run_sequence(client, "Quick Test", steps)


async def run_swipe_only():
    """Test only swipe gestures."""
    async with httpx.AsyncClient() as client:
        await press_button(client, "home")
        await run_sequence(client, "Swipe Test", build_swipe_test())


async def run_scroll_only():
    """Test only scroll gestures."""
    async with httpx.AsyncClient() as client:
        await launch_app(client, "com.android.settings", "Settings")
        
        steps = [
            GestureStep("Scroll Down 1", build_scroll("down", 0.5)),
            GestureStep("Scroll Down 2", build_scroll("down", 0.5)),
            GestureStep("Scroll Down 3", build_scroll("down", 0.5)),
            GestureStep("Scroll Up 1", build_scroll("up", 0.5)),
            GestureStep("Scroll Up 2", build_scroll("up", 0.5)),
        ]
        await run_sequence(client, "Scroll Test", steps)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AURA Gesture Test Suite")
    parser.add_argument(
        "--test", 
        choices=["all", "quick", "swipe", "scroll"],
        default="all",
        help="Which test to run (default: all)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=DEVICE_NAME,
        help=f"Device name (default: {DEVICE_NAME})"
    )
    
    args = parser.parse_args()
    DEVICE_NAME = args.device
    
    if args.test == "all":
        asyncio.run(run_all_tests())
    elif args.test == "quick":
        asyncio.run(run_quick_test())
    elif args.test == "swipe":
        asyncio.run(run_swipe_only())
    elif args.test == "scroll":
        asyncio.run(run_scroll_only())
