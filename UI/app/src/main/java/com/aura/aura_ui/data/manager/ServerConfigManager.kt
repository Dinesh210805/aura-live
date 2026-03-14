package com.aura.aura_ui.data.manager

import android.util.Log
import android.util.Patterns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager class for handling server configuration, validation, and connection testing.
 */
@Singleton
class ServerConfigManager
    @Inject
    constructor() {
        companion object {
            private const val TAG = "ServerConfigManager"
            private const val DEFAULT_PORT = 8000
            private const val HEALTH_ENDPOINT = "/health"
            private const val CONNECTION_TIMEOUT_SECONDS = 5L
            private const val READ_TIMEOUT_SECONDS = 10L
        }

        private val httpClient =
            OkHttpClient.Builder()
                .connectTimeout(CONNECTION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .writeTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .retryOnConnectionFailure(false)
                .build()

        /**
         * Validates if the provided URL is in a valid format.
         *
         * @param url The URL to validate
         * @return ValidationResult indicating if the URL is valid and any error message
         */
        fun validateServerUrl(url: String): ValidationResult {
            if (url.isBlank()) {
                return ValidationResult(false, "URL cannot be empty")
            }

            val trimmedUrl = url.trim()

            // Check if it starts with http or https
            if (!trimmedUrl.startsWith("http://") && !trimmedUrl.startsWith("https://")) {
                return ValidationResult(false, "URL must start with http:// or https://")
            }

            // Use Android's built-in URL validation
            if (!Patterns.WEB_URL.matcher(trimmedUrl).matches()) {
                return ValidationResult(false, "Invalid URL format")
            }

            // Additional checks for common issues
            if (trimmedUrl.contains(" ")) {
                return ValidationResult(false, "URL cannot contain spaces")
            }

            return ValidationResult(true, null)
        }

        /**
         * Formats a URL by ensuring it has the proper protocol and port if needed.
         *
         * @param input The input string (could be IP, IP:port, or full URL)
         * @return Properly formatted URL
         */
        fun formatServerUrl(input: String): String {
            var formatted = input.trim()

            // If it doesn't start with http, assume http
            if (!formatted.startsWith("http://") && !formatted.startsWith("https://")) {
                formatted = "http://$formatted"
            }

            // If it's just an IP without port, add default port
            if (formatted.matches(Regex("^https?://\\d+\\.\\d+\\.\\d+\\.\\d+$"))) {
                formatted = "$formatted:$DEFAULT_PORT"
            }

            return formatted
        }

        /**
         * Tests if the server at the given URL is reachable and healthy.
         *
         * @param url The server URL to test
         * @return ConnectionTestResult with success status and details
         */
        suspend fun testServerConnection(url: String): ConnectionTestResult {
            return withContext(Dispatchers.IO) {
                try {
                    val formattedUrl = formatServerUrl(url)
                    val validation = validateServerUrl(formattedUrl)

                    if (!validation.isValid) {
                        return@withContext ConnectionTestResult(
                            success = false,
                            message = validation.errorMessage ?: "Invalid URL",
                            responseTime = 0,
                        )
                    }

                    val startTime = System.currentTimeMillis()
                    val request =
                        Request.Builder()
                            .url("$formattedUrl$HEALTH_ENDPOINT")
                            .build()

                    Log.d(TAG, "Testing connection to: $formattedUrl$HEALTH_ENDPOINT")

                    httpClient.newCall(request).execute().use { response ->
                        val responseTime = System.currentTimeMillis() - startTime

                        if (response.isSuccessful) {
                            val body = response.body?.string()
                            Log.d(TAG, "✅ Server connection successful - Response time: ${responseTime}ms")
                            return@withContext ConnectionTestResult(
                                success = true,
                                message = "Server is reachable (${responseTime}ms)",
                                responseTime = responseTime,
                                serverResponse = body,
                            )
                        } else {
                            Log.w(TAG, "❌ Server responded with error: ${response.code} ${response.message}")
                            return@withContext ConnectionTestResult(
                                success = false,
                                message = "Server error: ${response.code} ${response.message}",
                                responseTime = responseTime,
                            )
                        }
                    }
                } catch (e: IOException) {
                    Log.w(TAG, "❌ Connection failed: ${e.message}")
                    return@withContext ConnectionTestResult(
                        success = false,
                        message = "Connection failed: ${e.message}",
                        responseTime = 0,
                    )
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Unexpected error testing connection", e)
                    return@withContext ConnectionTestResult(
                        success = false,
                        message = "Unexpected error: ${e.message}",
                        responseTime = 0,
                    )
                }
            }
        }

        /**
         * Extracts IP address from various input formats.
         *
         * @param input Could be "192.168.1.100", "192.168.1.100:8000", or "http://192.168.1.100:8000"
         * @return Just the IP address part
         */
        fun extractIpAddress(input: String): String {
            var processed = input.trim()

            // Remove protocol
            processed = processed.removePrefix("http://").removePrefix("https://")

            // Remove port
            processed = processed.substringBefore(":")

            // Remove path
            processed = processed.substringBefore("/")

            return processed
        }

        /**
         * Result of URL validation.
         */
        data class ValidationResult(
            val isValid: Boolean,
            val errorMessage: String?,
        )

        /**
         * Result of server connection test.
         */
        data class ConnectionTestResult(
            val success: Boolean,
            val message: String,
            val responseTime: Long,
            val serverResponse: String? = null,
        )
    }
