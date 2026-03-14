"""
Text-to-Speech (TTS) service using Microsoft Edge-TTS.

Free, high-quality neural voices with no API key required.
Uses same voices as Azure Cognitive Services.
"""

import asyncio
import io
import re
from typing import Optional

import edge_tts
from pydub import AudioSegment

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class TTSService:
    """TTS service using Microsoft Edge-TTS (free, high-quality neural voices)."""

    # Voice mapping: PlayAI voice names -> Edge-TTS voice names
    VOICE_MAP = {
        # Male voices
        "Fritz-PlayAI": "en-US-GuyNeural",
        "Angelo-PlayAI": "en-US-AndrewNeural",
        "Atlas-PlayAI": "en-US-BrianNeural",
        "Basil-PlayAI": "en-GB-RyanNeural",
        "Briggs-PlayAI": "en-US-EricNeural",
        "Calum-PlayAI": "en-US-GuyNeural",
        "Cillian-PlayAI": "en-IE-ConnorNeural",
        "Mikail-PlayAI": "en-US-DavisNeural",
        "Mitch-PlayAI": "en-US-JasonNeural",
        "Thunder-PlayAI": "en-US-TonyNeural",
        "Chip-PlayAI": "en-US-ChristopherNeural",
        "Mason-PlayAI": "en-US-RogerNeural",
        # Female voices
        "Aaliyah-PlayAI": "en-US-JennyNeural",
        "Adelaide-PlayAI": "en-AU-NatashaNeural",
        "Arista-PlayAI": "en-US-AriaNeural",
        "Celeste-PlayAI": "en-US-AriaNeural",
        "Cheyenne-PlayAI": "en-US-SaraNeural",
        "Deedee-PlayAI": "en-US-MichelleNeural",
        "Eleanor-PlayAI": "en-GB-SoniaNeural",
        "Gail-PlayAI": "en-US-JaneNeural",
        "Indigo-PlayAI": "en-US-NancyNeural",
        "Jennifer-PlayAI": "en-US-JennyNeural",
        "Judy-PlayAI": "en-US-AmberNeural",
        "Mamaw-PlayAI": "en-US-AnaNeural",
        "Nia-PlayAI": "en-US-AshleyNeural",
        "Quinn-PlayAI": "en-US-CoraNeural",
        "Ruby-PlayAI": "en-US-EmmaNeural",
    }

    def __init__(self, settings: Settings) -> None:
        """Initialize TTS service with Edge-TTS (no API key needed)."""
        self.settings = settings
        # Default voice: friendly female voice
        self.default_voice = "en-US-AriaNeural"
        logger.info("✅ TTSService initialized with Edge-TTS (free, high-quality)")

    async def speak_async(
        self, text: str, voice: Optional[str] = None, **kwargs
    ) -> Optional[bytes]:
        """
        Convert text to speech, returning WAV bytes.

        Streams MP3 from Edge-TTS then transcodes to WAV/PCM so the Android
        WavAudioPlayer (AudioTrack-based) can play it without modification.

        Args:
            text: Text to convert (max 10,000 characters).
            voice: Voice name (PlayAI or Edge-TTS format). Defaults to settings value.

        Returns:
            WAV audio bytes, or None if TTS fails.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to TTS")
            return None

        text = self._sanitize_for_speech(text)
        if not text:
            return None

        if len(text) > 10000:
            logger.warning(f"Text too long ({len(text)} chars), truncating to 10000")
            text = text[:10000]

        voice = voice or self.settings.default_tts_model
        edge_voice = self.VOICE_MAP.get(voice, voice)
        if not edge_voice.endswith("Neural") and not edge_voice.endswith("Multilingual"):
            logger.warning(
                f"Unknown voice '{voice}', using default {self.default_voice}"
            )
            edge_voice = self.default_voice

        logger.info(f"🎤 TTS: '{text[:50]}...' with voice={edge_voice}")

        try:
            communicate = edge_tts.Communicate(text=text, voice=edge_voice)
            mp3_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buffer.write(chunk["data"])

            mp3_bytes = mp3_buffer.getvalue()
            if not mp3_bytes:
                logger.error("❌ TTS returned empty audio")
                return None

            # Convert MP3 → WAV so the Android WavAudioPlayer (AudioTrack) can play it
            mp3_buffer.seek(0)
            audio = AudioSegment.from_mp3(mp3_buffer)
            wav_buffer = io.BytesIO()
            audio.export(wav_buffer, format="wav")
            wav_bytes = wav_buffer.getvalue()

            logger.info(f"✅ TTS successful: {len(mp3_bytes)} bytes MP3 → {len(wav_bytes)} bytes WAV")
            return wav_bytes

        except Exception as e:
            logger.error(f"❌ TTS failed: {e}")
            return None

    @staticmethod
    def _sanitize_for_speech(text: str) -> str:
        """Strip anything that sounds unnatural when spoken aloud."""
        # Fenced and inline code
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        # Markdown headings and emphasis
        text = re.sub(r'#+\s+', '', text)
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
        # Bullet / numbered list markers
        text = re.sub(r'^\s*[-*\u2022]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        # URLs
        text = re.sub(r'https?://\S+', 'a link', text)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n+', ' ', text).strip()
        return text

    def speak(
        self, text: str, voice: Optional[str] = None, **kwargs
    ) -> Optional[bytes]:
        """
        Sync wrapper around speak_async(). Returns WAV bytes.

        Use speak_async() directly in async contexts (WebSocket handlers) to avoid
        the overhead of spawning a new event loop per call.
        """
        return asyncio.run(self.speak_async(text, voice, **kwargs))
