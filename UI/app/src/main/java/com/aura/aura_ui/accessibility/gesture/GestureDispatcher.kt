package com.aura.aura_ui.accessibility.gesture

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.os.Handler
import android.os.Looper
import com.aura.aura_ui.utils.AgentLogger
import kotlinx.coroutines.*
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.resume

enum class DispatchResult { COMPLETED, CANCELLED, REJECTED, TIMEOUT }

class GestureDispatcher(private val service: AccessibilityService) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val pendingGestures = ConcurrentHashMap<String, Job>()

    suspend fun dispatch(
        commandId: String,
        gesture: GestureDescription,
        timeoutMs: Long,
    ): DispatchResult =
        suspendCancellableCoroutine { cont ->
            val timeoutJob =
                CoroutineScope(Dispatchers.Main).launch {
                    delay(timeoutMs)
                    if (cont.isActive) {
                        AgentLogger.Auto.w("Gesture timeout", mapOf("commandId" to commandId))
                        cont.resume(DispatchResult.TIMEOUT)
                    }
                }
            pendingGestures[commandId] = timeoutJob

            val callback =
                object : AccessibilityService.GestureResultCallback() {
                    override fun onCompleted(gestureDescription: GestureDescription?) {
                        timeoutJob.cancel()
                        pendingGestures.remove(commandId)
                        if (cont.isActive) {
                            AgentLogger.Auto.d("Gesture completed", mapOf("commandId" to commandId))
                            cont.resume(DispatchResult.COMPLETED)
                        }
                    }

                    override fun onCancelled(gestureDescription: GestureDescription?) {
                        timeoutJob.cancel()
                        pendingGestures.remove(commandId)
                        if (cont.isActive) {
                            AgentLogger.Auto.w("Gesture cancelled", mapOf("commandId" to commandId))
                            cont.resume(DispatchResult.CANCELLED)
                        }
                    }
                }

            cont.invokeOnCancellation {
                timeoutJob.cancel()
                pendingGestures.remove(commandId)
            }

            val dispatched = service.dispatchGesture(gesture, callback, mainHandler)
            if (!dispatched) {
                timeoutJob.cancel()
                pendingGestures.remove(commandId)
                AgentLogger.Auto.w("Gesture rejected by system", mapOf("commandId" to commandId))
                cont.resume(DispatchResult.REJECTED)
            }
        }

    fun cancelAll() {
        pendingGestures.values.forEach { it.cancel() }
        pendingGestures.clear()
        AgentLogger.Auto.i("All pending gestures cancelled")
    }
}
