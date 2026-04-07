"""
TTS Response Formatter — server-side text preparation for Android-native TTS.

Instead of synthesising audio server-side (edge-tts + pydub + ffmpeg → WAV bytes),
the server sanitises the text and sends a lightweight ``tts_response`` dict over
WebSocket.  The Android client's ``AuraTTSManager`` (TextToSpeech) handles synthesis
locally, cutting end-to-end latency from ~1.4 s to ~200 ms and eliminating the
ffmpeg/pydub dependency from the production image.

Gemini Live sessions are unaffected — Gemini synthesises audio natively server-side
via the ``/ws/live`` endpoint.
"""

import re
from typing import Optional

# Re-export the voice map so callers don't need to import TTSService just for names.
VOICE_MAP: dict[str, str] = {
    # Male voices (PlayAI name -> Edge-TTS / Android locale hint)
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

DEFAULT_VOICE = "en-US-AriaNeural"
MAX_TTS_CHARS = 10_000


def sanitize_for_speech(text: str) -> str:
    """Strip markdown / code / URLs so the text reads naturally when spoken aloud.

    Identical logic to ``TTSService._sanitize_for_speech`` — centralised here so
    both the Android-TTS path and the edge-tts fallback path share the same
    sanitisation without importing the heavy ``TTSService``.
    """
    # Fenced and inline code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Markdown headings and emphasis
    text = re.sub(r"#+\s+", "", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    # Bullet / numbered list markers
    text = re.sub(r"^\s*[-*\u2022]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # URLs
    text = re.sub(r"https?://\S+", "a link", text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text).strip()
    return text


def resolve_voice(voice: Optional[str]) -> str:
    """Normalise a PlayAI or Edge-TTS voice name to a canonical Edge-TTS voice.

    Falls back to ``DEFAULT_VOICE`` for unknown names so the Android client always
    receives a well-formed IETF language tag it can map to a locale.
    """
    if not voice:
        return DEFAULT_VOICE
    resolved = VOICE_MAP.get(voice, voice)
    # Accept any name that looks like a valid Edge-TTS / BCP-47 tag
    if resolved.endswith("Neural") or resolved.endswith("Multilingual"):
        return resolved
    return DEFAULT_VOICE


def format_tts_response(text: str, voice: Optional[str] = None) -> dict:
    """Build a ``tts_response`` payload ready to be sent over WebSocket.

    The Android client handles this message type in ``AuraTTSManager`` by calling
    ``TextToSpeech.speak()``.  No audio bytes are transmitted.

    Args:
        text:  Raw feedback text (may contain markdown / code blocks).
        voice: Optional voice hint (PlayAI name or Edge-TTS name).

    Returns:
        A dict with keys ``text``, ``voice``, ``format``.
        Returns an empty dict if ``text`` is blank after sanitisation.
    """
    if not text or not text.strip():
        return {}

    clean = sanitize_for_speech(text)
    if not clean:
        return {}

    if len(clean) > MAX_TTS_CHARS:
        clean = clean[:MAX_TTS_CHARS]

    return {
        "text": clean,
        "voice": resolve_voice(voice),
        "format": "tts_text",
    }
