package com.aura.aura_ui.network

import android.util.Log
import com.aura.aura_ui.data.Command
import com.aura.aura_ui.data.CommandResponse
import com.aura.aura_ui.data.CommandResult
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * HTTP client for communicating with AURA backend
 */
class BackendApiClient(private val serverUrl: String) {
    companion object {
        private const val TAG = "BackendApiClient"
        private const val CONNECT_TIMEOUT = 10L // seconds
        private const val READ_TIMEOUT = 10L
        private const val WRITE_TIMEOUT = 10L
    }

    private val client =
        OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT, TimeUnit.SECONDS)
            .writeTimeout(WRITE_TIMEOUT, TimeUnit.SECONDS)
            .build()

    private val gson = Gson()
    private val jsonMediaType = "application/json".toMediaType()

    /**
     * Fetch pending commands for a device
     */
    suspend fun fetchPendingCommands(deviceName: String): Result<List<Command>> =
        withContext(Dispatchers.IO) {
            try {
                val url = "$serverUrl/device/commands/pending?device_name=$deviceName"

                val request =
                    Request.Builder()
                        .url(url)
                        .get()
                        .build()

                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        Log.e(TAG, "Failed to fetch commands: ${response.code}")
                        return@withContext Result.failure(
                            IOException("HTTP ${response.code}: ${response.message}"),
                        )
                    }

                    val body =
                        response.body?.string() ?: return@withContext Result.failure(
                            IOException("Empty response body"),
                        )

                    val commandResponse = gson.fromJson(body, CommandResponse::class.java)

                    Log.i(TAG, "📥 Received ${commandResponse.commandCount} command(s)")
                    Result.success(commandResponse.commands)
                }
            } catch (e: IOException) {
                Log.e(TAG, "Network error fetching commands: ${e.message}")
                Result.failure(e)
            } catch (e: Exception) {
                Log.e(TAG, "Error fetching commands: ${e.message}", e)
                Result.failure(e)
            }
        }

    /**
     * Report command execution result to backend
     */
    suspend fun reportCommandResult(
        commandId: String,
        result: CommandResult,
    ): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val url = "$serverUrl/device/commands/$commandId/result"

                val json = gson.toJson(result)
                val requestBody = json.toRequestBody(jsonMediaType)

                val request =
                    Request.Builder()
                        .url(url)
                        .post(requestBody)
                        .build()

                client.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.i(TAG, "✅ Result reported for: $commandId")
                        Result.success(Unit)
                    } else {
                        Log.e(TAG, "❌ Failed to report result: ${response.code}")
                        Result.failure(IOException("HTTP ${response.code}: ${response.message}"))
                    }
                }
            } catch (e: IOException) {
                Log.e(TAG, "Network error reporting result: ${e.message}")
                Result.failure(e)
            } catch (e: Exception) {
                Log.e(TAG, "Error reporting result: ${e.message}", e)
                Result.failure(e)
            }
        }

    /**
     * Test connection to backend
     */
    suspend fun testConnection(): Result<Boolean> =
        withContext(Dispatchers.IO) {
            try {
                val url = "$serverUrl/device/status"

                val request =
                    Request.Builder()
                        .url(url)
                        .get()
                        .build()

                client.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.i(TAG, "✅ Backend connection successful")
                        Result.success(true)
                    } else {
                        Log.e(TAG, "❌ Backend connection failed: ${response.code}")
                        Result.failure(IOException("HTTP ${response.code}"))
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Backend connection error: ${e.message}")
                Result.failure(e)
            }
        }
}
