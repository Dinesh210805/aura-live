"""Test edge routing for tap vs send_message actions."""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from aura_graph.edges import should_continue_after_intent_parsing
from aura_graph.state import TaskState

print("\n" + "="*70)
print("EDGE ROUTING TEST")
print("="*70)

# Test 1: Tap action should route to perception
state1 = TaskState(
    thread_id="test1",
    transcript="tap on send button",
    intent={
        "action": "tap",
        "recipient": "send button",
        "confidence": 0.95,
        "parameters": {"visual_reference": True}
    }
)
route1 = should_continue_after_intent_parsing(state1)
print(f"\n✅ Test 1: 'tap on send button'")
print(f"   Action: tap")
print(f"   Route: {route1} (expected: perception)")

# Test 2: Send message without UI keywords should skip perception
state2 = TaskState(
    thread_id="test2",
    transcript="send hi to John",
    intent={
        "action": "send_message",
        "recipient": "John",
        "content": "hi",
        "confidence": 0.95,
        "parameters": {}
    }
)
route2 = should_continue_after_intent_parsing(state2)
print(f"\n✅ Test 2: 'send hi to John'")
print(f"   Action: send_message")
print(f"   Route: {route2} (expected: create_plan - deep link)")

# Test 3: Send message with "button" keyword should route to perception
state3 = TaskState(
    thread_id="test3",
    transcript="tap send button",
    intent={
        "action": "send_message",
        "recipient": "send button",
        "confidence": 0.95,
        "parameters": {}
    }
)
route3 = should_continue_after_intent_parsing(state3)
print(f"\n✅ Test 3: 'tap send button' (misclassified as send_message)")
print(f"   Action: send_message")
print(f"   Route: {route3} (expected: perception - has 'button' keyword)")

# Test 4: Open app should skip perception
state4 = TaskState(
    thread_id="test4",
    transcript="open whatsapp",
    intent={
        "action": "open_app",
        "recipient": "WhatsApp",
        "confidence": 0.95,
        "parameters": {}
    }
)
route4 = should_continue_after_intent_parsing(state4)
print(f"\n✅ Test 4: 'open whatsapp'")
print(f"   Action: open_app")
print(f"   Route: {route4} (expected: create_plan)")

print("\n" + "="*70)
