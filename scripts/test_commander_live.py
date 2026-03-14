"""
Interactive test script for Commander Agent.
Run this to test intent parsing in real-time.
"""

import time
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.commander import CommanderAgent
from services.llm import LLMService
from config.settings import Settings

# Rate limiting configuration
RATE_LIMIT_DELAY_MS = 100  # Delay between API calls in milliseconds
BATCH_DELAY_MS = 2000  # Delay after every batch of requests

# Test commands covering different action types and edge cases
TEST_COMMANDS = [
    # === Basic App Actions ===
    "open WhatsApp",
    "launch Instagram",
    "start YouTube",
    "open Chrome browser",
    
    # === Communication ===
    "send hi to John",
    "send hello how are you to Sarah",
    "call Mom",
    "call my boss",
    "message Dad saying I'm running late",
    
    # === Navigation & Gestures ===
    "scroll down",
    "scroll up",
    "swipe left",
    "swipe right",
    "go back",
    "press home",
    "go to home screen",
    
    # === Visual References ===
    "tap the blue button",
    "click the settings icon",
    "press the red icon",
    "tap the first item",
    "click the button at the top right",
    "tap the search icon in the bottom",
    "press that button",
    "click this",
    "tap the icon next to settings",
    
    # === Screen Actions ===
    "take a screenshot",
    "capture screen",
    "what is on my screen",
    "describe my screen",
    "what do you see",
    "read the screen",
    
    # === Multi-step Commands ===
    "open WhatsApp and scroll down",
    "launch Instagram then tap the first post",
    "scroll down and click the blue button",
    "open settings, scroll to bottom, and tap about",
    
    # === Edge Cases: Ambiguous ===
    "open",
    "click",
    "do something",
    "help me",
    "what can you do",
    
    # === Edge Cases: Typos & Variations ===
    "opne WhatsApp",
    "scrol down",
    "tak a screenshot",
    "clik the button",
    
    # === Edge Cases: Complex Descriptions ===
    "tap the small blue circular button with a plus sign in the bottom right corner",
    "click on the profile picture of the person who posted the third item from the top",
    
    # === Edge Cases: Multiple Targets ===
    "open WhatsApp or Instagram",
    "scroll down or up",
    
    # === Edge Cases: Conversational ===
    "hey can you open WhatsApp for me please",
    "I want to send a message to John",
    "could you help me take a screenshot",
    "please go back",
    
    # === Edge Cases: Questions ===
    "how do I open WhatsApp",
    "where is the settings button",
    "can you see the blue icon",
    
    # === Edge Cases: Negative/Unclear ===
    "don't open WhatsApp",
    "not that button",
    "something else",
    
    # === Special Characters & Numbers ===
    "open app #1",
    "tap button 3",
    "click the 2nd item",
    "send @John a message",
    
    # === Torch/Flashlight ===
    "turn on torch",
    "turn off flashlight",
    "enable torch light",
    "disable the torch",
    
    # === Long Commands ===
    "I need you to open WhatsApp and then scroll down to find my conversation with John and then tap on it to open the chat",
    
    # === Empty-like ===
    "um",
    "uh",
    "...",
    
    # === Greetings ===
    "hello",
    "hi there",
    "hey",
    "good morning",
]


def automated_test(agent):
    """Run automated tests with predefined commands."""
    # Create output directory
    output_dir = Path(__file__).parent.parent / "test_results"
    output_dir.mkdir(exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"commander_test_{timestamp}.txt"
    json_file = output_dir / f"commander_test_{timestamp}.json"
    
    print("\n" + "=" * 60)
    print("Running Automated Tests with Rate Limiting")
    print("=" * 60)
    print(f"Output: {log_file.name}")
    print(f"Rate limit: {RATE_LIMIT_DELAY_MS}ms between calls")
    print(f"Batch delay: {BATCH_DELAY_MS}ms every 10 commands")
    
    results = []
    total_time = 0
    api_calls = 0
    
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"Commander Agent Test Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        for i, cmd in enumerate(TEST_COMMANDS, 1):
            print(f"\n[{i}/{len(TEST_COMMANDS)}] Testing: '{cmd}'")
            f.write(f"\n[{i}/{len(TEST_COMMANDS)}] Command: {cmd}\n")
            f.write("-" * 80 + "\n")
            
            start = time.perf_counter()
            result = agent.parse_intent(cmd)
            elapsed = (time.perf_counter() - start) * 1000
            total_time += elapsed
            
            # Track if LLM was used (slower = LLM call)
            if elapsed > 100:
                api_calls += 1
            
            # Console output
            print(f"  Action:      {result.action}")
            print(f"  Recipient:   {result.recipient or 'None'}")
            print(f"  Content:     {result.content or 'None'}")
            print(f"  Confidence:  {result.confidence:.2f}")
            print(f"  Time:        {elapsed:.1f}ms", end="")
            
            # File output
            f.write(f"Action:      {result.action}\n")
            f.write(f"Recipient:   {result.recipient or 'None'}\n")
            f.write(f"Content:     {result.content or 'None'}\n")
            f.write(f"Confidence:  {result.confidence:.2f}\n")
            f.write(f"Time:        {elapsed:.1f}ms\n")
            f.write(f"Parameters:  {result.parameters}\n")
            
            if result.parameters.get('visual_reference'):
                print(" 🎨 Visual", end="")
                f.write("Visual Ref:  Yes (requires VLM)\n")
            if result.parameters.get('steps'):
                steps_count = len(result.parameters['steps'])
                print(f" 🔗 Multi-step({steps_count})", end="")
                f.write(f"Multi-step:  Yes ({steps_count} steps)\n")
            print()
            f.write("\n")
            
            results.append({
                'command': cmd,
                'action': result.action,
                'recipient': result.recipient,
                'content': result.content,
                'time': elapsed,
                'confidence': result.confidence,
                'parameters': result.parameters,
                'timestamp': datetime.now().isoformat()
            })
            
            # Rate limiting
            if elapsed > 100:  # LLM call detected
                time.sleep(RATE_LIMIT_DELAY_MS / 1000)
            
            # Batch delay every 10 commands
            if i % 10 == 0 and i < len(TEST_COMMANDS):
                print(f"  ⏸️  Batch delay ({BATCH_DELAY_MS}ms)...")
                f.write(f"[Batch delay: {BATCH_DELAY_MS}ms]\n\n")
                time.sleep(BATCH_DELAY_MS / 1000)
    
        # Summary
        summary = "\n" + "=" * 80 + "\n"
        summary += "Test Summary\n"
        summary += "=" * 80 + "\n"
        summary += f"Total commands:  {len(TEST_COMMANDS)}\n"
        summary += f"API calls (LLM): {api_calls}\n"
        summary += f"Rule-based:      {len(TEST_COMMANDS) - api_calls}\n"
        summary += f"Avg time:        {total_time/len(TEST_COMMANDS):.1f}ms\n"
        summary += f"Total time:      {total_time:.1f}ms\n"
        summary += f"Avg confidence:  {sum(r['confidence'] for r in results)/len(results):.2f}\n"
        
        # Action distribution
        actions = {}
        for r in results:
            actions[r['action']] = actions.get(r['action'], 0) + 1
        
        summary += f"\nAction distribution:\n"
        for action, count in sorted(actions.items(), key=lambda x: -x[1]):
            summary += f"  {action:20s}: {count}\n"
        
        # Confidence analysis
        low_conf = [r for r in results if r['confidence'] < 0.7]
        high_conf = [r for r in results if r['confidence'] >= 0.9]
        
        summary += f"\nConfidence analysis:\n"
        summary += f"  High (≥0.9):     {len(high_conf)} ({len(high_conf)/len(results)*100:.1f}%)\n"
        summary += f"  Low (<0.7):      {len(low_conf)} ({len(low_conf)/len(results)*100:.1f}%)\n"
        
        if low_conf:
            summary += f"\n  Low confidence commands:\n"
            for r in low_conf[:5]:
                summary += f"    • {r['command'][:60]:60s} ({r['confidence']:.2f})\n"
        
        # Performance analysis
        fast = [r for r in results if r['time'] < 50]
        slow = [r for r in results if r['time'] > 500]
        
        summary += f"\nPerformance analysis:\n"
        summary += f"  Fast (<50ms):    {len(fast)} - likely rule-based\n"
        summary += f"  Slow (>500ms):   {len(slow)} - likely LLM\n"
        summary += f"  API efficiency:  {((len(TEST_COMMANDS) - api_calls)/len(TEST_COMMANDS)*100):.1f}% avoided LLM\n"
        
        summary += "=" * 80 + "\n"
        
        # Write summary to file
        f.write(summary)
        
        # Print summary to console
        print(summary)
    
    # Save JSON results
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_commands': len(TEST_COMMANDS),
            'api_calls': api_calls,
            'total_time_ms': total_time,
            'avg_time_ms': total_time/len(TEST_COMMANDS),
            'results': results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to:")
    print(f"   Text: {log_file}")
    print(f"   JSON: {json_file}")


def interactive_test():
    """Interactive testing loop for Commander Agent."""
    print("Initializing Commander Agent...")
    
    try:
        settings = Settings()
        llm = LLMService(settings)
        agent = CommanderAgent(llm)
        print("✅ Commander Agent ready\n")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return
    
    # Ask user for test mode
    print("=" * 60)
    print("Commander Agent Test")
    print("=" * 60)
    print("1. Run automated tests (15 predefined commands)")
    print("2. Interactive mode (manual input)")
    print()
    
    mode = input("Choose mode (1/2) [default=1]: ").strip() or "1"
    
    if mode == "1":
        automated_test(agent)
        return
    
    print("\n" + "=" * 60)
    print("Interactive Mode")
    print("=" * 60)
    print("Type commands to test intent parsing")
    print("Type 'quit' or 'exit' to stop\n")
    
    while True:
        try:
            cmd = input("Command: ").strip()
            
            if not cmd:
                continue
                
            if cmd.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Exiting...")
                break
            
            # Parse intent and measure time
            start = time.perf_counter()
            result = agent.parse_intent(cmd)
            elapsed = (time.perf_counter() - start) * 1000
            
            # Display results
            print(f"\n{'─' * 60}")
            print(f"Action:      {result.action}")
            print(f"Recipient:   {result.recipient or 'None'}")
            print(f"Content:     {result.content or 'None'}")
            print(f"Confidence:  {result.confidence:.2f}")
            print(f"Parameters:  {result.parameters}")
            print(f"Time:        {elapsed:.1f}ms")
            
            if result.parameters.get('visual_reference'):
                print(f"Visual Ref:  ✓ (requires VLM)")
            
            if result.parameters.get('steps'):
                print(f"Multi-step:  ✓ ({len(result.parameters['steps'])} steps)")
            
            print(f"{'─' * 60}\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Exiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    interactive_test()
