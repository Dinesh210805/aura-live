package com.aura.aura_ui.executor

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import com.aura.aura_ui.MainActivity
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import com.aura.aura_ui.accessibility.gesture.*
import com.aura.aura_ui.data.Command
import com.aura.aura_ui.data.CommandResult
import java.util.UUID

/**
 * Executes commands received from the backend
 */
class CommandExecutor(private val context: Context) {
    companion object {
        private const val TAG = "CommandExecutor"
    }

    /**
     * Execute a command and return the result
     */
    fun executeCommand(command: Command): CommandResult {
        return try {
            Log.i(TAG, "⚙️ Executing: ${command.commandType} (${command.commandId})")

            val payload = command.payload ?: emptyMap()

            when (command.commandType) {
                "launch_app" -> executeLaunchApp(payload)
                "launch_deep_link" -> executeLaunchDeepLink(payload)
                "gesture" -> executeGesture(payload)
                "capture_screenshot" -> executeCaptureScreenshot()
                "send_message" -> executeSendMessage(payload)
                else -> {
                    Log.w(TAG, "⚠️ Unknown command type: ${command.commandType}")
                    CommandResult(
                        success = false,
                        error = "Unknown command type: ${command.commandType}",
                    )
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Command execution error: ${e.message}", e)
            CommandResult(
                success = false,
                error = "Execution failed: ${e.message}",
            )
        }
    }

    /**
     * Launch an app by package name
     */
    private fun executeLaunchApp(payload: Map<String, Any?>): CommandResult {
        val packageName = payload["package_name"] as? String

        if (packageName.isNullOrEmpty()) {
            return CommandResult(
                success = false,
                error = "Missing package_name in payload",
            )
        }

        return try {
            val intent = context.packageManager.getLaunchIntentForPackage(packageName)

            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)

                Log.i(TAG, "✅ Launched app: $packageName")
                CommandResult(success = true)
            } else {
                Log.e(TAG, "❌ App not found: $packageName")
                CommandResult(
                    success = false,
                    error = "App not found: $packageName",
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to launch app: ${e.message}", e)
            CommandResult(
                success = false,
                error = "Launch failed: ${e.message}",
            )
        }
    }

    /**
     * Launch a deep link URI (tel:, sms:, mailto:, http:, etc.)
     */
    private fun executeLaunchDeepLink(payload: Map<String, Any?>): CommandResult {
        val uri = payload["uri"] as? String
        val packageName = payload["package_name"] as? String

        if (uri.isNullOrEmpty()) {
            return CommandResult(
                success = false,
                error = "Missing uri in payload",
            )
        }

        return try {
            val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(uri))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

            // If a specific package is requested, target it
            if (!packageName.isNullOrEmpty()) {
                intent.setPackage(packageName)
            }

            // Check if any app can handle this intent
            val resolveInfo =
                context.packageManager.resolveActivity(
                    intent,
                    PackageManager.MATCH_DEFAULT_ONLY,
                )

            if (resolveInfo != null) {
                context.startActivity(intent)
                Log.i(TAG, "✅ Launched deep link: $uri${if (packageName != null) " via $packageName" else ""}")
                CommandResult(success = true)
            } else {
                Log.e(TAG, "❌ No app can handle URI: $uri")
                CommandResult(
                    success = false,
                    error = "No app available to handle: $uri",
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to launch deep link: ${e.message}", e)
            CommandResult(
                success = false,
                error = "Deep link launch failed: ${e.message}",
            )
        }
    }

    /**
     * Execute a gesture via AccessibilityService
     * Supports both new format (with target object) and legacy format (flat coordinates)
     */
    private fun executeGesture(payload: Map<String, Any?>): CommandResult {
        val service =
            AuraAccessibilityService.instance
                ?: return CommandResult(
                    success = false,
                    error = "AccessibilityService not available",
                )

        // Check if new format (has target object or gesture_type)
        val hasNewFormat = payload.containsKey("target") || payload.containsKey("gesture_type")

        if (hasNewFormat) {
            return executeNewGestureFormat(payload, service)
        }

        // Legacy format handling
        val action =
            payload["action"] as? String
                ?: return CommandResult(success = false, error = "Missing action in gesture payload")

        Log.i(TAG, "🎯 Executing gesture (legacy): action=$action")

        return executeLegacyGesture(action, payload, service)
    }

    /**
     * Execute new gesture format using GestureInjector
     * Returns immediately with a placeholder result - actual result reported asynchronously
     */
    private fun executeNewGestureFormat(
        payload: Map<String, Any?>,
        service: AuraAccessibilityService,
    ): CommandResult {
        val command =
            parseGestureCommand(payload)
                ?: return CommandResult(success = false, error = "Failed to parse gesture command")

        Log.i(TAG, "🎯 Executing gesture (new format): type=${command.gestureType}, id=${command.commandId}")

        // Execute asynchronously without blocking
        val callback =
            object : GestureCallback {
                override fun onSuccess(
                    cmd: GestureCommand,
                    executionTimeMs: Long,
                ) {
                    Log.i(TAG, "✅ Gesture succeeded: ${cmd.commandId} in ${executionTimeMs}ms")
                }

                override fun onFailure(
                    cmd: GestureCommand,
                    error: GestureError,
                    details: String?,
                ) {
                    Log.e(TAG, "❌ Gesture failed: ${cmd.commandId} - ${error.name}: $details")
                }

                override fun onCancelled(cmd: GestureCommand) {
                    Log.w(TAG, "⚠️ Gesture cancelled: ${cmd.commandId}")
                }
            }

        service.gestureInjector.execute(command, callback)

        // Return immediately - gesture will execute asynchronously
        // Actual result logged above but not blocking execution flow
        return CommandResult(success = true)
    }

    /**
     * Parse JSON payload into GestureCommand
     */
    private fun parseGestureCommand(payload: Map<String, Any?>): GestureCommand? {
        try {
            val commandId = (payload["command_id"] as? String) ?: "cmd_${UUID.randomUUID()}"
            val gestureTypeStr = (payload["gesture_type"] as? String) ?: "tap"
            val gestureType =
                when (gestureTypeStr.lowercase()) {
                    "tap" -> GestureType.TAP
                    "long_press" -> GestureType.LONG_PRESS
                    "swipe" -> GestureType.SWIPE
                    "scroll" -> GestureType.SCROLL
                    else -> GestureType.TAP
                }

            val target =
                parseGestureTarget(payload["target"])
                    ?: return null

            val endTarget =
                (payload["end_target"] as? Map<*, *>)?.let { endMap ->
                    @Suppress("UNCHECKED_CAST")
                    parseCoordinatesTarget(endMap as Map<String, Any?>)
                }

            val options = parseGestureOptions(payload["options"] as? Map<*, *>)

            return GestureCommand(
                commandId = commandId,
                gestureType = gestureType,
                target = target,
                endTarget = endTarget,
                options = options,
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse gesture command: ${e.message}", e)
            return null
        }
    }

    private fun parseGestureTarget(targetObj: Any?): GestureTarget? {
        if (targetObj == null) return null

        @Suppress("UNCHECKED_CAST")
        val targetMap = targetObj as? Map<String, Any?> ?: return null

        return when (val type = (targetMap["type"] as? String)?.lowercase()) {
            "coordinates" -> parseCoordinatesTarget(targetMap)
            "ui_element" -> parseUIElementTarget(targetMap)
            "direction" -> parseDirectionTarget(targetMap)
            else -> {
                // Auto-detect: if has x,y assume coordinates
                if (targetMap.containsKey("x") && targetMap.containsKey("y")) {
                    parseCoordinatesTarget(targetMap)
                } else if (targetMap.containsKey("direction")) {
                    parseDirectionTarget(targetMap)
                } else if (targetMap.containsKey("text") || targetMap.containsKey("resource_id")) {
                    parseUIElementTarget(targetMap)
                } else {
                    null
                }
            }
        }
    }

    private fun parseCoordinatesTarget(map: Map<String, Any?>): GestureTarget.Coordinates? {
        val x = (map["x"] as? Number)?.toFloat() ?: return null
        val y = (map["y"] as? Number)?.toFloat() ?: return null
        // Phase 8: Require explicit 'normalized' or 'format' field - no heuristic fallback
        val normalized = when {
            map.containsKey("normalized") -> map["normalized"] as? Boolean ?: false
            map.containsKey("format") -> (map["format"] as? String) != "pixels"
            else -> {
                Log.e(TAG, "❌ Invalid gesture: missing format/normalized field - coordinates must declare format")
                return null
            }
        }
        return GestureTarget.Coordinates(x, y, normalized)
    }

    private fun parseUIElementTarget(map: Map<String, Any?>): GestureTarget.UIElement {
        return GestureTarget.UIElement(
            text = map["text"] as? String,
            resourceId = (map["resource_id"] ?: map["resourceId"]) as? String,
            contentDesc = (map["content_desc"] ?: map["contentDesc"]) as? String,
            index = (map["index"] as? Number)?.toInt() ?: 0,
        )
    }

    private fun parseDirectionTarget(map: Map<String, Any?>): GestureTarget.Direction? {
        val dirStr = (map["direction"] as? String)?.uppercase() ?: return null
        val direction =
            try {
                SwipeDirection.valueOf(dirStr)
            } catch (e: Exception) {
                return null
            }
        val distanceRatio = (map["distance_ratio"] as? Number)?.toFloat() ?: 0.5f
        return GestureTarget.Direction(direction, distanceRatio)
    }

    private fun parseGestureOptions(optionsMap: Map<*, *>?): GestureOptions {
        if (optionsMap == null) return GestureOptions()

        return GestureOptions(
            durationMs = (optionsMap["duration_ms"] as? Number)?.toLong() ?: 100L,
            holdMs = (optionsMap["hold_ms"] as? Number)?.toLong() ?: 0L,
            retryCount = (optionsMap["retry_count"] as? Number)?.toInt() ?: 2,
            retryDelayMs = (optionsMap["retry_delay_ms"] as? Number)?.toLong() ?: 500L,
            timeoutMs = (optionsMap["timeout_ms"] as? Number)?.toLong() ?: 5000L,
        )
    }

    /**
     * DEPRECATED (Phase 8): Heuristic normalization detection.
     * This function is no longer used - all gestures must declare explicit format.
     * Kept for reference during transition.
     */
    @Deprecated("Phase 8: Use explicit format field instead of heuristic detection")
    private fun isNormalized(
        x: Float,
        y: Float,
    ): Boolean {
        return x in 0.0f..1.0f && y in 0.0f..1.0f
    }

    /**
     * Execute legacy gesture format
     */
    private fun executeLegacyGesture(
        action: String,
        payload: Map<String, Any?>,
        service: AuraAccessibilityService,
    ): CommandResult {
        return when (action.lowercase()) {
            "tap", "click" -> {
                val x =
                    (payload["x"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing x coordinate")
                val y =
                    (payload["y"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing y coordinate")

                service.performClick(x, y)
                Log.i(TAG, "✅ Tap executed at ($x, $y)")
                CommandResult(success = true)
            }

            "swipe" -> {
                val x1 =
                    (payload["x1"] as? Number)?.toInt()
                        ?: (payload["startX"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing start x coordinate")
                val y1 =
                    (payload["y1"] as? Number)?.toInt()
                        ?: (payload["startY"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing start y coordinate")
                val x2 =
                    (payload["x2"] as? Number)?.toInt()
                        ?: (payload["endX"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing end x coordinate")
                val y2 =
                    (payload["y2"] as? Number)?.toInt()
                        ?: (payload["endY"] as? Number)?.toInt()
                        ?: return CommandResult(success = false, error = "Missing end y coordinate")
                val duration = (payload["duration"] as? Number)?.toLong() ?: 300L

                service.performSwipe(x1, y1, x2, y2, duration)
                Log.i(TAG, "✅ Swipe executed from ($x1,$y1) to ($x2,$y2)")
                CommandResult(success = true)
            }

            "scroll_up" -> {
                service.performScroll("up")
                Log.i(TAG, "✅ Scroll up executed")
                CommandResult(success = true)
            }

            "scroll_down" -> {
                service.performScroll("down")
                Log.i(TAG, "✅ Scroll down executed")
                CommandResult(success = true)
            }

            "back" -> {
                service.performBack()
                Log.i(TAG, "✅ Back action executed")
                CommandResult(success = true)
            }

            "home" -> {
                service.performHome()
                Log.i(TAG, "✅ Home action executed")
                CommandResult(success = true)
            }

            "dismiss_keyboard" -> {
                service.dismissKeyboard()
                Log.i(TAG, "✅ Keyboard dismissed")
                CommandResult(success = true)
            }

            "press_enter" -> {
                val success = service.performEnterAction()
                Log.i(TAG, "✅ Enter key pressed (performEnterAction), success=$success")
                CommandResult(success = success)
            }

            "press_search" -> {
                service.pressKeyEvent(android.view.KeyEvent.KEYCODE_SEARCH)
                Log.i(TAG, "✅ Search key pressed")
                CommandResult(success = true)
            }

            "type", "text_input", "input" -> {
                val text =
                    payload["text"] as? String
                        ?: return CommandResult(success = false, error = "Missing text for input")

                val success = service.performTextInput(text)
                if (success) {
                    Log.i(TAG, "✅ Text input executed: '$text'")
                    CommandResult(success = true)
                } else {
                    Log.w(TAG, "⚠️ Text input failed")
                    CommandResult(success = false, error = "Text input failed - no focused input field")
                }
            }

            "capture_screenshot" -> {
                // Trigger immediate screenshot capture
                Log.i(TAG, "📸 Gesture: capture_screenshot triggered")
                if (!service.isMediaProjectionAvailable()) {
                    Log.w(TAG, "⚠️ MediaProjection not available")
                    requestScreenCapturePermissionPrompt()
                    CommandResult(success = false, error = "Screen capture permission required - prompt shown")
                } else {
                    service.triggerScreenshotCapture()
                    CommandResult(success = true)
                }
            }

            // System control actions (WiFi, Bluetooth, Flashlight, Volume, etc.)
            "control_torch", "control_flashlight", "toggle_flashlight",
            "wifi_on", "wifi_off", "toggle_wifi",
            "bluetooth_on", "bluetooth_off", "toggle_bluetooth",
            "volume_up", "volume_down", "mute", "unmute",
            "brightness_up", "brightness_down",
            -> {
                service.executeSystemAction(action)
                Log.i(TAG, "✅ System control executed: $action")
                CommandResult(success = true)
            }

            else -> {
                Log.w(TAG, "⚠️ Unknown gesture action: $action")
                CommandResult(success = false, error = "Unknown gesture action: $action")
            }
        }
    }

    /**
     * Capture screenshot immediately and send to backend
     */
    private fun executeCaptureScreenshot(): CommandResult {
        val service =
            AuraAccessibilityService.instance
                ?: return CommandResult(
                    success = false,
                    error = "AccessibilityService not available",
                )

        return try {
            Log.i(TAG, "📸 Capturing screenshot on demand...")

            // Check if MediaProjection is available
            if (!service.isMediaProjectionAvailable()) {
                Log.w(TAG, "⚠️ MediaProjection not available - screen capture permission not granted")
                requestScreenCapturePermissionPrompt()
                return CommandResult(
                    success = false,
                    error = "Screen capture permission required - prompt shown",
                )
            }

            // Trigger immediate screenshot capture
            service.triggerScreenshotCapture()

            Log.i(TAG, "✅ Screenshot capture triggered")
            CommandResult(success = true)
        } catch (e: Exception) {
            Log.e(TAG, "❌ Screenshot capture failed: ${e.message}", e)
            CommandResult(
                success = false,
                error = "Screenshot capture failed: ${e.message}",
            )
        }
    }

    private fun requestScreenCapturePermissionPrompt() {
        try {
            val intent =
                Intent(context, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    putExtra("REQUEST_SCREEN_CAPTURE", true)
                    putExtra("REQUEST_SOURCE", "command")
                    putExtra("FINISH_AFTER_PERMISSION", true)
                }
            context.startActivity(intent)
            Log.i(TAG, "📤 Started MainActivity for screen capture permission request")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to start permission request activity", e)
        }
    }

    /**
     * Send a message via deep link
     * TODO: Implement message sending
     */
    private fun executeSendMessage(payload: Map<String, Any?>): CommandResult {
        Log.i(TAG, "⚠️ Message sending not yet implemented")

        return CommandResult(
            success = false,
            error = "Message sending not yet implemented",
        )
    }
}
