package com.aura.aura_ui.voice

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.util.Base64
import android.util.Log
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import com.aura.aura_ui.audio.PcmStreamPlayer
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.conversation.ConversationViewModel
import com.aura.aura_ui.overlay.AuraOverlayService
import com.aura.aura_ui.overlay.HITLHandler
import com.aura.aura_ui.overlay.VisualFeedbackHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Gemini Live bidirectional audio controller — fully continuous/hands-free mode.
 *
 * Once [startCapture] is called the controller enters SESSION mode and runs a
 * continuous listen→respond→listen loop:
 *
 *   LISTENING  → user speaks → VAD silence → THINKING
 *   THINKING   → server streams audio_response chunks → RESPONDING
 *   RESPONDING → audio queue drained + turn complete → LISTENING  (wave back!)
 *   executing  → task_progress:executing → THINKING (mic paused for automation)
 *   idle       → task_progress:idle     → LISTENING (mic restarted after automation)
 *
 * The wave animation therefore runs continuously except during automation tasks.
 * The session ends only when [cancelCapture] is called (user presses "stop" button).
 *
 * Audio playback design:
 *   A single [audioPlayerJob] coroutine drains [audioQueue] — no per-chunk
 *   coroutines, no AudioTrack instance explosion.
 *
 * Outgoing to server (/ws/live):
 *   {"type": "audio_chunk",  "data": "<base64 PCM 16 kHz mono int16>"}
 *   {"type": "screenshot",   "data": "<base64 JPEG>"}   (every ~3 s while recording)
 *   {"type": "ui_tree",      "tree": {...}}              (every ~5 s while recording)
 *   {"type": "ping"}
 *
 * Incoming from server (/ws/live):
 *   {"type": "audio_response", "data": "<base64 PCM 24 kHz mono int16>"}
 *   {"type": "transcript",     "text": "..."}
 *   {"type": "task_progress",  "status": "executing"|"idle"}
 *   {"type": "error",          "message": "..."}
 *   {"type": "pong"}
 */
class GeminiLiveController(
    private val context: Context,
    private val serverUrl: String,
    private val viewModel: ConversationViewModel,
    private val scope: CoroutineScope,
    private val onAmplitudeUpdate: ((Float) -> Unit)? = null,
) {

    // ── Recording constants ───────────────────────────────────────────────────
    companion object {
        private const val TAG = "GeminiLiveCtrl"
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val CHUNK_MS = 100
        private const val SCREENSHOT_INTERVAL_MS = 3000L
        private const val UI_TREE_INTERVAL_MS = 5000L
        private const val PING_INTERVAL_MS = 25_000L
    }

    // ── OkHttp ───────────────────────────────────────────────────────────────
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // ── Connection state ──────────────────────────────────────────────────────
    private var webSocket: WebSocket? = null
    private var sessionId: String = UUID.randomUUID().toString()
    private val isConnected = AtomicBoolean(false)

    // ── Recording state ───────────────────────────────────────────────────────
    private val isRecording = AtomicBoolean(false)
    // True while the user's session is active (started by startCapture,
    // cleared by cancelCapture). Drives the auto-restart loop.
    private val sessionActive = AtomicBoolean(false)
    /** True while a bidirectional session is running — used by UI to gate wave animation. */
    val isSessionActive: Boolean get() = sessionActive.get()

    // ── Audio recording ───────────────────────────────────────────────────────
    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null
    private var screenshotJob: Job? = null
    private var pingJob: Job? = null
    private val vadDetector = SimpleVAD()

    // ── Audio playback (single-consumer queue pattern) ────────────────────────
    private val pcmPlayer = PcmStreamPlayer()
    private val audioQueue = ConcurrentLinkedQueue<ByteArray>()
    private var audioPlayerJob: Job? = null
    // Set true when server sends task_progress:idle — player drains then
    // restarts listening instead of going IDLE.
    private val isTurnComplete = AtomicBoolean(false)

    // ── Public API ────────────────────────────────────────────────────────────

    /** Connect to /ws/live. Returns true on success. */
    suspend fun connect(): Boolean = withContext(Dispatchers.IO) {
        if (isConnected.get()) return@withContext true

        sessionId = UUID.randomUUID().toString()
        val wsUrl = serverUrl
            .replace("http://", "ws://")
            .replace("https://", "wss://")
            .trimEnd('/') + "/ws/live?session_id=$sessionId"

        Log.i(TAG, "Connecting to Gemini Live: $wsUrl")

        var connectionResult = false
        val latch = java.util.concurrent.CountDownLatch(1)

        webSocket = client.newWebSocket(
            Request.Builder().url(wsUrl).build(),
            object : WebSocketListener() {

                override fun onOpen(ws: WebSocket, response: Response) {
                    Log.i(TAG, "✅ Gemini Live WebSocket connected")
                    isConnected.set(true)
                    connectionResult = true
                    latch.countDown()

                    scope.launch {
                        viewModel.updateServerConnection(true)
                        viewModel.updatePartialTranscript("Gemini Live connected!")
                    }

                    HITLHandler.setResponseCallback { resp -> ws.send(resp.toString()) }
                    startPingLoop()
                }

                override fun onMessage(ws: WebSocket, text: String) {
                    handleMessage(text)
                }

                override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                    Log.e(TAG, "WebSocket failure: ${t.message}")
                    isConnected.set(false)
                    connectionResult = false
                    latch.countDown()
                    scope.launch {
                        viewModel.updateServerConnection(false)
                        viewModel.setError("Gemini Live connection failed: ${t.message}")
                    }
                }

                override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closing: $reason")
                    isConnected.set(false)
                    scope.launch { viewModel.updateServerConnection(false) }
                }

                override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closed: $reason")
                    isConnected.set(false)
                }
            }
        )

        try {
            latch.await(6, TimeUnit.SECONDS)
        } catch (_: InterruptedException) {}

        connectionResult
    }

    /**
     * Start the continuous bidirectional session.
     *
     * After this call the controller enters SESSION mode: it will keep the
     * microphone active between turns, restarting capture automatically after
     * each AI response completes.  The session ends only on [cancelCapture].
     */
    fun startCapture() {
        if (isRecording.get()) return
        if (!isConnected.get()) {
            Log.w(TAG, "Cannot start capture — not connected")
            return
        }

        sessionActive.set(true)
        stopAudioPlayer()
        audioQueue.clear()
        isTurnComplete.set(false)

        startMicInternal()
    }

    /**
     * Internal mic start — used by [startCapture] and the auto-restart path.
     * Does not modify [sessionActive].
     */
    private fun startMicInternal() {
        if (isRecording.get()) return
        if (!isConnected.get()) return

        try {
            val chunkSize = (SAMPLE_RATE * CHUNK_MS / 1000) * 2
            val bufferSize = maxOf(
                AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT),
                chunkSize
            )
            @Suppress("MissingPermission")
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT, bufferSize
            )
            audioRecord?.startRecording()
            isRecording.set(true)
            vadDetector.reset()

            viewModel.updatePhase(ConversationPhase.LISTENING)
            viewModel.updatePartialTranscript("🎤 Listening...")

            recordingJob = scope.launch(Dispatchers.IO) { streamAudioToGemini(chunkSize) }
            screenshotJob = scope.launch(Dispatchers.IO) { streamScreenContext() }

            Log.i(TAG, "🎤 Gemini Live capture started (session active)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start capture: ${e.message}", e)
            viewModel.setError("Recording error: ${e.message}")
            sessionActive.set(false)
        }
    }

    /**
     * Stop recording after VAD or explicit server signal.
     * Session remains active — mic will restart after AI responds.
     */
    fun stopCapture() {
        if (!isRecording.get()) return
        isRecording.set(false)
        recordingJob?.cancel()
        recordingJob = null
        screenshotJob?.cancel()
        screenshotJob = null

        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        onAmplitudeUpdate?.invoke(0f)
        viewModel.updatePhase(ConversationPhase.THINKING)

        sendJson(JSONObject().apply { put("type", "end_turn") })
        Log.d(TAG, "Gemini Live capture stopped (session still active: ${sessionActive.get()})")
    }

    /**
     * Cancel recording and END the session.
     * The wave animation stops and capture will not auto-restart.
     */
    fun cancelCapture() {
        sessionActive.set(false)
        isRecording.set(false)
        recordingJob?.cancel()
        recordingJob = null
        screenshotJob?.cancel()
        screenshotJob = null

        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        stopAudioPlayer()
        audioQueue.clear()
        onAmplitudeUpdate?.invoke(0f)
        viewModel.updatePhase(ConversationPhase.IDLE)
        viewModel.updatePartialTranscript("")
        Log.d(TAG, "Gemini Live capture cancelled (session ended)")
    }

    fun sendTextCommand(text: String) {
        if (!isConnected.get()) return
        sendJson(JSONObject().apply { put("type", "text_command"); put("text", text) })
    }

    fun sendCancelTask() {
        if (!isConnected.get()) return
        sendJson(JSONObject().apply { put("type", "cancel_task"); put("session_id", sessionId) })
    }

    fun cleanup() {
        cancelCapture()
        pingJob?.cancel()
        pingJob = null
        webSocket?.close(1000, "Gemini Live controller cleanup")
        webSocket = null
        isConnected.set(false)
        Log.d(TAG, "GeminiLiveController cleaned up")
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private suspend fun streamAudioToGemini(chunkSize: Int) {
        val buffer = ByteArray(chunkSize)
        var speechDetected = false
        var silenceFrames = 0
        val silenceThreshold = 20 // ~2 s at 100 ms chunks

        while (isRecording.get()) {
            val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0
            if (bytesRead <= 0) continue

            val amplitude = calculateAmplitude(buffer, bytesRead)
            withContext(Dispatchers.Main) { onAmplitudeUpdate?.invoke(amplitude) }

            val isSpeech = vadDetector.isSpeech(buffer, bytesRead)
            if (isSpeech) {
                silenceFrames = 0
                speechDetected = true
            } else if (speechDetected) {
                silenceFrames++
            }

            val encoded = Base64.encodeToString(buffer.copyOf(bytesRead), Base64.NO_WRAP)
            sendJson(JSONObject().apply { put("type", "audio_chunk"); put("data", encoded) })

            if (speechDetected && silenceFrames >= silenceThreshold) {
                Log.i(TAG, "✋ VAD silence detected — auto-stopping Gemini Live capture")
                withContext(Dispatchers.Main) { stopCapture() }
                break
            }
        }
    }

    private suspend fun streamScreenContext() {
        var lastScreenshotMs = 0L
        var lastUiTreeMs = 0L

        while (isRecording.get()) {
            val now = System.currentTimeMillis()
            if (now - lastScreenshotMs >= SCREENSHOT_INTERVAL_MS) {
                captureAndSendScreenshot(); lastScreenshotMs = now
            }
            if (now - lastUiTreeMs >= UI_TREE_INTERVAL_MS) {
                captureAndSendUiTree(); lastUiTreeMs = now
            }
            delay(500)
        }
    }

    private fun captureAndSendScreenshot() {
        val service = AuraAccessibilityService.instance ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return
        try {
            service.screenCaptureManager?.captureScreenWithAnalysis(force = true) { data ->
                if (data.screenshot.isNotEmpty() && !data.screenshot.startsWith("error")) {
                    sendJson(JSONObject().apply { put("type", "screenshot"); put("data", data.screenshot) })
                }
            }
        } catch (e: Exception) { Log.w(TAG, "Screenshot failed: ${e.message}") }
    }

    private fun captureAndSendUiTree() {
        val service = AuraAccessibilityService.instance ?: return
        try {
            val elements = service.uiTreeExtractor?.getUIElements() ?: return
            val pkg = service.rootInActiveWindow?.packageName?.toString() ?: "unknown"
            val treeArray = org.json.JSONArray()
            elements.take(60).forEach { el ->
                treeArray.put(JSONObject().apply {
                    put("text", el.text ?: ""); put("desc", el.contentDescription ?: "")
                    put("class", el.className ?: ""); put("clickable", el.isClickable)
                    put("scrollable", el.isScrollable)
                })
            }
            sendJson(JSONObject().apply {
                put("type", "ui_tree"); put("packageName", pkg)
                put("tree", JSONObject().apply { put("elements", treeArray); put("count", elements.size) })
            })
        } catch (e: Exception) { Log.w(TAG, "UI tree capture failed: ${e.message}") }
    }

    private fun startPingLoop() {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (isActive && isConnected.get()) {
                delay(PING_INTERVAL_MS)
                if (isConnected.get()) sendJson(JSONObject().put("type", "ping"))
            }
        }
    }

    /**
     * Ensure the single audio-player coroutine is running.
     *
     * Enqueues happen on the WebSocket thread; only one consumer coroutine
     * ever writes to PcmStreamPlayer.
     *
     * After the queue drains AND [isTurnComplete] is true, the coroutine
     * restarts the microphone (bidirectional mode) instead of going IDLE.
     */
    private fun ensureAudioPlayerRunning() {
        if (audioPlayerJob?.isActive == true) return

        audioPlayerJob = scope.launch(Dispatchers.IO) {
            pcmPlayer.start()
            withContext(Dispatchers.Main) {
                viewModel.updatePhase(ConversationPhase.RESPONDING)
            }

            // Drain the queue
            while (isActive) {
                val chunk = audioQueue.poll()
                when {
                    chunk != null -> pcmPlayer.writeChunk(chunk)
                    isTurnComplete.get() -> break
                    else -> delay(10)
                }
            }
            // Drain any last stragglers
            var remaining: ByteArray?
            while (audioQueue.poll().also { remaining = it } != null) {
                pcmPlayer.writeChunk(remaining!!)
            }

            pcmPlayer.stop()
            isTurnComplete.set(false)
            audioPlayerJob = null

            // ── Bidirectional auto-restart ─────────────────────────────────
            // After AI finishes speaking, go back to LISTENING automatically
            // so the user can speak again without pressing any button.
            // Only restart if the session is still active AND we're not
            // recording (user might have pressed mic again already).
            if (sessionActive.get() && !isRecording.get()) {
                Log.d(TAG, "Audio drained — restarting mic for bidirectional session")
                withContext(Dispatchers.Main) { startMicInternal() }
            } else if (!sessionActive.get()) {
                // Session was cancelled while audio was playing
                withContext(Dispatchers.Main) {
                    viewModel.updatePhase(ConversationPhase.IDLE)
                    AuraOverlayService.restore(context)
                }
            }
        }
    }

    private fun stopAudioPlayer() {
        audioPlayerJob?.cancel()
        audioPlayerJob = null
        pcmPlayer.stop()
    }

    private fun handleMessage(text: String) {
        try {
            val json = JSONObject(text)
            when (val type = json.getString("type")) {

                "audio_response" -> {
                    // Enqueue for the single player coroutine — never launch per-chunk.
                    val data = json.optString("data", "")
                    if (data.isNotEmpty()) {
                        audioQueue.offer(Base64.decode(data, Base64.DEFAULT))
                        ensureAudioPlayerRunning()
                    }
                }

                "transcript" -> {
                    val transcript = json.optString("text", "")
                    val isFinal = json.optBoolean("is_final", true)
                    val isUser = json.optBoolean("is_user", false)
                    scope.launch {
                        if (isUser) {
                            // User speech transcription from Gemini input_transcription
                            if (transcript.isNotEmpty()) {
                                viewModel.addUserMessage(transcript)
                                viewModel.updatePartialTranscript("")
                            }
                        } else {
                            // AI output transcription
                            if (isFinal && transcript.isNotEmpty()) {
                                viewModel.addAssistantMessage(transcript)
                                viewModel.updatePartialTranscript("")
                            } else if (!isFinal) {
                                viewModel.updatePartialTranscript(transcript)
                            }
                        }
                    }
                }

                "task_progress" -> {
                    val status = json.optString("status", "idle")
                    scope.launch {
                        when (status) {
                            "executing" -> {
                                // Automation task running — pause mic so noise doesn't
                                // confuse Gemini, but keep sessionActive so mic restarts
                                // when the task is done.
                                if (isRecording.get()) stopCapture()
                                viewModel.updatePhase(ConversationPhase.THINKING)
                                AuraOverlayService.minimize(context)
                            }
                            "idle" -> {
                                // Guard: if user is already recording (e.g. rapid follow-up)
                                // don't interrupt LISTENING with IDLE.
                                if (isRecording.get()) {
                                    Log.d(TAG, "task_progress:idle ignored — already recording")
                                    return@launch
                                }
                                AuraOverlayService.restore(context)
                                isTurnComplete.set(true)

                                if (sessionActive.get()) {
                                    // Audio player handles the restart if audio is in flight.
                                    // If no audio was sent (text-only / automation), restart mic now.
                                    if (audioPlayerJob?.isActive != true) {
                                        Log.d(TAG, "task_progress:idle — restarting mic (no audio in flight)")
                                        startMicInternal()
                                    }
                                    // Otherwise ensureAudioPlayerRunning drain path will restart.
                                } else {
                                    // Session ended by user — go IDLE.
                                    if (audioPlayerJob?.isActive != true) {
                                        viewModel.updatePhase(ConversationPhase.IDLE)
                                    }
                                }
                            }
                        }
                    }
                }

                "error" -> {
                    val msg = json.optString("message", "Unknown Gemini Live error")
                    Log.e(TAG, "Server error: $msg")
                    scope.launch { viewModel.setError(msg) }
                }

                "pong" -> Log.v(TAG, "pong")

                "visual_feedback" -> VisualFeedbackHandler.handleMessage(json)

                "response" -> {
                    val responseText = json.optString("text", "")
                    val readyForNext = json.optBoolean("ready_for_next_turn", true)
                    scope.launch {
                        viewModel.addAssistantMessage(responseText)
                        viewModel.updatePhase(ConversationPhase.RESPONDING)
                        if (readyForNext) {
                            AuraOverlayService.restore(context)
                            if (sessionActive.get()) startMicInternal() else viewModel.resetToIdle()
                        }
                    }
                }

                else -> Log.d(TAG, "Unhandled Gemini Live message type: $type")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling Gemini Live message: ${e.message}", e)
        }
    }

    private fun sendJson(json: JSONObject) {
        val ws = webSocket
        if (ws == null || !isConnected.get()) return
        try { ws.send(json.toString()) } catch (e: Exception) {
            Log.w(TAG, "Failed to send WebSocket message: ${e.message}")
        }
    }

    private fun calculateAmplitude(buffer: ByteArray, bytesRead: Int): Float {
        if (bytesRead < 2) return 0f
        var sumSq = 0.0
        var i = 0
        while (i + 1 < bytesRead) {
            val sample = ((buffer[i + 1].toInt() shl 8) or (buffer[i].toInt() and 0xFF)).toShort()
            val normalized = sample / 32768.0
            sumSq += normalized * normalized
            i += 2
        }
        return Math.sqrt(sumSq / (bytesRead / 2)).toFloat().coerceIn(0f, 1f)
    }
}
