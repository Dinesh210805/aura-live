package com.aura.aura_ui.data.network

import retrofit2.Response
import retrofit2.http.*

/**
 * Retrofit API service for AURA Backend
 * Based on the existing FastAPI backend endpoints
 */
interface AuraApiService {
    /**
     * Execute a voice command task
     */
    @POST("tasks/execute")
    suspend fun executeTask(
        @Body request: TaskRequestDto,
    ): Response<TaskResponseDto>

    /**
     * Execute task from uploaded file
     */
    @Multipart
    @POST("tasks/execute-file")
    suspend fun executeTaskFromFile(
        @Part file: okhttp3.MultipartBody.Part,
        @Part("config") config: String? = null,
        @Part("thread_id") threadId: String? = null,
    ): Response<TaskResponseDto>

    /**
     * Get backend health status
     */
    @GET("health")
    suspend fun getHealthStatus(): Response<HealthResponseDto>

    /**
     * Get backend configuration
     */
    @GET("config")
    suspend fun getConfiguration(): Response<ConfigurationDto>

    /**
     * Get graph information
     */
    @GET("graph/info")
    suspend fun getGraphInfo(): Response<Map<String, Any>>
}
