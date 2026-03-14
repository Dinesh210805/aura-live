"""
Test script for sensitive action blocking policy.

Run this to verify that dangerous commands are properly blocked.
"""

import requests
import json
from typing import Dict

BASE_URL = "http://localhost:8000/api/v1"


def test_command(command: str, should_block: bool = False) -> bool:
    """
    Test a command to see if it's blocked.
    
    Args:
        command: Command to test
        should_block: Whether we expect it to be blocked
        
    Returns:
        Test passed
    """
    print(f"\n{'='*60}")
    print(f"Testing: {command}")
    print(f"Expected: {'BLOCKED' if should_block else 'ALLOWED'}")
    print(f"{'='*60}")
    
    # First check using policy endpoint
    check_response = requests.post(
        f"{BASE_URL}/sensitive-policy/check",
        json={"command": command}
    )
    
    check_result = check_response.json()
    is_sensitive = check_result.get("is_sensitive", False)
    
    print(f"Policy Check: {'🚫 SENSITIVE' if is_sensitive else '✅ SAFE'}")
    if is_sensitive:
        print(f"Reason: {check_result.get('reason')}")
        print(f"Message: {check_result.get('message')}")
    
    # Now test actual execution
    exec_response = requests.post(
        f"{BASE_URL}/tasks/execute",
        json={
            "input_type": "text",
            "text_input": command
        }
    )
    
    exec_result = exec_response.json()
    status = exec_result.get("status")
    
    print(f"\nExecution Status: {status}")
    print(f"Response: {exec_result.get('spoken_response', 'N/A')}")
    
    # Check if test passed
    if should_block:
        passed = status == "blocked"
        print(f"\n{'✅ TEST PASSED' if passed else '❌ TEST FAILED'}: Command was {'blocked' if status == 'blocked' else 'allowed'}")
    else:
        passed = status != "blocked"
        print(f"\n{'✅ TEST PASSED' if passed else '❌ TEST FAILED'}: Command was {'allowed' if status != 'blocked' else 'blocked'}")
    
    return passed


def run_all_tests():
    """Run comprehensive test suite."""
    print("\n" + "="*60)
    print("🧪 SENSITIVE ACTION BLOCKING TEST SUITE")
    print("="*60)
    
    # Test categories
    tests = [
        # Banking (should block)
        ("open chase bank", True),
        ("launch paypal", True),
        ("open bank of america", True),
        ("start google pay", True),
        ("send money via venmo", True),
        
        # System operations (should block)
        ("shutdown my phone", True),
        ("restart device", True),
        ("factory reset", True),
        ("reboot phone", True),
        
        # Destructive operations (should block)
        ("delete all photos", True),
        ("uninstall whatsapp", True),
        ("clear all data", True),
        ("remove this file", True),
        
        # Security (should block)
        ("disable fingerprint lock", True),
        ("turn off password", True),
        ("remove pin", True),
        
        # Safe operations (should NOT block)
        ("open youtube", False),
        ("play music on spotify", False),
        ("search for pizza", False),
        ("turn on wifi", False),
        ("take a screenshot", False),
        ("open camera", False),
    ]
    
    passed = 0
    failed = 0
    
    for command, should_block in tests:
        try:
            if test_command(command, should_block):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ TEST ERROR: {e}")
            failed += 1
    
    # Print summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: {passed + failed}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    # Get policy stats
    try:
        stats_response = requests.get(f"{BASE_URL}/sensitive-policy/stats")
        stats = stats_response.json()
        print(f"\n📈 Policy Stats:")
        print(f"   Enabled: {stats.get('enabled')}")
        print(f"   Total Blocked: {stats.get('blocked_count')}")
        print(f"   Categories:")
        for category, count in stats.get('categories', {}).items():
            print(f"      {category}: {count} keywords")
    except Exception as e:
        print(f"Could not fetch stats: {e}")


if __name__ == "__main__":
    print("\n⚠️  Make sure Aura server is running on localhost:8000")
    input("Press Enter to start tests...")
    
    run_all_tests()
    
    print("\n✨ Testing complete!")
    print("View detailed logs at: http://localhost:8000/api/v1/debug/unified-logs/export/html")
