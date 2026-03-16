package com.aura.aura_ui.accessibility

import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.app.NotificationManager
import android.bluetooth.BluetoothAdapter
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Rect
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.wifi.WifiManager
import android.nfc.NfcAdapter
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import androidx.annotation.RequiresApi
import com.aura.aura_ui.accessibility.gesture.GestureCallback
import com.aura.aura_ui.accessibility.gesture.GestureCommand
import com.aura.aura_ui.accessibility.gesture.GestureError
import com.aura.aura_ui.accessibility.gesture.GestureInjector
import com.aura.aura_ui.accessibility.gesture.GestureOptions
import com.aura.aura_ui.accessibility.gesture.GestureTarget
import com.aura.aura_ui.accessibility.gesture.GestureType
import com.aura.aura_ui.accessibility.gesture.SwipeDirection
import com.aura.aura_ui.agent.RuleBasedCommander
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.utils.AgentLogger
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AuraAccessibilityService : AccessibilityService() {
    companion object {
        private const val SCREENSHOT_REQUEST_CODE = 1000

        var BACKEND_URL = "http://10.0.2.2:8000"

        private var lastRegisteredUrl: String? = null
        private var isRegistering = AtomicBoolean(false)
        
        // StateFlow to track screen capture availability for UI observers
        private val _screenCaptureAvailable = MutableStateFlow(false)
        val screenCaptureAvailable: StateFlow<Boolean> = _screenCaptureAvailable.asStateFlow()
        
        /** Update screen capture status and notify observers */
        fun updateScreenCaptureStatus(available: Boolean) {
            _screenCaptureAvailable.value = available
        }

        var instance: AuraAccessibilityService? = null
            private set

        fun isServiceRunning(): Boolean = instance != null

        /**
         * Pending MediaProjection permission result that arrived before the service was running.
         * Consumed automatically in onServiceConnected().
         */
        var pendingMediaProjectionResultCode: Int? = null
        var pendingMediaProjectionData: Intent? = null

        fun setBackendUrl(url: String) {
            val normalizedUrl = url.trimEnd('/')
            BACKEND_URL = normalizedUrl

            AgentLogger.Auto.i("Backend URL updated", mapOf("url" to BACKEND_URL))

            // Update URL in all components (no automatic UI data send)
            instance?.updateAllBackendUrls(normalizedUrl)

            if (normalizedUrl != lastRegisteredUrl && !isRegistering.get()) {
                lastRegisteredUrl = normalizedUrl
                instance?.registerDeviceWithBackend()
            }

            // Command polling removed - all commands now use WebSocket
        }
        
        /**
         * Send screen capture permission result to backend.
         * Called by MainActivity when user grants or denies permission.
         */
        fun sendScreenCapturePermissionResult(granted: Boolean, error: String? = null) {
            // Update StateFlow immediately for UI observers
            updateScreenCaptureStatus(granted)
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val message = JSONObject().apply {
                        put("type", "screen_capture_permission_result")
                        put("granted", granted)
                        if (error != null) {
                            put("error", error)
                        }
                        put("timestamp", System.currentTimeMillis())
                    }

                    val request = Request.Builder()
                        .url("$BACKEND_URL/device/screen-capture-permission")
                        .post(message.toString().toRequestBody("application/json".toMediaType()))
                        .build()

                    OkHttpClient().newCall(request).execute().use { response ->
                        if (response.isSuccessful) {
                            AgentLogger.Screen.i(
                                "📸 Sent screen capture permission result",
                                mapOf("granted" to granted.toString())
                            )
                        } else {
                            AgentLogger.Screen.w(
                                "Failed to send permission result",
                                mapOf("code" to response.code.toString())
                            )
                        }
                    }
                } catch (e: Exception) {
                    AgentLogger.Screen.e("Error sending permission result", e)
                }
            }
        }
    }

    internal lateinit var screenCaptureManager: ScreenCaptureManager
    internal lateinit var uiTreeExtractor: UITreeExtractor
    private lateinit var backendCommunicator: BackendCommunicator
    // Command polling removed - all commands now use WebSocket

    lateinit var gestureInjector: GestureInjector
        private set

    private val commanderAgent = RuleBasedCommander()

    private var serviceScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var isFlashlightOn = false

    private var lastEventTime = 0L
    private val eventDebounceMs = 2000L
    private var isAuraAppActive = false

    override fun onServiceConnected() {
        super.onServiceConnected()

        instance = this

        // Keyboard starts in AUTO mode so the user can type normally when not
        // automating.  dismissKeyboard() switches to SHOW_MODE_HIDDEN on demand
        // during automation, and restoreKeyboard() switches back to AUTO when the
        // task finishes.

        serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

        uiTreeExtractor = UITreeExtractor(this)
        screenCaptureManager = ScreenCaptureManager(this, uiTreeExtractor)
        gestureInjector = GestureInjector(this)
        backendCommunicator = BackendCommunicator(this, uiTreeExtractor, serviceScope, BACKEND_URL)
        // Command polling removed - all commands now use WebSocket

        AgentLogger.UI.i("AURA Accessibility Service connected")

        // Apply any pending MediaProjection permission that arrived while the service was not yet running
        val pendingCode = pendingMediaProjectionResultCode
        val pendingData = pendingMediaProjectionData
        if (pendingCode != null && pendingData != null) {
            pendingMediaProjectionResultCode = null
            pendingMediaProjectionData = null
            AgentLogger.Screen.i("📸 Applying pending MediaProjection permission on service connect")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                val success = screenCaptureManager.initializeMediaProjection(pendingCode, pendingData)
                if (success) {
                    AgentLogger.Screen.i("✅ Pending MediaProjection initialized successfully")
                    updateScreenCaptureStatus(true)
                    sendScreenCapturePermissionResult(granted = true)
                } else {
                    AgentLogger.Screen.e("❌ Pending MediaProjection initialization failed — token may be expired")
                }
            }
        }

        startForegroundService()

        observeScreenCapturePreference()

        AgentLogger.UI.i("Waiting for MainActivity to configure backend URL...")
    }

    private fun observeScreenCapturePreference() {
        serviceScope.launch {
            var previousValue: Boolean? = null
            ThemeManager.enableScreenCapture.collect { enabled ->
                if (previousValue != null && previousValue != enabled) {
                    if (!enabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                        AgentLogger.Screen.i("Screen capture disabled by user - cleaning up resources")
                        screenCaptureManager.disableScreenCapture()
                        // Notify backend that screen capture is no longer available
                        sendScreenCapturePermissionResult(granted = false, error = "User disabled screen capture")
                    }
                    AgentLogger.Screen.i("Screen capture preference changed: $enabled")
                }
                previousValue = enabled
            }
        }
    }

    private fun updateAllBackendUrls(url: String) {
        backendCommunicator.updateBackendUrl(url)
        // Command polling removed - all commands now use WebSocket
        AgentLogger.Auto.i("All components updated with new backend URL", mapOf("url" to url))
    }

    fun executeIntentDrivenAction(
        userIntent: String,
        onComplete: ((Boolean) -> Unit)? = null,
    ) {
        serviceScope.launch {
            try {
                val decision = commanderAgent.parseIntent(userIntent)

                AgentLogger.Auto.i(
                    "Commander decision",
                    mapOf(
                        "action" to decision.action,
                        "needs_ui_tree" to decision.uiRequirement.needsUITree,
                        "needs_screenshot" to decision.uiRequirement.needsScreenshot,
                        "reason" to decision.uiRequirement.requestReason,
                    ),
                )

                if (decision.uiRequirement.needsScreenshot) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                        screenCaptureManager.captureScreenWithAnalysis { screenshotData ->
                            backendCommunicator.sendUIDataWithRequirement(
                                screenshotData,
                                decision.uiRequirement,
                                onComplete,
                            )
                        }
                    }
                } else if (decision.uiRequirement.needsUITree) {
                    backendCommunicator.sendUIDataIfRequired(decision.uiRequirement, onComplete)
                } else {
                    AgentLogger.Auto.i("No UI data required - executing gesture directly")
                    onComplete?.invoke(true)
                }
            } catch (e: Exception) {
                AgentLogger.Auto.e("Error executing intent-driven action", e)
                onComplete?.invoke(false)
            }
        }
    }

    private fun startForegroundService() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channelId = "aura_accessibility"
                val channelName = "AURA Accessibility"
                val importance = android.app.NotificationManager.IMPORTANCE_LOW

                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
                val channel = android.app.NotificationChannel(channelId, channelName, importance)
                notificationManager.createNotificationChannel(channel)

                val notification =
                    android.app.Notification.Builder(this, channelId)
                        .setContentTitle("AURA Active")
                        .setContentText("Screen capture enabled")
                        .setSmallIcon(android.R.drawable.ic_menu_view)
                        .build()

                startForeground(1, notification)
                AgentLogger.UI.i("✅ Started foreground service for MediaProjection")
            }
        } catch (e: Exception) {
            AgentLogger.UI.e("Failed to start foreground service", e)
        }
    }

    @SuppressLint("SwitchIntDef")
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event?.let {
            val eventPackageName = it.packageName?.toString() ?: ""
            val wasActive = isAuraAppActive

            var isAura = eventPackageName == "com.aura.aura_ui.debug" || eventPackageName == "com.aura.aura_ui"

            if (!isAura && eventPackageName == "com.android.systemui") {
                try {
                    val rootNode = uiTreeExtractor.safeGetRootInActiveWindow()

                    if (rootNode != null) {
                        val actualPackageName = rootNode.packageName?.toString() ?: ""
                        isAura = actualPackageName == "com.aura.aura_ui.debug" || actualPackageName == "com.aura.aura_ui"
                        if (isAura) {
                            AgentLogger.Auto.d("🔍 Event said systemui, but actual window: $actualPackageName - AURA DETECTED!")
                        }
                        @Suppress("DEPRECATION")
                        rootNode.recycle()
                    }
                } catch (e: Exception) {
                    AgentLogger.Auto.e("Error checking actual window package", e)
                }
            }

            isAuraAppActive = isAura
            // Command polling removed - all commands now use WebSocket

            if (isAuraAppActive != wasActive) {
                AgentLogger.Auto.d("AURA state: $wasActive -> $isAuraAppActive (eventPkg: $eventPackageName)")
            }

            if (it.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                AgentLogger.Auto.d("Window changed: $eventPackageName, isAuraAppActive: $isAuraAppActive")
            }

            if (!isAuraAppActive) {
                // Silent - don't spam logs when other apps are in foreground
                return
            }

            // UI data sending disabled - only send when explicitly requested via triggerScreenshotCapture()
            // This prevents continuous latency from automatic updates
        }
    }

    override fun onInterrupt() {
        AgentLogger.UI.w("Service interrupted")
        restoreKeyboard()
    }

    override fun onUnbind(intent: Intent?): Boolean {
        AgentLogger.UI.i("Service unbound")
        // Restore normal keyboard behaviour before the service disconnects
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            softKeyboardController.setShowMode(SHOW_MODE_AUTO)
        }
        cleanup()
        return super.onUnbind(intent)
    }

    @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
    fun initializeMediaProjection(
        resultCode: Int,
        data: Intent,
    ): Boolean {
        return screenCaptureManager.initializeMediaProjection(resultCode, data)
    }

    fun isMediaProjectionAvailable(): Boolean {
        return screenCaptureManager.isMediaProjectionAvailable()
    }

    fun triggerScreenshotCapture() {
        if (!screenCaptureManager.isMediaProjectionAvailable()) {
            AgentLogger.Screen.w("⚠️ triggerScreenshotCapture: MediaProjection not available")
            return
        }
        AgentLogger.Screen.i("📸 Manual screenshot capture triggered")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            screenCaptureManager.captureScreenWithAnalysis { screenshotData ->
                backendCommunicator.sendUIDataWithRequirement(
                    screenshotData,
                    UIDataRequirement.FULL_UI_DATA,
                    null,
                )
            }
        }
    }

    fun executeGesture(gestureRequest: GestureRequest) {
        when (gestureRequest.action.lowercase()) {
            "tap", "click" -> {
                val x = gestureRequest.x ?: return
                val y = gestureRequest.y ?: return
                performTap(x, y, gestureRequest.command_id)
            }
            "long_press" -> {
                val x = gestureRequest.x ?: return
                val y = gestureRequest.y ?: return
                performLongPress(x, y, gestureRequest.duration, gestureRequest.command_id)
            }
            "swipe" -> {
                val x1 = gestureRequest.x ?: return
                val y1 = gestureRequest.y ?: return
                val x2 = gestureRequest.x2 ?: return
                val y2 = gestureRequest.y2 ?: return
                performSwipe(x1, y1, x2, y2, gestureRequest.duration, gestureRequest.command_id)
            }
            "scroll_up" -> performScroll("up", gestureRequest.command_id)
            "scroll_down" -> performScroll("down", gestureRequest.command_id)
            "back" -> {
                performBack()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "home" -> {
                performHome()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "recents" -> {
                performRecents()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "dismiss_keyboard" -> {
                dismissKeyboard()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "restore_keyboard" -> {
                restoreKeyboard()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "press_enter" -> {
                performEnterAction()
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            "press_search" -> {
                pressKeyEvent(android.view.KeyEvent.KEYCODE_SEARCH)
                gestureRequest.command_id?.let { sendGestureAck(it, true, null) }
            }
            else -> executeSystemAction(gestureRequest.action, gestureRequest.command_id)
        }
    }

    // Phase 7: Send gesture acknowledgment back to backend via HTTP
    private fun sendGestureAck(commandId: String, success: Boolean, error: String?) {
        serviceScope.launch(Dispatchers.IO) {
            try {
                val ackMessage = JSONObject().apply {
                    put("type", "gesture_ack")
                    put("command_id", commandId)
                    put("success", success)
                    put("error", error ?: "")
                    put("timestamp", System.currentTimeMillis())
                }

                if (::backendCommunicator.isInitialized) {
                    val jsonStr = ackMessage.toString()

                    val request = Request.Builder()
                        .url("${backendCommunicator.getCurrentBackendUrl()}/device/gesture-ack")
                        .post(jsonStr.toRequestBody("application/json".toMediaType()))
                        .build()

                    OkHttpClient().newCall(request).execute().use { response ->
                        if (response.isSuccessful) {
                            AgentLogger.Auto.d(
                                "✅ Sent gesture ACK to backend",
                                mapOf("command_id" to commandId, "success" to success),
                            )
                        } else {
                            AgentLogger.Auto.w(
                                "Failed to send gesture ACK",
                                mapOf("code" to response.code.toString()),
                            )
                        }
                    }
                } else {
                    AgentLogger.Auto.w("⚠️ BackendCommunicator not ready, cannot send ACK")
                }
            } catch (e: Exception) {
                AgentLogger.Auto.e("Error sending gesture ACK", e)
            }
        }
    }

    private fun dispatchGestureCommand(
        gestureType: GestureType,
        target: GestureTarget,
        endTarget: GestureTarget.Coordinates? = null,
        options: GestureOptions = GestureOptions(),
        commandIdForAck: String? = null,
    ) {
        val commandId = commandIdForAck ?: "cmd_${UUID.randomUUID()}"
        val command = GestureCommand(
            commandId = commandId,
            gestureType = gestureType,
            target = target,
            endTarget = endTarget,
            options = options,
        )

        gestureInjector.execute(
            command,
            object : GestureCallback {
                override fun onSuccess(cmd: GestureCommand, executionTimeMs: Long) {
                    AgentLogger.Auto.i(
                        "Gesture succeeded",
                        mapOf("commandId" to cmd.commandId, "durationMs" to executionTimeMs),
                    )
                    commandIdForAck?.let { sendGestureAck(it, true, null) }
                }

                override fun onFailure(cmd: GestureCommand, error: GestureError, details: String?) {
                    AgentLogger.Auto.w(
                        "Gesture failed",
                        mapOf("commandId" to cmd.commandId, "error" to error.name, "details" to (details ?: "")),
                    )
                    commandIdForAck?.let { sendGestureAck(it, false, "$error${details?.let { d -> ": $d" } ?: ""}") }
                }

                override fun onCancelled(cmd: GestureCommand) {
                    AgentLogger.Auto.w("Gesture cancelled", mapOf("commandId" to cmd.commandId))
                    commandIdForAck?.let { sendGestureAck(it, false, "Gesture cancelled") }
                }
            },
        )
    }

    fun performTap(
        x: Int,
        y: Int,
        commandId: String? = null,
    ) {
        dispatchGestureCommand(
            gestureType = GestureType.TAP,
            target = GestureTarget.Coordinates(x.toFloat(), y.toFloat(), normalized = false),
            options = GestureOptions(durationMs = 100L),
            commandIdForAck = commandId,
        )
    }

    fun performLongPress(
        x: Int,
        y: Int,
        duration: Long = 1000L,
        commandId: String? = null,
    ) {
        dispatchGestureCommand(
            gestureType = GestureType.LONG_PRESS,
            target = GestureTarget.Coordinates(x.toFloat(), y.toFloat(), normalized = false),
            options = GestureOptions(durationMs = duration, holdMs = duration),
            commandIdForAck = commandId,
        )
    }

    fun performSwipe(
        x1: Int,
        y1: Int,
        x2: Int,
        y2: Int,
        duration: Long,
        commandId: String? = null,
    ) {
        dispatchGestureCommand(
            gestureType = GestureType.SWIPE,
            target = GestureTarget.Coordinates(x1.toFloat(), y1.toFloat(), normalized = false),
            endTarget = GestureTarget.Coordinates(x2.toFloat(), y2.toFloat(), normalized = false),
            options = GestureOptions(durationMs = duration.coerceAtLeast(100L)),
            commandIdForAck = commandId,
        )
    }

    fun performSwipe(direction: String) {
        performScroll(direction)
    }

    fun performSwipe(
        x1: Int? = null,
        y1: Int? = null,
        x2: Int? = null,
        y2: Int? = null,
        direction: String? = null,
        duration: Long = 500,
        commandId: String? = null,
    ) {
        when {
            direction != null -> performScroll(direction, commandId)
            x1 != null && y1 != null && x2 != null && y2 != null ->
                performSwipe(x1, y1, x2, y2, duration, commandId)
        }
    }

    fun performClick(
        x: Int,
        y: Int,
        commandId: String? = null,
    ) {
        performTap(x, y, commandId)
    }

    fun performScroll(direction: String, commandId: String? = null) {
        val swipeDirection = when (direction.lowercase()) {
            "up" -> SwipeDirection.UP
            "down" -> SwipeDirection.DOWN
            "left" -> SwipeDirection.LEFT
            "right" -> SwipeDirection.RIGHT
            else -> null
        }

        swipeDirection?.let {
            dispatchGestureCommand(
                gestureType = GestureType.SWIPE,
                target = GestureTarget.Direction(it, distanceRatio = 0.5f),
                options = GestureOptions(durationMs = 500L),
                commandIdForAck = commandId,
            )
        }
    }

    fun performBack() {
        performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
    }

    fun dismissKeyboard() {
        // Suppress the soft keyboard via the official SoftKeyboardController API
        // so it doesn't obscure the screen during automated actions / screenshots.
        // Call restoreKeyboard() when automation finishes to give control back.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            softKeyboardController.setShowMode(SHOW_MODE_HIDDEN)
        }
    }

    fun restoreKeyboard() {
        // Switch back to AUTO so the user (or the next manual interaction) can
        // bring up the keyboard normally.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            softKeyboardController.setShowMode(SHOW_MODE_AUTO)
        }
    }

    fun pressKeyEvent(keyCode: Int) {
        try {
            val process = Runtime.getRuntime().exec(arrayOf("input", "keyevent", keyCode.toString()))
            process.waitFor()
            AgentLogger.Auto.d("Key event sent", mapOf("keyCode" to keyCode.toString()))
        } catch (e: Exception) {
            AgentLogger.Auto.w("pressKeyEvent failed", mapOf("keyCode" to keyCode.toString(), "error" to e.message.orEmpty()))
        }
    }

    /**
     * Smart press_enter: tries ACTION_IME_ENTER on the focused input node first
     * (triggers the IME action like Search/Go/Send), falls back to raw keyevent 66.
     */
    fun performEnterAction(): Boolean {
        try {
            val rootNode = rootInActiveWindow
            if (rootNode != null) {
                // Strategy 1: FOCUS_INPUT (standard focused text field)
                var focusedNode = rootNode.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

                // Strategy 2: Search for focused editable node
                if (focusedNode == null) {
                    focusedNode = findFocusedEditableNode(rootNode)
                }

                // Strategy 3: FOCUS_ACCESSIBILITY
                if (focusedNode == null) {
                    focusedNode = rootNode.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
                    if (focusedNode != null && !focusedNode.isEditable &&
                        focusedNode.className?.toString()?.contains("EditText") != true) {
                        @Suppress("DEPRECATION")
                        focusedNode.recycle()
                        focusedNode = null
                    }
                }

                if (focusedNode != null) {
                    // WebView returns true for ACTION_IME_ENTER but silently ignores it.
                    // Skip IME_ENTER entirely for WebView and fall through to tapKeyboardActionButton.
                    val nodeClass = focusedNode.className?.toString().orEmpty()
                    val isWebView = nodeClass.contains("WebView", ignoreCase = true)
                    val imeResult = if (!isWebView) {
                        focusedNode.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)
                    } else false
                    if (imeResult) {
                        AgentLogger.Auto.i("press_enter: ACTION_IME_ENTER succeeded on focused node",
                            mapOf("class" to nodeClass))
                        @Suppress("DEPRECATION")
                        focusedNode.recycle()
                        @Suppress("DEPRECATION")
                        rootNode.recycle()
                        return true
                    }
                    AgentLogger.Auto.d("ACTION_IME_ENTER skipped/failed, trying keyboard button",
                        mapOf("class" to nodeClass, "isWebView" to isWebView.toString()))
                    @Suppress("DEPRECATION")
                    focusedNode.recycle()
                } else {
                    AgentLogger.Auto.d("No focused node found for IME_ENTER, falling back to keyevent")
                }
                @Suppress("DEPRECATION")
                rootNode.recycle()
            }
        } catch (e: Exception) {
            AgentLogger.Auto.w("performEnterAction IME strategy failed", mapOf("error" to e.message.orEmpty()))
        }

        // Strategy 2: tap the keyboard window's action button directly (works reliably with Gboard)
        if (tapKeyboardActionButton()) return true

        // Strategy 3: raw keyevent fallback
        AgentLogger.Auto.d("press_enter: using raw keyevent fallback")
        pressKeyEvent(android.view.KeyEvent.KEYCODE_ENTER)
        return true
    }

    /**
     * Find and tap the action button (Search/Go/Done/Send) in the visible IME keyboard window.
     * Works with Gboard because it runs in a separate TYPE_INPUT_METHOD window accessible via
     * the `windows` property (requires flagRetrieveInteractiveWindows in service config).
     */
    private fun tapKeyboardActionButton(): Boolean {
        return try {
            val allWindows = windows ?: return false
            for (window in allWindows) {
                if (window.type != AccessibilityWindowInfo.TYPE_INPUT_METHOD) continue
                val root = window.root ?: continue

                // Try Gboard and AOSP/Samsung keyboard resource IDs
                for (resId in listOf(
                    "com.google.android.inputmethod.latin:id/key_pos_ime_action",
                    "com.android.inputmethod.latin:id/key_pos_ime_action"
                )) {
                    val nodes = root.findAccessibilityNodeInfosByViewId(resId)
                    if (nodes.isNotEmpty()) {
                        val clicked = nodes[0].performAction(AccessibilityNodeInfo.ACTION_CLICK)
                        val keyName = resId.substringAfterLast("/")
                        AgentLogger.Auto.i(
                            "press_enter: action key tapped $keyName",
                            mapOf("success" to clicked.toString())
                        )
                        nodes.forEach { @Suppress("DEPRECATION") it.recycle() }
                        @Suppress("DEPRECATION") root.recycle()
                        return clicked
                    }
                    nodes.forEach { @Suppress("DEPRECATION") it.recycle() }
                }

                // Generic: any clickable node in the keyboard window with an action label
                for (label in listOf("Search", "Go", "Done", "Send", "Next")) {
                    val nodes = root.findAccessibilityNodeInfosByText(label)
                    val candidate = nodes.firstOrNull { it.isClickable && it.isEnabled }
                    if (candidate != null) {
                        val clicked = candidate.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                        AgentLogger.Auto.i(
                            "press_enter: action key '$label' tapped",
                            mapOf("success" to clicked.toString())
                        )
                        nodes.forEach { @Suppress("DEPRECATION") it.recycle() }
                        @Suppress("DEPRECATION") root.recycle()
                        return clicked
                    }
                    nodes.forEach { @Suppress("DEPRECATION") it.recycle() }
                }

                AgentLogger.Auto.d("press_enter: no action button found in IME window")
                @Suppress("DEPRECATION") root.recycle()
            }
            false
        } catch (e: Exception) {
            AgentLogger.Auto.w("press_enter: tapKeyboardActionButton failed",
                mapOf("error" to e.message.orEmpty()))
            false
        }
    }

    fun performHome() {
        performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
    }

    fun performRecents() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            performGlobalAction(AccessibilityService.GLOBAL_ACTION_TOGGLE_SPLIT_SCREEN)
        }
    }

    /**
     * @param x  Optional screen X (px) of the intended field's centre — from coordinator.
     * @param y  Optional screen Y (px) of the intended field's centre — from coordinator.
     *  When provided we do a bounds-hit-test to land on the right editable node and
     *  grant it accessibility-focus only (no ACTION_CLICK → keyboard never opens).
     */
    fun performTextInput(text: String, x: Int = -1, y: Int = -1): Boolean {
        return try {
            val rootNode =
                rootInActiveWindow ?: run {
                    AgentLogger.Auto.w("No active window for text input")
                    return false
                }

            // Strategy 0 (preferred): Coordinator supplied target coordinates.
            // Find the editable node whose bounds contain (x, y) and give it
            // accessibility focus — no tap, no keyboard.
            var focusedNode: AccessibilityNodeInfo? = null
            if (x >= 0 && y >= 0) {
                focusedNode = findEditableNodeAtPoint(rootNode, x, y)
                if (focusedNode != null) {
                    AgentLogger.Auto.d("Strategy 0: found editable node at ($x,$y), granting accessibility focus")
                    focusedNode.performAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS)
                    Thread.sleep(50)
                }
            }

            // Strategy 1: Try system focus finder
            if (focusedNode == null) {
                focusedNode = rootNode.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                // WebView nodes don't support ACTION_SET_TEXT - skip them
                if (focusedNode != null && focusedNode.className?.toString()?.contains("WebView") == true) {
                    AgentLogger.Auto.d("Skipping WebView node from FOCUS_INPUT, WebView doesn't support SET_TEXT")
                    @Suppress("DEPRECATION")
                    focusedNode.recycle()
                    focusedNode = null
                }
            }

            // Strategy 2: Look for node with isFocused=true among editable fields
            if (focusedNode == null) {
                AgentLogger.Auto.d("FOCUS_INPUT returned null, searching for focused editable node")
                focusedNode = findFocusedEditableNode(rootNode)
            }
            
            // Strategy 3: Fall back to accessibility focus
            if (focusedNode == null) {
                AgentLogger.Auto.d("No focused editable found, trying FOCUS_ACCESSIBILITY")
                focusedNode = rootNode.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
                // Only use if it's editable
                if (focusedNode != null && !focusedNode.isEditable && 
                    focusedNode.className?.toString()?.contains("EditText") != true &&
                    focusedNode.className?.toString()?.contains("AutoCompleteTextView") != true) {
                    @Suppress("DEPRECATION")
                    focusedNode.recycle()
                    focusedNode = null
                }
            }
            
            // Strategy 4: Last resort - find any editable (not ideal for multi-field forms)
            if (focusedNode == null) {
                AgentLogger.Auto.w("No focused node found, falling back to first editable - THIS MAY TYPE IN WRONG FIELD")
                focusedNode = findEditableNode(rootNode)

                // Give the node accessibility focus only — ACTION_CLICK would open the keyboard
                if (focusedNode != null) {
                    AgentLogger.Auto.d("Found editable node, granting accessibility focus (no click = no keyboard)")
                    focusedNode.performAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS)
                    Thread.sleep(50)
                }
            }

            if (focusedNode == null) {
                AgentLogger.Auto.w("No focused or editable node found for text input")
                @Suppress("DEPRECATION")
                rootNode.recycle()
                return false
            }
            
            AgentLogger.Auto.d("Using node for text input: class=${focusedNode.className}, text='${focusedNode.text}'")

            val arguments =
                Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }

            var success = focusedNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)

            // If SET_TEXT failed, try clearing first then setting
            if (!success) {
                AgentLogger.Auto.d("First SET_TEXT attempt failed, trying clear then set")
                val clearArgs = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "")
                }
                focusedNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, clearArgs)
                Thread.sleep(50)
                success = focusedNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
            }

            if (success) {
                AgentLogger.Auto.i("Text input successful", mapOf("text" to text))
                // Some apps show the keyboard as a side-effect of receiving focus/text.
                // Dismiss it immediately so it never obscures the UI for the next action.
                dismissKeyboard()
            } else {
                AgentLogger.Auto.w("ACTION_SET_TEXT failed, node may not support direct text input")
            }

            @Suppress("DEPRECATION")
            focusedNode.recycle()
            @Suppress("DEPRECATION")
            rootNode.recycle()
            success
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error performing text input", e)
            false
        }
    }

    fun launchApp(packageName: String) {
        try {
            val intent = packageManager.getLaunchIntentForPackage(packageName)
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                AgentLogger.Auto.d("Launched app", mapOf("packageName" to packageName))
            } else {
                AgentLogger.Auto.w("No launch intent found for package", mapOf("packageName" to packageName))
            }
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error launching app", e, mapOf("packageName" to packageName))
        }
    }

    fun findNodesByText(text: String) = uiTreeExtractor.findNodesByText(text)

    fun performClickOnNode(node: AccessibilityNodeInfo) {
        try {
            if (node.isClickable) {
                node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                AgentLogger.Auto.d("Performed click on node", mapOf("text" to node.text))
            } else {
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                performTap(bounds.centerX(), bounds.centerY())
                AgentLogger.Auto.d(
                    "Performed tap on node center",
                    mapOf("x" to bounds.centerX(), "y" to bounds.centerY()),
                )
            }
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error performing click on node", e)
        }
    }

    fun executeSystemAction(action: String, commandId: String? = null) {
        when (action.lowercase()) {
            "control_torch", "control_flashlight", "toggle_flashlight", "flashlight_on", "flashlight_off" -> {
                toggleFlashlight()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "wifi_on" -> {
                toggleWifi(true)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "wifi_off" -> {
                toggleWifi(false)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_wifi" -> {
                toggleWifi(null)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "bluetooth_on" -> {
                toggleBluetooth(true)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "bluetooth_off" -> {
                toggleBluetooth(false)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_bluetooth" -> {
                toggleBluetooth(null)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "volume_up" -> {
                adjustVolume(AudioManager.ADJUST_RAISE)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "volume_down" -> {
                adjustVolume(AudioManager.ADJUST_LOWER)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "mute" -> {
                adjustVolume(AudioManager.ADJUST_MUTE)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "unmute" -> {
                adjustVolume(AudioManager.ADJUST_UNMUTE)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "brightness_up" -> {
                adjustBrightness(true)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "brightness_down" -> {
                adjustBrightness(false)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            // ===== NEW SYSTEM CONTROLS (Google Assistant/Siri parity) =====
            "dnd_on", "do_not_disturb_on" -> {
                setDoNotDisturb(true)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "dnd_off", "do_not_disturb_off" -> {
                setDoNotDisturb(false)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_dnd", "toggle_do_not_disturb" -> {
                toggleDoNotDisturb()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "airplane_mode_on" -> {
                openAirplaneModeSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "airplane_mode_off" -> {
                openAirplaneModeSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "rotation_on", "auto_rotate_on" -> {
                setAutoRotate(true)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "rotation_off", "auto_rotate_off" -> {
                setAutoRotate(false)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_rotation", "toggle_auto_rotate" -> {
                toggleAutoRotate()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "battery_saver_on", "power_saver_on" -> {
                openBatterySaverSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "battery_saver_off", "power_saver_off" -> {
                openBatterySaverSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "dark_mode_on" -> {
                openDisplaySettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "dark_mode_off" -> {
                openDisplaySettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_dark_mode" -> {
                openDisplaySettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "location_on" -> {
                openLocationSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "location_off" -> {
                openLocationSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_location" -> {
                openLocationSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "mobile_data_on", "data_on" -> {
                openMobileDataSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "mobile_data_off", "data_off" -> {
                openMobileDataSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_mobile_data", "toggle_data" -> {
                openMobileDataSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "hotspot_on" -> {
                openHotspotSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "hotspot_off" -> {
                openHotspotSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_hotspot" -> {
                openHotspotSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "nfc_on" -> {
                openNfcSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "nfc_off" -> {
                openNfcSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "toggle_nfc" -> {
                openNfcSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "open_settings" -> {
                openSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "open_wifi_settings" -> {
                openWifiSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "open_bluetooth_settings" -> {
                openBluetoothSettings()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            // Keyboard control actions
            "dismiss_keyboard" -> {
                dismissKeyboard()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "press_enter" -> {
                performEnterAction()
                commandId?.let { sendGestureAck(it, true, null) }
            }
            "press_search" -> {
                pressKeyEvent(android.view.KeyEvent.KEYCODE_SEARCH)
                commandId?.let { sendGestureAck(it, true, null) }
            }
            else -> {
                AgentLogger.Auto.w("Unknown system action", mapOf("action" to action))
                commandId?.let { sendGestureAck(it, false, "Unknown action: $action") }
            }
        }
    }

    private fun findEditableNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val className = node.className?.toString().orEmpty()
        if ((node.isEditable || className.contains("EditText") || className.contains("AutoCompleteTextView")) && !className.contains("WebView")) {
            return node
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findEditableNode(child)
            if (result != null) return result
            @Suppress("DEPRECATION")
            child.recycle()
        }

        return null
    }

    /**
     * Returns the editable node whose screen bounds contain the point (x, y).
     * Used by Strategy 0 so that coordinator-supplied coordinates land on the
     * intended field without needing a tap.
     */
    private fun findEditableNodeAtPoint(node: AccessibilityNodeInfo, x: Int, y: Int): AccessibilityNodeInfo? {
        val className = node.className?.toString().orEmpty()
        val isEditable = node.isEditable || className.contains("EditText") || className.contains("AutoCompleteTextView")
        if (isEditable && !className.contains("WebView")) {
            val bounds = android.graphics.Rect()
            node.getBoundsInScreen(bounds)
            if (bounds.contains(x, y)) return node
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findEditableNodeAtPoint(child, x, y)
            if (result != null) return result
            @Suppress("DEPRECATION")
            child.recycle()
        }

        return null
    }
    
    /**
     * Find an editable node that has isFocused=true.
     * More reliable than findFocus(FOCUS_INPUT) for multi-field forms.
     */
    private fun findFocusedEditableNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val className = node.className?.toString().orEmpty()
        val isWebView = className.contains("WebView")
        val isEditable = node.isEditable || className.contains("EditText") || className.contains("AutoCompleteTextView")
        if (isEditable && !isWebView && node.isFocused) {
            return node
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findFocusedEditableNode(child)
            if (result != null) return result
            @Suppress("DEPRECATION")
            child.recycle()
        }

        return null
    }

    private fun toggleWifi(enable: Boolean?) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Android 10+: Use Quick Settings panel approach
                // Open quick settings and let user tap, or use Settings Panel
                AgentLogger.Auto.d("WiFi toggle requested on Android 10+, opening connectivity panel")
                val intent = Intent(Settings.Panel.ACTION_WIFI)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                return
            }

            @Suppress("DEPRECATION")
            val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            when (enable) {
                true -> wifiManager.isWifiEnabled = true
                false -> wifiManager.isWifiEnabled = false
                null -> wifiManager.isWifiEnabled = !wifiManager.isWifiEnabled
            }
            AgentLogger.Auto.d("WiFi toggled", mapOf("enabled" to (enable?.toString() ?: "toggle")))
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error toggling WiFi", e)
        }
    }

    private fun toggleBluetooth(enable: Boolean?) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                // Android 13+: Use Settings panel
                AgentLogger.Auto.d("Bluetooth toggle requested on Android 13+, opening bluetooth settings")
                val intent = Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                return
            }

            @Suppress("DEPRECATION")
            val bluetoothAdapter = BluetoothAdapter.getDefaultAdapter()
            bluetoothAdapter ?: return

            @Suppress("DEPRECATION")
            when (enable) {
                true -> bluetoothAdapter.enable()
                false -> bluetoothAdapter.disable()
                null -> if (bluetoothAdapter.isEnabled) bluetoothAdapter.disable() else bluetoothAdapter.enable()
            }
            AgentLogger.Auto.d("Bluetooth toggled", mapOf("enabled" to (enable?.toString() ?: "toggle")))
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error toggling Bluetooth", e)
        }
    }

    private fun toggleFlashlight() {
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            val cameraId = cameraManager.cameraIdList.firstOrNull() ?: return
            isFlashlightOn = !isFlashlightOn
            cameraManager.setTorchMode(cameraId, isFlashlightOn)
            AgentLogger.Auto.d("Flashlight toggled", mapOf("enabled" to isFlashlightOn))
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error toggling flashlight", e)
        }
    }

    private fun adjustVolume(direction: Int) {
        try {
            val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            audioManager.adjustVolume(direction, AudioManager.FLAG_SHOW_UI)
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error adjusting volume", e)
        }
    }

    private fun adjustBrightness(increase: Boolean) {
        try {
            val resolver = contentResolver
            val current = Settings.System.getInt(resolver, Settings.System.SCREEN_BRIGHTNESS, 128)
            val delta = if (increase) 32 else -32
            val newValue = (current + delta).coerceIn(10, 255)
            Settings.System.putInt(resolver, Settings.System.SCREEN_BRIGHTNESS, newValue)
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error adjusting brightness", e)
        }
    }

    // ===== NEW SYSTEM CONTROLS (Google Assistant/Siri parity) =====
    
    private fun setDoNotDisturb(enable: Boolean) {
        try {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (notificationManager.isNotificationPolicyAccessGranted) {
                val filter = if (enable) {
                    NotificationManager.INTERRUPTION_FILTER_NONE
                } else {
                    NotificationManager.INTERRUPTION_FILTER_ALL
                }
                notificationManager.setInterruptionFilter(filter)
                AgentLogger.Auto.d("Do Not Disturb set", mapOf("enabled" to enable))
            } else {
                // Open DND settings if no permission
                val intent = Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                AgentLogger.Auto.w("DND access not granted, opening settings")
            }
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error setting Do Not Disturb", e)
        }
    }

    private fun toggleDoNotDisturb() {
        try {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (notificationManager.isNotificationPolicyAccessGranted) {
                val currentFilter = notificationManager.currentInterruptionFilter
                val isCurrentlyEnabled = currentFilter != NotificationManager.INTERRUPTION_FILTER_ALL
                setDoNotDisturb(!isCurrentlyEnabled)
            } else {
                val intent = Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            }
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error toggling Do Not Disturb", e)
        }
    }

    private fun setAutoRotate(enable: Boolean) {
        try {
            Settings.System.putInt(
                contentResolver,
                Settings.System.ACCELEROMETER_ROTATION,
                if (enable) 1 else 0
            )
            AgentLogger.Auto.d("Auto-rotate set", mapOf("enabled" to enable))
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error setting auto-rotate", e)
        }
    }

    private fun toggleAutoRotate() {
        try {
            val currentValue = Settings.System.getInt(
                contentResolver,
                Settings.System.ACCELEROMETER_ROTATION,
                0
            )
            setAutoRotate(currentValue == 0)
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error toggling auto-rotate", e)
        }
    }

    private fun openAirplaneModeSettings() {
        try {
            val intent = Intent(Settings.ACTION_AIRPLANE_MODE_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened airplane mode settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening airplane mode settings", e)
        }
    }

    private fun openBatterySaverSettings() {
        try {
            val intent = Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened battery saver settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening battery saver settings", e)
        }
    }

    private fun openDisplaySettings() {
        try {
            val intent = Intent(Settings.ACTION_DISPLAY_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened display settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening display settings", e)
        }
    }

    private fun openLocationSettings() {
        try {
            val intent = Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened location settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening location settings", e)
        }
    }

    private fun openMobileDataSettings() {
        try {
            val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY)
            } else {
                Intent(Settings.ACTION_DATA_ROAMING_SETTINGS)
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened mobile data settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening mobile data settings", e)
        }
    }

    private fun openHotspotSettings() {
        try {
            val intent = Intent(Settings.ACTION_WIRELESS_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened hotspot settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening hotspot settings", e)
        }
    }

    private fun openNfcSettings() {
        try {
            val intent = Intent(Settings.ACTION_NFC_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened NFC settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening NFC settings", e)
        }
    }

    private fun openSettings() {
        try {
            val intent = Intent(Settings.ACTION_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened main settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening settings", e)
        }
    }

    private fun openWifiSettings() {
        try {
            val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened WiFi settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening WiFi settings", e)
        }
    }

    private fun openBluetoothSettings() {
        try {
            val intent = Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            AgentLogger.Auto.d("Opened Bluetooth settings")
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error opening Bluetooth settings", e)
        }
    }

    fun captureScreen(): String? {
        return try {
            // Use a CountDownLatch to wait for async screenshot capture
            val latch = java.util.concurrent.CountDownLatch(1)
            var screenshotBase64: String? = null
            
            screenCaptureManager.captureScreenWithAnalysis(force = true) { screenshotData ->
                screenshotBase64 = screenshotData.screenshot
                latch.countDown()
            }
            
            // Wait up to 5 seconds for screenshot (must be < backend's 8s timeout)
            val received = latch.await(5, java.util.concurrent.TimeUnit.SECONDS)
            if (!received) {
                AgentLogger.Screen.w("Screenshot capture timed out (5s)")
                return null
            }
            
            if (screenshotBase64.isNullOrEmpty()) {
                AgentLogger.Screen.w("Screenshot data is empty, retrying once...")
                // Retry once after a short pause - MediaProjection may need a frame cycle
                val retryLatch = java.util.concurrent.CountDownLatch(1)
                var retryBase64: String? = null
                Thread.sleep(500)
                screenCaptureManager.captureScreenWithAnalysis(force = true) { retryData ->
                    retryBase64 = retryData.screenshot
                    retryLatch.countDown()
                }
                val retryReceived = retryLatch.await(5, java.util.concurrent.TimeUnit.SECONDS)
                if (retryReceived && !retryBase64.isNullOrEmpty()) {
                    AgentLogger.Screen.i("📸 Screenshot retry succeeded: ${retryBase64?.length ?: 0} chars")
                    return retryBase64
                }
                AgentLogger.Screen.w("Screenshot retry also empty")
                return null
            }
            
            AgentLogger.Screen.i("📸 Screenshot captured: ${screenshotBase64?.length ?: 0} chars")
            screenshotBase64
        } catch (e: Exception) {
            AgentLogger.Screen.e("Error capturing screen", e)
            null
        }
    }

    fun captureScreenWithUI(): Map<String, Any>? {
        return try {
            val uiElements = uiTreeExtractor.getUIElements()

            mapOf(
                "timestamp" to System.currentTimeMillis(),
                "screenWidth" to screenCaptureManager.screenWidth,
                "screenHeight" to screenCaptureManager.screenHeight,
                "uiElements" to
                    uiElements.map { element ->
                        mapOf(
                            "text" to (element.text ?: ""),
                            "contentDescription" to (element.contentDescription ?: ""),
                            "className" to (element.className ?: ""),
                            "isClickable" to element.isClickable,
                            "isScrollable" to element.isScrollable,
                            "isEnabled" to element.isEnabled,
                            "packageName" to (element.packageName ?: ""),
                            "viewId" to (element.viewId ?: ""),
                            "bounds" to
                                mapOf(
                                    "left" to element.bounds.left,
                                    "top" to element.bounds.top,
                                    "right" to element.bounds.right,
                                    "bottom" to element.bounds.bottom,
                                    "centerX" to element.bounds.centerX,
                                    "centerY" to element.bounds.centerY,
                                    "width" to element.bounds.width,
                                    "height" to element.bounds.height,
                                ),
                        )
                    },
            )
        } catch (e: Exception) {
            AgentLogger.UI.e("Error capturing UI data", e)
            null
        }
    }

    fun getUITree(): Map<String, Any>? {
        return uiTreeExtractor.getUITree()
    }

    /**
     * Get screen width from ScreenCaptureManager
     */
    fun getScreenWidth(): Int {
        return screenCaptureManager.screenWidth
    }

    /**
     * Get screen height from ScreenCaptureManager
     */
    fun getScreenHeight(): Int {
        return screenCaptureManager.screenHeight
    }

    private fun registerDeviceWithBackend() {
        if (!isRegistering.compareAndSet(false, true)) {
            AgentLogger.Auto.i("⏭️ Registration already in progress, skipping")
            return
        }

        backendCommunicator.registerDevice(
            screenCaptureManager.screenWidth,
            screenCaptureManager.screenHeight,
            resources.displayMetrics.densityDpi,
        ) { success ->
            isRegistering.set(false)
            if (success) {
                AgentLogger.Auto.i("✅ Device registered - UI data will be sent only on explicit request")
                // Periodic updates disabled to prevent latency - use triggerScreenshotCapture() when needed
                // commandPollingManager.startPeriodicUpdates()
            }
        }
    }

    private fun cleanup() {
        gestureInjector.cancelAll()
        // Always restore keyboard show-mode before tearing down — dismissKeyboard()
        // is called inline after every type gesture to suppress the IME during
        // automation. If the session ends without an explicit restore_keyboard
        // command (app killed, WebSocket drop, etc.) the keyboard would stay
        // permanently hidden until the accessibility service is toggled.
        restoreKeyboard()
        // Command polling removed - all commands now use WebSocket
        serviceScope.cancel()
        screenCaptureManager.cleanup()
        backendCommunicator.cleanup()

        AgentLogger.UI.i("Service cleanup completed")
    }
}
