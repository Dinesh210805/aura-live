package com.aura.aura_ui.presentation.utils

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.ui.hapticfeedback.HapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalView

/**
 * Professional haptic feedback utility for micro-interactions
 * Provides consistent tactile feedback across the app
 */
object HapticUtils {
    
    /**
     * Perform light haptic feedback for UI interactions
     */
    fun performLightHaptic(view: View) {
        view.performHapticFeedback(
            HapticFeedbackConstants.KEYBOARD_TAP,
            HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING
        )
    }
    
    /**
     * Perform medium haptic feedback for button presses
     */
    fun performMediumHaptic(view: View) {
        view.performHapticFeedback(
            HapticFeedbackConstants.VIRTUAL_KEY,
            HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING
        )
    }
    
    /**
     * Perform heavy haptic feedback for important actions
     */
    fun performHeavyHaptic(view: View) {
        view.performHapticFeedback(
            HapticFeedbackConstants.LONG_PRESS,
            HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING
        )
    }
    
    /**
     * Perform success haptic pattern
     */
    fun performSuccessHaptic(context: Context) {
        val vibrator = getVibrator(context) ?: return
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            vibrator.vibrate(
                VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK)
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(50)
        }
    }
    
    /**
     * Perform error haptic pattern (double vibration)
     */
    fun performErrorHaptic(context: Context) {
        val vibrator = getVibrator(context) ?: return
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val pattern = longArrayOf(0, 100, 100, 100)
            vibrator.vibrate(
                VibrationEffect.createWaveform(pattern, -1)
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(longArrayOf(0, 100, 100, 100), -1)
        }
    }
    
    /**
     * Perform notification haptic
     */
    fun performNotificationHaptic(context: Context) {
        val vibrator = getVibrator(context) ?: return
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            vibrator.vibrate(
                VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK)
            )
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(
                VibrationEffect.createOneShot(100, VibrationEffect.DEFAULT_AMPLITUDE)
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(100)
        }
    }
    
    /**
     * Perform recording start haptic
     */
    fun performRecordingStartHaptic(context: Context) {
        val vibrator = getVibrator(context) ?: return
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(
                VibrationEffect.createOneShot(75, VibrationEffect.DEFAULT_AMPLITUDE)
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(75)
        }
    }
    
    /**
     * Perform recording stop haptic (double tap pattern)
     */
    fun performRecordingStopHaptic(context: Context) {
        val vibrator = getVibrator(context) ?: return
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val pattern = longArrayOf(0, 50, 50, 50)
            vibrator.vibrate(
                VibrationEffect.createWaveform(pattern, -1)
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(longArrayOf(0, 50, 50, 50), -1)
        }
    }
    
    private fun getVibrator(context: Context): Vibrator? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vibratorManager?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }
}

/**
 * Haptic feedback types for AURA interactions
 */
enum class AuraHapticType {
    LIGHT,          // Light tap feedback (voice selection, list items)
    MEDIUM,         // Button press feedback (toggle switches)
    HEAVY,          // Long press feedback
    SELECTION,      // Selection/navigation feedback
    SUCCESS,        // Operation completed successfully
    ERROR,          // Error occurred
    NOTIFICATION,   // New message/event
    RECORDING_START,// Started voice recording
    RECORDING_STOP  // Stopped voice recording
}

/**
 * Extension function for performing haptic feedback in Compose
 */
@Composable
fun rememberHapticFeedback(): (AuraHapticType) -> Unit {
    val view = LocalView.current
    val hapticFeedback = LocalHapticFeedback.current
    
    return { type ->
        when (type) {
            AuraHapticType.LIGHT -> hapticFeedback.performHapticFeedback(HapticFeedbackType.TextHandleMove)
            AuraHapticType.MEDIUM -> HapticUtils.performMediumHaptic(view)
            AuraHapticType.HEAVY -> hapticFeedback.performHapticFeedback(HapticFeedbackType.LongPress)
            AuraHapticType.SELECTION -> HapticUtils.performLightHaptic(view)
            AuraHapticType.SUCCESS -> HapticUtils.performSuccessHaptic(view.context)
            AuraHapticType.ERROR -> HapticUtils.performErrorHaptic(view.context)
            AuraHapticType.NOTIFICATION -> HapticUtils.performNotificationHaptic(view.context)
            AuraHapticType.RECORDING_START -> HapticUtils.performRecordingStartHaptic(view.context)
            AuraHapticType.RECORDING_STOP -> HapticUtils.performRecordingStopHaptic(view.context)
        }
    }
}

/**
 * Simple haptic feedback for common actions
 */
@Composable
fun rememberSimpleHaptic(): () -> Unit {
    val hapticFeedback = LocalHapticFeedback.current
    return {
        hapticFeedback.performHapticFeedback(HapticFeedbackType.LongPress)
    }
}
