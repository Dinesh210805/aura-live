package com.aura.aura_ui

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.aura.aura_ui.audio.AuraTTSManager
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

class VoiceConversationActivity : AppCompatActivity() {
    private lateinit var micButton: Button
    private lateinit var endButton: Button
    private lateinit var statusText: TextView
    private lateinit var conversationRecycler: RecyclerView

    private var webSocket: WebSocket? = null

    // On-device TTS — synthesises server feedback text locally (~200 ms vs ~1.4 s server-side)
    private val auraTtsManager: AuraTTSManager by lazy { AuraTTSManager(this) }

    @Volatile
    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private var sessionId: String? = null
    private var recordingThread: Thread? = null

    private val conversationMessages = mutableListOf<ConversationMessage>()
    private lateinit var conversationAdapter: ConversationAdapter

    companion object {
        private const val TAG = "VoiceConversation"
        private const val RECORD_AUDIO_PERMISSION = Manifest.permission.RECORD_AUDIO
        private const val PERMISSION_REQUEST_CODE = 200
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_voice_conversation)

        micButton = findViewById(R.id.micButton)
        endButton = findViewById(R.id.endButton)
        statusText = findViewById(R.id.statusText)
        conversationRecycler = findViewById(R.id.conversationRecycler)

        setupConversationRecycler()
        checkPermissions()
        setupButtons()
    }

    private fun setupConversationRecycler() {
        conversationAdapter = ConversationAdapter(conversationMessages)
        conversationRecycler.layoutManager = LinearLayoutManager(this)
        conversationRecycler.adapter = conversationAdapter
    }

    private fun setupButtons() {
        micButton.setOnClickListener {
            if (isRecording) {
                stopRecording()
            } else {
                startRecording()
            }
        }

        endButton.setOnClickListener {
            endConversation()
        }
    }

    private fun checkPermissions() {
        if (ContextCompat.checkSelfPermission(this, RECORD_AUDIO_PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(RECORD_AUDIO_PERMISSION), PERMISSION_REQUEST_CODE)
        }
    }

    private fun connectWebSocket() {
        val client = OkHttpClient()
        val request =
            Request.Builder()
                .url("ws://10.0.2.2:8000/ws/conversation")
                .build()

        webSocket =
            client.newWebSocket(
                request,
                object : WebSocketListener() {
                    override fun onOpen(
                        webSocket: WebSocket,
                        response: Response,
                    ) {
                        Log.d(TAG, "WebSocket connected")
                        runOnUiThread {
                            statusText.text = "Connected - Ready to talk"
                            sessionId = UUID.randomUUID().toString()
                        }
                    }

                    override fun onMessage(
                        webSocket: WebSocket,
                        text: String,
                    ) {
                        Log.i(TAG, "🔔 RAW WebSocket message received (${text.length} chars)")
                        handleWebSocketMessage(text)
                    }

                    override fun onFailure(
                        webSocket: WebSocket,
                        t: Throwable,
                        response: Response?,
                    ) {
                        Log.e(TAG, "WebSocket error: ${t.message}")
                        runOnUiThread {
                            statusText.text = "Connection failed"
                            Toast.makeText(this@VoiceConversationActivity, "Connection failed: ${t.message}", Toast.LENGTH_SHORT).show()
                        }
                    }

                    override fun onClosing(
                        webSocket: WebSocket,
                        code: Int,
                        reason: String,
                    ) {
                        Log.d(TAG, "WebSocket closing: $reason")
                    }
                },
            )
    }

    private fun handleWebSocketMessage(text: String) {
        try {
            Log.d(TAG, "📥 Received WebSocket message: ${text.take(200)}...") // DEBUG: Log incoming messages
            val json = JSONObject(text)
            val type = json.getString("type")

            when (type) {
                "connected" -> {
                    runOnUiThread {
                        statusText.text = "Ready to talk"
                    }
                }

                "recording" -> {
                    runOnUiThread {
                        statusText.text = "Recording..."
                    }
                }

                "transcript" -> {
                    val transcript = json.getString("text")
                    runOnUiThread {
                        addMessage(transcript, isUser = true)
                    }
                }

                "response" -> {
                    val responseText = json.getString("text")
                    val audioBase64 = json.optString("audio", null)

                    runOnUiThread {
                        addMessage(responseText, isUser = false)
                        statusText.text = "AURA speaking..."

                        if (audioBase64 != null && audioBase64.isNotEmpty()) {
                            playAudioFromBase64(audioBase64)
                        }
                    }
                }

                "goodbye" -> {
                    runOnUiThread {
                        statusText.text = "Conversation ended"
                        Toast.makeText(this, "Goodbye!", Toast.LENGTH_SHORT).show()
                        finish()
                    }
                }

                "error" -> {
                    val message = json.optString("message", "Unknown error")
                    runOnUiThread {
                        statusText.text = "Error occurred"
                        Toast.makeText(this, "Error: $message", Toast.LENGTH_SHORT).show()
                    }
                }

                "request_ui" -> {
                    // DEPRECATED: Use request_ui_tree instead
                    Log.w(TAG, "⚠️ DEPRECATED: request_ui received - use request_ui_tree instead")
                }

                "request_ui_tree" -> {
                    // Backend requests UI tree via Perception Controller
                    val requestId = json.optString("request_id", "")
                    val reason = json.optString("reason", "")
                    Log.i(TAG, "📋 Backend requested UI tree: request_id=$requestId, reason=$reason")
                    handleRequestUiTree(requestId, reason)
                }

                "request_screenshot" -> {
                    // Backend requests screenshot via Perception Controller
                    val requestId = json.optString("request_id", "")
                    val reason = json.optString("reason", "")
                    Log.i(TAG, "📸 Backend requested screenshot: request_id=$requestId, reason=$reason")
                    handleRequestScreenshot(requestId, reason)
                }

                "execute_gesture" -> {
                    // Phase 8: Backend wants to execute a gesture via WebSocket
                    val gesture = json.optJSONObject("gesture")
                    val commandId = gesture?.optString("command_id", "")
                    Log.i(TAG, "⚡ Gesture received: commandId=$commandId")
                    if (gesture != null && commandId?.isNotEmpty() == true) {
                        // Pass commandId to handleExecuteGesture - ack will be sent by gesture system
                        handleExecuteGesture(gesture, commandId)
                    } else if (gesture != null) {
                        // Legacy gesture without command_id
                        handleExecuteGesture(gesture, null)
                    }
                }

                "launch_app" -> {
                    // Backend wants to launch an app via WebSocket
                    val packageName = json.optString("package_name", "")
                    val packageCandidates = json.optJSONArray("package_candidates")
                    val commandId = json.optString("command_id", "")
                    Log.i(TAG, "🚀 Launch app received: package=$packageName, commandId=$commandId")
                    handleLaunchApp(packageName, packageCandidates, commandId)
                }

                "launch_deep_link" -> {
                    // Backend wants to launch a deep link via WebSocket
                    val uri = json.optString("uri", "")
                    val packageName = json.optString("package_name", null)
                    val commandId = json.optString("command_id", "")
                    Log.i(TAG, "🔗 Launch deep link received: uri=$uri, commandId=$commandId")
                    handleLaunchDeepLink(uri, packageName, commandId)
                }
                
                "task_progress" -> {
                    // Backend sends task progress updates for todo-style display
                    val goal = json.optString("goal", "")
                    val tasks = json.optJSONArray("tasks")
                    val currentTask = json.optInt("current_task", 0)
                    val totalTasks = json.optInt("total_tasks", 0)
                    val isComplete = json.optBoolean("is_complete", false)
                    val isAborted = json.optBoolean("is_aborted", false)

                    Log.i(TAG, "📋 Task progress: $currentTask/$totalTasks - $goal")
                    handleTaskProgress(goal, tasks, currentTask, totalTasks, isComplete, isAborted)
                }

                "task_result" -> {
                    // Primary result message from /ws/audio pipeline.
                    // tts_response carries {text, voice, format} for on-device synthesis;
                    // spoken_response is the plain-text fallback for UI display.
                    val spokenResponse = json.optString("spoken_response", "")
                    val ttsPayload = json.optJSONObject("tts_response")

                    runOnUiThread {
                        if (spokenResponse.isNotEmpty()) {
                            addMessage(spokenResponse, isUser = false)
                        }
                        statusText.text = "Done"
                    }

                    if (ttsPayload != null) {
                        val ttsText  = ttsPayload.optString("text", "")
                        val ttsVoice = ttsPayload.optString("voice", "en-US-AriaNeural")
                        if (ttsText.isNotEmpty()) {
                            Log.i(TAG, "🔊 Android TTS: ${ttsText.take(60)}… (voice=$ttsVoice)")
                            auraTtsManager.speak(ttsText, ttsVoice) {
                                runOnUiThread { statusText.text = "Ready to talk" }
                            }
                        }
                    } else {
                        Log.w(TAG, "task_result had no tts_response payload")
                    }
                }

                else -> {
                    Log.w(TAG, "⚠️ Unknown message type: $type")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error handling message: ${e.message}", e)
            e.printStackTrace() // Print full stack trace for debugging
        }
    }

    // REMOVED: handleRequestUiSnapshot() - legacy function, backend uses request_ui_tree now

    private fun handleExecuteGesture(gesture: JSONObject, commandId: String?) {
        Thread {
            try {
                val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance

                if (service != null) {
                    val action = gesture.getString("action")
                    Log.i(TAG, "⚡ Executing gesture: $action, commandId=$commandId")

                    when (action.lowercase()) {
                        "tap", "click" -> {
                            val x = gesture.optInt("x", -1)
                            val y = gesture.optInt("y", -1)
                            if (x >= 0 && y >= 0) {
                                // Pass commandId so gesture system sends ack on success/failure
                                service.performTap(x, y, commandId)
                                Log.i(TAG, "✅ Tap dispatched at ($x, $y), commandId=$commandId")
                            } else {
                                Log.e(TAG, "❌ Invalid tap coordinates: x=$x, y=$y")
                                if (commandId != null) {
                                    sendGestureAck(commandId, false, "Invalid coordinates: x=$x, y=$y")
                                }
                            }
                        }
                        "swipe" -> {
                            val x1 = gesture.optInt("x1", -1)
                            val y1 = gesture.optInt("y1", -1)
                            val x2 = gesture.optInt("x2", -1)
                            val y2 = gesture.optInt("y2", -1)
                            val duration = gesture.optLong("duration", 300L)
                            if (x1 >= 0 && y1 >= 0 && x2 >= 0 && y2 >= 0) {
                                service.performSwipe(x1, y1, x2, y2, duration, commandId)
                                Log.i(TAG, "✅ Swipe dispatched from ($x1, $y1) to ($x2, $y2), commandId=$commandId")
                            } else {
                                Log.e(TAG, "❌ Invalid swipe coordinates")
                                if (commandId != null) {
                                    sendGestureAck(commandId, false, "Invalid swipe coordinates")
                                }
                            }
                        }
                        "long_press" -> {
                            val x = gesture.optInt("x", -1)
                            val y = gesture.optInt("y", -1)
                            val duration = gesture.optLong("duration", 1000L)
                            if (x >= 0 && y >= 0) {
                                service.performLongPress(x, y, duration, commandId)
                                Log.i(TAG, "✅ Long press dispatched at ($x, $y), commandId=$commandId")
                            } else {
                                Log.e(TAG, "❌ Invalid long press coordinates")
                                if (commandId != null) {
                                    sendGestureAck(commandId, false, "Invalid coordinates")
                                }
                            }
                        }
                        "capture_screenshot" -> {
                            val screenshot = service.captureScreen()
                            Log.i(TAG, "📸 Screenshot captured: ${screenshot?.length ?: 0} bytes")
                            // Screenshot doesn't need gesture ack
                        }
                        else -> {
                            service.executeSystemAction(action, commandId)
                            Log.i(TAG, "✅ System gesture dispatched: $action, commandId=$commandId")
                        }
                    }
                } else {
                    Log.w(TAG, "⚠️ AccessibilityService not available for gesture")
                    if (commandId != null) {
                        sendGestureAck(commandId, false, "AccessibilityService not available")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error executing gesture: ${e.message}")
                if (commandId != null) {
                    sendGestureAck(commandId, false, e.message)
                }
            }
        }.start()
    }

    /**
     * Phase 8: Send gesture acknowledgment to backend
     */
    private fun sendGestureAck(commandId: String, success: Boolean = true, error: String? = null) {
        try {
            val ackMessage = JSONObject().apply {
                put("type", "gesture_ack")
                put("command_id", commandId)
                put("success", success)
                if (error != null) {
                    put("error", error)
                }
                put("timestamp", System.currentTimeMillis())
            }
            webSocket?.send(ackMessage.toString())
            Log.i(TAG, "🔔 Ack sent: commandId=$commandId, success=$success")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to send gesture ack: ${e.message}")
        }
    }

    /**
     * Handle launch_app message - launch app via WebSocket
     */
    private fun handleLaunchApp(
        packageName: String,
        packageCandidates: org.json.JSONArray?,
        commandId: String,
    ) {
        Thread {
            try {
                val executor = com.aura.aura_ui.executor.CommandExecutor(this)
                
                // Try package candidates in order
                val candidates = mutableListOf<String>()
                if (packageName.isNotEmpty()) {
                    candidates.add(packageName)
                }
                if (packageCandidates != null) {
                    for (i in 0 until packageCandidates.length()) {
                        val candidate = packageCandidates.optString(i, "")
                        if (candidate.isNotEmpty() && !candidates.contains(candidate)) {
                            candidates.add(candidate)
                        }
                    }
                }
                
                var success = false
                var error: String? = null
                
                for (pkg in candidates) {
                    val result = executor.executeCommand(
                        com.aura.aura_ui.data.Command(
                            commandId = commandId,
                            commandType = "launch_app",
                            payload = mapOf("package_name" to pkg),
                            createdAt = System.currentTimeMillis().toString(),
                        )
                    )
                    
                    if (result.success) {
                        success = true
                        Log.i(TAG, "✅ App launched: $pkg")
                        break
                    } else {
                        error = result.error
                        Log.w(TAG, "⚠️ Failed to launch $pkg: ${result.error}")
                    }
                }
                
                // Send result back to backend
                sendCommandResult(commandId, "launch_app", success, error)
            } catch (e: Exception) {
                Log.e(TAG, "Error launching app: ${e.message}")
                sendCommandResult(commandId, "launch_app", false, e.message)
            }
        }.start()
    }

    /**
     * Handle launch_deep_link message - launch deep link via WebSocket
     */
    private fun handleLaunchDeepLink(
        uri: String,
        packageName: String?,
        commandId: String,
    ) {
        Thread {
            try {
                val executor = com.aura.aura_ui.executor.CommandExecutor(this)
                
                val payload = mutableMapOf<String, Any?>("uri" to uri)
                if (packageName != null) {
                    payload["package_name"] = packageName
                }
                
                val result = executor.executeCommand(
                    com.aura.aura_ui.data.Command(
                        commandId = commandId,
                        commandType = "launch_deep_link",
                        payload = payload,
                        createdAt = System.currentTimeMillis().toString(),
                    )
                )
                
                // Send result back to backend
                sendCommandResult(commandId, "launch_deep_link", result.success, result.error)
            } catch (e: Exception) {
                Log.e(TAG, "Error launching deep link: ${e.message}")
                sendCommandResult(commandId, "launch_deep_link", false, e.message)
            }
        }.start()
    }

    /**
     * Send command result back to backend
     */
    private fun sendCommandResult(
        commandId: String,
        commandType: String,
        success: Boolean,
        error: String?,
    ) {
        try {
            val response = JSONObject().apply {
                put("type", "command_result")
                put("command_id", commandId)
                put("command_type", commandType)
                put("success", success)
                if (error != null) {
                    put("error", error)
                }
            }
            webSocket?.send(response.toString())
            Log.i(TAG, "📤 Sent command result: $commandType, success=$success")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to send command result: ${e.message}")
        }
    }
    
    /**
     * Handle task_progress message - show todo-style task list with progress
     */
    private fun handleTaskProgress(
        goal: String,
        tasks: org.json.JSONArray?,
        currentTask: Int,
        totalTasks: Int,
        isComplete: Boolean,
        isAborted: Boolean
    ) {
        runOnUiThread {
            try {
                // Build task progress message
                val sb = StringBuilder()
                sb.append("📋 $goal\n\n")
                
                if (tasks != null) {
                    for (i in 0 until tasks.length()) {
                        val task = tasks.getJSONObject(i)
                        val taskId = task.optInt("id", i + 1)
                        val description = task.optString("description", "Step $taskId")
                        val status = task.optString("status", "pending")
                        
                        val statusIcon = when (status) {
                            "completed" -> "✅"
                            "in_progress" -> "⏳"
                            "failed" -> "❌"
                            else -> "⬜"
                        }
                        
                        sb.append("$statusIcon $description\n")
                    }
                }
                
                if (isComplete) {
                    sb.append("\n✨ Task completed!")
                } else if (isAborted) {
                    sb.append("\n⚠️ Task aborted")
                }
                
                // Show as a message in the conversation
                addMessage(sb.toString().trim(), isUser = false)
                
                // Update status text
                statusText.text = when {
                    isComplete -> "Task complete"
                    isAborted -> "Task aborted"
                    else -> "Step $currentTask of $totalTasks"
                }
                
            } catch (e: Exception) {
                Log.e(TAG, "Error displaying task progress: ${e.message}")
            }
        }
    }

    /**
     * Handle request_ui_tree message - send UI tree to backend via Perception Controller
     */
    private fun handleRequestUiTree(requestId: String, reason: String) {
        Thread {
            try {
                val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
                if (service == null) {
                    Log.w(TAG, "AccessibilityService not available for UI tree")
                    sendUiTreeResponse(requestId, null)
                    return@Thread
                }

                val uiTree = service.getUITree()
                sendUiTreeResponse(requestId, uiTree)
            } catch (e: Exception) {
                Log.e(TAG, "Error capturing UI tree: ${e.message}")
                sendUiTreeResponse(requestId, null)
            }
        }.start()
    }

    /**
     * Send UI tree response to backend
     */
    private fun sendUiTreeResponse(requestId: String, uiTree: Map<String, Any>?) {
        try {
            val response = JSONObject().apply {
                put("type", "ui_tree_response")
                put("request_id", requestId)
                if (uiTree != null) {
                    val uiTreeObj = JSONObject(uiTree)
                    // Always include screen dimensions for backend device_info sync
                    val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
                    val screenWidth = service?.getScreenWidth() ?: 1080
                    val screenHeight = service?.getScreenHeight() ?: 1920
                    uiTreeObj.put("screen_width", screenWidth)
                    uiTreeObj.put("screen_height", screenHeight)
                    put("ui_tree", uiTreeObj)
                } else {
                    val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
                    val screenWidth = service?.getScreenWidth() ?: 1080
                    val screenHeight = service?.getScreenHeight() ?: 1920
                    put("ui_tree", JSONObject().apply {
                        put("elements", JSONArray())
                        put("screen_width", screenWidth)
                        put("screen_height", screenHeight)
                        put("orientation", "portrait")
                        put("timestamp", System.currentTimeMillis())
                    })
                }
            }
            webSocket?.send(response.toString())
            Log.i(TAG, "📤 Sent UI tree response: request_id=$requestId")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to send UI tree response: ${e.message}")
        }
    }

    /**
     * Handle request_screenshot message - send screenshot to backend via Perception Controller
     */
    private fun handleRequestScreenshot(requestId: String, reason: String) {
        Thread {
            try {
                val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
                if (service == null) {
                    Log.w(TAG, "AccessibilityService not available for screenshot")
                    sendScreenshotResponse(requestId, null)
                    return@Thread
                }

                val screenshot = service.captureScreen()
                sendScreenshotResponse(requestId, screenshot)
            } catch (e: Exception) {
                Log.e(TAG, "Error capturing screenshot: ${e.message}")
                sendScreenshotResponse(requestId, null)
            }
        }.start()
    }

    /**
     * Send screenshot response to backend
     */
    private fun sendScreenshotResponse(requestId: String, screenshot: String?) {
        try {
            val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
            // Get screen dimensions from screenCaptureManager via service
            val screenWidth = service?.getScreenWidth() ?: 1080
            val screenHeight = service?.getScreenHeight() ?: 1920
            
            val response = JSONObject().apply {
                put("type", "screenshot_response")
                put("request_id", requestId)
                put("screenshot_base64", screenshot ?: "")
                put("screen_width", screenWidth)
                put("screen_height", screenHeight)
                put("orientation", "portrait")  // Could be detected
                put("timestamp", System.currentTimeMillis())
            }
            webSocket?.send(response.toString())
            Log.i(TAG, "📤 Sent screenshot response: request_id=$requestId, size=${screenshot?.length ?: 0} bytes")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to send screenshot response: ${e.message}")
        }
    }

    private fun startRecording() {
        if (webSocket == null) {
            connectWebSocket()
            // Wait for connection asynchronously
            micButton.postDelayed({
                if (webSocket != null) {
                    startActualRecording()
                } else {
                    Toast.makeText(this, "Connection not ready. Try again.", Toast.LENGTH_SHORT).show()
                }
            }, 800)
            return
        }
        startActualRecording()
    }

    private fun startActualRecording() {
        val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)

        if (ActivityCompat.checkSelfPermission(this, RECORD_AUDIO_PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            checkPermissions()
            return
        }

        audioRecord =
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize,
            )

        audioRecord?.startRecording()
        isRecording = true

        // Send start message with TTS voice preference
        val voicePrefs = getSharedPreferences("aura_voice_settings", MODE_PRIVATE)
        val voiceId = voicePrefs.getString("selected_voice_id", "en-US-AriaNeural") ?: "en-US-AriaNeural"
        
        val startMsg =
            JSONObject().apply {
                put("type", "start")
                put("session_id", sessionId ?: UUID.randomUUID().toString())
                put("voice_id", voiceId)
            }
        webSocket?.send(startMsg.toString())

        micButton.text = "Stop"
        statusText.text = "Listening..."

        // Stream audio
        recordingThread =
            Thread {
                val buffer = ByteArray(bufferSize)
                while (isRecording) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                    if (read > 0) {
                        val socket = webSocket
                        if (socket != null) {
                            try {
                                socket.send(buffer.copyOf(read).toByteString())
                            } catch (e: Exception) {
                                Log.e(TAG, "Failed to send audio: ${e.message}")
                                break
                            }
                        } else {
                            Log.w(TAG, "WebSocket null, stopping recording")
                            break
                        }
                    }
                }
            }
        recordingThread?.start()
    }

    private fun stopRecording() {
        isRecording = false

        // Wait for recording thread to finish
        recordingThread?.join(1000)
        recordingThread = null

        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        // Send end turn message
        val endMsg =
            JSONObject().apply {
                put("type", "end_turn")
            }
        webSocket?.send(endMsg.toString())

        micButton.text = "Speak"
        statusText.text = "Processing..."
    }

    private fun endConversation() {
        val endMsg =
            JSONObject().apply {
                put("type", "end_conversation")
            }
        webSocket?.send(endMsg.toString())

        if (isRecording) {
            stopRecording()
        }

        webSocket?.close(1000, "User ended conversation")
        finish()
    }

    private fun addMessage(
        text: String,
        isUser: Boolean,
    ) {
        conversationMessages.add(ConversationMessage(text, isUser))
        conversationAdapter.notifyItemInserted(conversationMessages.size - 1)
        conversationRecycler.smoothScrollToPosition(conversationMessages.size - 1)
    }

    private fun playAudioFromBase64(audioBase64: String) {
        try {
            val audioData = Base64.decode(audioBase64, Base64.DEFAULT)

            val mediaPlayer = MediaPlayer()
            val tempFile = java.io.File.createTempFile("aura_response", ".wav", cacheDir)
            tempFile.writeBytes(audioData)

            try {
                mediaPlayer.setDataSource(tempFile.absolutePath)
                mediaPlayer.prepare()
                mediaPlayer.setOnCompletionListener {
                    it.release()
                    tempFile.delete()
                    runOnUiThread {
                        statusText.text = "Ready to talk"
                    }
                }
                mediaPlayer.start()
            } catch (e: Exception) {
                Log.e(TAG, "MediaPlayer failed, trying AudioTrack: ${e.message}")
                mediaPlayer.release()
                tempFile.delete()
                playWithAudioTrack(audioData)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Audio playback failed: ${e.message}")
            runOnUiThread {
                statusText.text = "Ready to talk"
            }
        }
    }

    private fun playWithAudioTrack(audioData: ByteArray) {
        try {
            val wavInfo = parseWavHeader(audioData)
            val pcmData = audioData.copyOfRange(wavInfo.dataOffset, wavInfo.dataOffset + wavInfo.dataLength)

            val channelConfig = if (wavInfo.channels == 1) AudioFormat.CHANNEL_OUT_MONO else AudioFormat.CHANNEL_OUT_STEREO
            val bufferSize = AudioTrack.getMinBufferSize(wavInfo.sampleRate, channelConfig, wavInfo.encoding)

            val audioTrack =
                AudioTrack.Builder()
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ASSISTANT)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build(),
                    )
                    .setAudioFormat(
                        AudioFormat.Builder()
                            .setSampleRate(wavInfo.sampleRate)
                            .setEncoding(wavInfo.encoding)
                            .setChannelMask(channelConfig)
                            .build(),
                    )
                    .setBufferSizeInBytes(bufferSize)
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .build()

            audioTrack.play()
            audioTrack.write(pcmData, 0, pcmData.size)
            audioTrack.stop()
            audioTrack.release()

            runOnUiThread {
                statusText.text = "Ready to talk"
            }
        } catch (e: Exception) {
            Log.e(TAG, "AudioTrack playback failed: ${e.message}")
        }
    }

    private fun parseWavHeader(data: ByteArray): WavInfo {
        val buffer = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
        buffer.position(22)
        val channels = buffer.short.toInt()
        val sampleRate = buffer.int
        buffer.position(34)
        val bitsPerSample = buffer.short.toInt()

        val encoding =
            when (bitsPerSample) {
                8 -> AudioFormat.ENCODING_PCM_8BIT
                16 -> AudioFormat.ENCODING_PCM_16BIT
                32 -> AudioFormat.ENCODING_PCM_FLOAT
                else -> AudioFormat.ENCODING_PCM_16BIT
            }

        var dataOffset = 44
        var dataLength = data.size - 44

        return WavInfo(sampleRate, channels, encoding, dataOffset, dataLength)
    }

    data class WavInfo(
        val sampleRate: Int,
        val channels: Int,
        val encoding: Int,
        val dataOffset: Int,
        val dataLength: Int,
    )

    override fun onDestroy() {
        super.onDestroy()
        if (isRecording) {
            isRecording = false
            recordingThread?.interrupt()
            recordingThread = null
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
        }
        webSocket?.close(1000, "Activity destroyed")
        webSocket = null
        auraTtsManager.release()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERMISSION_REQUEST_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                Toast.makeText(this, "Permission granted", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "Permission denied - cannot record audio", Toast.LENGTH_SHORT).show()
            }
        }
    }
}

data class ConversationMessage(val text: String, val isUser: Boolean)
