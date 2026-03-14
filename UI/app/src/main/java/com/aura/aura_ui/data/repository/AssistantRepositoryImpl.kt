package com.aura.aura_ui.data.repository

import com.aura.aura_ui.data.network.AuraApiService
import com.aura.aura_ui.data.network.TaskRequestDto
import com.aura.aura_ui.domain.model.VoiceSessionState
import com.aura.aura_ui.utils.Logger
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Implementation of AssistantRepository with backend server integration
 */
@Singleton
class AssistantRepositoryImpl
    @Inject
    constructor(
        private val auraApiService: AuraApiService,
        private val logger: Logger,
    ) : AssistantRepository {
        private val _voiceSessionState = MutableStateFlow<VoiceSessionState>(VoiceSessionState.Idle)
        override val voiceSessionState: StateFlow<VoiceSessionState> = _voiceSessionState.asStateFlow()

        override suspend fun startListening() {
            logger.d("AssistantRepository", "Starting voice listening")
            _voiceSessionState.value = VoiceSessionState.Listening()
        }

        override suspend fun stopListening() {
            logger.d("AssistantRepository", "Stopping voice listening")
            _voiceSessionState.value = VoiceSessionState.Idle
        }

        override suspend fun processTextCommand(text: String) {
            logger.d("AssistantRepository", "Processing text command: $text")
            _voiceSessionState.value = VoiceSessionState.Processing("Sending command to AURA backend")

            try {
                // Send command to backend server - convert text to audioData format
                val request =
                    TaskRequestDto(
                        audioData = text, // Using text as audio data for now
                        inputType = "text", // Specify this is text input, not audio
                    )
                val response = auraApiService.executeTask(request)

                if (response.isSuccessful && response.body() != null) {
                    val taskResponse = response.body()!!
                    logger.d("AssistantRepository", "Server response: ${taskResponse.spokenResponse}")
                    _voiceSessionState.value = VoiceSessionState.Responding(taskResponse.spokenResponse)
                } else {
                    logger.w("AssistantRepository", "Server returned error: ${response.code()}")
                    _voiceSessionState.value = VoiceSessionState.Responding("Server error: ${response.code()}")
                }

                kotlinx.coroutines.delay(2000) // Show response message
                _voiceSessionState.value = VoiceSessionState.Idle
            } catch (e: Exception) {
                logger.e("AssistantRepository", "Failed to process command on server", e)
                _voiceSessionState.value = VoiceSessionState.Responding("Error: Unable to connect to AURA backend - ${e.message}")

                kotlinx.coroutines.delay(3000) // Show error message longer
                _voiceSessionState.value = VoiceSessionState.Idle
            }
        }

        override suspend fun initializeSession() {
            logger.d("AssistantRepository", "Initializing voice session and checking server connectivity")
            _voiceSessionState.value = VoiceSessionState.Processing("Connecting to AURA backend")

            try {
                // Test server connectivity
                val healthResponse = auraApiService.getHealthStatus()
                logger.d("AssistantRepository", "Server health check: ${healthResponse.body()?.status}")

                if (healthResponse.isSuccessful && healthResponse.body()?.status == "healthy") {
                    _voiceSessionState.value = VoiceSessionState.Responding("Connected to AURA backend successfully")
                    kotlinx.coroutines.delay(1500)
                    _voiceSessionState.value = VoiceSessionState.Idle
                } else {
                    _voiceSessionState.value = VoiceSessionState.Responding("Backend server is not ready")
                    kotlinx.coroutines.delay(2000)
                    _voiceSessionState.value = VoiceSessionState.Idle
                }
            } catch (e: Exception) {
                logger.e("AssistantRepository", "Failed to connect to backend server", e)
                _voiceSessionState.value = VoiceSessionState.Responding("Cannot connect to AURA backend at 192.168.1.41:8000")
                kotlinx.coroutines.delay(3000)
                _voiceSessionState.value = VoiceSessionState.Idle
            }
        }

        override suspend fun cleanup() {
            logger.d("AssistantRepository", "Cleaning up repository")
            _voiceSessionState.value = VoiceSessionState.Idle
        }
    }
