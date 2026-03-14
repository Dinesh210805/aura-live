package com.aura.aura_ui

import android.app.Application
import com.aura.aura_ui.overlay.AuraOverlayManager
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class AuraApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        
        // Initialize overlay manager for system-wide overlay support
        AuraOverlayManager.initialize(this)
    }
}
