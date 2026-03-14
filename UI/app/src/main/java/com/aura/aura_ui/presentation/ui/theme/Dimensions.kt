package com.aura.aura_ui.presentation.ui.theme

import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * AURA Dimensions and spacing values
 */
object AuraDimensions {
    // Floating mic button
    val MicButtonSize = 56.dp
    val MicButtonTouchTarget = 64.dp
    val MicButtonElevation = 8.dp

    // Animations
    val HaloInnerRadius = 30.dp
    val HaloOuterRadius = 60.dp
    val WaveformBarWidth = 2.dp
    val WaveformBarMaxHeight = 20.dp
    val WaveformBarMinHeight = 4.dp

    // Transcription panel
    val TranscriptionMaxWidth = 280.dp
    val TranscriptionPadding = 12.dp
    val TranscriptionCornerRadius = 16.dp

    // Quick settings panel
    val SettingsPanelWidth = 240.dp
    val SettingsPanelHeight = 320.dp
    val SettingsItemHeight = 48.dp

    // Spacing
    val SpaceSmall = 8.dp
    val SpaceMedium = 16.dp
    val SpaceLarge = 24.dp
    val ScreenEdgeMargin = 16.dp

    // Typography
    val TranscriptionTextSize = 14.sp
    val InterimTextSize = 14.sp
    val ErrorTextSize = 12.sp
    val SettingsTitleSize = 16.sp
}

/**
 * Animation constants
 */
object AuraAnimations {
    // State transitions
    const val STATE_TRANSITION_DURATION = 300L
    const val FADE_ANIMATION_DURATION = 200L
    const val SCALE_ANIMATION_DURATION = 150L

    // Continuous animations
    const val BREATHING_CYCLE_DURATION = 2000L
    const val PROCESSING_ROTATION_DURATION = 1500L
    const val PULSE_DURATION = 800L

    // Waveform animation
    const val WAVEFORM_UPDATE_INTERVAL = 33L // ~30 FPS
    const val AMPLITUDE_SMOOTHING_FACTOR = 0.3f

    // Scale factors
    const val IDLE_SCALE_MIN = 1.0f
    const val IDLE_SCALE_MAX = 1.05f
    const val LISTENING_SCALE_MIN = 1.0f
    const val LISTENING_SCALE_MAX = 1.25f
    const val PULSE_SCALE_FACTOR = 0.15f
}
