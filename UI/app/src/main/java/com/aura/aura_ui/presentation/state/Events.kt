package com.aura.aura_ui.presentation.state

import com.aura.aura_ui.data.network.TaskResponseDto

/**
 * User interaction events for the assistant UI
 */
sealed class AssistantUiEvent {
    object StartVoiceCapture : AssistantUiEvent()

    object StopVoiceCapture : AssistantUiEvent()

    object CancelVoiceCapture : AssistantUiEvent()

    object ToggleContinuousMode : AssistantUiEvent()

    object ShowOverlay : AssistantUiEvent()

    object HideOverlay : AssistantUiEvent()

    data class UpdateMicPosition(val x: Float, val y: Float) : AssistantUiEvent()

    data class UpdateAmplitude(val amplitude: Float) : AssistantUiEvent()

    object RetryLastCommand : AssistantUiEvent()

    object ClearError : AssistantUiEvent()

    object RequestPermissions : AssistantUiEvent()

    object OpenSettings : AssistantUiEvent()
}

/**
 * System events from backend or audio system
 */
sealed class SystemEvent {
    data class BackendResponseReceived(val response: TaskResponseDto) : SystemEvent()

    data class AudioAmplitudeUpdated(val amplitude: Float) : SystemEvent()

    data class TranscriptUpdated(val transcript: String, val isFinal: Boolean) : SystemEvent()

    data class ErrorOccurred(val error: Throwable) : SystemEvent()

    object AudioCaptureStarted : SystemEvent()

    object AudioCaptureStopped : SystemEvent()

    object BackendConnected : SystemEvent()

    object BackendDisconnected : SystemEvent()
}
