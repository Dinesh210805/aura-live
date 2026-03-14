package com.aura.aura_ui.data.deeplink

import android.content.Context
import android.content.SharedPreferences
import com.aura.aura_ui.utils.AgentLogger
import org.json.JSONArray
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Local cache for app metadata and deep-link information
 * Uses SharedPreferences for development, can be extended to Room DB later
 */
@Singleton
class AppMetadataCache
    @Inject
    constructor(
        private val context: Context,
    ) {
        companion object {
            private const val PREFS_NAME = "app_metadata_cache"
            private const val KEY_METADATA_JSON = "metadata_json"
            private const val KEY_LAST_SYNC = "last_sync_timestamp"
            private const val KEY_CACHE_VERSION = "cache_version"
            private const val CURRENT_CACHE_VERSION = 1
        }

        private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        /**
         * Cache app metadata
         */
        fun cacheAppMetadata(metadataList: List<DeepLinkMetadata>) {
            try {
                AgentLogger.Deeplink.d("Caching metadata for ${metadataList.size} apps")

                val jsonArray = JSONArray()
                metadataList.forEach { metadata ->
                    val metadataJson =
                        JSONObject().apply {
                            put("packageName", metadata.packageName)
                            put("appName", metadata.appName)
                            put("lastUpdated", metadata.lastUpdated)

                            val deepLinksArray = JSONArray()
                            metadata.deepLinks.forEach { deepLink ->
                                val deepLinkJson =
                                    JSONObject().apply {
                                        put("scheme", deepLink.scheme)
                                        put("host", deepLink.host)
                                        put("pathPattern", deepLink.pathPattern)
                                        put("action", deepLink.action)
                                        put("categories", JSONArray(deepLink.categories))
                                        put("mimeType", deepLink.mimeType)
                                        put("isExported", deepLink.isExported)
                                    }
                                deepLinksArray.put(deepLinkJson)
                            }
                            put("deepLinks", deepLinksArray)
                        }
                    jsonArray.put(metadataJson)
                }

                prefs.edit()
                    .putString(KEY_METADATA_JSON, jsonArray.toString())
                    .putLong(KEY_LAST_SYNC, System.currentTimeMillis())
                    .putInt(KEY_CACHE_VERSION, CURRENT_CACHE_VERSION)
                    .apply()

                AgentLogger.Deeplink.i("Successfully cached metadata")
            } catch (e: Exception) {
                AgentLogger.Deeplink.e("Failed to cache metadata", e)
            }
        }

        /**
         * Retrieve cached app metadata
         */
        fun getCachedMetadata(): List<DeepLinkMetadata> {
            try {
                val jsonString = prefs.getString(KEY_METADATA_JSON, null)
                if (jsonString.isNullOrEmpty()) {
                    AgentLogger.Deeplink.d("No cached metadata found")
                    return emptyList()
                }

                val cacheVersion = prefs.getInt(KEY_CACHE_VERSION, 0)
                if (cacheVersion != CURRENT_CACHE_VERSION) {
                    AgentLogger.Deeplink.w("Cache version mismatch, clearing cache")
                    clearCache()
                    return emptyList()
                }

                val jsonArray = JSONArray(jsonString)
                val metadataList = mutableListOf<DeepLinkMetadata>()

                for (i in 0 until jsonArray.length()) {
                    val metadataJson = jsonArray.getJSONObject(i)

                    val deepLinks = mutableListOf<DeepLinkInfo>()
                    val deepLinksArray = metadataJson.getJSONArray("deepLinks")

                    for (j in 0 until deepLinksArray.length()) {
                        val deepLinkJson = deepLinksArray.getJSONObject(j)
                        val categories = mutableListOf<String>()
                        val categoriesArray = deepLinkJson.getJSONArray("categories")

                        for (k in 0 until categoriesArray.length()) {
                            categories.add(categoriesArray.getString(k))
                        }

                        deepLinks.add(
                            DeepLinkInfo(
                                scheme = deepLinkJson.optString("scheme", null),
                                host = deepLinkJson.optString("host", null),
                                pathPattern = deepLinkJson.optString("pathPattern", null),
                                action = deepLinkJson.getString("action"),
                                categories = categories,
                                mimeType = deepLinkJson.optString("mimeType", null),
                                isExported = deepLinkJson.optBoolean("isExported", false),
                            ),
                        )
                    }

                    metadataList.add(
                        DeepLinkMetadata(
                            packageName = metadataJson.getString("packageName"),
                            appName = metadataJson.getString("appName"),
                            deepLinks = deepLinks,
                            lastUpdated = metadataJson.getLong("lastUpdated"),
                        ),
                    )
                }

                AgentLogger.Deeplink.d("Retrieved ${metadataList.size} cached metadata entries")
                return metadataList
            } catch (e: Exception) {
                AgentLogger.Deeplink.e("Failed to retrieve cached metadata", e)
                return emptyList()
            }
        }

        /**
         * Get metadata for specific package
         */
        fun getMetadataForPackage(packageName: String): DeepLinkMetadata? {
            return getCachedMetadata().find { it.packageName == packageName }
        }

        /**
         * Check if cache is stale (older than specified hours)
         */
        fun isCacheStale(maxAgeHours: Int = 24): Boolean {
            val lastSync = prefs.getLong(KEY_LAST_SYNC, 0)
            val maxAge = maxAgeHours * 60 * 60 * 1000L // Convert to milliseconds
            val isStale = (System.currentTimeMillis() - lastSync) > maxAge

            AgentLogger.Deeplink.d(
                "Cache age check",
                mapOf(
                    "lastSync" to lastSync,
                    "maxAgeHours" to maxAgeHours,
                    "isStale" to isStale,
                ),
            )

            return isStale
        }

        /**
         * Clear all cached metadata
         */
        fun clearCache() {
            try {
                prefs.edit()
                    .remove(KEY_METADATA_JSON)
                    .remove(KEY_LAST_SYNC)
                    .remove(KEY_CACHE_VERSION)
                    .apply()

                AgentLogger.Deeplink.i("Cache cleared successfully")
            } catch (e: Exception) {
                AgentLogger.Deeplink.e("Failed to clear cache", e)
            }
        }

        /**
         * Get cache statistics
         */
        fun getCacheStats(): Map<String, Any> {
            val metadata = getCachedMetadata()
            val lastSync = prefs.getLong(KEY_LAST_SYNC, 0)
            val totalDeepLinks = metadata.sumOf { it.deepLinks.size }

            return mapOf(
                "totalApps" to metadata.size,
                "totalDeepLinks" to totalDeepLinks,
                "lastSync" to lastSync,
                "cacheVersion" to prefs.getInt(KEY_CACHE_VERSION, 0),
                "isStale" to isCacheStale(),
            )
        }

        /**
         * Placeholder for future server sync functionality
         */
        suspend fun syncWithServer(): Boolean {
            // TODO: Implement server synchronization
            AgentLogger.Deeplink.i("Server sync placeholder called - not yet implemented")
            return false
        }
    }
