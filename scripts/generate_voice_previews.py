"""Generate TTS voice preview files for the Android app."""

import asyncio
import io
import os

import edge_tts
from pydub import AudioSegment

VOICES = [
    ("en-US-AriaNeural", "Welcome boss! How can I help you today?"),
    ("en-US-GuyNeural", "Hey there boss! I'm ready to assist you with anything."),
    ("en-US-JennyNeural", "Hi boss! Let's get things done together!"),
    ("en-US-ChristopherNeural", "Good to see you boss! What's on the agenda?"),
    ("en-GB-SoniaNeural", "Hello boss! Shall we get started?"),
    ("en-GB-RyanNeural", "At your service, boss! How may I assist you?"),
    ("en-AU-NatashaNeural", "G'day boss! Ready when you are!"),
    ("en-US-EmmaNeural", "Hello boss! I'm here to make your life easier."),
]


async def generate_audio(voice_id: str, text: str) -> AudioSegment:
    """Generate TTS audio using Edge-TTS."""
    communicate = edge_tts.Communicate(text=text, voice=voice_id)
    audio_buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])
    mp3_bytes = audio_buffer.getvalue()
    mp3_buffer = io.BytesIO(mp3_bytes)
    return AudioSegment.from_mp3(mp3_buffer)


def main():
    """Generate all voice preview files."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    output_dir = os.path.join(project_root, "UI", "app", "src", "main", "res", "raw")
    
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    generated = 0
    skipped = 0
    failed = 0
    
    for voice_id, text in VOICES:
        # Convert voice ID to valid Android resource name (lowercase, underscores)
        name = voice_id.replace("-", "_").lower()
        filename = f"voice_preview_{name}.wav"
        filepath = os.path.join(output_dir, filename)
        
        # Skip if already exists
        if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            print(f"Skipping {voice_id} (already exists)")
            skipped += 1
            continue
        
        print(f"Generating {voice_id}...")
        try:
            audio = asyncio.run(generate_audio(voice_id, text))
            audio.export(filepath, format="wav")
            print(f"  Saved: {filename} ({os.path.getsize(filepath)} bytes)")
            generated += 1
        except Exception as e:
            print(f"  Failed: {e}")
            failed += 1
    
    print(f"\nDone! Generated: {generated}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
