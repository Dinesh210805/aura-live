package com.aura.aura_ui.presentation.state

import com.aura.aura_ui.domain.model.VoiceSessionState

/**
 * Data class representing the complete UI state for the AURA voice assistant
 */
data class AssistantUiState(
    // Permissions
    val hasAllPermissions: Boolean = false,
    val missingPermissions: List<String> = emptyList(),
    // Service status
    val isServiceRunning: Boolean = false,
    // Voice session state
    val voiceSessionState: VoiceSessionState = VoiceSessionState.Idle,
    // Loading and error states
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    // Voice session data
    val currentTranscript: String = "",
    val isListening: Boolean = false,
    val currentStep: String = "",
    val responseText: String = "",
    // UI overlay state
    val isOverlayVisible: Boolean = false,
    val overlayPosition: Pair<Float, Float> = Pair(0f, 0f),
)
