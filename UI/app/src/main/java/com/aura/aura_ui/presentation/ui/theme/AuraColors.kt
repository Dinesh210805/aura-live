package com.aura.aura_ui.presentation.ui.theme

import androidx.compose.ui.graphics.Color
import com.aura.aura_ui.ui.theme.*

/**
 * AURA Modern Color System - Professional & Cohesive
 * Updated to match the main theme colors for consistency
 */
object AuraColors {
    // Primary brand colors - Modern Navy & Teal
    val PrimaryBlue = AuraPrimary // Rich navy blue - Professional
    val AccentPurple = AuraTertiary // Modern purple - AI/Creative
    val SuccessGreen = AuraSuccess // Forest green - Natural success
    val WarningOrange = AuraWarning // Clean amber - Clear attention
    val ErrorRed = AuraError // Modern red - Clear danger

    // Secondary & Supporting Colors
    val SecondaryTeal = AuraSecondary // Modern teal - Fresh tech
    val InfoBlue = AuraInfo // Bright blue - Information
    val SecondaryGray = AuraNeutral600 // Professional gray

    // Surface & Background Colors
    val SurfaceDark = AuraNeutral900 // Dark surfaces
    val SurfaceLight = AuraSurfaceSecondary // Light surfaces
    val OnSurface = AuraNeutral50 // Text on dark surfaces
    val OnSurfaceVariant = AuraNeutral300 // Secondary text
    val BackgroundOverlay = AuraNeutral950.copy(alpha = 0.85f) // Professional overlay

    // Modern Gradient Collections
    val IdleGradientStart = AuraPrimary
    val IdleGradientEnd = AuraPrimaryLight

    val ListeningGradientStart = AuraSuccess
    val ListeningGradientEnd = AuraSecondary

    val ProcessingGradientStart = AuraWarning
    val ProcessingGradientEnd = AuraInfo

    val ResponseGradientStart = AuraTertiary
    val ResponseGradientEnd = AuraPrimaryLight

    val ErrorGradientStart = AuraError
    val ErrorGradientEnd = AuraErrorLight

    val ConnectingGradientStart = AuraInfo
    val ConnectingGradientEnd = AuraSecondary
}

/**
 * Get modern color based on voice session state
 */
fun getStateColor(state: com.aura.aura_ui.domain.model.VoiceSessionState): Color {
    return when (state) {
        is com.aura.aura_ui.domain.model.VoiceSessionState.Idle -> AuraIdle
        is com.aura.aura_ui.domain.model.VoiceSessionState.Listening -> AuraListening
        is com.aura.aura_ui.domain.model.VoiceSessionState.Processing -> AuraProcessing
        is com.aura.aura_ui.domain.model.VoiceSessionState.Responding -> AuraResponding
        is com.aura.aura_ui.domain.model.VoiceSessionState.Error -> AuraError
        is com.aura.aura_ui.domain.model.VoiceSessionState.Initializing -> AuraConnecting
        is com.aura.aura_ui.domain.model.VoiceSessionState.Connecting -> AuraConnecting
    }
}

/**
 * Get gradient colors for voice session state
 */
fun getStateGradient(state: com.aura.aura_ui.domain.model.VoiceSessionState): List<Color> {
    return when (state) {
        is com.aura.aura_ui.domain.model.VoiceSessionState.Idle -> AuraGradientPrimary
        is com.aura.aura_ui.domain.model.VoiceSessionState.Listening -> AuraGradientSuccess
        is com.aura.aura_ui.domain.model.VoiceSessionState.Processing -> AuraGradientWarning
        is com.aura.aura_ui.domain.model.VoiceSessionState.Responding -> AuraGradientAccent
        is com.aura.aura_ui.domain.model.VoiceSessionState.Error -> AuraGradientError
        is com.aura.aura_ui.domain.model.VoiceSessionState.Initializing -> AuraGradientSecondary
        is com.aura.aura_ui.domain.model.VoiceSessionState.Connecting -> AuraGradientSecondary
    }
}
