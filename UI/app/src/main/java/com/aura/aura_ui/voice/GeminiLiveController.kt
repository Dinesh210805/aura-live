package com.aura.aura_ui.voice

import android.content.Context
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
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
import java.util.concurrent.atomic.AtomicLong

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

        // ── Post-response auto-stop ───────────────────────────────────────────
        // After the AI finishes speaking, the mic restarts for follow-up.
        // If the user stays silent for this long, the session auto-ends cleanly.
        private const val POST_RESPONSE_SILENCE_MS = 8000L
        // Amplitude below this = silence (normalised 0..1 RMS scale)
        private const val SPEECH_AMPLITUDE_THRESHOLD = 0.025f
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
    // No client-side VAD — server RealtimeInputConfig handles all turn detection

    // ── Audio playback (single-consumer queue pattern) ────────────────────────
    private val pcmPlayer = PcmStreamPlayer()
    private val audioQueue = ConcurrentLinkedQueue<ByteArray>()
    private var audioPlayerJob: Job? = null
    // Set true when server sends task_progress:idle — player drains then
    // restarts listening instead of going IDLE.
    private val isTurnComplete = AtomicBoolean(false)

    // True while server has an automation task in flight (task_progress:executing received
    // but task_progress:idle not yet received). Guards restore() calls so the overlay
    // never expands mid-task and hides the screen being automated.
    private val automationInProgress = AtomicBoolean(false)

    // ── Transcript accumulation ───────────────────────────────────────────────
    // Buffer user speech fragments received during a turn; flushed as ONE
    // chat message when the AI starts responding (mic muted for playback).
    // Backend already accumulates AI transcripts into one message per turn.
    private val pendingUserTranscript = StringBuilder()

    // ── Post-response silence auto-stop ───────────────────────────────────────
    // Tracks the last time non-silence audio was captured. After a response
    // completes the controller starts a watchdog; if this timestamp isn't
    // updated within POST_RESPONSE_SILENCE_MS the session auto-ends.
    private val lastSpeechMs = AtomicLong(0L)
    private var postResponseSilenceJob: Job? = null

    // ── AudioManager for AEC mode ─────────────────────────────────────────────
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    // True when hardware AcousticEchoCanceler was successfully attached to the mic.
    // When true: mic stays open during playback — barge-in is fully supported.
    // When false: mic is muted during playback to prevent echo feedback loop.
    private val hasHardwareAec = AtomicBoolean(false)

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
        cancelPostResponseSilenceTimer()
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

        // Reset turn-completion flag and any stale audio from the previous turn.
        // If the previous turn had no audio (Gemini was silent), isTurnComplete is
        // still true from task_progress:idle — leaving it true causes the next turn's
        // drain loop to exit immediately before playing any audio chunks.
        isTurnComplete.set(false)
        audioQueue.clear()

        try {
            // Use VOICE_COMMUNICATION mode: enables hardware AEC, noise suppression,
            // and automatic gain control at the driver level on most devices.
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION

            val chunkSize = (SAMPLE_RATE * CHUNK_MS / 1000) * 2
            val bufferSize = maxOf(
                AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT),
                chunkSize
            )
            @Suppress("MissingPermission")
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION, // best source for AEC
                SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT, bufferSize
            )

            // Apply hardware Acoustic Echo Canceler if available — prevents mic from
            // picking up speaker output and creating a Gemini-hears-itself loop.
            val sessionId = audioRecord?.audioSessionId ?: AudioManager.ERROR
            if (sessionId != AudioManager.ERROR && AcousticEchoCanceler.isAvailable()) {
                val aec = AcousticEchoCanceler.create(sessionId)
                if (aec != null) {
                    aec.enabled = true
                    hasHardwareAec.set(true)
                    Log.i(TAG, "✅ AcousticEchoCanceler enabled — barge-in active (session $sessionId)")
                } else {
                    hasHardwareAec.set(false)
                    Log.w(TAG, "AcousticEchoCanceler.create() returned null — falling back to mic-mute")
                }
            } else {
                hasHardwareAec.set(false)
                Log.w(TAG, "AcousticEchoCanceler not available — barge-in disabled, mic-mute mode active")
            }

            audioRecord?.startRecording()
            isRecording.set(true)

            viewModel.updatePhase(ConversationPhase.LISTENING)
            viewModel.updatePartialTranscript("")

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
        automationInProgress.set(false)
        cancelPostResponseSilenceTimer()
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
        pendingUserTranscript.clear()
        onAmplitudeUpdate?.invoke(0f)
        audioManager.isSpeakerphoneOn = false  // restore default routing
        audioManager.mode = AudioManager.MODE_NORMAL
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
        cancelCapture()          // also cancels postResponseSilenceTimer
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

        // Stream audio continuously to Gemini Live — no client-side VAD stopping.
        // The server's RealtimeInputConfig (AutomaticActivityDetection, 2 s silence)
        // handles all turn boundaries. Client-side silence detection caused the
        // "1.6 s cutoff" bug and fought against server VAD causing random commands.
        while (isRecording.get()) {
            val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0
            if (bytesRead <= 0) continue

            // Amplitude used for UI waveform animation only
            val amplitude = calculateAmplitude(buffer, bytesRead)
            withContext(Dispatchers.Main) { onAmplitudeUpdate?.invoke(amplitude) }

            // Track last-speech timestamp. If user speaks during the post-response
            // silence window, cancel the auto-stop timer — they want to continue.
            if (amplitude > SPEECH_AMPLITUDE_THRESHOLD) {
                lastSpeechMs.set(System.currentTimeMillis())
                cancelPostResponseSilenceTimer()
            }

            val encoded = Base64.encodeToString(buffer.copyOf(bytesRead), Base64.NO_WRAP)
            sendJson(JSONObject().apply { put("type", "audio_chunk"); put("data", encoded) })
        }
        Log.d(TAG, "streamAudioToGemini: loop exited (isRecording=${isRecording.get()})")
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

            // Reset the turn-complete gate at the very start of each drain coroutine.
            // If task_progress:idle arrived before the first audio chunk (race condition),
            // isTurnComplete would already be true and the loop would exit immediately
            // without playing anything. Resetting here ensures we always wait for a
            // fresh idle signal before declaring this turn done.
            isTurnComplete.set(false)

            withContext(Dispatchers.Main) {
                if (hasHardwareAec.get()) {
                    // ── AEC path: mic stays OPEN during playback ──────────
                    // Hardware echo canceller prevents the speaker output from
                    // being captured by the mic, so Gemini won't hear itself.
                    // This also enables barge-in: user can speak while AI
                    // is talking and Gemini will interrupt itself.
                    Log.d(TAG, "🎤 Mic stays open during playback (AEC active, barge-in enabled)")
                } else {
                    // ── No-AEC path: mute mic to prevent echo feedback ────
                    // On this device hardware AEC is unavailable so any speaker
                    // output would be captured and fed back to Gemini.
                    // Barge-in is unavailable in this mode.
                    muteMicForPlayback()
                }
                // Flush accumulated user transcript as one chat message
                flushPendingUserTranscript()
                // Ensure audio plays through the loudspeaker, not the earpiece.
                // MODE_IN_COMMUNICATION (set for mic AEC) defaults to earpiece routing;
                // isSpeakerphoneOn overrides that so the user can hear AURA's response.
                audioManager.isSpeakerphoneOn = true
            }

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

            // ── Echo cooldown before mic restarts (no-AEC path only) ────────
            // With AEC: mic is already open, no cooldown needed.
            // Without AEC: wait for room reverb to decay before reopening mic,
            // otherwise the speaker echo triggers Gemini's VAD immediately.
            if (sessionActive.get()) {
                delay(if (hasHardwareAec.get()) 200L else 1000L)
            }

            // ── Bidirectional auto-restart / phase reset ───────────────────
            if (sessionActive.get() && !isRecording.get()) {
                // No-AEC path: mic was muted, restart it now
                Log.d(TAG, "Audio drained + cooldown done — restarting mic")
                withContext(Dispatchers.Main) {
                    startMicInternal()
                    startPostResponseSilenceTimer()
                }
            } else if (sessionActive.get() && isRecording.get()) {
                // AEC path: mic stayed open, just flip phase back to LISTENING
                Log.d(TAG, "Audio drained — returning to LISTENING (mic was open)")
                withContext(Dispatchers.Main) {
                    viewModel.updatePhase(ConversationPhase.LISTENING)
                    startPostResponseSilenceTimer()
                }
            } else if (!sessionActive.get()) {
                withContext(Dispatchers.Main) {
                    audioManager.mode = AudioManager.MODE_NORMAL
                    viewModel.updatePhase(ConversationPhase.IDLE)
                    AuraOverlayService.restore(context)
                }
            }
        }
    }

    /**
     * Mute the microphone while AI audio plays back — prevents the speaker
     * output from being captured by the mic and fed back to Gemini (echo loop).
     *
     * Unlike [stopCapture], this does NOT send `end_turn` and does NOT change
     * [sessionActive] — the session remains alive and mic will auto-restart.
     */
    private fun muteMicForPlayback() {
        if (!isRecording.get()) return
        isRecording.set(false)
        recordingJob?.cancel(); recordingJob = null
        screenshotJob?.cancel(); screenshotJob = null
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        onAmplitudeUpdate?.invoke(0f)
        Log.d(TAG, "🔇 Mic muted for playback — echo prevention (session still active)")
    }

    /**
     * Flush accumulated user speech transcript as one chat message.
     * Called just before AI starts playing audio (end of user turn).
     */
    private fun flushPendingUserTranscript() {
        val text = pendingUserTranscript.toString().trim()
        pendingUserTranscript.clear()
        if (text.isNotEmpty()) {
            scope.launch {
                viewModel.addUserMessage(text)
                viewModel.updatePartialTranscript("")
            }
        }
    }

    private fun stopAudioPlayer() {
        audioPlayerJob?.cancel()
        audioPlayerJob = null
        pcmPlayer.stop()
    }

    /**
     * Start the post-response silence watchdog.
     *
     * After each AI turn ends the controller restarts the mic and enters a
     * brief listen-for-follow-up window.  If the user doesn't speak above
     * [SPEECH_AMPLITUDE_THRESHOLD] for [POST_RESPONSE_SILENCE_MS] milliseconds,
     * the session is cancelled automatically — no infinite listening loop.
     *
     * Cancelled early by [cancelPostResponseSilenceTimer] whenever the amplitude
     * tracker in [streamAudioToGemini] detects real speech.
     */
    private fun startPostResponseSilenceTimer() {
        postResponseSilenceJob?.cancel()
        lastSpeechMs.set(System.currentTimeMillis())  // grace period starts now
        postResponseSilenceJob = scope.launch {
            while (isActive && sessionActive.get()) {
                delay(500L)  // check every 500 ms
                val silenceMs = System.currentTimeMillis() - lastSpeechMs.get()
                if (silenceMs >= POST_RESPONSE_SILENCE_MS) {
                    Log.i(TAG, "⏱ No speech for ${POST_RESPONSE_SILENCE_MS / 1000}s — auto-ending session")
                    withContext(Dispatchers.Main) { cancelCapture() }
                    break
                }
            }
        }
        Log.d(TAG, "Post-response silence timer started (${POST_RESPONSE_SILENCE_MS / 1000}s)")
    }

    private fun cancelPostResponseSilenceTimer() {
        postResponseSilenceJob?.cancel()
        postResponseSilenceJob = null
    }

    /**
     * Immediately interrupt AI audio playback because the user started speaking.
     *
     * Called when a [transcript] with [is_user=true] arrives while the audio
     * player is active. Only triggered on AEC-capable devices where the mic
     * is open during playback.
     *
     * Steps:
     *  1. Clear the pending audio queue so no more chunks are written.
     *  2. Cancel the player coroutine (exits the drain loop immediately).
     *  3. Stop the AudioTrack (flushes hardware buffer).
     *  4. Reset state flags so the next turn starts clean.
     *  5. Update UI phase back to LISTENING (mic is already open on AEC path).
     */
    private fun interruptPlaybackForBargein() {
        if (audioPlayerJob?.isActive != true) return
        Log.i(TAG, "🗣️ Barge-in detected — interrupting AI playback immediately")
        audioQueue.clear()           // drop queued chunks we haven't played yet
        isTurnComplete.set(false)    // reset so next turn's drain loop works correctly
        audioPlayerJob?.cancel()     // exit the drain coroutine at next suspension point
        audioPlayerJob = null
        pcmPlayer.stop()             // flush + release AudioTrack immediately
        viewModel.updatePhase(ConversationPhase.LISTENING)
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
                    if (isUser && transcript.isNotEmpty()) {
                        if (!isFinal) {
                            // Partial update — show live "what you're saying" in the wave
                            // area but do NOT add to chat history yet. The server streams
                            // progressively more accurate versions until turn_complete.
                            //
                            // DO NOT call interruptPlaybackForBargein() here.
                            // Gemini sends late/corrected input_transcription events for the
                            // PREVIOUS user utterance while the AI is already responding.
                            // Triggering barge-in on those cuts off the AI mid-sentence.
                            // Real barge-in is handled by the server's "interrupted" message
                            // (server_content.interrupted=True), which Gemini sets when it
                            // actually detects new user speech during model output.
                            scope.launch(Dispatchers.Main) {
                                viewModel.updatePartialTranscript(transcript)
                            }
                            Log.d(TAG, "User transcript partial: ${transcript.take(60)}")
                        } else {
                            // Final corrected transcript arrives at turn_complete.
                            // Add directly to chat — bypasses the pendingUserTranscript
                            // buffer because flushPendingUserTranscript() runs before this
                            // (when audio playback starts) and would otherwise lose it.
                            Log.d(TAG, "User transcript final: ${transcript.take(60)}")
                            pendingUserTranscript.clear()
                            scope.launch(Dispatchers.Main) {
                                viewModel.addUserMessage(transcript)
                                viewModel.updatePartialTranscript("")
                            }
                        }
                    } else if (!isUser && isFinal && transcript.isNotEmpty()) {
                        // AI transcript arrives once per turn (is_final=true).
                        // Add directly to chat — no buffering needed.
                        Log.d(TAG, "AI transcript received: ${transcript.take(60)}")
                        scope.launch { viewModel.addAssistantMessage(transcript) }
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
                                automationInProgress.set(true)
                                if (isRecording.get()) stopCapture()
                                viewModel.updatePhase(ConversationPhase.THINKING)
                                AuraOverlayService.minimize(context)
                            }
                            "idle" -> {
                                // IMPORTANT: set isTurnComplete FIRST, before any guard.
                                // The audio drain loop polls this flag every 10 ms to know
                                // when to stop. In AEC mode the mic stays open during
                                // playback (isRecording=true), so if we guard-return before
                                // setting this flag the drain loop runs forever — the audio
                                // player job stays alive, blocking all future turns (stuck).
                                automationInProgress.set(false)
                                isTurnComplete.set(true)
                                AuraOverlayService.restore(context)

                                if (isRecording.get()) {
                                    // AEC path: mic is already open. The drain loop will exit
                                    // on its own now that isTurnComplete is set. No mic restart
                                    // needed — phase transition happens inside the drain coroutine.
                                    Log.d(TAG, "task_progress:idle — mic already open (AEC), drain loop will exit")
                                    return@launch
                                }

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

                // Server detected the user started speaking mid-response (barge-in).
                // Matches Google's reference: clear audio queue + stop playback
                // immediately so the user doesn't wait for the queue to drain.
                "interrupted" -> {
                    Log.i(TAG, "🛑 Server interrupted signal — clearing audio queue")
                    interruptPlaybackForBargein()
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
                            // Only restore the overlay if no automation task is in flight.
                            // If task_progress:executing already minimized the overlay, leave it
                            // minimized — task_progress:idle will restore it when the task finishes.
                            if (!automationInProgress.get()) {
                                AuraOverlayService.restore(context)
                            }
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
