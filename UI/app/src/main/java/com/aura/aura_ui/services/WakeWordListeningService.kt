package com.aura.aura_ui.services

import android.app.AlarmManager
import android.app.KeyguardManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.aura.aura_ui.MainActivity
import com.aura.aura_ui.R
import com.aura.aura_ui.overlay.AuraOverlayService
import com.aura.aura_ui.voice.ListeningMode
import com.aura.aura_ui.voice.ListeningModeController
import com.aura.aura_ui.voice.StubWakeWordDetector
import com.aura.aura_ui.voice.WakeWordDetector
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * WakeWordListeningService - Background service for always-on wake word detection.
 * 
 * This foreground service runs continuously in the background, listening for the
 * "Hey AURA" wake word. When detected, it triggers the voice assistant overlay.
 * 
 * Key features:
 * - Runs as foreground service with low-priority notification
 * - Uses Picovoice Porcupine for efficient wake word detection
 * - Coordinates with ListeningModeController to avoid audio conflicts
 * - Battery efficient (~1% CPU usage)
 * 
 * Lifecycle:
 * 1. Start via startService() when user enables wake word
 * 2. Runs in PASSIVE mode (wake word detection)
 * 3. On wake word → transition to ACTIVE → show overlay
 * 4. Overlay handles STT, then signals completion
 * 5. Returns to PASSIVE mode
 * 
 * Usage:
 * ```kotlin
 * WakeWordListeningService.start(context)  // Enable wake word
 * WakeWordListeningService.stop(context)   // Disable wake word
 * ```
 */
class WakeWordListeningService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    
    private var wakeWordDetector: WakeWordDetector? = null
    private var listeningModeController: ListeningModeController? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private var isWakeWordEnabled = false
    private var activeModeSince = 0L  // timestamp when mode became ACTIVE, 0 = not active

    companion object {
        private const val TAG = "WakeWordService"
        private const val NOTIFICATION_ID = 2001
        private const val CHANNEL_ID = "aura_wake_word_channel"
        
        const val ACTION_START = "com.aura.aura_ui.START_WAKE_WORD"
        const val ACTION_STOP = "com.aura.aura_ui.STOP_WAKE_WORD"
        const val ACTION_TOGGLE = "com.aura.aura_ui.TOGGLE_WAKE_WORD"
        
        @Volatile
        private var instance: WakeWordListeningService? = null
        
        /**
         * Start the wake word listening service.
         */
        fun start(context: Context) {
            val intent = Intent(context, WakeWordListeningService::class.java).apply {
                action = ACTION_START
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
        
        /**
         * Stop the wake word listening service.
         */
        fun stop(context: Context) {
            val intent = Intent(context, WakeWordListeningService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
        
        /**
         * Toggle the wake word listening service.
         */
        fun toggle(context: Context) {
            val intent = Intent(context, WakeWordListeningService::class.java).apply {
                action = ACTION_TOGGLE
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
        
        /**
         * Check if wake word listening is currently active.
         */
        fun isActive(): Boolean = instance?.isWakeWordEnabled ?: false
        
        /**
         * Get current listening mode.
         */
        fun getCurrentMode(): ListeningMode = 
            instance?.listeningModeController?.currentMode?.value ?: ListeningMode.OFF
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, createNotification(false))
        
        // Initialize components
        listeningModeController = ListeningModeController.getInstance(this)
        setupModeController()
        
        Log.i(TAG, "✨ WakeWordListeningService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "onStartCommand: action=${intent?.action}, isEnabled=$isWakeWordEnabled")
        
        when (intent?.action) {
            ACTION_START -> enableWakeWord()
            ACTION_STOP -> disableWakeWord()
            ACTION_TOGGLE -> {
                if (isWakeWordEnabled) {
                    disableWakeWord()
                } else {
                    enableWakeWord()
                }
            }
            else -> {
                // Default: enable wake word
                enableWakeWord()
            }
        }
        
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        
        disableWakeWord()
        releaseWakeLock()
        serviceScope.cancel()
        instance = null
        
        Log.i(TAG, "WakeWordListeningService destroyed")
    }
    
    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
        
        Log.i(TAG, "⚠️ Task removed (app swiped from recents) - wake word will restart")
        
        // Only restart if wake word was enabled
        if (isWakeWordEnabled) {
            // Restart the service after a short delay
            val restartIntent = Intent(applicationContext, WakeWordListeningService::class.java).apply {
                action = ACTION_START
            }
            
            val pendingIntent = PendingIntent.getService(
                this,
                1,
                restartIntent,
                PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
            )
            
            val alarmManager = getSystemService(Context.ALARM_SERVICE) as AlarmManager
            alarmManager.set(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                android.os.SystemClock.elapsedRealtime() + 1000, // Restart after 1 second
                pendingIntent
            )
        }
        
        // Don't call stopSelf() - let the system restart us
    }

    override fun onLowMemory() {
        super.onLowMemory()
        Log.w(TAG, "Low memory - wake word detection continues")
        // Don't stop wake word on low memory - it's critical functionality
    }
    
    private fun setupModeController() {
        listeningModeController?.setOnModeChanged { oldMode, newMode ->
            Log.i(TAG, "Mode changed: $oldMode → $newMode")
            
            when (newMode) {
                ListeningMode.PASSIVE -> {
                    activeModeSince = 0L
                    startWakeWordDetection()
                }
                ListeningMode.ACTIVE, ListeningMode.HITL -> {
                    activeModeSince = System.currentTimeMillis()
                    // Stop wake word - STT will take over
                    stopWakeWordDetection()
                    // Show overlay and let it handle STT
                    if (oldMode != newMode) showOverlayAndStartSTT()
                }
                ListeningMode.OFF -> {
                    activeModeSince = 0L
                    stopWakeWordDetection()
                }
            }
            
            // Update notification
            updateNotification(newMode == ListeningMode.PASSIVE)
        }
        
        listeningModeController?.setOnWakeWordDetected { keyword ->
            Log.i(TAG, "🔊 Wake word callback triggered: $keyword")
            // The mode change to ACTIVE will trigger overlay show
        }
        
        // Observe mode changes for cleanup
        serviceScope.launch {
            listeningModeController?.currentMode?.collectLatest { mode ->
                when (mode) {
                    ListeningMode.PASSIVE -> {
                        listeningModeController?.markWakeWordStarted()
                    }
                    else -> {
                        listeningModeController?.markWakeWordStopped()
                    }
                }
            }
        }
    }
    
    private fun enableWakeWord() {
        if (isWakeWordEnabled) {
            Log.d(TAG, "Wake word already enabled - ensuring detection is running")
            // Even if enabled, ensure detection is actually running
            ensureWakeWordDetectionRunning()
            return
        }
        
        Log.i(TAG, "🎤 Enabling wake word detection...")
        
        // Initialize detector if needed
        if (wakeWordDetector == null) {
            Log.i(TAG, "Creating wake word detector...")
            wakeWordDetector = WakeWordDetector.create(this)
            
            // Check if we got a real detector or stub
            val detectorType = wakeWordDetector?.javaClass?.simpleName ?: "null"
            Log.i(TAG, "Wake word detector created: $detectorType")
            
            if (wakeWordDetector is StubWakeWordDetector) {
                Log.w(TAG, "⚠️ Using stub detector - wake word will not work! Check Picovoice access key.")
            }
            
            setupWakeWordDetector()
        }
        
        isWakeWordEnabled = true
        acquireWakeLock()
        startWatchdog()

        // Transition to PASSIVE mode (this triggers startWakeWordDetection via callback)
        val currentMode = listeningModeController?.currentMode?.value
        if (currentMode == ListeningMode.PASSIVE) {
            // Already in PASSIVE, manually start detection
            Log.i(TAG, "Already in PASSIVE mode, starting detection directly")
            startWakeWordDetection()
        } else {
            listeningModeController?.transitionToPassive()
        }

        updateNotification(true)
        saveWakeWordEnabled(true)

        Log.i(TAG, "✅ Wake word detection enabled (detector listening: ${wakeWordDetector?.isListening?.value})")
    }
    
    /**
     * Ensures wake word detection is running if it should be.
     * Called when service is already enabled but detection might have stopped.
     */
    private fun ensureWakeWordDetectionRunning() {
        if (wakeWordDetector == null) {
            Log.w(TAG, "⚠️ Wake word detector is null - recreating...")
            wakeWordDetector = WakeWordDetector.create(this)
            val detectorType = wakeWordDetector?.javaClass?.simpleName ?: "null"
            Log.i(TAG, "Wake word detector recreated: $detectorType")
            setupWakeWordDetector()
        }
        
        val isListening = wakeWordDetector?.isListening?.value ?: false
        val currentMode = listeningModeController?.currentMode?.value
        
        Log.d(TAG, "Ensuring wake word running: isListening=$isListening, mode=$currentMode, detector=${wakeWordDetector?.javaClass?.simpleName}")
        
        // Always try to start if in PASSIVE mode - start() will handle the "already listening" case
        if (currentMode == ListeningMode.PASSIVE) {
            Log.i(TAG, "In PASSIVE mode - starting/ensuring wake word detection...")
            startWakeWordDetection()
        } else if (currentMode == ListeningMode.OFF || currentMode == null) {
            Log.i(TAG, "Mode is OFF/null, transitioning to PASSIVE...")
            listeningModeController?.transitionToPassive()
        }
    }
    
    /**
     * Watchdog: every 45 s, if we're stuck in ACTIVE mode (command never completed),
     * force-return to PASSIVE so wake word can fire again.
     */
    private fun startWatchdog() {
        serviceScope.launch {
            while (isActive && isWakeWordEnabled) {
                delay(45_000L)
                val stuck = activeModeSince > 0L &&
                    (System.currentTimeMillis() - activeModeSince) > 40_000L
                if (stuck) {
                    Log.w(TAG, "⚠️ Watchdog: stuck in ACTIVE for >40 s — forcing PASSIVE")
                    listeningModeController?.transitionToPassive()
                    activeModeSince = 0L
                }
            }
        }
    }

    private fun disableWakeWord() {
        if (!isWakeWordEnabled) return
        
        Log.i(TAG, "🔇 Disabling wake word detection...")
        
        isWakeWordEnabled = false
        
        // Transition to OFF mode
        listeningModeController?.transitionToOff()
        
        // Release detector
        wakeWordDetector?.release()
        wakeWordDetector = null
        
        releaseWakeLock()
        updateNotification(false)
        saveWakeWordEnabled(false)
        
        // Stop service when disabled
        stopSelf()
        
        Log.i(TAG, "Wake word detection disabled")
    }
    
    private fun setupWakeWordDetector() {
        wakeWordDetector?.setOnWakeWordDetected { keyword ->
            Log.i(TAG, "🔊 Wake word detected: $keyword")
            
            // Notify mode controller (this stops wake word and triggers ACTIVE mode)
            listeningModeController?.onWakeWordTriggered(keyword)
        }
    }
    
    private fun startWakeWordDetection() {
        if (wakeWordDetector == null) {
            Log.e(TAG, "❌ Cannot start wake word detection - detector is null")
            return
        }
        
        if (wakeWordDetector?.isListening?.value == true) {
            Log.d(TAG, "Wake word detection already running")
            return
        }
        
        Log.i(TAG, "▶️ Starting wake word detection (detector: ${wakeWordDetector?.javaClass?.simpleName})...")
        wakeWordDetector?.start()
        
        // Verify it started
        serviceScope.launch {
            delay(100) // Small delay to allow start to complete
            val isListening = wakeWordDetector?.isListening?.value ?: false
            if (isListening) {
                Log.i(TAG, "✅ Wake word detection started successfully")
            } else {
                Log.e(TAG, "❌ Wake word detection failed to start - check logcat for errors")
            }
        }
    }
    
    private fun stopWakeWordDetection() {
        if (wakeWordDetector?.isListening?.value != true) {
            Log.d(TAG, "Wake word detection not running")
            return
        }
        
        Log.i(TAG, "⏹️ Stopping wake word detection...")
        wakeWordDetector?.stop()
    }
    
    private fun showOverlayAndStartSTT() {
        Log.i(TAG, "🎯 Showing overlay for STT...")
        
        // Check if device is locked - wake word should work on locked device but request unlock
        val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        
        val isDeviceLocked = keyguardManager.isKeyguardLocked
        val isScreenOn = powerManager.isInteractive
        
        Log.i(TAG, "Device state: locked=$isDeviceLocked, screenOn=$isScreenOn")
        
        if (isDeviceLocked) {
            Log.i(TAG, "🔒 Device is locked - requesting unlock first")
            requestUnlockAndShowOverlay()
        } else {
            // Device is unlocked, show overlay directly
            AuraOverlayService.showAndListen(this)
        }
    }
    
    /**
     * Request device unlock before showing the overlay.
     * Uses KeyguardManager to prompt for unlock on lock screen.
     */
    private fun requestUnlockAndShowOverlay() {
        val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        
        // Turn on the screen if it's off
        wakeUpScreen()
        
        val activity = createUnlockActivity()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && activity != null) {
            // Use the dismiss keyguard API for Android O+ when we have an activity
            // This shows the unlock prompt on the lock screen
            keyguardManager.requestDismissKeyguard(
                activity,
                object : KeyguardManager.KeyguardDismissCallback() {
                    override fun onDismissSucceeded() {
                        Log.i(TAG, "🔓 Device unlocked successfully")
                        serviceScope.launch {
                            // Small delay to let the unlock animation complete
                            delay(300)
                            AuraOverlayService.showAndListen(this@WakeWordListeningService)
                        }
                    }
                    
                    override fun onDismissCancelled() {
                        Log.i(TAG, "🔒 Unlock cancelled by user")
                        // Return to passive mode
                        listeningModeController?.transitionToPassive()
                    }
                    
                    override fun onDismissError() {
                        Log.e(TAG, "❌ Error dismissing keyguard")
                        // Return to passive mode
                        listeningModeController?.transitionToPassive()
                    }
                }
            )
        } else {
            // For older Android versions or when no activity reference available,
            // launch an activity that handles unlock
            launchUnlockActivity()
        }
    }
    
    /**
     * Wake up the screen using PowerManager.
     */
    private fun wakeUpScreen() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        
        if (!powerManager.isInteractive) {
            Log.i(TAG, "💡 Waking up screen...")
            
            // Use ACQUIRE_CAUSES_WAKEUP to turn on screen
            @Suppress("DEPRECATION")
            val screenWakeLock = powerManager.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or 
                PowerManager.ACQUIRE_CAUSES_WAKEUP or
                PowerManager.ON_AFTER_RELEASE,
                "aura:screen_wake_lock"
            )
            screenWakeLock.acquire(3000) // 3 seconds to show unlock prompt
            
            // Release after a short delay
            serviceScope.launch {
                delay(3000)
                if (screenWakeLock.isHeld) {
                    screenWakeLock.release()
                }
            }
        }
    }
    
    /**
     * Create a dummy activity reference for keyguard dismiss callback.
     * Note: This is a workaround - in production, you'd want a dedicated unlock activity.
     */
    private fun createUnlockActivity(): android.app.Activity? {
        // For keyguard dismiss, we need an Activity reference
        // Try to get MainActivity if it exists
        return null // Will show on lock screen without specific activity
    }
    
    /**
     * Launch an activity to handle unlock for older Android versions.
     */
    private fun launchUnlockActivity() {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra("UNLOCK_AND_SHOW_OVERLAY", true)
            putExtra("AUTO_START_LISTENING", true)
        }
        startActivity(intent)
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Main channel - DEFAULT importance for Live Alert visibility
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AURA Voice Assistant",
                NotificationManager.IMPORTANCE_DEFAULT  // DEFAULT required for Live Alert
            ).apply {
                description = "AURA voice assistant - Say 'Hey AURA' to activate"
                setShowBadge(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                // Disable sound but keep importance for Live Alert
                setSound(null, null)
                enableVibration(false)
            }
            
            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager?.createNotificationChannel(channel)
        }
    }
    
    private fun createNotification(isListening: Boolean): Notification {
        val toggleIntent = Intent(this, WakeWordListeningService::class.java).apply {
            action = ACTION_TOGGLE
        }
        val togglePendingIntent = PendingIntent.getService(
            this, 0, toggleIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val openIntent = Intent(this, MainActivity::class.java)
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val statusText = if (isListening) {
            "Say \"Hey AURA\" to activate"
        } else {
            "Wake word disabled"
        }
        
        // Build notification optimized for OnePlus Live Alerts / Dynamic Island
        // Key requirements:
        // 1. IMPORTANCE_DEFAULT or higher channel
        // 2. Category that triggers Live Alert (SERVICE, STATUS, or PROGRESS)
        // 3. Ongoing flag for persistent display
        // 4. Colorized appearance
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AURA Assistant")
            .setContentText(statusText)
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setOnlyAlertOnce(true)  // Don't repeatedly alert
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)  // Match channel importance
            .setCategory(NotificationCompat.CATEGORY_STATUS)   // Status category for Live Alert
            .setContentIntent(openPendingIntent)
            .setColorized(true)
            .setColor(0xFF6B4EFF.toInt())  // AURA purple
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(
                R.drawable.ic_mic,
                if (isListening) "Disable" else "Enable",
                togglePendingIntent
            )
            .build()
    }
    
    private fun updateNotification(isListening: Boolean) {
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager?.notify(NOTIFICATION_ID, createNotification(isListening))
    }
    
    private fun acquireWakeLock() {
        if (wakeLock == null) {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "aura:wake_word_lock"
            ).apply {
                setReferenceCounted(false)
            }
        }
        wakeLock?.acquire(30 * 60 * 1000L) // 30 minutes max, reacquired on mode changes
        Log.d(TAG, "Wake lock acquired")
    }
    
    private fun releaseWakeLock() {
        wakeLock?.let { lock ->
            if (lock.isHeld) {
                lock.release()
                Log.d(TAG, "Wake lock released")
            }
        }
    }
    
    private fun saveWakeWordEnabled(enabled: Boolean) {
        val prefs = getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
        prefs.edit().putBoolean("wake_word_enabled", enabled).apply()
    }
}
