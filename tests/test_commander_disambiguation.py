"""Quick test for Commander tap vs send_message disambiguation."""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.commander import CommanderAgent
from services.llm import LLMService
from config.settings import get_settings

settings = get_settings()
llm_service = LLMService(settings)
commander = CommanderAgent(llm_service)

test_cases = [
    ("tap on send button", "tap"),
    ("tap on the send button", "tap"),
    ("click the send button", "tap"),
    ("press send button", "tap"),
    ("send message to John", "send_message"),
    ("send hi to John", "send_message"),
    ("send John hello", "send_message"),
]

print("\n" + "="*70)
print("COMMANDER DISAMBIGUATION TEST")
print("="*70)

for transcript, expected_action in test_cases:
    intent = commander.parse_intent(transcript)
    actual_action = intent.action.lower()
    
    status = "✅" if actual_action == expected_action else "❌"
    print(f"\n{status} \"{transcript}\"")
    print(f"   Expected: {expected_action}")
    print(f"   Got:      {actual_action}")
    if intent.recipient:
        print(f"   Recipient: {intent.recipient}")
    if intent.content:
        print(f"   Content: {intent.content}")

print("\n" + "="*70)
