package com.aura.aura_ui.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.WindowManager
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.aura.aura_ui.MainActivity
import com.aura.aura_ui.R
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.conversation.ConversationViewModel
import com.aura.aura_ui.presentation.screens.VoiceAssistantCallbacks
import com.aura.aura_ui.presentation.screens.VoiceAssistantOverlay
import com.aura.aura_ui.presentation.screens.VoiceAssistantState
import com.aura.aura_ui.ui.theme.AuraUITheme
import com.aura.aura_ui.voice.ListeningModeController
import com.aura.aura_ui.voice.VoiceCaptureController
import com.aura.aura_ui.functiongemma.FunctionGemmaManager
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import android.animation.ValueAnimator
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.View
import android.view.animation.AccelerateInterpolator
import android.view.animation.DecelerateInterpolator
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.ui.graphics.Brush
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * AuraOverlayService - System-wide overlay service for AURA voice assistant.
 * 
 * This service displays the voice assistant UI as a system overlay,
 * allowing users to interact with AURA while using other apps.
 * 
 * Key features:
 * - True system overlay (TYPE_APPLICATION_OVERLAY)
 * - Foreground service with persistent notification
 * - Full Compose UI support via ComposeView
 * - Proper lifecycle management for ViewModel
 * - WebSocket connection via VoiceCaptureController
 * - Touch handling for interactive overlay
 * - Back button handling for dismissal
 * - Wake lock management for voice capture
 * 
 * Edge cases handled:
 * - Permission denied: Falls back gracefully
 * - Service killed: Restarts via START_STICKY
 * - Configuration changes: Properly handled
 * - Memory pressure: Cleanup on low memory
 * - Screen rotation: Window params auto-update
 * - Multiple show/hide calls: Singleton pattern
 */
class AuraOverlayService : Service(), LifecycleOwner, SavedStateRegistryOwner {

    @EntryPoint
    @InstallIn(SingletonComponent::class)
    interface FunctionGemmaEntryPoint {
        fun functionGemmaManager(): FunctionGemmaManager
    }

    companion object {
        private const val TAG = "AuraOverlayService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "aura_overlay_channel"
        private const val CHANNEL_ID_WORKING = "aura_working_channel" // For Live Alert / Dynamic Island
        private const val ACTION_SHOW = "com.aura.SHOW_OVERLAY"
        private const val ACTION_SHOW_AND_LISTEN = "com.aura.SHOW_AND_LISTEN" // For wake word trigger
        private const val ACTION_HIDE = "com.aura.HIDE_OVERLAY"
        private const val ACTION_TOGGLE = "com.aura.TOGGLE_OVERLAY"
        private const val ACTION_MINIMIZE = "com.aura.MINIMIZE_OVERLAY"
        private const val ACTION_RESTORE = "com.aura.RESTORE_OVERLAY"
        private const val ACTION_CANCEL_TASK = "com.aura.CANCEL_TASK"

        private var instance: AuraOverlayService? = null

        /**
         * Check if overlay permission is granted
         */
        fun canDrawOverlays(context: Context): Boolean {
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Settings.canDrawOverlays(context)
            } else {
                true
            }
        }

        /**
         * Show the overlay
         */
        fun show(context: Context) {
            if (!canDrawOverlays(context)) {
                Log.w(TAG, "Cannot show overlay - permission not granted")
                return
            }
            val intent = Intent(context, AuraOverlayService::class.java).apply {
                action = ACTION_SHOW
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
        
        /**
         * Show the overlay and immediately start listening.
         * Called by wake word detection to auto-start voice capture.
         */
        fun showAndListen(context: Context) {
            if (!canDrawOverlays(context)) {
                Log.w(TAG, "Cannot show overlay - permission not granted")
                return
            }
            val intent = Intent(context, AuraOverlayService::class.java).apply {
                action = ACTION_SHOW_AND_LISTEN
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        /**
         * Hide the overlay
         */
        fun hide(context: Context) {
            val intent = Intent(context, AuraOverlayService::class.java).apply {
                action = ACTION_HIDE
            }
            context.startService(intent)
        }

        /**
         * Minimize overlay during automation - hide UI but keep service running.
         * Shows "executing command" notification.
         */
        fun minimize(context: Context) {
            instance?.minimizeOverlay(showExecutingNotification = true)
        }
        
        /**
         * Temporarily hide overlay without showing "executing" notification.
         * Used when opening settings or other non-command activities.
         */
        fun temporarilyHide(context: Context) {
            instance?.minimizeOverlay(showExecutingNotification = false)
        }

        /**
         * Restore overlay after automation completes
         */
        fun restore(context: Context) {
            instance?.restoreOverlay()
        }

        /**
         * Toggle the overlay visibility
         */
        fun toggle(context: Context) {
            val intent = Intent(context, AuraOverlayService::class.java).apply {
                action = ACTION_TOGGLE
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        /**
         * Check if overlay is currently visible
         */
        fun isVisible(): Boolean = instance?._isOverlayVisible?.value ?: false
        
        /**
         * Check if overlay is minimized
         */
        fun isMinimized(): Boolean = instance?._isMinimized?.value ?: false

        /**
         * Get the service instance
         */
        fun getInstance(): AuraOverlayService? = instance
    }

    // Lifecycle management for Compose
    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedStateRegistryController = SavedStateRegistryController.create(this)

    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val savedStateRegistry: SavedStateRegistry 
        get() = savedStateRegistryController.savedStateRegistry

    // Service components
    private var windowManager: WindowManager? = null
    private var overlayView: ComposeView? = null
    // Live Alert pill animation state (replaces floating toast overlay)
    private var _workingVerb: String = "Working"
    private var _workingStepCurrent: Int = 0
    private var _workingStepTotal: Int = 0
    private var _workingGoal: String = ""
    private var _taskStartTime: Long = 0L
    private var _dotAnimJob: Job? = null
    // Edge glow overlay (automation in-progress aura ring)
    private var edgeGlowView: View? = null

    private var wakeLock: PowerManager.WakeLock? = null

    // State management
    private val _isOverlayVisible = MutableStateFlow(false)
    val isOverlayVisible: StateFlow<Boolean> = _isOverlayVisible.asStateFlow()
    
    private val _isMinimized = MutableStateFlow(false)
    val isMinimized: StateFlow<Boolean> = _isMinimized.asStateFlow()

    // Coroutine scope for service
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var connectionJob: Job? = null

    // Voice capture controller (always connected for device control / gesture execution)
    private var voiceCaptureController: VoiceCaptureController? = null

    // Gemini Live controller — active when use_gemini_live preference is true.
    // Handles bidirectional audio with Gemini Live; VoiceCaptureController stays
    // connected in parallel to keep the device control pipe (gestures, UI tree) alive.
    private var geminiLiveController: com.aura.aura_ui.voice.GeminiLiveController? = null

    /** True when the Gemini Live audio layer is active. */
    private val useGeminiLive: Boolean
        get() {
            val prefs = getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
            return prefs.getBoolean("use_gemini_live", false)
        }

    // ViewModel for conversation state (service-scoped)
    private val conversationViewModel = ConversationViewModel()

    // UI State (observable)
    private val audioAmplitude = mutableFloatStateOf(0f)

    // Server URL (will be discovered)
    private var serverUrl: String = "http://107.78.51.4:8000"

    override fun onCreate() {
        super.onCreate()
        instance = this

        // CRITICAL: set transparent theme BEFORE any view is created.
        // ComposeView(context) inherits the context's windowBackground drawable.
        // Without this, the service context uses Theme.Material.Light which draws
        // a white/dark opaque background behind every overlay ComposeView.
        setTheme(R.style.Theme_Aura_Transparent)

        // Initialize lifecycle
        savedStateRegistryController.performAttach()
        savedStateRegistryController.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED

        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager

        // Create notification channel
        createNotificationChannel()

        Log.i(TAG, "✨ AuraOverlayService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Start as foreground service immediately
        startForeground(NOTIFICATION_ID, createNotification())

        when (intent?.action) {
            ACTION_SHOW -> showOverlay()
            ACTION_SHOW_AND_LISTEN -> showOverlayAndStartListening()
            ACTION_HIDE -> hideOverlay()
            ACTION_TOGGLE -> {
                if (_isOverlayVisible.value) {
                    hideOverlay()
                } else {
                    showOverlay()
                }
            }
            ACTION_CANCEL_TASK -> {
                Log.i(TAG, "🚫 Cancel task requested from notification")
                if (geminiLiveController != null) {
                    // Terminate entire Gemini Live bidirectional session
                    geminiLiveController?.cancelCapture()
                    geminiLiveController?.sendCancelTask()
                } else {
                    voiceCaptureController?.sendCancelTask()
                }
                restoreOverlay()
                conversationViewModel.resetToIdle()
            }
            else -> {
                // Default action: show overlay
                showOverlay()
            }
        }

        // Return START_STICKY to restart service if killed
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        
        // Cleanup
        hideOverlay()
        cleanupResources()
        
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        serviceScope.cancel()
        instance = null

        Log.i(TAG, "AuraOverlayService destroyed")
    }

    override fun onLowMemory() {
        super.onLowMemory()
        Log.w(TAG, "Low memory - cleaning up non-essential resources")
        releaseWakeLock()
    }

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        when (level) {
            TRIM_MEMORY_RUNNING_CRITICAL,
            TRIM_MEMORY_RUNNING_LOW -> {
                Log.w(TAG, "Memory pressure (level=$level) - releasing resources")
                releaseWakeLock()
            }
        }
    }

    /**
     * Show the overlay UI
     */
    private fun showOverlay() {
        if (_isOverlayVisible.value) {
            Log.d(TAG, "Overlay already visible")
            return
        }

        if (!canDrawOverlays(this)) {
            Log.e(TAG, "Cannot show overlay - permission not granted")
            stopSelf()
            return
        }

        try {
            // Move lifecycle to STARTED before creating the view
            lifecycleRegistry.currentState = Lifecycle.State.STARTED

            // Create and configure the overlay view
            overlayView = createOverlayView()

            // Create window params for overlay
            val params = createWindowParams()

            // Exclude overlay from screen capture (Android 13+) - MUST be set before addView
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                try {
                    Log.d(TAG, "📱 Android ${Build.VERSION.SDK_INT} detected - setting screen capture exclusion")
                    // Use reflection to access privateFlags (hidden API)
                    val privateFlagsField = WindowManager.LayoutParams::class.java.getDeclaredField("privateFlags")
                    privateFlagsField.isAccessible = true
                    val currentFlags = privateFlagsField.getInt(params)
                    // PRIVATE_FLAG_EXCLUDE_FROM_SCREEN_CAPTURE = 0x00000080
                    val newFlags = currentFlags or 0x00000080
                    privateFlagsField.setInt(params, newFlags)
                    Log.d(TAG, "🎭 Overlay privateFlags: $currentFlags -> $newFlags (screen capture exclusion set)")
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Failed to set screen capture exclusion: ${e.javaClass.simpleName}: ${e.message}", e)
                }
            } else {
                Log.w(TAG, "⚠️ Android ${Build.VERSION.SDK_INT} < TIRAMISU (33) - screen capture exclusion NOT available")
            }

            // Add view to window manager
            windowManager?.addView(overlayView, params)

            // Move lifecycle to RESUMED
            lifecycleRegistry.currentState = Lifecycle.State.RESUMED

            // Acquire partial wake lock for voice capture
            acquireWakeLock()

            // Initialize voice capture controller
            initializeVoiceController()

            _isOverlayVisible.value = true
            updateNotification(true)

            Log.i(TAG, "✅ Overlay shown successfully")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to show overlay", e)
            hideOverlay()
        }
    }
    
    /**
     * Show overlay and immediately start voice capture.
     * Called when wake word is detected.
     *
     * In Gemini Live mode: just show the overlay — do NOT auto-start the session.
     * The Gemini Live session is continuous and the user must explicitly press the
     * mic button to begin. Auto-starting caused the "listening on open" bug.
     *
     * In classic STT mode: auto-start as before (push-to-talk style).
     */
    private fun showOverlayAndStartListening() {
        Log.i(TAG, "🎤 Show overlay (wake word triggered)")

        // Show the overlay first
        showOverlay()

        // Only auto-start for classic VoiceCaptureController (STT/TTS mode).
        // Gemini Live is always-on once the user presses mic — never auto-start.
        if (geminiLiveController != null) {
            Log.i(TAG, "🎙️ Gemini Live mode — waiting for user to press mic button")
            return
        }

        serviceScope.launch {
            // Give the voice controller time to initialise and connect
            var attempts = 0
            while (voiceCaptureController == null && attempts < 20) {
                kotlinx.coroutines.delay(100)
                attempts++
            }

            if (voiceCaptureController != null) {
                Log.i(TAG, "🎙️ Auto-starting VoiceCaptureController after wake word")
                voiceCaptureController?.startCapture()
            } else {
                Log.e(TAG, "❌ No voice controller ready for auto-capture")
            }
        }
    }

    /**
     * Hide the overlay UI
     */
    private fun hideOverlay() {
        if (!_isOverlayVisible.value && overlayView == null) {
            return
        }

        try {
            // Remove edge glow if automation was running
            hideEdgeGlow()

            // Remove view from window manager
            overlayView?.let { view ->
                try {
                    windowManager?.removeView(view)
                } catch (e: Exception) {
                    Log.w(TAG, "Error removing overlay view", e)
                }
            }
            overlayView = null

            // Cleanup voice controller
            cleanupVoiceController()

            // Release wake lock
            releaseWakeLock()

            // Move lifecycle back to STARTED
            if (lifecycleRegistry.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                lifecycleRegistry.currentState = Lifecycle.State.STARTED
            }

            _isOverlayVisible.value = false
            _isMinimized.value = false
            updateNotification(false)

            Log.i(TAG, "Overlay hidden")

            // Stop service when hidden
            stopSelf()

        } catch (e: Exception) {
            Log.e(TAG, "Error hiding overlay", e)
        }
    }
    
    /**
     * Minimize the overlay during automation - hide the UI but keep service running
     * @param showExecutingNotification If true, shows "AURA is working..." notification
     */
    fun minimizeOverlay(showExecutingNotification: Boolean = true) {
        if (!_isOverlayVisible.value || _isMinimized.value) {
            return
        }

        // Flag immediately to prevent re-entry before animation completes
        _isMinimized.value = true

        try {
            // Smooth slide-down + fade-out before hiding the view
            overlayView?.let { view ->
                view.animate()
                    .alpha(0f)
                    .translationY(50f)
                    .setDuration(280)
                    .setInterpolator(AccelerateInterpolator(1.5f))
                    .withEndAction {
                        view.visibility = android.view.View.GONE
                        view.alpha = 1f          // reset for next restore
                        view.translationY = 0f
                        // Edge glow + haptic kick once view is fully gone
                        if (showExecutingNotification) {
                            triggerAutomationStartHaptic()
                            showEdgeGlow()
                        }
                    }
                    .start()
            } ?: run {
                // No view to animate — go straight
                if (showExecutingNotification) {
                    triggerAutomationStartHaptic()
                    showEdgeGlow()
                }
            }

            if (showExecutingNotification) {
                _taskStartTime = System.currentTimeMillis()
                updateNotificationForAutomation(chipText = buildChipText())
                Log.i(TAG, "🔽 Overlay minimized for automation (with notification)")
            } else {
                updateNotification(false)
                Log.i(TAG, "🔽 Overlay minimized (no execution notification)")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error minimizing overlay", e)
        }
    }
    
    /**
     * Restore the overlay after automation completes.
     * Ensures execution on main thread since it modifies views.
     */
    fun restoreOverlay() {
        if (!_isMinimized.value) {
            return
        }
        
        // Ensure we're on main thread for view operations
        if (Looper.myLooper() != Looper.getMainLooper()) {
            Handler(Looper.getMainLooper()).post { restoreOverlay() }
            return
        }
        
        try {
            // Cancel live-notification dot animation and reset state
            _dotAnimJob?.cancel()
            _dotAnimJob = null
            _workingVerb = "Working"
            _workingStepCurrent = 0
            _workingStepTotal = 0
            _workingGoal = ""
            _taskStartTime = 0L

            // Remove edge glow before showing the overlay again
            hideEdgeGlow()

            // Smooth fade-in restore
            overlayView?.let { view ->
                view.alpha = 0f
                view.visibility = android.view.View.VISIBLE
                view.animate()
                    .alpha(1f)
                    .setDuration(260)
                    .setInterpolator(DecelerateInterpolator())
                    .start()
            }

            _isMinimized.value = false
            updateNotification(true)

            Log.i(TAG, "🔼 Overlay restored after automation")

        } catch (e: Exception) {
            Log.e(TAG, "Error restoring overlay", e)
        }
    }
    
    // ── Live Alert pill animation helpers ──────────────────────────────────────

    /** Map pipeline agent names → short verb for the notch chip text (≤10 chars). */
    private fun agentToShortVerb(agent: String): String = when (agent.trim().uppercase()) {
        "COMMANDER"  -> "Parsing"
        "PLANNER"    -> "Planning"
        "REACTIVE"   -> "Thinking"
        "PERCEIVER"  -> "Scanning"
        "ACTOR"      -> "Acting"
        "EXECUTOR"   -> "Acting"
        "VERIFIER"   -> "Checking"
        "RESPONDER"  -> "Responding"
        "AURA"       -> "Running"
        else         -> "Working"
    }

    /**
     * Compose the chip text shown inside the notch pill (right side of camera hole).
     * The timer lives on the LEFT via setUsesChronometer(); this returns only the verb part.
     * Format: "Parsing" or "2/5 Scanning"
     */
    private fun buildChipText(): String {
        return if (_workingStepTotal > 0)
            "${_workingStepCurrent}/${_workingStepTotal} $_workingVerb"
        else
            _workingVerb
    }

    /**
     * Push a single Live Alert chip update. Called only when the verb or step count changes.
     * The chronometer widget (setUsesChronometer) handles the timer ticking automatically,
     * so there is no need to poll every second.
     */
    private fun pushLiveUpdate(statusText: String) {
        val chip = buildChipText()
        Log.i(TAG, "💠 pushLiveUpdate: chip='$chip', status='${statusText.take(60)}'")
        _dotAnimJob?.cancel()
        _dotAnimJob = serviceScope.launch {
            updateNotificationForAutomation(
                statusText = statusText,
                chipText = chip,
                stepCurrent = _workingStepCurrent,
                stepTotal = _workingStepTotal
            )
        }
    }

    /**
     * Show a welcome notification as a Fluid Cloud / Live Update pill when the app opens.
     * Auto-reverts to the normal foreground notification after 3 seconds.
     */
    private fun showWelcomePill() {
        val openIntent = Intent(this, MainActivity::class.java)
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val builder = NotificationCompat.Builder(this, CHANNEL_ID_WORKING)
            .setContentTitle("AURA")
            .setContentText("Hey! I'm ready — ask me anything ✨")
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_NAVIGATION)
            .setUsesChronometer(true)
            .setWhen(System.currentTimeMillis())
            .setColorized(true)
            .setColor(0xFFFFFFFF.toInt())  // Monochrome white — matches edge glow
            .setContentIntent(openPendingIntent)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        
        val promoted = promoteIfSupported(
            builder.build(), chipText = "Ready \u2728", indeterminate = true
        )
        startForeground(NOTIFICATION_ID, promoted)
        
        // Revert to normal notification after 3 seconds
        serviceScope.launch {
            kotlinx.coroutines.delay(3000)
            if (_isOverlayVisible.value && !_isMinimized.value) {
                updateNotification(true)
            }
        }
    }

    /**
     * Unified Live Alert / Promoted Notification updater.
     *
     * Everything that wants to update the notch pill funnels through here.
     * The [chipText] is what appears in the pill itself (≤15 chars).
     * [stepCurrent]/[stepTotal] drive the progress bar fill inside the pill.
     * [color] lets the completion flash switch to green momentarily.
     */
    private fun updateNotificationForAutomation(
        statusText: String = "Processing your request...",
        chipText: String = "Working...",
        stepCurrent: Int = 0,
        stepTotal: Int = 0,
        color: Int = 0xFFFFFFFF.toInt()  // Monochrome white
    ) {
        val notificationManager = getSystemService(NotificationManager::class.java)
        val openIntent = Intent(this, MainActivity::class.java)
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val cancelIntent = Intent(this, AuraOverlayService::class.java).apply {
            action = ACTION_CANCEL_TASK
        }
        val cancelPendingIntent = PendingIntent.getService(
            this, 99, cancelIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val indeterminate = stepTotal <= 0
        val title = if (_workingGoal.isNotEmpty()) "AURA \u2014 $_workingGoal" else "AURA"

        val builder = NotificationCompat.Builder(this, CHANNEL_ID_WORKING)
            .setContentTitle(title)
            .setContentText(statusText)
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_NAVIGATION)
            .setProgress(
                if (indeterminate) 0 else stepTotal,
                if (indeterminate) 0 else stepCurrent,
                indeterminate
            )
            .setColor(color)
            .setContentIntent(openPendingIntent)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setShowWhen(false)
            .addAction(R.drawable.ic_notification, "Cancel", cancelPendingIntent)

        val promoted = promoteIfSupported(
            builder.build(),
            chipText = chipText,
            max = if (indeterminate) 0 else stepTotal,
            progress = if (indeterminate) 0 else stepCurrent,
            indeterminate = indeterminate
        )
        // Always call startForeground() — notify() alone does not refresh setShortCriticalText
        // on OxygenOS / OnePlus Live Alert chips.
        startForeground(NOTIFICATION_ID, promoted)
    }
    
    /**
     * Update the Live Alert pill with the current agent pipeline stage.
     *
     * Called from VoiceCaptureController on every `agent_status` WebSocket message.
     * Maps the agent name to a short verb and (re)starts the dot-pulse animation so
     * the notch pill text cycles  "Scanning" → "Scanning·" → "Scanning··" → "Scanning···"
     * at 450 ms intervals, giving it a living, breathing quality with zero extra screen area.
     */
    fun updateLiveNotification(agent: String, output: String) {
        if (_taskStartTime == 0L) _taskStartTime = System.currentTimeMillis()
        val newVerb = agentToShortVerb(agent)
        if (newVerb != _workingVerb) {
            Log.i(TAG, "🔄 Verb changed: '$_workingVerb' → '$newVerb' (agent=$agent)")
            _workingVerb = newVerb
        } else {
            Log.d(TAG, "Verb unchanged: '$_workingVerb' (agent=$agent)")
        }
        pushLiveUpdate("$agent: $output")
    }

    /**
     * Update the Live Alert pill with task step progress.
     *
     * Called from VoiceCaptureController on every `task_progress` WebSocket message.
     * - While running: chip shows "2/5 · Scanning···" and the progress bar fills.
     * - On completion: pill flashes green with "Done ✓" for 2.5 s, then resets.
     */
    fun updateLiveNotificationProgress(goal: String, current: Int, total: Int, isComplete: Boolean, isAborted: Boolean = false) {
        if (isAborted) {
            _dotAnimJob?.cancel()
            _dotAnimJob = null
            // Red flash: "Cancelled" for 2 s then restore overlay and normal notification
            serviceScope.launch {
                updateNotificationForAutomation(
                    statusText = "\uD83D\uDEAB Task cancelled",
                    chipText = "Cancelled",
                    stepCurrent = current,
                    stepTotal = total.takeIf { it > 0 } ?: 1,
                    color = 0xFFFF5252.toInt()   // Red
                )
                kotlinx.coroutines.delay(2000)
                updateNotification(false)
                // Restore overlay so user can issue a new command
                if (_isMinimized.value) restoreOverlay()
            }
            return
        }
        if (isComplete) {
            _dotAnimJob?.cancel()
            _dotAnimJob = null
            // Green flash: "Done ✓" for 2.5 s then restore the normal notification
            serviceScope.launch {
                updateNotificationForAutomation(
                    statusText = "\u2705 Task complete!",
                    chipText = "Done \u2713",
                    stepCurrent = total,
                    stepTotal = total,
                    color = 0xFF4CAF50.toInt()   // Material Green
                )
                kotlinx.coroutines.delay(2500)
                updateNotification(false)
            }
            return
        }

        _workingGoal = goal
        _workingStepCurrent = current
        _workingStepTotal = total
        Log.i(TAG, "📊 Progress update: verb='$_workingVerb', step=$current/$total")
        // Push update — chip immediately reflects new step count
        pushLiveUpdate("$_workingVerb: step $current of $total")
    }

    /**
     * On Android 16+ (API 36), build a Live Update notification using direct
     * platform APIs (no reflection). Requires compileSdk=36.
     */
    @Suppress("NewApi")
    private fun promoteIfSupported(
        notification: Notification,
        chipText: String = "AURA",
        max: Int = 0,
        progress: Int = 0,
        indeterminate: Boolean = false
    ): Notification {
        if (Build.VERSION.SDK_INT < 36) return notification

        val nm = getSystemService(NotificationManager::class.java)
        val permGranted = checkSelfPermission("android.permission.POST_PROMOTED_NOTIFICATIONS")
        Log.i(TAG, "POST_PROMOTED_NOTIFICATIONS permission: ${if (permGranted == android.content.pm.PackageManager.PERMISSION_GRANTED) "GRANTED" else "DENIED"}")
        Log.i(TAG, "canPostPromotedNotifications(): ${nm.canPostPromotedNotifications()}")

        return try {
            val openIntent = Intent(this, MainActivity::class.java)
            val openPendingIntent = PendingIntent.getActivity(
                this, 0, openIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            // Build ProgressStyle directly (no reflection)
            val progressStyle = Notification.ProgressStyle()
            if (indeterminate || max <= 0) {
                progressStyle.setProgressIndeterminate(true)
                Log.i(TAG, "\u2705 ProgressStyle: indeterminate=true")
            } else {
                val scaledProgress = ((progress.toFloat() / max) * 100).toInt().coerceIn(0, 100)
                progressStyle.setProgress(scaledProgress)
                Log.i(TAG, "\u2705 ProgressStyle: progress=$scaledProgress (from $progress/$max)")
            }
            progressStyle.setStyledByProgress(false)

            // Cancel button for the promoted Live Alert
            val cancelIntentPromoted = Intent(this, AuraOverlayService::class.java).apply {
                action = ACTION_CANCEL_TASK
            }
            val cancelPendingIntentPromoted = PendingIntent.getService(
                this, 99, cancelIntentPromoted,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            // Build notification with direct API calls
            val builder = Notification.Builder(this, CHANNEL_ID_WORKING)
                .setContentTitle(notification.extras.getString(Notification.EXTRA_TITLE) ?: "AURA")
                .setContentText(notification.extras.getString(Notification.EXTRA_TEXT) ?: "")
                .setSmallIcon(R.mipmap.ic_launcher)
                .setOngoing(true)
                // FLAG_ONLY_ALERT_ONCE: prevents the Live Alert pill from re-expanding
                // on every status update — it stays as the collapsed chip and only
                // expands when the user taps it.
                .setOnlyAlertOnce(true)
                .setColor(0xFFFFFFFF.toInt())  // White — glass-like Live Alert border
                .setContentIntent(openPendingIntent)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_DEFAULT)
                .setStyle(progressStyle)
                // Chip text: setShortCriticalText and setUsesChronometer are mutually
                // exclusive for the status-bar chip (docs say "or").  Chronometer
                // was winning, so the verb never updated.  Use shortCriticalText only
                // to show the agent verb; the elapsed timer still appears in the
                // notification body via the compat builder.
                .setShortCriticalText(chipText)
                .addAction(
                    Notification.Action.Builder(
                        null, "Cancel", cancelPendingIntentPromoted
                    ).build()
                )

            // Set EXTRA_REQUEST_PROMOTED_ONGOING via extras (key from AOSP source)
            val promoExtras = android.os.Bundle()
            promoExtras.putBoolean("android.requestPromotedOngoing", true)
            builder.addExtras(promoExtras)

            val result = builder.build()

            // Diagnostic logging
            val hasPromotable = result.hasPromotableCharacteristics()
            val nflags = result.flags
            val isOngoing = (nflags and Notification.FLAG_ONGOING_EVENT) != 0
            val reqPromoted = result.extras.getBoolean("android.requestPromotedOngoing")
            Log.i(TAG, "hasPromotableCharacteristics(): $hasPromotable")
            Log.i(TAG, "  flags=0x${Integer.toHexString(nflags)}, ongoing=$isOngoing, requestPromoted=$reqPromoted")
            Log.i(TAG, "  title=${result.extras.getString(Notification.EXTRA_TITLE)}")
            Log.i(TAG, "  shortCriticalText='$chipText'")
            Log.i(TAG, "  contentView=${result.contentView}, bigContentView=${result.bigContentView}, headsUpContentView=${result.headsUpContentView}")

            result
        } catch (e: Exception) {
            Log.w(TAG, "\u274C Live Update build failed: ${e.javaClass.simpleName}: ${e.message}")
            e.printStackTrace()
            notification
        }
    }

    // ── Edge Glow + Haptic ────────────────────────────────────────────────────

    /**
     * Pure-Canvas View that draws white gradient strips at each screen edge.
     * No Compose, no theme, no Material surface — only pixels we paint.
     * A ValueAnimator drives the breathing alpha (0.28 ↔ 0.72, 2.2 s).
     */
    private inner class EdgeGlowCanvasView(context: Context) : View(context) {

        private val animator = ValueAnimator.ofFloat(0.28f, 0.72f).apply {
            duration = 2200
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { invalidate() }
        }

        private val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)

        init {
            // Absolutely no background — not null, not a color, nothing.
            background = null
            setLayerType(LAYER_TYPE_HARDWARE, null)
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            animator.start()
        }

        override fun onDetachedFromWindow() {
            animator.cancel()
            super.onDetachedFromWindow()
        }

        override fun onDraw(canvas: android.graphics.Canvas) {
            val alpha = animator.animatedValue as Float
            val gp   = 32f * resources.displayMetrics.density
            val w    = width.toFloat()
            val h    = height.toFloat()

            fun white(a: Float) = android.graphics.Color.argb(
                (255 * a * alpha).toInt().coerceIn(0, 255), 255, 255, 255
            )
            val clear = android.graphics.Color.TRANSPARENT

            // Top  — bright at 0px, fades to clear at 32dp
            paint.shader = android.graphics.LinearGradient(
                0f, 0f, 0f, gp,
                intArrayOf(white(0.95f), white(0.25f), clear),
                floatArrayOf(0f, 0.55f, 1f),
                android.graphics.Shader.TileMode.CLAMP
            )
            canvas.drawRect(0f, 0f, w, gp, paint)

            // Bottom
            paint.shader = android.graphics.LinearGradient(
                0f, h - gp, 0f, h,
                intArrayOf(clear, white(0.25f), white(0.95f)),
                floatArrayOf(0f, 0.45f, 1f),
                android.graphics.Shader.TileMode.CLAMP
            )
            canvas.drawRect(0f, h - gp, w, h, paint)

            // Left
            paint.shader = android.graphics.LinearGradient(
                0f, 0f, gp, 0f,
                intArrayOf(white(0.95f), white(0.25f), clear),
                floatArrayOf(0f, 0.55f, 1f),
                android.graphics.Shader.TileMode.CLAMP
            )
            canvas.drawRect(0f, 0f, gp, h, paint)

            // Right
            paint.shader = android.graphics.LinearGradient(
                w - gp, 0f, w, 0f,
                intArrayOf(clear, white(0.25f), white(0.95f)),
                floatArrayOf(0f, 0.45f, 1f),
                android.graphics.Shader.TileMode.CLAMP
            )
            canvas.drawRect(w - gp, 0f, w, h, paint)
        }
    }

    /** Attach edge glow overlay to WindowManager (non-interactive, passthrough). */
    private fun showEdgeGlow() {
        if (edgeGlowView != null) return
        try {
            val glowView = EdgeGlowCanvasView(this)
            val (screenW, screenH) = realScreenSize()

            val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_SYSTEM_ALERT

            val params = WindowManager.LayoutParams(
                screenW, screenH,
                overlayType,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
                x = 0; y = 0
            }

            windowManager?.addView(glowView, params)
            edgeGlowView = glowView
            Log.i(TAG, "✨ Edge glow shown (${screenW}x${screenH})")
        } catch (e: Exception) {
            Log.e(TAG, "Error showing edge glow", e)
        }
    }

    /** Returns true physical display pixel dimensions (includes status bar + gesture nav). */
    private fun realScreenSize(): Pair<Int, Int> {
        val wm = windowManager!!
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val bounds = wm.maximumWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = wm.currentWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else {
            val size = android.graphics.Point()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealSize(size)
            size.x to size.y
        }
    }

    /** Detach edge glow overlay from WindowManager. */
    private fun hideEdgeGlow() {
        edgeGlowView?.let { view ->
            try { windowManager?.removeView(view) } catch (e: Exception) { Log.w(TAG, "Error removing edge glow", e) }
            edgeGlowView = null
            Log.i(TAG, "Edge glow hidden")
        }
    }

    /**
     * Single crisp haptic double-tap when automation starts.
     * Feels like a satisfying mechanical "click-clack" — snappy, not buzzy.
     */
    private fun triggerAutomationStartHaptic() {
        try {
            val timings    = longArrayOf(0, 18, 55, 28)
            val amplitudes = intArrayOf(0, 220, 0, 130)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = getSystemService(VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vm.defaultVibrator.vibrate(
                    VibrationEffect.createWaveform(timings, amplitudes, -1)
                )
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                @Suppress("DEPRECATION")
                (getSystemService(VIBRATOR_SERVICE) as Vibrator).vibrate(
                    VibrationEffect.createWaveform(timings, amplitudes, -1)
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "Haptic error", e)
        }
    }

    /**
     * Create the ComposeView for the overlay
     */
    private fun createOverlayView(): ComposeView {
        return ComposeView(this).apply {
            // Set lifecycle and state registry owners
            setViewTreeLifecycleOwner(this@AuraOverlayService)
            setViewTreeSavedStateRegistryOwner(this@AuraOverlayService)

            setContent {
                // Use transparent background - critical for true overlay effect
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.Transparent)
                ) {
                    AuraUITheme(darkTheme = true) {
                        OverlayContent()
                    }
                }
            }
        }
    }

    /**
     * Compose content for the overlay
     */
    @Composable
    private fun OverlayContent() {
        val conversationState by conversationViewModel.state.collectAsState()
        val conversationMessages by conversationViewModel.messages.collectAsState()
        val agentOutputs by conversationViewModel.agentOutputs.collectAsState()
        val latestAgentOutput by conversationViewModel.latestAgentOutput.collectAsState()
        val taskProgress by conversationViewModel.taskProgress.collectAsState()

        // Create overlay state
        val overlayState = VoiceAssistantState(
            isVisible = true,
            isListening = conversationState.conversationState == ConversationPhase.LISTENING,
            isProcessing = conversationState.conversationState == ConversationPhase.THINKING,
            isResponding = conversationState.conversationState == ConversationPhase.RESPONDING,
            partialTranscript = conversationState.partialTranscript,
            messages = conversationMessages,
            serverConnected = conversationState.isServerConnected,
            audioAmplitude = audioAmplitude.floatValue,
            processingContext = conversationState.processingContext,
            suggestedCommands = conversationState.suggestedCommands,
            recentCommands = conversationState.recentCommands,
            agentOutputs = agentOutputs,
            latestAgentOutput = latestAgentOutput,
            taskProgress = taskProgress,
            isGeminiLiveSession = geminiLiveController?.isSessionActive == true,
        )

        // Create callbacks
        val overlayCallbacks = VoiceAssistantCallbacks(
            onDismiss = {
                // Cancel any ongoing operation and hide
                when (conversationState.conversationState) {
                    ConversationPhase.LISTENING -> {
                        geminiLiveController?.cancelCapture() ?: voiceCaptureController?.cancelCapture()
                        conversationViewModel.resetToIdle()
                    }
                    ConversationPhase.THINKING, ConversationPhase.RESPONDING -> {
                        conversationViewModel.resetToIdle()
                    }
                    else -> { }
                }
                // Always return to PASSIVE so wake word re-arms after dismiss
                ListeningModeController.getInstance(this@AuraOverlayService).transitionToPassive()
                hide(this@AuraOverlayService)
            },
            onMicClick = {
                when (conversationState.conversationState) {
                    ConversationPhase.IDLE -> {
                        // Prefer Gemini Live controller when connected, else fall back to VCC
                        if (geminiLiveController != null) {
                            geminiLiveController?.startCapture()
                        } else {
                            voiceCaptureController?.startCapture()
                        }
                    }
                    ConversationPhase.LISTENING -> {
                        if (geminiLiveController != null) {
                            // In bidirectional mode: mic press while listening = END session
                            geminiLiveController?.cancelCapture()
                        } else {
                            voiceCaptureController?.stopCapture()
                        }
                    }
                    else -> { }
                }
            },
            onSettingsClick = {
                // Open main activity for settings
                val intent = Intent(this@AuraOverlayService, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    putExtra("NAVIGATE_TO_SETTINGS", true)
                }
                startActivity(intent)
            },
            onTextSubmit = { text ->
                conversationViewModel.addRecentCommand(text)
                // Text commands go to whichever voice layer is active
                if (geminiLiveController != null) {
                    geminiLiveController?.sendTextCommand(text)
                } else {
                    voiceCaptureController?.sendTextCommand(text)
                }
            },
            onMessageCopy = { text ->
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                val clip = android.content.ClipData.newPlainText("AURA Message", text)
                clipboard.setPrimaryClip(clip)
            },
            onMessageRetry = { message ->
                if (geminiLiveController != null) {
                    geminiLiveController?.sendTextCommand(message.text)
                } else {
                    voiceCaptureController?.sendTextCommand(message.text)
                }
            },
            onMessageShare = { text ->
                val shareIntent = Intent().apply {
                    action = Intent.ACTION_SEND
                    putExtra(Intent.EXTRA_TEXT, text)
                    type = "text/plain"
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                startActivity(Intent.createChooser(shareIntent, "Share via").apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                })
            },
            onMessageDelete = { messageId ->
                conversationViewModel.deleteMessage(messageId)
            },
            onSuggestionClick = { suggestion ->
                conversationViewModel.addRecentCommand(suggestion)
                if (geminiLiveController != null) {
                    geminiLiveController?.sendTextCommand(suggestion)
                } else {
                    voiceCaptureController?.sendTextCommand(suggestion)
                }
            },
            onClearChat = {
                conversationViewModel.clearAllMessages()
            },
        )

        VoiceAssistantOverlay(
            state = overlayState,
            callbacks = overlayCallbacks,
        )
    }

    /**
     * Create WindowManager.LayoutParams for the overlay
     */
    private fun createWindowParams(): WindowManager.LayoutParams {
        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
        }

        // Use real display pixel size so the window covers status bar + gesture nav bar.
        // MATCH_PARENT is relative to the app window area and leaves inset gaps.
        val (screenW, screenH) = realScreenSize()

        return WindowManager.LayoutParams(
            screenW, screenH,
            overlayType,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0; y = 0
            @Suppress("DEPRECATION")
            softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_PAN or
                WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                flags = flags or WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED
            }
        }
    }

    /**
     * Initialize the voice capture controller
     */
    private fun initializeVoiceController() {
        connectionJob?.cancel()
        connectionJob = serviceScope.launch {
            try {
                // Discover server URL
                serverUrl = discoverServerUrl()

                if (useGeminiLive) {
                    // ── Gemini Live mode ──────────────────────────────────────────
                    // GeminiLiveController handles ALL voice I/O (mic → Gemini → audio).
                    // VoiceCaptureController connects to /ws/conversation as a silent
                    // gesture-execution pipe only (no mic, no TTS).
                    Log.i(TAG, "🌟 Gemini Live mode — voice fully replaced by Gemini Live")

                    voiceCaptureController = VoiceCaptureController(
                        context = this@AuraOverlayService,
                        serverUrl = serverUrl,
                        viewModel = conversationViewModel,
                        scope = serviceScope,
                        onAmplitudeUpdate = null,          // waveform driven by GLC
                        functionGemmaManager = null,       // not needed in Live mode
                        deviceControlOnly = true,          // silence mic + TTS
                    )
                    val vccConnected = voiceCaptureController?.connect() ?: false
                    Log.i(TAG, if (vccConnected) "✅ Gesture pipe /ws/conversation connected"
                               else "⚠️ Gesture pipe failed to connect (gestures may not work)")

                    geminiLiveController = com.aura.aura_ui.voice.GeminiLiveController(
                        context = this@AuraOverlayService,
                        serverUrl = serverUrl,
                        viewModel = conversationViewModel,
                        scope = serviceScope,
                        onAmplitudeUpdate = { amplitude ->
                            audioAmplitude.floatValue = amplitude
                        }
                    )
                    val liveConnected = geminiLiveController?.connect() ?: false
                    if (!liveConnected) {
                        Log.w(TAG, "⚠️ GeminiLiveController failed to connect — voice unavailable")
                        geminiLiveController?.cleanup()
                        geminiLiveController = null
                    } else {
                        Log.i(TAG, "✅ GeminiLiveController connected — Gemini Live is the voice pipeline")

                    // ── Phase → Live Alert observer ──────────────────────────────
                    // Keep the notch chip updated for every conversation phase,
                    // not just during automation tasks.
                    serviceScope.launch {
                        conversationViewModel.state.collect { state ->
                            if (!_isOverlayVisible.value) return@collect
                            val isAutomation = _isMinimized.value
                            if (!isAutomation) {
                                // Show conversational verbs in the Live Alert
                                when (state.conversationState) {
                                    ConversationPhase.LISTENING -> {
                                        updateNotificationForAutomation(
                                            statusText = "AURA is listening…",
                                            chipText = "Listening 🎤",
                                        )
                                    }
                                    ConversationPhase.THINKING -> {
                                        updateNotificationForAutomation(
                                            statusText = "AURA is thinking…",
                                            chipText = "Thinking…",
                                        )
                                    }
                                    ConversationPhase.RESPONDING -> {
                                        updateNotificationForAutomation(
                                            statusText = "AURA is speaking…",
                                            chipText = "Speaking…",
                                        )
                                    }
                                    ConversationPhase.IDLE, ConversationPhase.ERROR -> {
                                        updateNotification(true)
                                    }
                                }
                            }
                        }
                    }
                    }

                } else {
                    // ── Classic STT/TTS mode ──────────────────────────────────────
                    // VoiceCaptureController owns mic + TTS + gesture pipe.
                    Log.i(TAG, "🎙️ Classic mode — using Groq STT + Edge-TTS pipeline")

                    voiceCaptureController = VoiceCaptureController(
                        context = this@AuraOverlayService,
                        serverUrl = serverUrl,
                        viewModel = conversationViewModel,
                        scope = serviceScope,
                        onAmplitudeUpdate = { amplitude ->
                            audioAmplitude.floatValue = amplitude
                        },
                        functionGemmaManager = try {
                            EntryPointAccessors.fromApplication(
                                applicationContext,
                                FunctionGemmaEntryPoint::class.java
                            ).functionGemmaManager()
                        } catch (e: Exception) {
                            Log.w(TAG, "FunctionGemmaManager not available", e)
                            null
                        }
                    )
                    val vccConnected = voiceCaptureController?.connect() ?: false
                    if (!vccConnected) {
                        Log.w(TAG, "VoiceCaptureController: failed to connect (will retry on interaction)")
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error initializing voice controller", e)
            }
        }
    }

    /**
     * Cleanup the voice capture controller
     */
    private fun cleanupVoiceController() {
        connectionJob?.cancel()
        connectionJob = null
        geminiLiveController?.cleanup()
        geminiLiveController = null
        voiceCaptureController?.cleanup()
        voiceCaptureController = null
    }

    /**
     * Discover the server URL (simplified version)
     */
    private suspend fun discoverServerUrl(): String {
        // Try to get from shared preferences or use default
        val prefs = getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
        return prefs.getString("server_url", null) 
            ?: "http://10.193.156.197:8000"
    }

    /**
     * Create notification channel for foreground service
     * 
     * OnePlus Live Alerts Requirements:
     * - Channel importance must be DEFAULT or higher
     * - Notification must be ongoing
     * - App must appear in Live Alerts settings
     */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Main channel - DEFAULT importance for Live Alert compatibility
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AURA Voice Assistant",
                NotificationManager.IMPORTANCE_DEFAULT  // DEFAULT required for Live Alert visibility
            ).apply {
                description = "AURA voice assistant service - appears in Live Alerts"
                setShowBadge(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                // Disable sound but keep importance for Live Alert
                setSound(null, null)
                enableVibration(false)
            }
            
            // High priority channel for active commands / Live Alert pill
            val workingChannel = NotificationChannel(
                CHANNEL_ID_WORKING,
                "AURA Active",
                NotificationManager.IMPORTANCE_HIGH  // HIGH for Live Alert pill appearance
            ).apply {
                description = "Shows in Live Alert pill when AURA is working"
                setShowBadge(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                // Disable sound/vibration but keep high importance for Live Alert
                setSound(null, null)
                enableVibration(false)
            }

            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager?.createNotificationChannel(channel)
            notificationManager?.createNotificationChannel(workingChannel)
        }
    }

    /**
     * Create the foreground service notification optimized for Live Alerts
     */
    private fun createNotification(): Notification {
        // Pending intent to toggle overlay
        val toggleIntent = Intent(this, AuraOverlayService::class.java).apply {
            action = ACTION_TOGGLE
        }
        val togglePendingIntent = PendingIntent.getService(
            this, 0, toggleIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Pending intent to open main activity
        val openIntent = Intent(this, MainActivity::class.java)
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Notification optimized for OnePlus Live Alerts
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AURA Assistant")
            .setContentText("Listening • Tap to toggle")
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setCategory(NotificationCompat.CATEGORY_STATUS)  // Status for Live Alert
            .setContentIntent(togglePendingIntent)
            .setColorized(true)
            .setColor(0xFFFFFFFF.toInt())  // Monochrome white
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(
                R.drawable.ic_notification,
                if (_isOverlayVisible.value) "Hide" else "Show",
                togglePendingIntent
            )
            .addAction(
                R.drawable.ic_notification,
                "Open",
                openPendingIntent
            )
            .build()
    }

    /**
     * Update the notification based on overlay state.
     * isVisible=true  → pin/refresh the quiet DEFAULT-channel foreground notification.
     * isVisible=false → stop any dot animation, demote the foreground service (removes
     *                   the Live Alert / promoted pill), then re-pin a quiet DEFAULT
     *                   notification only if the overlay is still alive.
     */
    private fun updateNotification(isVisible: Boolean) {
        if (isVisible) {
            startForeground(NOTIFICATION_ID, createNotification())
        } else {
            // Cancel live-update animation loop
            _dotAnimJob?.cancel()
            _dotAnimJob = null
            // Remove the foreground status + its notification (cancels Live Alert pill)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                stopForeground(STOP_FOREGROUND_REMOVE)
            } else {
                @Suppress("DEPRECATION")
                stopForeground(true)
            }
            // Re-pin with a quiet DEFAULT-channel notification only while the overlay
            // is still running (avoids the "no notification for foreground service" crash).
            if (_isOverlayVisible.value) {
                startForeground(NOTIFICATION_ID, createNotification())
            }
        }
    }

    /**
     * Acquire wake lock for voice capture
     */
    private fun acquireWakeLock() {
        if (wakeLock == null) {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "aura:overlay_wake_lock"
            ).apply {
                setReferenceCounted(false)
            }
        }
        wakeLock?.acquire(10 * 60 * 1000L) // 10 minutes max
        Log.d(TAG, "Wake lock acquired")
    }

    /**
     * Release wake lock
     */
    private fun releaseWakeLock() {
        wakeLock?.let { lock ->
            if (lock.isHeld) {
                lock.release()
                Log.d(TAG, "Wake lock released")
            }
        }
    }

    /**
     * Cleanup all resources
     */
    private fun cleanupResources() {
        cleanupVoiceController()
        releaseWakeLock()
        overlayView = null
    }
}
