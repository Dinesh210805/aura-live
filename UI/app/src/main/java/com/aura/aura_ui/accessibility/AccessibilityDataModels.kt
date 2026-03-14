package com.aura.aura_ui.accessibility

data class UIElementData(
    val text: String?,
    val contentDescription: String?,
    val bounds: BoundsData,
    val className: String?,
    val isClickable: Boolean,
    val isScrollable: Boolean,
    val isEditable: Boolean,
    val isEnabled: Boolean,
    val isFocused: Boolean,
    val actions: List<String>,
    val packageName: String?,
    val viewId: String?,
)

data class BoundsData(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
    val centerX: Int,
    val centerY: Int,
    val width: Int,
    val height: Int,
)

data class ScreenshotData(
    val screenshot: String,
    val screenWidth: Int,
    val screenHeight: Int,
    val timestamp: Long,
    val uiElements: List<UIElementData>,
    val error: String? = null,  // Optional error message (permission invalidation, etc.)
)

data class GestureRequest(
    val action: String,
    val x: Int? = null,
    val y: Int? = null,
    val x2: Int? = null,
    val y2: Int? = null,
    val duration: Long = 300L,
    val command_id: String? = null,
)

data class DeviceInfo(
    val deviceName: String,
    val manufacturer: String,
    val model: String,
    val androidVersion: String,
    val screenWidth: Int,
    val screenHeight: Int,
)
