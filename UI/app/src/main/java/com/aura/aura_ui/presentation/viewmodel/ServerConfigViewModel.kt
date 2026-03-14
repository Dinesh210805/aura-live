package com.aura.aura_ui.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aura.aura_ui.data.manager.ServerConfigManager
import com.aura.aura_ui.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for ServerConfigurationScreen handling server configuration logic.
 */
@HiltViewModel
class ServerConfigViewModel
    @Inject
    constructor(
        private val settingsRepository: SettingsRepository,
        private val serverConfigManager: ServerConfigManager,
    ) : ViewModel() {
        private val _uiState = MutableStateFlow(ServerConfigUiState())
        val uiState: StateFlow<ServerConfigUiState> = _uiState.asStateFlow()

        init {
            // Observe settings changes
            viewModelScope.launch {
                combine(
                    settingsRepository.observeUseAutoDiscovery(),
                    settingsRepository.observeServerUrl(),
                    settingsRepository.observeServerUrls(),
                ) { useAutoDiscovery, serverUrl, serverUrls ->
                    _uiState.value =
                        _uiState.value.copy(
                            useAutoDiscovery = useAutoDiscovery,
                            savedServerUrl = serverUrl,
                            serverUrl = serverUrl ?: "",
                            savedServerUrls = serverUrls,
                        )
                }.collect()
            }
        }

        fun setUseAutoDiscovery(useAutoDiscovery: Boolean) {
            _uiState.value = _uiState.value.copy(useAutoDiscovery = useAutoDiscovery)

            viewModelScope.launch {
                settingsRepository.updateUseAutoDiscovery(useAutoDiscovery)
            }
        }

        fun setServerUrl(url: String) {
            _uiState.value =
                _uiState.value.copy(
                    serverUrl = url,
                    validationError = null,
                    connectionTestResult = null,
                )

            // Validate URL in real-time
            if (url.isNotBlank()) {
                val formattedUrl = serverConfigManager.formatServerUrl(url)
                val validation = serverConfigManager.validateServerUrl(formattedUrl)

                if (!validation.isValid) {
                    _uiState.value =
                        _uiState.value.copy(
                            validationError = validation.errorMessage,
                        )
                }
            }
        }

        suspend fun testConnection() {
            val currentUrl = _uiState.value.serverUrl
            if (currentUrl.isBlank()) return

            _uiState.value =
                _uiState.value.copy(
                    isTestingConnection = true,
                    connectionTestResult = null,
                )

            try {
                val result = serverConfigManager.testServerConnection(currentUrl)
                _uiState.value =
                    _uiState.value.copy(
                        connectionTestResult = result,
                        lastConnectionTest = if (result.success) result.responseTime else null,
                    )
            } finally {
                _uiState.value = _uiState.value.copy(isTestingConnection = false)
            }
        }

        suspend fun saveSettings() {
            val currentState = _uiState.value

            if (currentState.serverUrl.isNotBlank()) {
                // When user manually enters a URL, automatically disable auto-discovery
                val formattedUrl = serverConfigManager.formatServerUrl(currentState.serverUrl)
                settingsRepository.updateServerUrl(formattedUrl)
                if (currentState.useAutoDiscovery) {
                    settingsRepository.updateUseAutoDiscovery(false)
                    _uiState.value = _uiState.value.copy(useAutoDiscovery = false)
                }
            } else if (currentState.serverUrl.isBlank() && !currentState.useAutoDiscovery) {
                // If URL is cleared and auto-discovery is off, enable auto-discovery
                settingsRepository.updateUseAutoDiscovery(true)
                settingsRepository.updateServerUrl(null)
            }

            // Show success feedback
            _uiState.value =
                _uiState.value.copy(
                    connectionTestResult =
                        ServerConfigManager.ConnectionTestResult(
                            success = true,
                            message = "Settings saved successfully",
                            responseTime = 0,
                        ),
                )

            // Clear the success message after a delay
            viewModelScope.launch {
                kotlinx.coroutines.delay(3000)
                _uiState.value = _uiState.value.copy(connectionTestResult = null)
            }
        }

        // Multi-IP management methods
        fun setNewServerUrl(url: String) {
            _uiState.value = _uiState.value.copy(
                newServerUrl = url,
                validationError = null
            )
        }

        fun addServerUrl(url: String) {
            viewModelScope.launch {
                val formattedUrl = serverConfigManager.formatServerUrl(url)
                val validation = serverConfigManager.validateServerUrl(formattedUrl)
                
                if (validation.isValid) {
                    settingsRepository.addServerUrl(formattedUrl)
                    _uiState.value = _uiState.value.copy(
                        newServerUrl = "",
                        validationError = null
                    )
                } else {
                    _uiState.value = _uiState.value.copy(
                        validationError = validation.errorMessage
                    )
                }
            }
        }

        fun removeServerUrl(url: String) {
            viewModelScope.launch {
                settingsRepository.removeServerUrl(url)
            }
        }

        suspend fun testServerUrl(url: String): ServerConfigManager.ConnectionTestResult {
            return serverConfigManager.testServerConnection(url)
        }
    }

/**
 * UI state for ServerConfigurationScreen.
 */
data class ServerConfigUiState(
    val useAutoDiscovery: Boolean = true,
    val serverUrl: String = "",
    val savedServerUrl: String? = null,
    val savedServerUrls: List<String> = emptyList(),
    val newServerUrl: String = "",
    val validationError: String? = null,
    val isTestingConnection: Boolean = false,
    val connectionTestResult: ServerConfigManager.ConnectionTestResult? = null,
    val lastConnectionTest: Long? = null,
)
