package com.aura.aura_ui.presentation.overlay

import android.content.Context
import android.util.Log
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import com.aura.aura_ui.services.LiveUpdateNotificationHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

/**
 * Central manager for overlay system
 * Handles WebSocket sync, state management, and screenshot exclusion
 */
class OverlayManager(
    private val context: Context,
    private val scope: CoroutineScope,
    private val serverUrl: String,
) {
    private var floatingOverlay: FloatingMicOverlay? = null
    private var webSocket: WebSocket? = null
    private val httpClient =
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MINUTES) // No timeout for WebSocket
            .build()

    // State flows for UI updates
    private val _overlayState = MutableStateFlow<OverlayState>(OverlayState.Idle)
    val overlayState: StateFlow<OverlayState> = _overlayState

    private val _userTranscript = MutableStateFlow("")
    val userTranscript: StateFlow<String> = _userTranscript

    private val _assistantResponse = MutableStateFlow("")
    val assistantResponse: StateFlow<String> = _assistantResponse

    companion object {
        private const val TAG = "OverlayManager"
    }

    fun initialize() {
        Log.d(TAG, "Initializing OverlayManager")

        // Register with AccessibilityService
        AuraAccessibilityService.instance?.let { service ->
            // Set reference for screenshot exclusion
            Log.d(TAG, "Registered with AccessibilityService")
        }

        // Create overlay
        floatingOverlay =
            FloatingMicOverlay(
                context = context,
                onMicClick = ::handleMicClick,
                onMicLongClick = ::handleMicLongClick,
                onPositionChanged = ::savePosition,
            )

        // Observe state changes — drive both the overlay orb and the Live Update chip
        scope.launch {
            overlayState.collect { state ->
                floatingOverlay?.updateExpandedState(state)

                // Show/cancel the Live Update status bar chip based on phase.
                // The chip carries execution status; the bubble stays compact.
                when (state) {
                    OverlayState.Processing ->
                        LiveUpdateNotificationHelper.show(context, "Executing task...")
                    OverlayState.Listening ->
                        LiveUpdateNotificationHelper.cancel(context)
                    OverlayState.Idle, OverlayState.Error ->
                        LiveUpdateNotificationHelper.cancel(context)
                    else -> { /* Speaking: leave chip visible until idle */ }
                }
            }
        }

        scope.launch {
            userTranscript.collect { user ->
                floatingOverlay?.updateTranscript(user, _assistantResponse.value)
            }
        }

        scope.launch {
            assistantResponse.collect { assistant ->
                floatingOverlay?.updateTranscript(_userTranscript.value, assistant)
            }
        }

        // Connect to backend WebSocket
        connectWebSocket()
    }

    fun show() {
        Log.d(TAG, "OverlayManager.show() called")
        floatingOverlay?.show()
        Log.d(TAG, "FloatingMicOverlay.show() completed")
    }

    fun hide() {
        floatingOverlay?.hide()
        disconnect()
    }

    fun hideTemporarily(durationMs: Long = 200) {
        // TODO: Implement temporary hiding for screenshots
        floatingOverlay?.updatePosition(-1000f, -1000f) // Move off-screen
        scope.launch {
            kotlinx.coroutines.delay(durationMs)
            // Restore position
        }
    }

    private fun handleMicClick() {
        when (_overlayState.value) {
            OverlayState.Idle -> startListening()
            OverlayState.Listening -> stopListening()
            else -> {
                // Ignore during processing/speaking
            }
        }
    }

    private fun handleMicLongClick() {
        floatingOverlay?.expandPanel()
    }

    private fun savePosition(
        x: Float,
        y: Float,
    ) {
        // Save to SharedPreferences for persistence
        context.getSharedPreferences("overlay_prefs", Context.MODE_PRIVATE)
            .edit()
            .putFloat("overlay_x", x)
            .putFloat("overlay_y", y)
            .apply()
    }

    private fun connectWebSocket() {
        val wsUrl = serverUrl.replace("http://", "ws://").replace("https://", "wss://")
        val request =
            Request.Builder()
                .url("$wsUrl/ws/conversation")
                .build()

        webSocket =
            httpClient.newWebSocket(
                request,
                object : WebSocketListener() {
                    override fun onOpen(
                        webSocket: WebSocket,
                        response: okhttp3.Response,
                    ) {
                        Log.d(TAG, "WebSocket connected")
                    }

                    override fun onMessage(
                        webSocket: WebSocket,
                        text: String,
                    ) {
                        Log.d(TAG, "WebSocket message: $text")
                        handleWebSocketMessage(text)
                    }

                    override fun onFailure(
                        webSocket: WebSocket,
                        t: Throwable,
                        response: okhttp3.Response?,
                    ) {
                        Log.e(TAG, "WebSocket error", t)
                        _overlayState.value = OverlayState.Error
                    }

                    override fun onClosed(
                        webSocket: WebSocket,
                        code: Int,
                        reason: String,
                    ) {
                        Log.d(TAG, "WebSocket closed: $reason")
                    }
                },
            )
    }

    private fun handleWebSocketMessage(message: String) {
        try {
            val json = org.json.JSONObject(message)
            val type = json.optString("type", "")

            when (type) {
                "state_update" -> {
                    val state = json.optString("state", "idle")
                    _overlayState.value =
                        when (state) {
                            "listening" -> OverlayState.Listening
                            "processing" -> OverlayState.Processing
                            "speaking" -> OverlayState.Speaking
                            "error" -> OverlayState.Error
                            else -> OverlayState.Idle
                        }
                }
                "transcript" -> {
                    _userTranscript.value = json.optString("text", "")
                }
                "response" -> {
                    _assistantResponse.value = json.optString("text", "")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing WebSocket message", e)
        }
    }

    private fun startListening() {
        _overlayState.value = OverlayState.Listening
        _userTranscript.value = ""
        _assistantResponse.value = ""

        // Send WebSocket message to start capture
        webSocket?.send("""{"action":"start_listening"}""")
    }

    private fun stopListening() {
        _overlayState.value = OverlayState.Processing

        // Send WebSocket message to stop capture
        webSocket?.send("""{"action":"stop_listening"}""")
    }

    fun disconnect() {
        webSocket?.close(1000, "User closed overlay")
        webSocket = null
    }
}
