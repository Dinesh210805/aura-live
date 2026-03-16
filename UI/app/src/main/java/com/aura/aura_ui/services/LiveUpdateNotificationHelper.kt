package com.aura.aura_ui.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.aura.aura_ui.R

/**
 * Manages Android Live Update (promoted ongoing) notifications during AURA task execution.
 *
 * Per Google Live Update design guidelines (developer.android.com/develop/ui/views/notifications/live-update):
 *   - Appears as a compact chip in the status bar — does NOT expand the bubble overlay
 *   - Ongoing + promoted so it stays visible until the task completes
 *   - Cancelled immediately when execution finishes or errors
 *   - Falls back to a standard ongoing notification on API < 36
 *
 * Phase verbs shown in the chip:
 *   EXECUTING  → "Executing task"
 *   THINKING   → "Thinking..."
 *   SPEAKING   → "Speaking"
 *   ERROR      → "Error"
 */
object LiveUpdateNotificationHelper {

    private const val TAG = "LiveUpdateNotif"
    private const val CHANNEL_ID = "aura_live_update"
    private const val CHANNEL_NAME = "AURA Task Execution"
    private const val NOTIFICATION_ID = 9_001

    /** Post the live update chip. Call when automation starts (Processing state). */
    fun show(context: Context, taskDescription: String = "Executing task") {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        ensureChannel(nm)

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("AURA")
            .setContentText(taskDescription)
            .setOngoing(true)           // cannot be swiped away during execution
            .setOnlyAlertOnce(true)     // no repeated sound/vibration on updates
            .setShowWhen(false)

        // Request promotion to Live Update chip (Android 16 / API 36+)
        // On older devices this is silently ignored and falls back to standard ongoing.
        if (Build.VERSION.SDK_INT >= 36) {
            try {
                // Reflection-safe: if the method isn't present on the build, catch and continue
                val method = NotificationCompat.Builder::class.java
                    .getMethod("setRequestPromotedOngoing", Boolean::class.java)
                method.invoke(builder, true)
            } catch (e: Exception) {
                Log.d(TAG, "setRequestPromotedOngoing not available: ${e.message}")
            }
        }

        nm.notify(NOTIFICATION_ID, builder.build())
        Log.d(TAG, "Live update notification posted: $taskDescription")
    }

    /** Update the chip text mid-execution (e.g. step name changes). */
    fun update(context: Context, taskDescription: String) {
        show(context, taskDescription)
    }

    /** Cancel the chip. Call when execution completes, errors, or session ends. */
    fun cancel(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.cancel(NOTIFICATION_ID)
        Log.d(TAG, "Live update notification cancelled")
    }

    private fun ensureChannel(nm: NotificationManager) {
        if (nm.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            // IMPORTANCE_LOW = no sound, no heads-up; just status bar chip
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shows AURA task execution progress as a compact status bar chip"
            setShowBadge(false)
            enableVibration(false)
            enableLights(false)
        }
        nm.createNotificationChannel(channel)
    }
}
