package com.aura.aura_ui.services

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.aura.aura_ui.R
import com.aura.aura_ui.data.audio.AudioCaptureManager
import com.aura.aura_ui.presentation.overlay.OverlayManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Foreground service responsible for maintaining the floating voice assistant overlay
 * and handling background operations for voice processing.
 */
@AndroidEntryPoint
class AssistantForegroundService : LifecycleService() {
    @Inject
    lateinit var audioManager: AudioCaptureManager

    private var overlayManager: OverlayManager? = null
    private val notificationId = 1001
    private val channelId = "AuraAssistantChannel"

    companion object {
        const val ACTION_START_OVERLAY = "com.aura.aura_ui.START_OVERLAY"
        const val ACTION_STOP_OVERLAY = "com.aura.aura_ui.STOP_OVERLAY"
        const val ACTION_TOGGLE_LISTENING = "com.aura.aura_ui.TOGGLE_LISTENING"

        fun startOverlay(context: Context) {
            val intent =
                Intent(context, AssistantForegroundService::class.java).apply {
                    action = ACTION_START_OVERLAY
                }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopOverlay(context: Context) {
            val intent =
                Intent(context, AssistantForegroundService::class.java).apply {
                    action = ACTION_STOP_OVERLAY
                }
            context.startService(intent)
        }

        fun toggleListening(context: Context) {
            val intent =
                Intent(context, AssistantForegroundService::class.java).apply {
                    action = ACTION_TOGGLE_LISTENING
                }
            context.startService(intent)
        }
    }

    override fun onCreate() {
        super.onCreate()
        Log.d("AssistantService", "onCreate - Service created")
        createNotificationChannel()
        startForegroundService()
        Log.d("AssistantService", "onCreate - Foreground service started")
    }

    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int,
    ): Int {
        super.onStartCommand(intent, flags, startId)

        Log.d("AssistantService", "onStartCommand called with action: ${intent?.action}")

        intent?.action?.let { action ->
            when (action) {
                ACTION_START_OVERLAY -> {
                    Log.d("AssistantService", "ACTION_START_OVERLAY received")
                    if (overlayManager == null) {
                        Log.d("AssistantService", "OverlayManager is null, creating new one")
                        startOverlay()
                        if (overlayManager != null) {
                            Log.d("AssistantService", "✅ OverlayManager created and initialized successfully")
                        } else {
                            Log.e("AssistantService", "❌ OverlayManager is still null after startOverlay()")
                        }
                    } else {
                        Log.w("AssistantService", "OverlayManager already exists, calling show() again")
                        overlayManager?.show()
                    }
                }
                ACTION_STOP_OVERLAY -> {
                    Log.d("AssistantService", "ACTION_STOP_OVERLAY received")
                    stopOverlay()
                    stopSelf()
                }
                ACTION_TOGGLE_LISTENING -> {
                    Log.d("AssistantService", "ACTION_TOGGLE_LISTENING received")
                    // Toggle listening functionality would be handled by the overlay callback
                    // This action is currently not implemented
                }
            }
        }

        return START_STICKY
    }

    override fun onDestroy() {
        overlayManager?.hide()
        overlayManager = null
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val name = "AURA Voice Assistant"
            val descriptionText = "AURA voice assistant service - appears in Live Alerts"
            val importance = NotificationManager.IMPORTANCE_DEFAULT  // DEFAULT for Live Alert
            val channel =
                NotificationChannel(channelId, name, importance).apply {
                    description = descriptionText
                    setShowBadge(true)
                    enableLights(false)
                    enableVibration(false)
                    setSound(null, null)
                    lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                }

            val notificationManager: NotificationManager =
                getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundService() {
        val pendingIntent = createMainActivityPendingIntent()

        // Notification optimized for OnePlus Live Alerts
        val notification =
            NotificationCompat.Builder(this, channelId)
                .setContentTitle("AURA Assistant")
                .setContentText("Voice assistant active")
                .setSmallIcon(R.drawable.ic_mic)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setCategory(NotificationCompat.CATEGORY_STATUS)  // Status for Live Alert
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setColorized(true)
                .setColor(0xFF6B4EFF.toInt())  // AURA purple
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .addAction(createToggleAction())
                .addAction(createStopAction())
                .build()

        startForeground(notificationId, notification)
    }

    private fun createMainActivityPendingIntent(): PendingIntent {
        val intent = packageManager.getLaunchIntentForPackage(packageName)
        return PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun createToggleAction(): NotificationCompat.Action {
        val intent =
            Intent(this, AssistantForegroundService::class.java).apply {
                action = ACTION_TOGGLE_LISTENING
            }
        val pendingIntent =
            PendingIntent.getService(
                this,
                1,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

        return NotificationCompat.Action.Builder(
            R.drawable.ic_mic,
            "Toggle",
            pendingIntent,
        ).build()
    }

    private fun createStopAction(): NotificationCompat.Action {
        val intent =
            Intent(this, AssistantForegroundService::class.java).apply {
                action = ACTION_STOP_OVERLAY
            }
        val pendingIntent =
            PendingIntent.getService(
                this,
                2,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

        return NotificationCompat.Action.Builder(
            R.drawable.ic_mic_off,
            "Stop",
            pendingIntent,
        ).build()
    }

    private fun startOverlay() {
        try {
            Log.d("AssistantService", "startOverlay() called")

            // Check overlay permission
            if (!android.provider.Settings.canDrawOverlays(this)) {
                Log.e("AssistantService", "❌ Cannot draw overlays - permission not granted!")
                return
            }

            Log.d("AssistantService", "✅ Overlay permission granted")

            // Use OverlayManager for enhanced functionality
            overlayManager =
                OverlayManager(
                    context = this,
                    scope = lifecycleScope,
                    serverUrl = getServerUrl(),
                )
            Log.d("AssistantService", "OverlayManager instance created: ${overlayManager != null}")

            overlayManager?.initialize()
            Log.d("AssistantService", "OverlayManager.initialize() completed")

            overlayManager?.show()
            Log.d("AssistantService", "OverlayManager.show() completed")

            // Small delay to check if overlay actually appeared
            lifecycleScope.launch {
                kotlinx.coroutines.delay(500)
                Log.d("AssistantService", "Post-show check: overlayManager=${overlayManager != null}")
            }

            Log.i("AssistantService", "✅ Overlay started with manager")
        } catch (e: Exception) {
            Log.e("AssistantService", "❌ Failed to start overlay: ${e.message}", e)
            overlayManager = null
        }
    }

    private fun getServerUrl(): String {
        // Get from preferences or use default
        val prefs = getSharedPreferences("aura_prefs", Context.MODE_PRIVATE)
        return prefs.getString("server_url", "http://10.193.156.197:8000") ?: "http://10.193.156.197:8000"
    }

    private fun stopOverlay() {
        overlayManager?.hide()
        overlayManager = null
    }
}
