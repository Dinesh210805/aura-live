package com.aura.aura_ui.presentation.viewmodel

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aura.aura_ui.data.repository.AssistantRepository
import com.aura.aura_ui.domain.model.VoiceSessionState
import com.aura.aura_ui.presentation.state.AssistantUiState
import com.aura.aura_ui.utils.Logger
import com.aura.aura_ui.utils.PermissionManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Main ViewModel coordinating the voice assistant UI state and operations
 */
@HiltViewModel
class AssistantViewModel
    @Inject
    constructor(
        private val repository: AssistantRepository,
        private val permissionManager: PermissionManager,
        private val logger: Logger,
    ) : ViewModel() {
        private val _uiState = MutableStateFlow(AssistantUiState())
        val uiState: StateFlow<AssistantUiState> = _uiState.asStateFlow()

        init {
            // Observe voice session state changes
            observeVoiceSessionState()

            // Initialize voice session and check server connectivity
            initializeVoiceSession()

            logger.d("AssistantViewModel", "ViewModel initialized")
        }

        /**
         * Check and update permission status
         */
        fun checkPermissions(context: Context) {
            viewModelScope.launch {
                try {
                    val hasAllPermissions = permissionManager.hasAllRequiredPermissions(context)
                    val missingPermissions = permissionManager.getMissingPermissions(context)

                    _uiState.update { currentState ->
                        currentState.copy(
                            hasAllPermissions = hasAllPermissions,
                            missingPermissions = missingPermissions,
                            isLoading = false,
                        )
                    }

                    logger.d("AssistantViewModel", "Permissions checked - All granted: $hasAllPermissions")
                    logger.d("AssistantViewModel", "Missing permissions: $missingPermissions")
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Error checking permissions", e)
                    _uiState.update { currentState ->
                        currentState.copy(
                            isLoading = false,
                            errorMessage = "Failed to check permissions: ${e.message}",
                        )
                    }
                }
            }
        }

        /**
         * Handle permission request results
         */
        fun handlePermissionResults(permissions: Map<String, Boolean>) {
            viewModelScope.launch {
                val deniedPermissions = permissions.filterValues { !it }.keys

                if (deniedPermissions.isEmpty()) {
                    logger.d("AssistantViewModel", "All requested permissions granted")
                    // Re-check all permissions to update UI state
                    _uiState.update { currentState ->
                        currentState.copy(
                            missingPermissions =
                                currentState.missingPermissions.filter { permission ->
                                    !permissions.keys.any { grantedPermission ->
                                        grantedPermission.contains(permission, ignoreCase = true)
                                    }
                                },
                        )
                    }
                } else {
                    logger.d("AssistantViewModel", "Some permissions denied: $deniedPermissions")
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Some permissions were denied. The app may not function properly.",
                        )
                    }
                }
            }
        }

        /**
         * Update service running status
         */
        fun updateServiceStatus(isRunning: Boolean) {
            viewModelScope.launch {
                _uiState.update { currentState ->
                    currentState.copy(isServiceRunning = isRunning)
                }
                logger.d("AssistantViewModel", "Service status updated: $isRunning")
            }
        }

        /**
         * Start voice listening session
         */
        fun startListening() {
            viewModelScope.launch {
                try {
                    repository.startListening()
                    logger.d("AssistantViewModel", "Voice listening started")
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Failed to start listening", e)
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Failed to start listening: ${e.message}",
                        )
                    }
                }
            }
        }

        /**
         * Stop voice listening session
         */
        fun stopListening() {
            viewModelScope.launch {
                try {
                    repository.stopListening()
                    logger.d("AssistantViewModel", "Voice listening stopped")
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Failed to stop listening", e)
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Failed to stop listening: ${e.message}",
                        )
                    }
                }
            }
        }

        /**
         * Process voice command text with Commander-based UI capture
         */
        fun processVoiceCommand(text: String) {
            viewModelScope.launch {
                try {
                    logger.d("AssistantViewModel", "Processing voice command with Commander: $text")

                    // Use Commander to determine if UI data is needed
                    val service = com.aura.aura_ui.accessibility.AuraAccessibilityService.instance
                    if (service != null) {
                        service.executeIntentDrivenAction(text) { success ->
                            if (success) {
                                logger.d("AssistantViewModel", "✅ UI data captured and sent based on intent")
                            } else {
                                logger.w("AssistantViewModel", "⚠️ Failed to capture UI data for command")
                            }
                        }
                    }

                    // Then send command to backend
                    repository.processTextCommand(text)
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Failed to process voice command", e)
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Failed to process command: ${e.message}",
                        )
                    }
                }
            }
        }

        /**
         * Clear error message
         */
        fun clearError() {
            viewModelScope.launch {
                _uiState.update { currentState ->
                    currentState.copy(errorMessage = null)
                }
            }
        }

        /**
         * Get current voice session state
         */
        fun getCurrentVoiceState(): VoiceSessionState {
            return uiState.value.voiceSessionState
        }

        /**
         * Observe voice session state changes from repository
         */
        private fun observeVoiceSessionState() {
            repository.voiceSessionState
                .onEach { newState ->
                    _uiState.update { currentState ->
                        currentState.copy(voiceSessionState = newState)
                    }
                    logger.d("AssistantViewModel", "Voice session state updated: $newState")
                }
                .catch { exception ->
                    logger.e("AssistantViewModel", "Error observing voice session state", exception)
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Voice session error: ${exception.message}",
                        )
                    }
                }
                .launchIn(viewModelScope)
        }

        /**
         * Initialize voice session
         */
        fun initializeVoiceSession() {
            viewModelScope.launch {
                try {
                    repository.initializeSession()
                    logger.d("AssistantViewModel", "Voice session initialized")
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Failed to initialize voice session", e)
                    _uiState.update { currentState ->
                        currentState.copy(
                            errorMessage = "Failed to initialize voice session: ${e.message}",
                        )
                    }
                }
            }
        }

        /**
         * Cleanup resources
         */
        override fun onCleared() {
            super.onCleared()
            viewModelScope.launch {
                try {
                    repository.cleanup()
                    logger.d("AssistantViewModel", "ViewModel cleared and resources cleaned up")
                } catch (e: Exception) {
                    logger.e("AssistantViewModel", "Error during cleanup", e)
                }
            }
        }
    }
