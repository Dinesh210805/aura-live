"""
Audio utilities for processing and validating audio data.
"""

import io
import logging
import wave

logger = logging.getLogger(__name__)


def add_wav_header(
    pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2
) -> bytes:
    """
    Add WAV header to raw PCM audio data.

    Args:
        pcm_data: Raw PCM audio bytes
        sample_rate: Sample rate in Hz (default: 16000)
        channels: Number of audio channels (default: 1 for mono)
        sample_width: Bytes per sample (default: 2 for 16-bit)

    Returns:
        WAV formatted audio bytes with proper header
    """
    try:
        # Create WAV file in memory
        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

        # Get the WAV bytes
        wav_data = wav_buffer.getvalue()
        wav_buffer.close()

        logger.debug(
            f"Added WAV header: {len(pcm_data)} PCM bytes → {len(wav_data)} WAV bytes"
        )
        return wav_data

    except Exception as e:
        logger.error(f"Failed to add WAV header: {e}")
        return pcm_data  # Return original data as fallback


def validate_audio_format(audio_data: bytes) -> tuple[bool, str]:
    """
    Validate if audio data has proper WAV format.

    Args:
        audio_data: Audio bytes to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check minimum size
        if len(audio_data) < 44:  # WAV header is 44 bytes
            return (
                False,
                f"Audio data too small: {len(audio_data)} bytes (minimum 44 bytes for WAV)",
            )

        # Check WAV header
        if not audio_data.startswith(b"RIFF"):
            return False, "Missing RIFF header - not a valid WAV file"

        # Check WAVE format
        if b"WAVE" not in audio_data[:12]:
            return False, "Missing WAVE format identifier"

        # Try to parse with wave module
        wav_buffer = io.BytesIO(audio_data)
        try:
            with wave.open(wav_buffer, "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                # Validate parameters
                if channels not in [1, 2]:
                    return False, f"Invalid channel count: {channels} (must be 1 or 2)"

                if sample_width not in [1, 2, 4]:
                    return False, f"Invalid sample width: {sample_width} bytes"

                if framerate < 8000 or framerate > 48000:
                    return (
                        False,
                        f"Invalid sample rate: {framerate} Hz (must be 8000-48000)",
                    )

                if n_frames == 0:
                    return False, "Audio file contains no frames"

                duration = n_frames / framerate
                if duration < 0.1:
                    return False, f"Audio too short: {duration:.2f}s (minimum 0.1s)"

                logger.debug(
                    f"✅ Valid WAV: {channels}ch, {sample_width * 8}bit, {framerate}Hz, {duration:.2f}s"
                )
                return True, ""

        except wave.Error as e:
            return False, f"Invalid WAV format: {e}"
        finally:
            wav_buffer.close()

    except Exception as e:
        return False, f"Validation error: {e}"


def ensure_wav_format(
    audio_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """
    Ensure audio data is in proper WAV format.
    If not, add WAV header to raw PCM data.

    Args:
        audio_data: Audio bytes (WAV or raw PCM)
        sample_rate: Sample rate if converting from PCM
        channels: Channel count if converting from PCM
        sample_width: Sample width if converting from PCM

    Returns:
        Audio data guaranteed to be in WAV format
    """
    is_valid, error = validate_audio_format(audio_data)

    if is_valid:
        logger.debug("Audio already in valid WAV format")
        return audio_data

    logger.info(f"Converting raw PCM to WAV: {error}")
    return add_wav_header(audio_data, sample_rate, channels, sample_width)
