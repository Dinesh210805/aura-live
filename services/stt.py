"""
Speech-to-Text (STT) service wrapper.

This module provi        # Initialize Gemini client (placeholder for future STT support)
        if GEMINI_AVAILABLE and self.settings.gemini_api_key and self.settings.gemini_api_key != "...":
            try:
                self.gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
                logger.debug("Gemini STT client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini STT client: {e}")
        elif not GEMINI_AVAILABLE:
            logger.warning("Gemini STT not available - google-genai package not installed properly")ied interface for converting audio to text
using different STT providers with automatic fallback and error handling.
"""

import io
import struct
from typing import Any, Optional, Union

import groq

try:
    from google import genai
    from google.genai import types as genai_types

    GEMINI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Google GenAI not available: {e}")
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

from config.settings import Settings
from utils.exceptions import ModelProviderError
from utils.logger import get_logger

logger = get_logger(__name__)


class STTService:
    """
    Service class for Speech-to-Text operations.

    Provides a unified interface for audio transcription using different
    STT providers with automatic fallback and error handling.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the STT service with configuration settings.

        Args:
            settings: Application settings containing API keys and model configs.
        """
        self.settings = settings
        self.groq_client: Optional[groq.Groq] = None
        self.gemini_model: Optional[Any] = None

        # Initialize clients based on available API keys
        self._initialize_clients()

        logger.info(
            f"STTService initialized with default provider: {self.settings.default_stt_provider}"
        )

    def _initialize_clients(self) -> None:
        """Initialize STT provider clients based on available API keys."""
        # Initialize Groq client
        if self.settings.groq_api_key and self.settings.groq_api_key != "gsk_...":
            try:
                self.groq_client = groq.Groq(api_key=self.settings.groq_api_key)
                logger.debug("Groq STT client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq STT client: {e}")

    def transcribe(
        self,
        audio_data: Union[bytes, str],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Transcribe audio to text using the specified or default STT provider.

        Args:
            audio_data: Audio data as bytes or file path string.
            provider: Override default provider ('groq' or 'gemini').
            model: Override default model name.
            language: Language code for transcription (e.g., 'en', 'es').
            **kwargs: Additional parameters passed to the STT service.

        Returns:
            Transcribed text from the audio.

        Raises:
            ModelProviderError: If all available providers fail.
        """
        target_provider = provider or self.settings.default_stt_provider
        target_model = model or self.settings.default_stt_model

        logger.info(
            f"Transcribing audio with provider: {target_provider}, model: {target_model}"
        )

        # Try the specified provider first
        try:
            transcript = self._call_provider(
                target_provider, target_model, audio_data, language, **kwargs
            )
            logger.debug(f"Audio transcribed successfully using {target_provider}")
            return transcript
        except ModelProviderError as e:
            logger.warning(f"Primary STT provider {target_provider} failed: {e}")

            # If fallback is enabled, try alternative providers
            if self.settings.enable_provider_fallback:
                # Only include implemented providers for fallback
                available_providers = ["groq"]  # Gemini STT not implemented yet
                fallback_providers = [
                    p for p in available_providers if p != target_provider
                ]

                for fallback_provider in fallback_providers:
                    try:
                        logger.info(f"Attempting STT fallback to {fallback_provider}")
                        transcript = self._call_provider(
                            fallback_provider,
                            target_model,
                            audio_data,
                            language,
                            **kwargs,
                        )
                        logger.info(f"STT fallback to {fallback_provider} successful")
                        return transcript
                    except ModelProviderError as fallback_error:
                        logger.warning(
                            f"STT fallback provider {fallback_provider} failed: {fallback_error}"
                        )
                        continue

            # If all providers fail, raise the original error
            raise e

    async def transcribe_streaming(
        self,
        audio_data: bytes,
        is_final: bool = False,
        language: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Transcribe streaming audio data with support for partial and final results.

        This method is optimized for real-time streaming scenarios where audio
        comes in chunks and we need both partial and final transcripts.

        Whisper (Groq) supports automatic language detection for:
        - English (en), Tamil (ta), Hindi (hi), Spanish (es), French (fr), German (de)
        - Japanese (ja), Korean (ko), Chinese (zh), Arabic (ar), Russian (ru)
        - And 90+ other languages

        Args:
            audio_data: Raw audio bytes to transcribe.
            is_final: Whether this is the final audio chunk (for better accuracy).
            language: Optional language code (e.g., 'en', 'ta', 'hi'). If None, auto-detects.
            provider: Override the default STT provider.
            model: Override the default STT model.
            **kwargs: Additional provider-specific options.

        Returns:
            Transcribed text from the audio chunk.

        Raises:
            ModelProviderError: If transcription fails.
        """
        target_provider = provider or self.settings.default_stt_provider
        target_model = model or self.settings.default_stt_model

        # Use default language from settings if not provided
        effective_language = language or self.settings.default_stt_language

        if effective_language:
            logger.debug(
                f"Streaming STT with provider: {target_provider}, language: {effective_language}, is_final: {is_final}, size: {len(audio_data)} bytes"
            )
        else:
            logger.debug(
                f"Streaming STT with provider: {target_provider}, auto-detect language, is_final: {is_final}, size: {len(audio_data)} bytes"
            )

        # For streaming, we use the regular transcribe method
        # but with optimizations for real-time processing at the service level
        try:
            # Filter out streaming-specific parameters that APIs don't understand
            # Keep only standard transcription parameters
            api_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k not in ["streaming", "is_final", "enable_partial_results"]
            }

            # Call the regular transcription method without streaming parameters
            transcript = self._call_provider(
                target_provider,
                target_model,
                audio_data,
                effective_language,
                **api_kwargs,
            )

            if transcript and len(transcript.strip()) > 0:
                logger.debug(
                    f"Streaming STT result: '{transcript[:50]}...' (final: {is_final})"
                )
                return transcript.strip()
            else:
                return ""

        except ModelProviderError as e:
            logger.warning(f"Streaming STT failed with {target_provider}: {e}")

            # For streaming, we're more lenient with errors and return empty string
            # rather than failing completely, unless it's the final chunk
            # For final chunks, try fallback if available
            if is_final:
                # For final chunks, try fallback if available
                if self.settings.enable_provider_fallback:
                    # Only include implemented providers for fallback
                    available_providers = ["groq"]  # Gemini STT not implemented yet
                    fallback_providers = [
                        p for p in available_providers if p != target_provider
                    ]

                    for fallback_provider in fallback_providers:
                        try:
                            logger.info(
                                f"Attempting streaming STT fallback to {fallback_provider}"
                            )
                            # Use the same filtered kwargs for fallback
                            transcript = self._call_provider(
                                fallback_provider,
                                target_model,
                                audio_data,
                                effective_language,
                                **api_kwargs,
                            )
                            if transcript:
                                logger.info(
                                    f"Streaming STT fallback to {fallback_provider} successful"
                                )
                                return transcript.strip()
                        except ModelProviderError:
                            continue

                # If final transcription fails completely, raise error
                raise e
            else:
                # For partial results, just return empty string and continue
                return ""

    def _call_provider(
        self,
        provider: str,
        model: str,
        audio_data: Union[bytes, str],
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Call a specific STT provider with error handling.

        Args:
            provider: Provider name ('groq' or 'gemini').
            model: Model name to use.
            audio_data: Audio data to transcribe.
            language: Language code for transcription.
            **kwargs: Additional parameters.

        Returns:
            Transcribed text.

        Raises:
            ModelProviderError: If the provider call fails.
        """
        try:
            if provider == "groq":
                return self._call_groq(model, audio_data, language, **kwargs)
            elif provider == "gemini":
                return self._call_gemini(model, audio_data, language, **kwargs)
            else:
                raise ModelProviderError(
                    f"Unsupported STT provider: {provider}",
                    provider=provider,
                    error_code="UNSUPPORTED_PROVIDER",
                )
        except Exception as e:
            if isinstance(e, ModelProviderError):
                raise e

            raise ModelProviderError(
                f"STT provider {provider} failed: {str(e)}",
                provider=provider,
                model=model,
                error_code="PROVIDER_CALL_FAILED",
                context={"original_error": str(e)},
            )

    def _convert_pcm_to_wav(
        self,
        pcm_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """
        Convert raw PCM audio data to WAV format.

        Args:
            pcm_data: Raw PCM audio bytes
            sample_rate: Audio sample rate (default: 16kHz)
            channels: Number of audio channels (default: 1 for mono)
            sample_width: Bytes per sample (default: 2 for 16-bit)

        Returns:
            WAV formatted audio bytes
        """
        # Create WAV file in memory
        wav_buffer = io.BytesIO()

        # Write WAV header
        # RIFF chunk descriptor
        wav_buffer.write(b"RIFF")
        wav_buffer.write(struct.pack("<I", 36 + len(pcm_data)))  # File size - 8
        wav_buffer.write(b"WAVE")

        # fmt sub-chunk
        wav_buffer.write(b"fmt ")
        wav_buffer.write(struct.pack("<I", 16))  # Subchunk1Size (16 for PCM)
        wav_buffer.write(struct.pack("<H", 1))  # AudioFormat (1 for PCM)
        wav_buffer.write(struct.pack("<H", channels))  # NumChannels
        wav_buffer.write(struct.pack("<I", sample_rate))  # SampleRate
        wav_buffer.write(
            struct.pack("<I", sample_rate * channels * sample_width)
        )  # ByteRate
        wav_buffer.write(struct.pack("<H", channels * sample_width))  # BlockAlign
        wav_buffer.write(struct.pack("<H", sample_width * 8))  # BitsPerSample

        # data sub-chunk
        wav_buffer.write(b"data")
        wav_buffer.write(struct.pack("<I", len(pcm_data)))  # Subchunk2Size
        wav_buffer.write(pcm_data)

        # Get WAV bytes
        wav_bytes = wav_buffer.getvalue()
        wav_buffer.close()

        logger.debug(
            f"Converted PCM ({len(pcm_data)} bytes) to WAV ({len(wav_bytes)} bytes)"
        )
        return wav_bytes

    def _call_groq(
        self,
        model: str,
        audio_data: Union[bytes, str],
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Call Groq STT provider (Whisper).

        Args:
            model: Groq STT model name.
            audio_data: Audio data or file path.
            language: Language code (e.g., 'en', 'ta', 'hi'). If None, Whisper auto-detects.
            **kwargs: Additional parameters.

        Returns:
            Transcribed text.

        Raises:
            ModelProviderError: If Groq STT call fails.
        """
        if not self.groq_client:
            raise ModelProviderError(
                "Groq STT client not initialized. Check API key configuration.",
                provider="groq",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        try:
            # Prepare transcription parameters
            transcription_params = {"model": model}

            # Language handling: If no language specified, Whisper will auto-detect
            # Supported languages: en, ta, hi, es, fr, de, ja, ko, zh, etc.
            if language:
                # Normalize language code (handle both 'en' and 'en-US' formats)
                lang_code = language.lower().split("-")[0]
                transcription_params["language"] = lang_code
                logger.debug(f"Using explicit language: {lang_code}")
            else:
                # Let Whisper auto-detect language (works for Tamil, English, Hindi, etc.)
                logger.debug("Using automatic language detection")

            # Filter out any non-standard parameters that Groq API doesn't understand
            allowed_groq_params = {"response_format", "prompt", "temperature"}
            filtered_kwargs = {
                k: v for k, v in kwargs.items() if k in allowed_groq_params
            }
            transcription_params.update(filtered_kwargs)

            # Handle different audio data types
            if isinstance(audio_data, str):
                # Assume it's a file path
                with open(audio_data, "rb") as audio_file:
                    response = self.groq_client.audio.transcriptions.create(
                        file=audio_file, **transcription_params
                    )
            else:
                # Check minimum audio size
                if len(audio_data) < 100:
                    logger.warning(
                        f"Audio data too short ({len(audio_data)} bytes), skipping transcription"
                    )
                    return ""

                # Detect audio format by checking magic bytes
                is_webm = audio_data[:4] == b"\x1a\x45\xdf\xa3"  # WebM/EBML signature
                is_wav = audio_data[:4] == b"RIFF"
                audio_data[:8] == b"OpusHead"

                if is_webm:
                    logger.debug(f"Detected WebM format ({len(audio_data)} bytes)")
                    # Send WebM directly - Groq Whisper supports it
                    response = self.groq_client.audio.transcriptions.create(
                        file=("audio.webm", audio_data), **transcription_params
                    )
                elif is_wav:
                    logger.debug(f"Detected WAV format ({len(audio_data)} bytes)")
                    response = self.groq_client.audio.transcriptions.create(
                        file=("audio.wav", audio_data), **transcription_params
                    )
                else:
                    # Assume raw PCM from Android
                    logger.debug(f"Assuming PCM format ({len(audio_data)} bytes)")
                    # Convert raw PCM bytes to WAV format
                    # Android sends 16-bit PCM mono at 16kHz
                    wav_data = self._convert_pcm_to_wav(
                        pcm_data=audio_data,
                        sample_rate=16000,
                        channels=1,
                        sample_width=2,
                    )

                    response = self.groq_client.audio.transcriptions.create(
                        file=("audio.wav", wav_data), **transcription_params
                    )

            transcript_text = response.text.strip()

            # Log detected/used language if available in response
            if hasattr(response, "language"):
                logger.info(f"STT transcribed in language: {response.language}")

            logger.debug(f"Transcription result: '{transcript_text[:100]}...'")
            return transcript_text

        except Exception as e:
            raise ModelProviderError(
                f"Groq STT API call failed: {str(e)}",
                provider="groq",
                model=model,
                error_code="API_CALL_FAILED",
                context={"original_error": str(e)},
            )
