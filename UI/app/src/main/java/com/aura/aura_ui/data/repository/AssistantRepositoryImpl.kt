package com.aura.aura_ui.data.repository

import com.aura.aura_ui.data.network.AuraApiService
import com.aura.aura_ui.data.network.TaskRequestDto
import com.aura.aura_ui.domain.model.VoiceSessionState
import com.aura.aura_ui.network.ConnectionManager
import com.aura.aura_ui.network.ConnectionState
import com.aura.aura_ui.utils.Logger
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "AssistantRepository"
private const val MAX_RETRIES = 3
private const val RETRY_BASE_DELAY_MS = 2_000L

/**
 * Implementation of AssistantRepository with backend server integration.
 *
 * Retry strategy:
 * - Up to [MAX_RETRIES] attempts per command.
 * - Delay between retries: 2 s, 4 s, 8 s (exponential backoff, not capped — the
 *   maximum for 3 retries is 8 s which is acceptable UX).
 * - Does NOT retry on non-retriable HTTP errors (4xx client errors).
 *
 * Connection awareness:
 * - [connectionState] mirrors [ConnectionManager.state] for the UI to display
 *   a banner when the backend is unreachable.
 */
@Singleton
class AssistantRepositoryImpl
    @Inject
    constructor(
        private val auraApiService: AuraApiService,
        private val connectionManager: ConnectionManager,
        private val logger: Logger,
    ) : AssistantRepository {

        private val _voiceSessionState = MutableStateFlow<VoiceSessionState>(VoiceSessionState.Idle)
        override val voiceSessionState: StateFlow<VoiceSessionState> = _voiceSessionState.asStateFlow()

        /** Exposes the WebSocket connection state so the UI can show a reconnect banner. */
        val connectionState: StateFlow<ConnectionState> = connectionManager.state

        override suspend fun startListening() {
            logger.d(TAG, "Starting voice listening")
            _voiceSessionState.value = VoiceSessionState.Listening()
        }

        override suspend fun stopListening() {
            logger.d(TAG, "Stopping voice listening")
            _voiceSessionState.value = VoiceSessionState.Idle
        }

        override suspend fun processTextCommand(text: String) {
            logger.d(TAG, "Processing text command: $text")
            _voiceSessionState.value = VoiceSessionState.Processing("Sending command to AURA backend")

            var lastError: Exception? = null
            repeat(MAX_RETRIES) { attempt ->
                try {
                    val request = TaskRequestDto(
                        audioData = text,
                        inputType = "text",
                    )
                    val response = auraApiService.executeTask(request)

                    if (response.isSuccessful && response.body() != null) {
                        val taskResponse = response.body()!!
                        logger.d(TAG, "Server response: ${taskResponse.spokenResponse}")
                        _voiceSessionState.value = VoiceSessionState.Responding(taskResponse.spokenResponse)
                        delay(2000)
                        _voiceSessionState.value = VoiceSessionState.Idle
                        return // ← success, exit retry loop
                    }

                    val code = response.code()
                    logger.w(TAG, "Server returned HTTP $code on attempt ${attempt + 1}")

                    // 4xx errors are the client's fault — retrying will not help
                    if (code in 400..499) {
                        _voiceSessionState.value = VoiceSessionState.Error(
                            "Request error (HTTP $code)",
                            canRetry = false,
                        )
                        delay(2000)
                        _voiceSessionState.value = VoiceSessionState.Idle
                        return
                    }

                    lastError = RuntimeException("HTTP $code")
                } catch (e: Exception) {
                    logger.w(TAG, "Attempt ${attempt + 1} failed: ${e.message}")
                    lastError = e
                }

                if (attempt < MAX_RETRIES - 1) {
                    val backoffMs = RETRY_BASE_DELAY_MS * (1L shl attempt) // 2s, 4s
                    logger.d(TAG, "Retrying in ${backoffMs}ms…")
                    _voiceSessionState.value = VoiceSessionState.Processing(
                        "Retrying… (${attempt + 2}/$MAX_RETRIES)"
                    )
                    delay(backoffMs)
                }
            }

            // All retries exhausted
            logger.e(TAG, "All $MAX_RETRIES attempts failed", lastError)
            _voiceSessionState.value = VoiceSessionState.Error(
                "Unable to reach AURA backend after $MAX_RETRIES attempts",
                canRetry = true,
            )
            delay(3000)
            _voiceSessionState.value = VoiceSessionState.Idle
        }

        override suspend fun initializeSession() {
            logger.d(TAG, "Initializing voice session")
            _voiceSessionState.value = VoiceSessionState.Connecting

            try {
                val healthResponse = auraApiService.getHealthStatus()
                logger.d(TAG, "Health check: ${healthResponse.body()?.status}")

                if (healthResponse.isSuccessful && healthResponse.body()?.status == "healthy") {
                    _voiceSessionState.value = VoiceSessionState.Responding("Connected to AURA backend")
                    delay(1500)
                    _voiceSessionState.value = VoiceSessionState.Idle
                } else {
                    _voiceSessionState.value = VoiceSessionState.Error(
                        "Backend server not ready (HTTP ${healthResponse.code()})",
                        canRetry = true,
                    )
                    delay(2000)
                    _voiceSessionState.value = VoiceSessionState.Idle
                }
            } catch (e: Exception) {
                logger.e(TAG, "Failed to connect to backend", e)
                _voiceSessionState.value = VoiceSessionState.Error(
                    "Cannot reach AURA backend — check server URL in Settings",
                    canRetry = true,
                )
                delay(3000)
                _voiceSessionState.value = VoiceSessionState.Idle
            }
        }

        override suspend fun cleanup() {
            logger.d(TAG, "Cleaning up repository")
            _voiceSessionState.value = VoiceSessionState.Idle
        }
    }
