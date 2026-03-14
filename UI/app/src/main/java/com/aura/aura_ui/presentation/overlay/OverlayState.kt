package com.aura.aura_ui.presentation.overlay

/**
 * Represents the state of the overlay assistant
 */
sealed class OverlayState {
    data object Idle : OverlayState()

    data object Listening : OverlayState()

    data object Processing : OverlayState()

    data object Speaking : OverlayState()

    data object Error : OverlayState()
}
