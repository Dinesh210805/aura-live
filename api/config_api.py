"""Configuration endpoints."""

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import get_settings
from services.tts import TTSService
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Initialize TTS service for voice preview
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get or create TTS service instance."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService(settings)
    return _tts_service


# TTS Voice Models
class TTSVoice(BaseModel):
    """TTS Voice option for selection."""
    id: str
    name: str
    description: str
    gender: str
    accent: str
    preview_text: str = "Welcome boss! How can I help you today?"


class TTSVoicesResponse(BaseModel):
    """Response with available TTS voices."""
    voices: List[TTSVoice]
    current_voice: str


class TTSVoiceUpdateRequest(BaseModel):
    """Request to update TTS voice."""
    voice_id: str


class TTSPreviewResponse(BaseModel):
    """Response with voice preview audio."""
    voice_id: str
    audio_base64: str
    audio_format: str = "wav"


# Available TTS voices with friendly names and descriptions
TTS_VOICES = [
    TTSVoice(
        id="en-US-AriaNeural",
        name="Aria",
        description="Friendly & warm female voice",
        gender="female",
        accent="American",
        preview_text="Welcome boss! How can I help you today?"
    ),
    TTSVoice(
        id="en-US-GuyNeural",
        name="Guy",
        description="Professional male voice",
        gender="male",
        accent="American",
        preview_text="Hey there boss! I'm ready to assist you with anything."
    ),
    TTSVoice(
        id="en-US-JennyNeural",
        name="Jenny",
        description="Cheerful & energetic female voice",
        gender="female",
        accent="American",
        preview_text="Hi boss! Let's get things done together!"
    ),
    TTSVoice(
        id="en-US-ChristopherNeural",
        name="Christopher",
        description="Calm & confident male voice",
        gender="male",
        accent="American",
        preview_text="Good to see you boss! What's on the agenda?"
    ),
    TTSVoice(
        id="en-GB-SoniaNeural",
        name="Sonia",
        description="Elegant British female voice",
        gender="female",
        accent="British",
        preview_text="Hello boss! Shall we get started?"
    ),
    TTSVoice(
        id="en-GB-RyanNeural",
        name="Ryan",
        description="Sophisticated British male voice",
        gender="male",
        accent="British",
        preview_text="At your service, boss! How may I assist you?"
    ),
    TTSVoice(
        id="en-AU-NatashaNeural",
        name="Natasha",
        description="Friendly Australian female voice",
        gender="female",
        accent="Australian",
        preview_text="G'day boss! Ready when you are!"
    ),
    TTSVoice(
        id="en-US-EmmaNeural",
        name="Emma",
        description="Clear & articulate female voice",
        gender="female",
        accent="American",
        preview_text="Hello boss! I'm here to make your life easier."
    ),
]


@router.get("/tts/voices")
async def get_tts_voices() -> TTSVoicesResponse:
    """
    Get available TTS voices for selection.
    
    Returns:
        List of available voices with their details.
    """
    try:
        return TTSVoicesResponse(
            voices=TTS_VOICES,
            current_voice=settings.default_tts_model
        )
    except Exception as e:
        logger.error(f"Failed to get TTS voices: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve TTS voices")


@router.post("/tts/voice")
async def update_tts_voice(request: TTSVoiceUpdateRequest) -> Dict[str, Any]:
    """
    Update the selected TTS voice.
    
    Args:
        request: Voice update request with voice_id.
        
    Returns:
        Confirmation of voice update.
    """
    try:
        # Validate voice exists
        valid_voice_ids = [v.id for v in TTS_VOICES]
        if request.voice_id not in valid_voice_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid voice ID. Choose from: {valid_voice_ids}"
            )
        
        # Update settings (runtime only - for persistence, would need env/config file update)
        settings.default_tts_model = request.voice_id
        
        logger.info(f"TTS voice updated to: {request.voice_id}")
        
        return {
            "success": True,
            "voice_id": request.voice_id,
            "message": f"Voice updated to {request.voice_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update TTS voice: {e}")
        raise HTTPException(status_code=500, detail="Failed to update TTS voice")


@router.get("/tts/preview/{voice_id}")
async def preview_tts_voice(voice_id: str) -> TTSPreviewResponse:
    """
    Generate a preview audio sample for a TTS voice.
    
    Args:
        voice_id: The voice ID to preview.
        
    Returns:
        Base64 encoded audio preview.
    """
    try:
        # Find voice config
        voice_config = next((v for v in TTS_VOICES if v.id == voice_id), None)
        if not voice_config:
            raise HTTPException(status_code=404, detail=f"Voice not found: {voice_id}")
        
        # Generate audio preview
        tts_service = get_tts_service()
        audio_bytes = tts_service.speak(voice_config.preview_text, voice=voice_id)
        
        if audio_bytes is None:
            raise HTTPException(status_code=500, detail="Failed to generate voice preview")
        
        # Encode to base64
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        
        logger.info(f"Generated preview for voice: {voice_id}")
        
        return TTSPreviewResponse(
            voice_id=voice_id,
            audio_base64=audio_base64,
            audio_format="wav"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate voice preview: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate voice preview")


@router.get("/config")
async def get_configuration() -> Dict[str, Any]:
    """
    Get current configuration (non-sensitive values only).

    Returns:
        Public configuration information.
    """
    try:
        logger.info("Configuration requested")

        return {
            "llm_provider": settings.default_llm_provider,
            "llm_model": settings.default_llm_model,
            "stt_provider": settings.default_stt_provider,
            "vlm_provider": settings.default_vlm_provider,
            "vlm_model": settings.default_vlm_model,
            "tts_provider": settings.default_tts_provider,
            "server_host": settings.host,
            "server_port": settings.port,
            "log_level": settings.log_level,
            "environment": settings.environment,
            "enable_provider_fallback": settings.enable_provider_fallback,
        }

    except Exception as e:
        logger.error(f"Failed to get configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve configuration")
