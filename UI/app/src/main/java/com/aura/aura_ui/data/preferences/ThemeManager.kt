package com.aura.aura_ui.data.preferences

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Theme preferences and state management
 */
object ThemeManager {
    // Theme mode enum
    enum class ThemeMode {
        LIGHT,
        DARK,
        SYSTEM,
    }

    // Current theme state
    private val _themeMode = MutableStateFlow(ThemeMode.SYSTEM)
    val themeMode: StateFlow<ThemeMode> = _themeMode.asStateFlow()

    private val _isDarkTheme = MutableStateFlow(false)
    val isDarkTheme: StateFlow<Boolean> = _isDarkTheme.asStateFlow()

    // App preferences
    private val _autoStartOnBoot = MutableStateFlow(true)
    val autoStartOnBoot: StateFlow<Boolean> = _autoStartOnBoot.asStateFlow()

    private val _enableHapticFeedback = MutableStateFlow(true)
    val enableHapticFeedback: StateFlow<Boolean> = _enableHapticFeedback.asStateFlow()

    private val _voiceActivationSensitivity = MutableStateFlow(0.7f)
    val voiceActivationSensitivity: StateFlow<Float> = _voiceActivationSensitivity.asStateFlow()

    private val _responseSpeed = MutableStateFlow(0.5f)
    val responseSpeed: StateFlow<Float> = _responseSpeed.asStateFlow()

    private val _enableNotifications = MutableStateFlow(true)
    val enableNotifications: StateFlow<Boolean> = _enableNotifications.asStateFlow()

    private val _enableAdvancedFeatures = MutableStateFlow(false)
    val enableAdvancedFeatures: StateFlow<Boolean> = _enableAdvancedFeatures.asStateFlow()

    private val _enableDebugMode = MutableStateFlow(false)
    val enableDebugMode: StateFlow<Boolean> = _enableDebugMode.asStateFlow()

    private val _enableBetaFeatures = MutableStateFlow(false)
    val enableBetaFeatures: StateFlow<Boolean> = _enableBetaFeatures.asStateFlow()

    private val _enableScreenCapture = MutableStateFlow(true)
    val enableScreenCapture: StateFlow<Boolean> = _enableScreenCapture.asStateFlow()
    
    // Wake word detection preference
    private val _enableWakeWord = MutableStateFlow(false)
    val enableWakeWord: StateFlow<Boolean> = _enableWakeWord.asStateFlow()
    
    private var appContext: Context? = null

    /**
     * Initialize ThemeManager with saved preferences from SharedPreferences.
     * Call this from Application.onCreate() or MainActivity.
     */
    fun initialize(context: Context) {
        appContext = context.applicationContext
        val prefs = context.getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
        _enableWakeWord.value = prefs.getBoolean("wake_word_enabled", false)
        _enableScreenCapture.value = prefs.getBoolean("screen_capture_enabled", true)
    }

    // Functions to update preferences
    fun updateThemeMode(mode: ThemeMode) {
        _themeMode.value = mode
        updateDarkTheme(mode == ThemeMode.DARK)
    }

    fun updateDarkTheme(isDark: Boolean) {
        _isDarkTheme.value = isDark
    }

    fun updateAutoStartOnBoot(enabled: Boolean) {
        _autoStartOnBoot.value = enabled
    }

    fun updateHapticFeedback(enabled: Boolean) {
        _enableHapticFeedback.value = enabled
    }

    fun updateVoiceActivationSensitivity(sensitivity: Float) {
        _voiceActivationSensitivity.value = sensitivity
    }

    fun updateResponseSpeed(speed: Float) {
        _responseSpeed.value = speed
    }

    fun updateNotifications(enabled: Boolean) {
        _enableNotifications.value = enabled
    }

    fun updateAdvancedFeatures(enabled: Boolean) {
        _enableAdvancedFeatures.value = enabled
    }

    fun updateDebugMode(enabled: Boolean) {
        _enableDebugMode.value = enabled
    }

    fun updateBetaFeatures(enabled: Boolean) {
        _enableBetaFeatures.value = enabled
    }

    fun updateScreenCapture(enabled: Boolean) {
        _enableScreenCapture.value = enabled
        appContext?.getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
            ?.edit()?.putBoolean("screen_capture_enabled", enabled)?.apply()
    }
    
    fun updateWakeWord(enabled: Boolean) {
        _enableWakeWord.value = enabled
    }

    // Mock functions for buttons
    fun exportSettings(): String {
        return "Settings exported successfully!"
    }

    fun importSettings(): String {
        return "Settings imported successfully!"
    }

    fun resetSettings() {
        _themeMode.value = ThemeMode.SYSTEM
        _autoStartOnBoot.value = true
        _enableHapticFeedback.value = true
        _voiceActivationSensitivity.value = 0.7f
        _responseSpeed.value = 0.5f
        _enableNotifications.value = true
        _enableAdvancedFeatures.value = false
        _enableDebugMode.value = false
        _enableBetaFeatures.value = false
        _enableScreenCapture.value = true
        _enableWakeWord.value = false
    }

    fun checkForUpdates(): String {
        return "Checking for updates... No updates available."
    }

    fun viewPrivacyPolicy(): String {
        return "Opening privacy policy..."
    }

    fun contactSupport(): String {
        return "Opening support chat..."
    }
}
