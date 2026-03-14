"""Test the improved command logger format."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from services.command_logger import CommandLogger

# Create a test logger
logger = CommandLogger(log_dir='logs', execution_id='test_format')

# Log a command
logger.log_command('test command', 'text', 'session123')

# Log an LLM call
logger.log_llm_call(
    prompt='What is 2+2?',
    response='4',
    provider='groq',
    model='llama-3.3-70b',
    token_usage={'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}
)

# Log a VLM call
logger.log_llm_call(
    prompt='Describe this image',
    response='A dog',
    provider='gemini',
    model='gemini-2.5-flash',
    token_usage={'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
    is_vlm=True
)

# Log a gesture with timing
sent = datetime.now()
executed = sent + timedelta(milliseconds=150)
logger.log_gesture(
    gesture_type='tap',
    gesture_data={'x': 100, 'y': 200, 'action': 'tap'},
    result={'success': True, 'strategy': 'websocket'},
    execution_time=0.15,
    sent_at=sent,
    executed_at=executed
)

# Finalize
logger.finalize(status='completed')

# Print log file path
print(f'Log file: {logger.log_file}')
print(f'LLM calls: {logger.llm_call_count}, VLM calls: {logger.vlm_call_count}, Gestures: {logger.gesture_count}')

# Read and print the log
with open(logger.log_file, 'r') as f:
    print('\n--- LOG CONTENT ---')
    print(f.read())
