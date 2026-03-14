"""
Test suite for the improved gesture execution system.

Tests all gesture types and execution strategies.
"""

import asyncio
import sys
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, '.')

from services.gesture_executor import get_gesture_executor, GestureType
from services.real_accessibility import real_accessibility_service
from utils.logger import get_logger

logger = get_logger(__name__)


class GestureTestSuite:
    """Comprehensive test suite for gesture execution."""

    def __init__(self):
        self.executor = get_gesture_executor()
        self.passed = 0
        self.failed = 0
        self.results = []

    def print_header(self, text: str):
        """Print a test section header."""
        print("\n" + "=" * 70)
        print(f"  {text}")
        print("=" * 70)

    def print_test(self, name: str, status: str, details: str = ""):
        """Print test result."""
        symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏭️"
        print(f"{symbol} {name}")
        if details:
            print(f"   {details}")

    async def setup_device(self) -> bool:
        """Setup test device connection."""
        self.print_header("Device Setup")
        
        # Register test device
        device_info = {
            "device_name": "Test Android Device",
            "android_version": "13",
            "screen_width": 1080,
            "screen_height": 2400,
            "density_dpi": 420,
            "connected_at": asyncio.get_event_loop().time()
        }
        
        real_accessibility_service.set_device_connection(device_info)
        
        if real_accessibility_service.is_device_connected():
            self.print_test("Device Registration", "PASS", "Test device registered")
            return True
        else:
            self.print_test("Device Registration", "FAIL", "Failed to register device")
            return False

    async def test_tap_gesture(self):
        """Test tap gesture execution."""
        self.print_header("Test 1: Tap Gesture")
        
        test_cases = [
            {
                "name": "Tap with absolute coordinates",
                "plan": [{
                    "action": "tap",
                    "coordinates": [540, 1200]
                }]
            },
            {
                "name": "Tap with normalized coordinates",
                "plan": [{
                    "action": "tap",
                    "coordinates": [0.5, 0.5]
                }]
            },
            {
                "name": "Tap with dict coordinates",
                "plan": [{
                    "action": "tap",
                    "coordinates": {"x": 540, "y": 1200}
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Strategy: {result['execution_steps'][0].get('strategy', 'unknown')}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_swipe_gesture(self):
        """Test swipe gesture execution."""
        self.print_header("Test 2: Swipe Gesture")
        
        test_cases = [
            {
                "name": "Swipe with start/end coordinates",
                "plan": [{
                    "action": "swipe",
                    "coordinates": {
                        "start": {"x": 540, "y": 1800},
                        "end": {"x": 540, "y": 600}
                    },
                    "duration": 500
                }]
            },
            {
                "name": "Swipe with x1/y1/x2/y2",
                "plan": [{
                    "action": "swipe",
                    "coordinates": {
                        "x1": 540, "y1": 1800,
                        "x2": 540, "y2": 600
                    },
                    "duration": 500
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Strategy: {result['execution_steps'][0].get('strategy', 'unknown')}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_scroll_gesture(self):
        """Test scroll gesture execution."""
        self.print_header("Test 3: Scroll Gesture")
        
        test_cases = [
            {
                "name": "Scroll down",
                "plan": [{"action": "scroll", "direction": "down"}]
            },
            {
                "name": "Scroll up",
                "plan": [{"action": "scroll", "direction": "up"}]
            },
            {
                "name": "Scroll left",
                "plan": [{"action": "scroll", "direction": "left"}]
            },
            {
                "name": "Scroll right",
                "plan": [{"action": "scroll", "direction": "right"}]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Direction: {test['plan'][0]['direction']}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_long_press_gesture(self):
        """Test long press gesture execution."""
        self.print_header("Test 4: Long Press Gesture")
        
        test_cases = [
            {
                "name": "Long press at center",
                "plan": [{
                    "action": "long_press",
                    "coordinates": [540, 1200]
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Strategy: {result['execution_steps'][0].get('strategy', 'unknown')}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_app_launch(self):
        """Test app launch execution."""
        self.print_header("Test 5: App Launch")
        
        test_cases = [
            {
                "name": "Launch with app name",
                "plan": [{
                    "action": "launch_app",
                    "app_name": "Settings"
                }]
            },
            {
                "name": "Launch with package name",
                "plan": [{
                    "action": "launch_app",
                    "package_name": "com.android.settings"
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Strategy: {result['execution_steps'][0].get('strategy', 'intent')}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_type_text(self):
        """Test text input execution."""
        self.print_header("Test 6: Text Input")
        
        test_cases = [
            {
                "name": "Type simple text",
                "plan": [{
                    "action": "type",
                    "text": "Hello World"
                }]
            },
            {
                "name": "Type with special characters",
                "plan": [{
                    "action": "type",
                    "text": "test@example.com"
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Text length: {len(test['plan'][0]['text'])}"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_wait_action(self):
        """Test wait/delay action."""
        self.print_header("Test 7: Wait Action")
        
        test_cases = [
            {
                "name": "Wait 1 second",
                "plan": [{
                    "action": "wait",
                    "duration": 1.0
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    exec_time = result['execution_steps'][0].get('execution_time', 0)
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Actual time: {exec_time:.2f}s"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_multi_step_execution(self):
        """Test multi-step action plan."""
        self.print_header("Test 8: Multi-Step Execution")
        
        test_cases = [
            {
                "name": "Launch app, wait, then tap",
                "plan": [
                    {
                        "action": "launch_app",
                        "app_name": "Settings",
                        "post_delay": 2.0
                    },
                    {
                        "action": "wait",
                        "duration": 1.0
                    },
                    {
                        "action": "tap",
                        "coordinates": [540, 400]
                    }
                ]
            },
            {
                "name": "Tap, scroll, tap sequence",
                "plan": [
                    {
                        "action": "tap",
                        "coordinates": [540, 400],
                        "post_delay": 0.5
                    },
                    {
                        "action": "scroll",
                        "direction": "down",
                        "post_delay": 0.5
                    },
                    {
                        "action": "tap",
                        "coordinates": [540, 1200]
                    }
                ]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                success_rate = f"{result['successful_steps']}/{result['total_steps']}"
                
                if result["success"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Steps: {success_rate}, Time: {result['total_execution_time']:.2f}s"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Steps: {success_rate}, Errors: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    async def test_error_handling(self):
        """Test error handling."""
        self.print_header("Test 9: Error Handling")
        
        test_cases = [
            {
                "name": "Invalid action type",
                "plan": [{
                    "action": "invalid_action"
                }]
            },
            {
                "name": "Tap without coordinates",
                "plan": [{
                    "action": "tap"
                }]
            },
            {
                "name": "Scroll with invalid direction",
                "plan": [{
                    "action": "scroll",
                    "direction": "diagonal"
                }]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                # These should fail gracefully
                if not result["success"] and result["errors"]:
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Error handled correctly: {result['errors'][0][:50]}..."
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        "Should have failed but didn't"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                # Exception is acceptable for error test
                self.print_test(test["name"], "PASS", f"Exception caught: {str(e)[:50]}...")
                self.passed += 1

    async def test_coordinate_normalization(self):
        """Test coordinate normalization."""
        self.print_header("Test 10: Coordinate Normalization")
        
        test_cases = [
            {
                "name": "Absolute coordinates (1080x2400)",
                "plan": [{"action": "tap", "coordinates": [1080, 2400]}]
            },
            {
                "name": "Normalized coordinates (0-1)",
                "plan": [{"action": "tap", "coordinates": [0.9, 0.9]}]
            },
            {
                "name": "Mixed format (absolute)",
                "plan": [{"action": "tap", "coordinates": {"x": 800, "y": 1500}}]
            }
        ]
        
        for test in test_cases:
            try:
                result = await self.executor.execute_plan(test["plan"])
                if result["success"]:
                    details = result['execution_steps'][0].get('details', {})
                    self.print_test(
                        test["name"], 
                        "PASS",
                        f"Normalized to: ({details.get('x', 0)}, {details.get('y', 0)})"
                    )
                    self.passed += 1
                else:
                    self.print_test(
                        test["name"], 
                        "FAIL",
                        f"Error: {result['errors']}"
                    )
                    self.failed += 1
                self.results.append({"test": test["name"], "result": result})
            except Exception as e:
                self.print_test(test["name"], "FAIL", f"Exception: {str(e)}")
                self.failed += 1

    def print_summary(self):
        """Print test summary."""
        self.print_header("Test Summary")
        
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📊 Pass Rate: {pass_rate:.1f}%")
        
        if self.passed == total:
            print("\n🎉 All tests passed!")
        elif pass_rate >= 80:
            print("\n✅ Most tests passed!")
        else:
            print("\n⚠️  Some tests failed. Review results above.")
        
        print("\n" + "=" * 70)

    async def run_all_tests(self):
        """Run all test suites."""
        print("\n")
        print("╔" + "=" * 68 + "╗")
        print("║" + " " * 15 + "GESTURE EXECUTOR TEST SUITE" + " " * 25 + "║")
        print("╚" + "=" * 68 + "╝")
        
        # Setup
        if not await self.setup_device():
            print("\n❌ Device setup failed. Cannot continue tests.")
            return
        
        # Run all tests
        await self.test_tap_gesture()
        await self.test_swipe_gesture()
        await self.test_scroll_gesture()
        await self.test_long_press_gesture()
        await self.test_app_launch()
        await self.test_type_text()
        await self.test_wait_action()
        await self.test_multi_step_execution()
        await self.test_error_handling()
        await self.test_coordinate_normalization()
        
        # Summary
        self.print_summary()


async def main():
    """Main test runner."""
    test_suite = GestureTestSuite()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
