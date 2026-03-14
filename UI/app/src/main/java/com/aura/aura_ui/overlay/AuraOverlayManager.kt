package com.aura.aura_ui.overlay

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * AuraOverlayManager - Singleton manager for AURA overlay operations.
 * 
 * Provides a unified API for managing the overlay service lifecycle,
 * checking permissions, and handling show/hide operations.
 * 
 * Usage:
 * ```kotlin
 * // Initialize in Application.onCreate()
 * AuraOverlayManager.initialize(context)
 * 
 * // Show overlay
 * AuraOverlayManager.show()
 * 
 * // Hide overlay
 * AuraOverlayManager.hide()
 * 
 * // Toggle overlay
 * AuraOverlayManager.toggle()
 * 
 * // Observe visibility state
 * AuraOverlayManager.isVisible.collect { visible -> ... }
 * ```
 */
object AuraOverlayManager {

    private const val TAG = "AuraOverlayManager"

    private var appContext: Context? = null

    // Observable state
    private val _isVisible = MutableStateFlow(false)
    val isVisible: StateFlow<Boolean> = _isVisible.asStateFlow()

    private val _hasPermission = MutableStateFlow(false)
    val hasPermission: StateFlow<Boolean> = _hasPermission.asStateFlow()

    /**
     * Initialize the manager with application context.
     * Call this in Application.onCreate()
     */
    fun initialize(context: Context) {
        appContext = context.applicationContext
        checkPermission()
        Log.i(TAG, "AuraOverlayManager initialized")
    }

    /**
     * Check if overlay permission is granted
     */
    fun checkPermission(): Boolean {
        val context = appContext ?: return false
        val hasPermission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(context)
        } else {
            true
        }
        _hasPermission.value = hasPermission
        return hasPermission
    }

    /**
     * Request overlay permission by opening system settings
     */
    fun requestPermission(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${context.packageName}")
            ).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            Log.i(TAG, "Opened overlay permission settings")
        }
    }

    /**
     * Show the overlay
     */
    fun show(): Boolean {
        val context = appContext ?: run {
            Log.e(TAG, "Manager not initialized")
            return false
        }

        if (!checkPermission()) {
            Log.w(TAG, "Cannot show overlay - permission not granted")
            return false
        }

        AuraOverlayService.show(context)
        _isVisible.value = true
        Log.i(TAG, "Overlay show requested")
        return true
    }

    /**
     * Hide the overlay
     */
    fun hide() {
        val context = appContext ?: run {
            Log.e(TAG, "Manager not initialized")
            return
        }

        AuraOverlayService.hide(context)
        _isVisible.value = false
        Log.i(TAG, "Overlay hide requested")
    }

    /**
     * Toggle overlay visibility
     */
    fun toggle(): Boolean {
        val context = appContext ?: run {
            Log.e(TAG, "Manager not initialized")
            return false
        }

        if (!checkPermission()) {
            Log.w(TAG, "Cannot toggle overlay - permission not granted")
            return false
        }

        AuraOverlayService.toggle(context)
        _isVisible.value = !_isVisible.value
        Log.i(TAG, "Overlay toggled, now visible: ${_isVisible.value}")
        return true
    }

    /**
     * Update visibility state (called by service)
     */
    internal fun updateVisibility(visible: Boolean) {
        _isVisible.value = visible
    }

    /**
     * Check if wake word detection is available
     * (Placeholder for future implementation)
     */
    fun isWakeWordAvailable(): Boolean {
        // TODO: Implement wake word detection check
        // This will return true when wake word detection is implemented
        return false
    }

    /**
     * Enable wake word detection
     * (Placeholder for future implementation)
     */
    fun enableWakeWord(enabled: Boolean) {
        // TODO: Implement wake word enable/disable
        Log.d(TAG, "Wake word detection ${if (enabled) "enabled" else "disabled"} (not yet implemented)")
    }
}
