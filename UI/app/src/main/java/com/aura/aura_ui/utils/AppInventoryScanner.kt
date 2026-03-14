package com.aura.aura_ui.utils

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.util.Log
import com.aura.aura_ui.data.AppInfo
import com.aura.aura_ui.data.IntentFilterInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Scans device for installed apps and extracts package names, app names, and deep links
 */
class AppInventoryScanner(private val context: Context) {
    companion object {
        private const val TAG = "AppInventoryScanner"

        // Comprehensive list of deep link schemes to check
        private val DEEP_LINK_SCHEMES =
            listOf(
                // Standard schemes
                "http",
                "https",
                "content",
                "file",
                // Communication
                "tel",
                "sms",
                "smsto",
                "mms",
                "mmsto",
                "mailto",
                // Social media & messaging
                "whatsapp",
                "fb",
                "instagram",
                "twitter",
                "telegram",
                "snapchat",
                "tiktok",
                "linkedin",
                "reddit",
                "discord",
                // Media & entertainment
                "youtube",
                "spotify",
                "netflix",
                "prime",
                "disney",
                "twitch",
                "soundcloud",
                // Productivity
                "zoom",
                "zoomus",
                "meet",
                "teams",
                "slack",
                "notion",
                "evernote",
                "onenote",
                // Maps & navigation
                "geo",
                "maps",
                "google.navigation",
                "waze",
                // Finance & payments
                "upi",
                "paytm",
                "gpay",
                "phonepe",
                "bhim",
                // Shopping
                "amazon",
                "flipkart",
                "myntra",
                "swiggy",
                "zomato",
                // Utilities
                "market",
                "intent",
                "package",
                "settings",
                // Generic app schemes
                "app",
                "apps",
                "android-app",
            )
    }

    /**
     * Scan all installed apps and extract their information.
     * Uses queryIntentActivities per scheme to build a reverse map —
     * the only reliable approach since package names don't reveal URI schemes.
     */
    suspend fun scanInstalledApps(): List<AppInfo> =
        withContext(Dispatchers.Default) {
            val packageManager = context.packageManager
            val installedApps = mutableListOf<AppInfo>()

            try {
                Log.i(TAG, "🔍 Starting app inventory scan...")

                // Get all installed packages
                val packages =
                    try {
                        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
                            packageManager.getInstalledApplications(
                                PackageManager.ApplicationInfoFlags.of(PackageManager.GET_META_DATA.toLong()),
                            )
                        } else {
                            @Suppress("DEPRECATION")
                            packageManager.getInstalledApplications(PackageManager.GET_META_DATA)
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to get installed applications: ${e.message}", e)
                        emptyList()
                    }

                // Build reverse map: packageName -> set of schemes it actually handles
                // queryIntentActivities is the only reliable way — package name ≠ URI scheme
                val packageSchemes = mutableMapOf<String, MutableSet<String>>()
                val packageBrowsableFilters = mutableMapOf<String, MutableList<IntentFilterInfo>>()

                for (scheme in DEEP_LINK_SCHEMES) {
                    try {
                        val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("$scheme://test")).apply {
                            addCategory(Intent.CATEGORY_BROWSABLE)
                        }
                        @Suppress("DEPRECATION")
                        val resolveInfos: List<ResolveInfo> = packageManager.queryIntentActivities(intent, 0)
                        for (info in resolveInfos) {
                            val pkg = info.activityInfo.packageName
                            packageSchemes.getOrPut(pkg) { mutableSetOf() }.add(scheme)
                            packageBrowsableFilters.getOrPut(pkg) { mutableListOf() }.add(
                                IntentFilterInfo(
                                    action = Intent.ACTION_VIEW,
                                    categories = listOf(Intent.CATEGORY_BROWSABLE),
                                    dataScheme = scheme,
                                    dataHost = info.filter?.authoritiesIterator()
                                        ?.takeIf { it.hasNext() }?.next()?.host,
                                )
                            )
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to query scheme $scheme: ${e.message}")
                    }
                }

                Log.i(TAG, "🔗 Scheme query complete: ${packageSchemes.size} apps have deep links")

                for (appInfo in packages) {
                    try {
                        val packageName = appInfo.packageName
                        val appName = try {
                            appInfo.loadLabel(packageManager).toString()
                        } catch (e: Exception) {
                            packageName
                        }
                        val versionName = try {
                            packageManager.getPackageInfo(packageName, 0).versionName ?: ""
                        } catch (e: Exception) {
                            ""
                        }
                        val isSystemApp = (appInfo.flags and ApplicationInfo.FLAG_SYSTEM) != 0

                        val intentFilters = mutableListOf<IntentFilterInfo>()
                        if (packageManager.getLaunchIntentForPackage(packageName) != null) {
                            intentFilters.add(
                                IntentFilterInfo(
                                    action = Intent.ACTION_MAIN,
                                    categories = listOf(Intent.CATEGORY_LAUNCHER),
                                ),
                            )
                        }
                        intentFilters.addAll(packageBrowsableFilters[packageName] ?: emptyList())

                        installedApps.add(
                            AppInfo(
                                packageName = packageName,
                                appName = appName,
                                isSystemApp = isSystemApp,
                                versionName = versionName,
                                deepLinks = (packageSchemes[packageName]?.sorted() ?: emptyList()),
                                intentFilters = intentFilters,
                            ),
                        )
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to scan app: ${appInfo.packageName} - ${e.message}")
                    }
                }

                Log.i(TAG, "✅ Scan complete: ${installedApps.size} apps found")
                Log.i(TAG, "📱 User apps: ${installedApps.count { !it.isSystemApp }}")
                Log.i(TAG, "⚙️ System apps: ${installedApps.count { it.isSystemApp }}")
                Log.i(TAG, "🔗 Apps with deep links: ${installedApps.count { it.deepLinks.isNotEmpty() }}")
            } catch (e: Exception) {
                Log.e(TAG, "❌ App scan failed: ${e.message}", e)
            }

            return@withContext installedApps
        }

    // Kept for reference — replaced by queryIntentActivities-based reverse lookup in scanInstalledApps()
    @Suppress("unused")
    private fun extractViewIntents_LEGACY(
        packageManager: PackageManager,
        packageName: String,
    ): ViewIntentResult {
        val deepLinks = mutableSetOf<String>()
        val intentFilters = mutableListOf<IntentFilterInfo>()

        try {
            // Check if app is launchable
            val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            if (launchIntent != null) {
                intentFilters.add(
                    IntentFilterInfo(
                        action = Intent.ACTION_MAIN,
                        categories = listOf(Intent.CATEGORY_LAUNCHER),
                        dataScheme = null,
                        dataHost = null
                    ),
                )
            }

            // Smart pattern matching for popular apps
            val pkgLower = packageName.lowercase()
            
            when {
                // Messaging
                "whatsapp" in pkgLower -> {
                    deepLinks.addAll(listOf("whatsapp", "https", "tel"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, listOf(Intent.CATEGORY_BROWSABLE), "whatsapp", null))
                }
                "telegram" in pkgLower -> {
                    deepLinks.addAll(listOf("tg", "https", "tel"))
                }
                "snapchat" in pkgLower -> {
                    deepLinks.addAll(listOf("snapchat", "https"))
                }
                "discord" in pkgLower -> {
                    deepLinks.addAll(listOf("discord", "https"))
                }
                
                // Social media
                "facebook" in pkgLower || "fb.apk" in pkgLower -> {
                    deepLinks.addAll(listOf("fb", "https"))
                }
                "instagram" in pkgLower -> {
                    deepLinks.addAll(listOf("instagram", "https"))
                }
                "twitter" in pkgLower || "x.com" in pkgLower -> {
                    deepLinks.addAll(listOf("twitter", "https"))
                }
                "tiktok" in pkgLower -> {
                    deepLinks.addAll(listOf("tiktok", "https"))
                }
                "linkedin" in pkgLower -> {
                    deepLinks.addAll(listOf("linkedin", "https"))
                }
                "reddit" in pkgLower -> {
                    deepLinks.addAll(listOf("reddit", "https"))
                }
                
                // Email
                "gmail" in pkgLower || "android.gm" in pkgLower || "email" in pkgLower -> {
                    deepLinks.addAll(listOf("mailto", "https"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, emptyList(), "mailto", null))
                }
                
                // Video conferencing
                "zoom" in pkgLower -> {
                    deepLinks.addAll(listOf("zoomus", "tel", "https"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, listOf(Intent.CATEGORY_BROWSABLE), "zoomus", "zoom.us"))
                }
                "meet" in pkgLower && "google" in pkgLower -> {
                    deepLinks.addAll(listOf("https"))
                }
                "teams" in pkgLower && "microsoft" in pkgLower -> {
                    deepLinks.addAll(listOf("msteams", "https"))
                }
                
                // Maps
                "maps" in pkgLower || "navigation" in pkgLower -> {
                    deepLinks.addAll(listOf("geo", "https"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, listOf(Intent.CATEGORY_BROWSABLE), "geo", null))
                }
                
                // Browsers
                "chrome" in pkgLower || "browser" in pkgLower || "brave" in pkgLower || "firefox" in pkgLower -> {
                    deepLinks.addAll(listOf("http", "https"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, listOf(Intent.CATEGORY_BROWSABLE), "http", null))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, listOf(Intent.CATEGORY_BROWSABLE), "https", null))
                }
                
                // Phone & SMS
                "dialer" in pkgLower || "phone" in pkgLower || "contacts" in pkgLower || "truecaller" in pkgLower -> {
                    deepLinks.addAll(listOf("tel", "sms"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, emptyList(), "tel", null))
                }
                "message" in pkgLower || "sms" in pkgLower -> {
                    deepLinks.addAll(listOf("sms", "smsto"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, emptyList(), "sms", null))
                }
                
                // Media
                "youtube" in pkgLower -> {
                    deepLinks.addAll(listOf("youtube", "https"))
                }
                "spotify" in pkgLower -> {
                    deepLinks.addAll(listOf("spotify", "https"))
                }
                "netflix" in pkgLower -> {
                    deepLinks.addAll(listOf("netflix", "https"))
                }
                
                // Payments
                "paytm" in pkgLower || "phonepe" in pkgLower || "gpay" in pkgLower || "bhim" in pkgLower -> {
                    deepLinks.addAll(listOf("upi", "https"))
                    intentFilters.add(IntentFilterInfo(Intent.ACTION_VIEW, emptyList(), "upi", null))
                }
            }

            // Fallback: generic app scheme for launchable apps
            if (deepLinks.isEmpty() && launchIntent != null) {
                deepLinks.add("app")
            }

        } catch (e: Exception) {
            Log.w(TAG, "Failed to extract deep links for $packageName: ${e.message}")
        }

        return ViewIntentResult(
            deepLinks = deepLinks.toList().sorted(),
            intentFilters = intentFilters,
        )
    }

    /**
     * Helper class for VIEW intent results
     */
    private data class ViewIntentResult(
        val deepLinks: List<String>,
        val intentFilters: List<IntentFilterInfo>,
    )
}
