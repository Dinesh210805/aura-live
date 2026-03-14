package com.aura.aura_ui.data.network

import com.google.gson.annotations.SerializedName

/**
 * Data Transfer Objects for AURA Backend API
 */

/**
 * Task request to backend
 */
data class TaskRequestDto(
    @SerializedName("audio_data")
    val audioData: String,
    @SerializedName("input_type")
    val inputType: String = "audio",
    @SerializedName("config")
    val config: Map<String, Any>? = null,
    @SerializedName("thread_id")
    val threadId: String? = null,
)

/**
 * Task response from backend
 */
data class TaskResponseDto(
    @SerializedName("task_id")
    val taskId: String,
    @SerializedName("status")
    val status: String,
    @SerializedName("transcript")
    val transcript: String,
    @SerializedName("intent")
    val intent: IntentDto?,
    @SerializedName("spoken_response")
    val spokenResponse: String,
    @SerializedName("execution_time")
    val executionTime: Double,
    @SerializedName("error_message")
    val errorMessage: String?,
    @SerializedName("debug_info")
    val debugInfo: Map<String, Any> = emptyMap(),
)

/**
 * Intent data from backend
 */
data class IntentDto(
    @SerializedName("action")
    val action: String,
    @SerializedName("recipient")
    val recipient: String?,
    @SerializedName("content")
    val content: String?,
    @SerializedName("confidence")
    val confidence: Float?,
)

/**
 * Health response from backend
 */
data class HealthResponseDto(
    @SerializedName("status")
    val status: String,
    @SerializedName("version")
    val version: String,
    @SerializedName("timestamp")
    val timestamp: String,
    @SerializedName("services")
    val services: Map<String, String>,
)

/**
 * Configuration response from backend
 */
data class ConfigurationDto(
    @SerializedName("llm_provider")
    val llmProvider: String,
    @SerializedName("llm_model")
    val llmModel: String,
    @SerializedName("stt_provider")
    val sttProvider: String,
    @SerializedName("vlm_provider")
    val vlmProvider: String,
    @SerializedName("vlm_model")
    val vlmModel: String,
    @SerializedName("tts_provider")
    val ttsProvider: String,
    @SerializedName("server_host")
    val serverHost: String,
    @SerializedName("server_port")
    val serverPort: Int,
    @SerializedName("log_level")
    val logLevel: String,
    @SerializedName("environment")
    val environment: String,
    @SerializedName("enable_provider_fallback")
    val enableProviderFallback: Boolean,
)

// ============================================================================
// TTS Voice Selection DTOs
// ============================================================================

/**
 * TTS Voice option for selection
 */
data class TTSVoiceDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("name")
    val name: String,
    @SerializedName("description")
    val description: String,
    @SerializedName("gender")
    val gender: String,
    @SerializedName("accent")
    val accent: String,
    @SerializedName("preview_text")
    val previewText: String,
)

/**
 * Response with available TTS voices
 */
data class TTSVoicesResponseDto(
    @SerializedName("voices")
    val voices: List<TTSVoiceDto>,
    @SerializedName("current_voice")
    val currentVoice: String,
)

/**
 * Request to update TTS voice
 */
data class TTSVoiceUpdateRequestDto(
    @SerializedName("voice_id")
    val voiceId: String,
)

/**
 * Response with voice preview audio
 */
data class TTSPreviewResponseDto(
    @SerializedName("voice_id")
    val voiceId: String,
    @SerializedName("audio_base64")
    val audioBase64: String,
    @SerializedName("audio_format")
    val audioFormat: String = "wav",
)
