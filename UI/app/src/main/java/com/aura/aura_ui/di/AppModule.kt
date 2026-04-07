package com.aura.aura_ui.di

import android.content.Context
import androidx.room.Room
import com.aura.aura_ui.data.database.AuraDatabase
import com.aura.aura_ui.data.manager.ServerConfigManager
import com.aura.aura_ui.data.network.AuraApiService
import com.aura.aura_ui.functiongemma.FunctionGemmaManager
import com.aura.aura_ui.data.repository.AssistantRepository
import com.aura.aura_ui.data.repository.AssistantRepositoryImpl
import com.aura.aura_ui.data.repository.AudioRepository
import com.aura.aura_ui.data.repository.AudioRepositoryImpl
import com.aura.aura_ui.data.repository.SettingsRepository
import com.aura.aura_ui.data.repository.SettingsRepositoryImpl
import com.aura.aura_ui.utils.AndroidLogger
import com.aura.aura_ui.utils.Logger
import com.aura.aura_ui.utils.PermissionManager
import com.google.gson.Gson
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

/**
 * Hilt module that provides application-level dependencies.
 * This module is installed in the SingletonComponent and follows
 * AURA's modular architecture principles.
 *
 * Network Configuration:
 * - Development: Uses phone hotspot (192.168.43.1) or WiFi (192.168.1.41)
 * - Production: Uses deployed server URL
 * - Automatically detects network environment
 */
@Module
@InstallIn(SingletonComponent::class)
object AppModule {
    /**
     * Network configuration for AURA backend connectivity.
     * Automatically discovers the server on the local network.
     */
    private fun getAuraBaseUrl(): String {
        return discoverAuraServer()
    }

    /**
     * Comprehensive server discovery mechanism.
     * Tries multiple strategies to find the AURA backend server.
     */
    private fun discoverAuraServer(): String {
        // Try to use cached IP first (if available)
        val cachedUrl = getCachedServerUrl()
        if (cachedUrl != null && isServerAvailable(cachedUrl)) {
            android.util.Log.i("AppModule", "✅ Using cached server: $cachedUrl")
            return cachedUrl
        }

        val candidateIPs = generateCandidateIPs()

        // Try each candidate IP
        for (ip in candidateIPs) {
            val url = "http://$ip:8000/"
            if (isServerAvailable(url)) {
                android.util.Log.i("AppModule", "✅ Found AURA server at: $url")
                // Cache the working URL for next time
                cacheServerUrl(url)
                return url
            } else {
                android.util.Log.d("AppModule", "❌ Server not available at: $url")
            }
        }

        // Fallback to first candidate if none found
        val fallback = "http://${candidateIPs.first()}:8000/"
        android.util.Log.w("AppModule", "⚠️ No server found, using fallback: $fallback")
        return fallback
    }

    /**
     * Get cached server URL from SharedPreferences.
     */
    private fun getCachedServerUrl(): String? {
        return try {
            // This will be injected properly when called from DI context
            null // For now, implement in actual usage
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Cache the working server URL for future use.
     */
    private fun cacheServerUrl(url: String) {
        try {
            // This will be implemented when we have proper context
            android.util.Log.i("AppModule", "Caching server URL: $url")
        } catch (e: Exception) {
            // Ignore caching errors
        }
    }

    /**
     * Generate list of candidate IP addresses to try.
     * Based on common network configurations.
     */
    private fun generateCandidateIPs(): List<String> {
        val candidates = mutableListOf<String>()

        // 1. Most likely candidates first (based on your changing IPs)
        candidates.addAll(
            listOf(
                "10.193.156.197", // Current machine IP
                "192.168.1.42", // Original config
                "192.168.43.1", // Phone hotspot
                "192.168.1.100", // Common range
                "192.168.1.101",
                "192.168.1.102",
                "192.168.0.100", // Another common range
                "192.168.0.101",
                "10.0.2.2", // Emulator (fallback)
            ),
        )

        // 2. Generate a few more common network IPs
        // Scan a limited range to avoid too much delay
        for (i in 1..10) {
            candidates.add("192.168.1.$i")
            candidates.add("192.168.0.$i")
        }

        // 3. Some common 10.x.x.x addresses
        candidates.addAll(
            listOf(
                "10.0.0.1",
                "10.1.1.1",
                "10.10.10.1",
            ),
        )

        return candidates.distinct()
    }

    /**
     * Quick check if AURA server is available at given URL.
     */
    private fun isServerAvailable(baseUrl: String): Boolean {
        return try {
            val client =
                OkHttpClient.Builder()
                    .connectTimeout(2, TimeUnit.SECONDS) // Very quick timeout
                    .readTimeout(3, TimeUnit.SECONDS)
                    .build()

            val request =
                Request.Builder()
                    .url("${baseUrl}health")
                    .build()

            client.newCall(request).execute().use { response ->
                response.isSuccessful && response.body?.string()?.contains("healthy") == true
            }
        } catch (e: Exception) {
            false
        }
    }

    @Provides
    @Singleton
    fun provideAuraDatabase(@ApplicationContext context: Context): AuraDatabase {
        return Room.databaseBuilder(
            context,
            AuraDatabase::class.java,
            "aura_database"
        ).build()
    }

    @Provides
    @Singleton
    fun provideSettingsRepository(
        @ApplicationContext context: Context,
    ): SettingsRepository {
        return SettingsRepositoryImpl(context)
    }

    @Provides
    @Singleton
    fun provideAudioRepository(database: AuraDatabase): AudioRepository {
        return AudioRepositoryImpl(database.audioDao())
    }

    @Provides
    @Singleton
    fun provideLogger(): Logger {
        return AndroidLogger()
    }

    @Provides
    @Singleton
    fun providePermissionManager(logger: Logger): PermissionManager {
        return PermissionManager(logger)
    }

    @Provides
    @Singleton
    fun provideGson(): Gson {
        return Gson()
    }

    /**
     * Provides HTTP client with logging for development debugging.
     * Follows AURA's diagnostic and monitoring principles.
     */
    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient {
        val builder =
            OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)

        // Add logging interceptor for development
        val loggingInterceptor =
            HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
            }
        builder.addInterceptor(loggingInterceptor)

        return builder.build()
    }

    /**
     * Provides Retrofit instance with dynamic network configuration.
     * Uses intelligent network detection for development flexibility.
     */
    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient): Retrofit {
        val baseUrl = getAuraBaseUrl()

        return Retrofit.Builder()
            .baseUrl(baseUrl) // Dynamic configuration
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    @Provides
    @Singleton
    fun provideAuraApiService(retrofit: Retrofit): AuraApiService {
        return retrofit.create(AuraApiService::class.java)
    }

    @Provides
    @Singleton
    fun provideAssistantRepository(
        auraApiService: AuraApiService,
        logger: Logger,
    ): AssistantRepository {
        return AssistantRepositoryImpl(auraApiService, logger)
    }

    @Provides
    @Singleton
    fun provideServerConfigManager(): ServerConfigManager {
        return ServerConfigManager()
    }

    @Provides
    @Singleton
    fun provideFunctionGemmaManager(
        @ApplicationContext context: Context,
    ): FunctionGemmaManager {
        return FunctionGemmaManager(context)
    }
}
