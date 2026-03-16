package com.aura.aura_ui.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.aura.aura_ui.services.WakeWordListeningService

/**
 * BroadcastReceiver that starts WakeWordListeningService after device boot
 * if wake word was previously enabled by the user.
 * 
 * Handles:
 * - BOOT_COMPLETED: Device finished booting
 * - QUICKBOOT_POWERON: Fast boot on some devices
 * - MY_PACKAGE_REPLACED: App was updated
 */
class BootReceiver : BroadcastReceiver() {
    
    companion object {
        private const val TAG = "BootReceiver"
        private const val PREFS_NAME = "aura_settings"
        private const val KEY_WAKE_WORD_ENABLED = "wake_word_enabled"
    }
    
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.d(TAG, "Received broadcast: $action")
        
        when (action) {
            Intent.ACTION_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON",
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                if (isWakeWordEnabled(context)) {
                    Log.i(TAG, "Wake word was enabled - starting WakeWordListeningService")
                    WakeWordListeningService.start(context)
                } else {
                    Log.d(TAG, "Wake word not enabled - skipping service start")
                }
            }
        }
    }
    
    private fun isWakeWordEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getBoolean(KEY_WAKE_WORD_ENABLED, false)
    }
}
