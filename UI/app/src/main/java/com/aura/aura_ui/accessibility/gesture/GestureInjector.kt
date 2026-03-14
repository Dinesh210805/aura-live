package com.aura.aura_ui.accessibility.gesture

import android.accessibilityservice.AccessibilityService
import com.aura.aura_ui.utils.AgentLogger
import kotlinx.coroutines.*

class GestureInjector(private val service: AccessibilityService) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val resolver = CoordinateResolver(service)
    private val builder = GestureBuilder()
    private val dispatcher = GestureDispatcher(service)
    private val retryExecutor = RetryExecutor(resolver, builder, dispatcher)

    fun execute(
        command: GestureCommand,
        callback: GestureCallback,
    ) {
        scope.launch {
            try {
                val validationError = validateCommand(command)
                if (validationError != null) {
                    callback.onFailure(command, validationError.first, validationError.second)
                    return@launch
                }

                val result = retryExecutor.executeWithRetry(command)

                when (result) {
                    is GestureResult.Success -> {
                        AgentLogger.Auto.i(
                            "Gesture executed successfully",
                            mapOf(
                                "commandId" to result.commandId,
                                "executionTimeMs" to result.executionTimeMs,
                            ),
                        )
                        callback.onSuccess(command, result.executionTimeMs)
                    }
                    is GestureResult.Failure -> {
                        AgentLogger.Auto.w(
                            "Gesture execution failed",
                            mapOf(
                                "commandId" to result.commandId,
                                "error" to result.error.name,
                                "details" to (result.details ?: ""),
                            ),
                        )
                        callback.onFailure(command, result.error, result.details)
                    }
                    is GestureResult.Cancelled -> {
                        AgentLogger.Auto.i(
                            "Gesture cancelled",
                            mapOf(
                                "commandId" to result.commandId,
                            ),
                        )
                        callback.onCancelled(command)
                    }
                }
            } catch (e: Exception) {
                AgentLogger.Auto.e("Gesture execution exception", e)
                callback.onFailure(
                    command,
                    GestureError.DISPATCH_FAILED,
                    e.message ?: "Unknown error",
                )
            }
        }
    }

    fun cancelAll() {
        dispatcher.cancelAll()
        AgentLogger.Auto.i("GestureInjector: All gestures cancelled")
    }

    fun getScreenDimensions(): Pair<Int, Int> {
        return Pair(resolver.screenWidth, resolver.screenHeight)
    }

    private fun validateCommand(command: GestureCommand): Pair<GestureError, String>? {
        if (service.rootInActiveWindow == null) {
            return Pair(GestureError.SERVICE_UNAVAILABLE, "No active window available")
        }

        if (command.commandId.isBlank()) {
            return Pair(GestureError.INVALID_COMMAND, "Command ID is blank")
        }

        if (command.gestureType == GestureType.SWIPE &&
            command.target is GestureTarget.Coordinates &&
            command.endTarget == null
        ) {
            return Pair(GestureError.INVALID_COMMAND, "Swipe requires end_target for coordinate targets")
        }

        return null
    }
}
