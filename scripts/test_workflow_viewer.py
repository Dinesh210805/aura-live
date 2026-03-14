"""
Quick test script to demonstrate the workflow viewer.

This sends test commands to AURA and shows how to access the workflow viewer.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"


def test_text_command(text: str):
    """Send a text command and return the session info."""
    print(f"\n{'='*60}")
    print(f"Testing: '{text}'")
    print('='*60)
    
    response = requests.post(
        f"{BASE_URL}/tasks/execute",
        json={
            "input_type": "text",
            "text_input": text,
            "config": {"track_workflow": True}
        }
    )
    
    result = response.json()
    print(f"Status: {result.get('status')}")
    print(f"Response: {result.get('spoken_response', 'N/A')[:100]}")
    
    return result


def list_sessions():
    """List all workflow sessions."""
    response = requests.get(f"{BASE_URL}/api/workflow/sessions")
    sessions = response.json()
    
    print(f"\n{'='*60}")
    print(f"Available Sessions: {len(sessions)}")
    print('='*60)
    
    for i, session in enumerate(sessions[:5], 1):
        print(f"{i}. {session['transcript'][:50]} ({session['status']})")
    
    return sessions


def view_workflow(session_id: str):
    """Get workflow details for a session."""
    response = requests.get(f"{BASE_URL}/api/workflow/{session_id}")
    workflow = response.json()
    
    print(f"\n{'='*60}")
    print(f"Workflow Details: {session_id}")
    print('='*60)
    print(f"Transcript: {workflow.get('transcript')}")
    print(f"Status: {workflow.get('status')}")
    print(f"Agents Used: {workflow.get('used_agents', [])}")
    print(f"\nWorkflow Steps:")
    
    for i, step in enumerate(workflow.get('workflow_steps', []), 1):
        exec_time = step.get('execution_time', 0)
        print(f"  {i}. {step['node']} - {step['status']} ({exec_time*1000:.0f}ms)")
    
    return workflow


if __name__ == "__main__":
    print("AURA Workflow Viewer Test Script")
    print("="*60)
    print("\n🌐 Open your browser and navigate to:")
    print(f"   {BASE_URL}/api/workflow/viewer/ui")
    print("\n   This will show you the visual workflow viewer!")
    print("="*60)
    
    # Test different command types
    commands = [
        "open WhatsApp",
        "scroll down",
        "what's on my screen",
    ]
    
    results = []
    for cmd in commands:
        try:
            result = test_text_command(cmd)
            results.append(result)
            time.sleep(1)  # Give the server time to process
        except Exception as e:
            print(f"Error: {e}")
    
    # List all sessions
    time.sleep(1)
    sessions = list_sessions()
    
    # View the first workflow in detail
    if sessions:
        print("\n" + "="*60)
        print("Viewing first workflow in detail...")
        print("="*60)
        view_workflow(sessions[0]['session_id'])
    
    print("\n" + "="*60)
    print("🎉 Test Complete!")
    print("="*60)
    print("\n📊 Now open the workflow viewer in your browser:")
    print(f"   {BASE_URL}/api/workflow/viewer/ui")
    print("\n   Select a session from the dropdown to see the visual flow!")
    print("="*60)
