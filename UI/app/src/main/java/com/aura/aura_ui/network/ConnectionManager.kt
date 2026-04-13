package com.aura.aura_ui.network

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.min
import kotlin.math.pow

/**
 * Represents the lifecycle state of the persistent WebSocket connection.
 */
sealed class ConnectionState {
    /** No active connection and no reconnect scheduled. */
    data object Disconnected : ConnectionState()

    /** Initial TCP handshake + WebSocket upgrade in progress. */
    data object Connecting : ConnectionState()

    /** Connection is open and messages can flow. */
    data class Connected(val serverUrl: String) : ConnectionState()

    /**
     * Connection dropped; waiting [delayMs]ms before attempt [attempt].
     * The UI can display a "Reconnecting…" indicator using this state.
     */
    data class Reconnecting(val attempt: Int, val delayMs: Long) : ConnectionState()

    /** Permanently stopped (service shut down). */
    data object Stopped : ConnectionState()
}

/**
 * Manages a single, persistent OkHttp WebSocket connection to the AURA backend
 * `/ws/device` endpoint.
 *
 * Key design decisions:
 * - **No read timeout**: WebSocket connections are long-lived; read timeouts only
 *   apply to HTTP upgrade requests (handled by connectTimeout).
 * - **Built-in OkHttp ping**: `pingInterval` causes OkHttp to send WS-level PING
 *   frames every [PING_INTERVAL_MS]ms; the broker's PONG resets our liveness clock.
 * - **Exponential backoff**: 1 s → 2 s → 4 s → … → capped at 30 s between retries.
 * - **Message queue**: outgoing messages sent while disconnected are buffered in an
 *   unlimited Channel and drained immediately when the socket reconnects.
 * - **Single active connection**: old WebSocket is always closed before creating a
 *   new one so the server never sees duplicate device sessions.
 */
@Singleton
class ConnectionManager @Inject constructor() {

    companion object {
        private const val TAG = "ConnectionManager"
        private const val WS_PATH = "/ws/device"
        private const val PING_INTERVAL_MS = 20_000L    // send PING every 20 s
        private const val PONG_TIMEOUT_MS = 12_000L     // allow 12 s for PONG reply
        private const val INITIAL_BACKOFF_MS = 1_000L
        private const val MAX_BACKOFF_MS = 30_000L
    }

    private val _state = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    /** Listener set by consumers (e.g. AuraAccessibilityService) to handle server messages. */
    var onMessage: ((String) -> Unit)? = null

    private val messageQueue = Channel<String>(capacity = Channel.UNLIMITED)
    private val reconnectAttempt = AtomicInteger(0)

    @Volatile private var webSocket: WebSocket? = null
    @Volatile private var serverUrl: String = ""
    private var scope: CoroutineScope? = null
    private var heartbeatJob: Job? = null
    private var reconnectJob: Job? = null
    private var lastActivityMs: Long = 0L

    /**
     * Dedicated OkHttpClient for WebSocket:
     * - readTimeout = 0 means OkHttp never times out reads (correct for WS).
     * - pingInterval lets OkHttp send frames automatically; we layer our own
     *   liveness check on top for belt-and-suspenders reliability.
     */
    private val wsClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .pingInterval(PING_INTERVAL_MS, TimeUnit.MILLISECONDS)
        .retryOnConnectionFailure(false) // We own the retry logic
        .build()

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Start the connection manager. Call once from [AssistantForegroundService.onCreate].
     * [scope] should be the service's lifecycleScope so the coroutines are cancelled
     * automatically when the service is destroyed.
     */
    fun start(serverUrl: String, scope: CoroutineScope) {
        this.serverUrl = serverUrl
        this.scope = scope
        reconnectAttempt.set(0)
        connect()
    }

    /**
     * Update the target server URL and immediately reconnect.
     * Safe to call while already connected — the old socket is closed cleanly.
     */
    fun updateServerUrl(newUrl: String) {
        serverUrl = newUrl
        Log.i(TAG, "Server URL updated to $newUrl — reconnecting")
        reconnectJob?.cancel()
        heartbeatJob?.cancel()
        webSocket?.close(1001, "URL changed") // 1001 = Going Away
        webSocket = null
        reconnectAttempt.set(0)
        connect()
    }

    /**
     * Send a text message. If the socket is currently open the message is sent
     * immediately; otherwise it is queued and delivered once the connection
     * is re-established.
     *
     * @return true if sent immediately, false if queued.
     */
    fun send(message: String): Boolean {
        val ws = webSocket
        return if (ws != null && _state.value is ConnectionState.Connected) {
            val ok = ws.send(message)
            if (!ok) {
                messageQueue.trySend(message)
            }
            ok
        } else {
            messageQueue.trySend(message).isSuccess
        }
    }

    /**
     * Gracefully close the connection and stop all reconnection attempts.
     * Call from [AssistantForegroundService.onDestroy].
     */
    fun stop() {
        Log.i(TAG, "ConnectionManager stopping")
        reconnectJob?.cancel()
        heartbeatJob?.cancel()
        webSocket?.close(1000, "Service stopped")
        webSocket = null
        scope = null
        _state.value = ConnectionState.Stopped
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private fun connect() {
        if (_state.value == ConnectionState.Stopped) return
        val currentScope = scope ?: return

        val wsUrl = serverUrl
            .replace("http://", "ws://")
            .replace("https://", "wss://")
            .trimEnd('/') + WS_PATH

        val attempt = reconnectAttempt.get()
        Log.i(TAG, "Connecting to $wsUrl (attempt $attempt)")
        _state.value = ConnectionState.Connecting

        val request = Request.Builder().url(wsUrl).build()

        webSocket = wsClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "✅ WebSocket connected — $wsUrl")
                reconnectAttempt.set(0)
                lastActivityMs = System.currentTimeMillis()
                _state.value = ConnectionState.Connected(serverUrl)

                currentScope.launch { drainQueue(webSocket) }
                startHeartbeatMonitor(webSocket, currentScope)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                lastActivityMs = System.currentTimeMillis()
                onMessage?.invoke(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.w(TAG, "Peer closing: $code $reason")
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.w(TAG, "WebSocket closed: $code $reason")
                heartbeatJob?.cancel()
                if (code == 1000 && _state.value == ConnectionState.Stopped) {
                    // Clean stop — stay Stopped
                    _state.value = ConnectionState.Stopped
                } else {
                    scheduleReconnect(currentScope)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket failure: ${t.message}")
                heartbeatJob?.cancel()
                scheduleReconnect(currentScope)
            }
        })
    }

    private fun scheduleReconnect(scope: CoroutineScope) {
        if (_state.value == ConnectionState.Stopped) return

        val attempt = reconnectAttempt.incrementAndGet()
        // backoff = 1s * 2^(attempt-1), capped at MAX_BACKOFF_MS
        val delayMs = min(
            (INITIAL_BACKOFF_MS * 2.0.pow((attempt - 1).toDouble())).toLong(),
            MAX_BACKOFF_MS
        )

        Log.i(TAG, "Reconnecting in ${delayMs}ms (attempt $attempt)")
        _state.value = ConnectionState.Reconnecting(attempt, delayMs)

        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(delayMs)
            if (isActive && _state.value !is ConnectionState.Stopped) {
                connect()
            }
        }
    }

    /**
     * Monitors whether we are receiving any activity (messages or OkHttp PONG frames).
     * If [PING_INTERVAL_MS] + [PONG_TIMEOUT_MS] passes without activity, forcefully
     * cancels the socket to trigger [WebSocketListener.onFailure] → [scheduleReconnect].
     */
    private fun startHeartbeatMonitor(ws: WebSocket, scope: CoroutineScope) {
        heartbeatJob?.cancel()
        heartbeatJob = scope.launch {
            while (isActive) {
                delay(PING_INTERVAL_MS + PONG_TIMEOUT_MS)
                val silent = System.currentTimeMillis() - lastActivityMs
                if (silent > PING_INTERVAL_MS + PONG_TIMEOUT_MS) {
                    Log.w(TAG, "No server activity for ${silent}ms — forcing reconnect")
                    ws.cancel() // triggers onFailure → scheduleReconnect
                    break
                }
            }
        }
    }

    private suspend fun drainQueue(ws: WebSocket) {
        var msg = messageQueue.tryReceive().getOrNull()
        while (msg != null) {
            ws.send(msg)
            msg = messageQueue.tryReceive().getOrNull()
        }
    }
}
