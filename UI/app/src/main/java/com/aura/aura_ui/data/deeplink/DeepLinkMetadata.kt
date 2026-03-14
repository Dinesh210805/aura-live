package com.aura.aura_ui.data.deeplink

/**
 * Data models for deep-link metadata
 */
data class DeepLinkMetadata(
    val packageName: String,
    val appName: String,
    val deepLinks: List<DeepLinkInfo>,
    val lastUpdated: Long = System.currentTimeMillis(),
)

data class DeepLinkInfo(
    val scheme: String?,
    val host: String?,
    val pathPattern: String?,
    val action: String,
    val categories: List<String>,
    val mimeType: String?,
    val isExported: Boolean = false,
)

data class AppInfo(
    val packageName: String,
    val appName: String,
    val versionName: String,
    val versionCode: Long,
    val isSystemApp: Boolean,
    val lastUpdateTime: Long,
)
