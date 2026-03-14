
package com.aura.aura_ui.data.deeplink

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import com.aura.aura_ui.utils.AgentLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager for discovering and caching deep-link metadata from installed apps
 */
@Singleton
class DeepLinkManager
    @Inject
    constructor(
        private val context: Context,
        private val cache: AppMetadataCache,
    ) {
        private val packageManager = context.packageManager

        /**
         * Discover deep-links from all installed apps and cache locally
         */
        suspend fun discoverAndCacheDeepLinks(forceRefresh: Boolean = false): Boolean =
            withContext(Dispatchers.IO) {
                try {
                    if (!forceRefresh && !cache.isCacheStale()) {
                        AgentLogger.Deeplink.d("Cache is fresh, skipping discovery")
                        return@withContext true
                    }

                    AgentLogger.Deeplink.i("Starting deep-link discovery for installed apps")

                    val installedPackages = packageManager.getInstalledPackages(PackageManager.GET_ACTIVITIES)
                    val metadataList = mutableListOf<DeepLinkMetadata>()

                    var processedCount = 0
                    var errorCount = 0

                    installedPackages.forEach { packageInfo ->
                        try {
                            val deepLinks = extractDeepLinksFromPackage(packageInfo.packageName)
                            val appName = getAppName(packageInfo.packageName)

                            if (deepLinks.isNotEmpty()) {
                                metadataList.add(
                                    DeepLinkMetadata(
                                        packageName = packageInfo.packageName,
                                        appName = appName,
                                        deepLinks = deepLinks,
                                    ),
                                )

                                AgentLogger.Deeplink.d("Found ${deepLinks.size} deep-links for $appName")
                            }

                            processedCount++
                        } catch (e: Exception) {
                            errorCount++
                            AgentLogger.Deeplink.e("Failed to process package ${packageInfo.packageName}", e)
                        }
                    }

                    // Cache the discovered metadata
                    cache.cacheAppMetadata(metadataList)

                    AgentLogger.Deeplink.i(
                        "Deep-link discovery completed",
                        mapOf(
                            "totalPackages" to installedPackages.size,
                            "processedPackages" to processedCount,
                            "appsWithDeepLinks" to metadataList.size,
                            "totalDeepLinks" to metadataList.sumOf { it.deepLinks.size },
                            "errors" to errorCount,
                        ),
                    )

                    return@withContext true
                } catch (e: Exception) {
                    AgentLogger.Deeplink.e("Deep-link discovery failed", e)
                    return@withContext false
                }
            }

        /**
         * Extract deep-link information from a specific package
         */
        private fun extractDeepLinksFromPackage(packageName: String): List<DeepLinkInfo> {
            val deepLinks = mutableListOf<DeepLinkInfo>()

            try {
                // Get all activities that can handle intents
                val intent =
                    Intent(Intent.ACTION_VIEW).apply {
                        setPackage(packageName)
                    }

                val resolveInfos = packageManager.queryIntentActivities(intent, PackageManager.GET_RESOLVED_FILTER)

                resolveInfos.forEach { resolveInfo ->
                    resolveInfo.filter?.let { intentFilter ->
                        // Extract actions
                        val actions = mutableListOf<String>()
                        for (i in 0 until intentFilter.countActions()) {
                            actions.add(intentFilter.getAction(i))
                        }

                        // Extract categories
                        val categories = mutableListOf<String>()
                        for (i in 0 until intentFilter.countCategories()) {
                            categories.add(intentFilter.getCategory(i))
                        }

                        // Extract data schemes and hosts
                        if (intentFilter.countDataSchemes() > 0 || intentFilter.countDataAuthorities() > 0) {
                            for (schemeIndex in 0 until maxOf(1, intentFilter.countDataSchemes())) {
                                val scheme =
                                    if (intentFilter.countDataSchemes() > schemeIndex) {
                                        intentFilter.getDataScheme(schemeIndex)
                                    } else {
                                        null
                                    }

                                for (authIndex in 0 until maxOf(1, intentFilter.countDataAuthorities())) {
                                    val authority =
                                        if (intentFilter.countDataAuthorities() > authIndex) {
                                            intentFilter.getDataAuthority(authIndex)
                                        } else {
                                            null
                                        }

                                    val host = authority?.host

                                    // Extract path patterns
                                    val pathPatterns = mutableListOf<String>()
                                    for (pathIndex in 0 until intentFilter.countDataPaths()) {
                                        pathPatterns.add(intentFilter.getDataPath(pathIndex).path)
                                    }

                                    actions.forEach { action ->
                                        deepLinks.add(
                                            DeepLinkInfo(
                                                scheme = scheme,
                                                host = host,
                                                pathPattern = pathPatterns.firstOrNull(),
                                                action = action,
                                                categories = categories,
                                                mimeType =
                                                    if (intentFilter.countDataTypes() > 0) {
                                                        intentFilter.getDataType(0)
                                                    } else {
                                                        null
                                                    },
                                                isExported = resolveInfo.activityInfo.exported,
                                            ),
                                        )
                                    }
                                }
                            }
                        } else {
                            // No data schemes, just add basic intent info
                            actions.forEach { action ->
                                deepLinks.add(
                                    DeepLinkInfo(
                                        scheme = null,
                                        host = null,
                                        pathPattern = null,
                                        action = action,
                                        categories = categories,
                                        mimeType = null,
                                        isExported = resolveInfo.activityInfo.exported,
                                    ),
                                )
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                AgentLogger.Deeplink.e("Failed to extract deep-links for $packageName", e)
            }

            return deepLinks
        }

        /**
         * Get human-readable app name for package
         */
        private fun getAppName(packageName: String): String {
            return try {
                val appInfo = packageManager.getApplicationInfo(packageName, 0)
                packageManager.getApplicationLabel(appInfo).toString()
            } catch (e: Exception) {
                packageName // Fallback to package name
            }
        }

        /**
         * Get cached deep-link metadata for all apps
         */
        fun getAllCachedMetadata(): List<DeepLinkMetadata> {
            return cache.getCachedMetadata()
        }

        /**
         * Get deep-link metadata for specific package
         */
        fun getMetadataForPackage(packageName: String): DeepLinkMetadata? {
            return cache.getMetadataForPackage(packageName)
        }

        /**
         * Search for apps with specific deep-link schemes
         */
        fun findAppsWithScheme(scheme: String): List<DeepLinkMetadata> {
            return cache.getCachedMetadata().filter { metadata ->
                metadata.deepLinks.any { it.scheme?.equals(scheme, ignoreCase = true) == true }
            }
        }

        /**
         * Search for apps with specific hosts
         */
        fun findAppsWithHost(host: String): List<DeepLinkMetadata> {
            return cache.getCachedMetadata().filter { metadata ->
                metadata.deepLinks.any { it.host?.equals(host, ignoreCase = true) == true }
            }
        }

        /**
         * Get cache statistics
         */
        fun getCacheStats(): Map<String, Any> {
            return cache.getCacheStats()
        }

        /**
         * Clear cache and force refresh on next discovery
         */
        fun clearCache() {
            cache.clearCache()
            AgentLogger.Deeplink.i("Deep-link cache cleared")
        }

        /**
         * Placeholder for server synchronization
         */
        suspend fun syncWithServer(): Boolean {
            return cache.syncWithServer()
        }
    }
