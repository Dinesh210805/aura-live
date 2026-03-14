package com.aura.aura_ui

import android.Manifest
import android.accessibilityservice.AccessibilityServiceInfo
import android.app.KeyguardManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.WindowManager
import android.view.accessibility.AccessibilityManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import com.aura.aura_ui.audio.WavAudioPlayer
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.conversation.ConversationViewModel
import com.aura.aura_ui.data.manager.ServerConfigManager
import com.aura.aura_ui.data.preferences.OnboardingPreferences
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.data.repository.SettingsRepository
import com.aura.aura_ui.functiongemma.FunctionGemmaManager
import com.aura.aura_ui.presentation.screens.*
import com.aura.aura_ui.services.AssistantForegroundService
import com.aura.aura_ui.services.WakeWordListeningService
import com.aura.aura_ui.ui.theme.*
import com.aura.aura_ui.voice.VoiceCaptureController
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject
    lateinit var settingsRepository: SettingsRepository

    @Inject
    lateinit var serverConfigManager: ServerConfigManager

    @Inject
    lateinit var functionGemmaManager: FunctionGemmaManager

    companion object {
        private const val TAG = "MainActivity"
        private const val EXTRA_REQUEST_SCREEN_CAPTURE = "REQUEST_SCREEN_CAPTURE"
        private const val EXTRA_REQUEST_SOURCE = "REQUEST_SOURCE"
        private const val EXTRA_FINISH_AFTER_PERMISSION = "FINISH_AFTER_PERMISSION"
        private const val REQUEST_SOURCE_SETTINGS = "settings"

        // Fallback URLs if discovery fails
        private val FALLBACK_SERVER_URLS =
            arrayOf(
                "http://10.193.156.197:8000", // Current development machine IP
                "http://192.168.1.41:8000", // Original config
                "http://192.168.43.1:8000", // Phone hotspot
                "http://10.0.2.2:8000", // Android emulator host (fallback)
            )

        private fun generateMoreCandidates(): Array<String> {
            val candidates = mutableListOf<String>()

            // Generate some common IP ranges
            for (i in 100..110) {
                candidates.add("http://192.168.1.$i:8000")
                candidates.add("http://192.168.0.$i:8000")
            }

            return candidates.toTypedArray()
        }

        private fun isServerReachable(url: String): Boolean {
            return try {
                val client =
                    OkHttpClient.Builder()
                        .connectTimeout(2, TimeUnit.SECONDS)
                        .readTimeout(3, TimeUnit.SECONDS)
                        .build()

                val request =
                    okhttp3.Request.Builder()
                        .url("$url/health")
                        .build()

                client.newCall(request).execute().use { response ->
                    response.isSuccessful
                }
            } catch (e: Exception) {
                false
            }
        }
    }

    // Current server URL state
    private var currentServerUrl: String = FALLBACK_SERVER_URLS[0]

    // Smart UI capture state
    private var captureReason: String = "routine_monitoring"

    /**
     * Gets the current server URL based on user settings.
     * Uses manual configuration if set, otherwise falls back to auto-discovery.
     * Also updates the accessibility service with the discovered URL.
     */
    private suspend fun getCurrentServerUrl(): String {
        return withContext(Dispatchers.IO) {
            try {
                val useAutoDiscovery = settingsRepository.observeUseAutoDiscovery().first()
                val manualServerUrl = settingsRepository.observeServerUrl().first()

                val serverUrl =
                    when {
                        !useAutoDiscovery && !manualServerUrl.isNullOrBlank() -> {
                            Log.i(TAG, "✅ Using manual server configuration: $manualServerUrl")
                            currentServerUrl = manualServerUrl
                            manualServerUrl
                        }
                        else -> {
                            Log.i(TAG, "🔍 Using auto-discovery for server connection")
                            val discovered = discoverServer()
                            currentServerUrl = discovered
                            discovered
                        }
                    }

                // Update accessibility service with the current backend URL
                AuraAccessibilityService.setBackendUrl(serverUrl)

                serverUrl
            } catch (e: Exception) {
                Log.e(TAG, "Error getting server URL, using fallback", e)
                val fallback = FALLBACK_SERVER_URLS[0]
                currentServerUrl = fallback

                // Update accessibility service even with fallback URL
                AuraAccessibilityService.setBackendUrl(fallback)

                fallback
            }
        }
    }

    /**
     * Discovers available server on the network.
     * Tries saved URLs first, then fallback URLs.
     */
    private suspend fun discoverServer(): String {
        // Get saved URLs from settings
        val savedUrls =
            try {
                settingsRepository.getServerUrls()
            } catch (e: Exception) {
                Log.w(TAG, "Failed to load saved server URLs", e)
                emptyList()
            }

        // Combine saved URLs + fallback URLs + generated candidates
        val candidateUrls = savedUrls + FALLBACK_SERVER_URLS + generateMoreCandidates()

        Log.d(TAG, "🔍 Trying ${candidateUrls.size} server URLs (${savedUrls.size} saved, ${FALLBACK_SERVER_URLS.size} fallback)")

        for (url in candidateUrls) {
            if (isServerReachable(url)) {
                Log.i(TAG, "✅ Discovered server at: $url")
                return url
            }
        }

        // If no server found, use first fallback
        val fallback = FALLBACK_SERVER_URLS[0]
        Log.w(TAG, "⚠️ No server discovered, using fallback: $fallback")
        return fallback
    }

    private val httpClient =
        OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS) // Reduced for faster feedback
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false) // Don't retry immediately
            .build()

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var audioData = mutableListOf<ByteArray>()

    // Conversation mode controller
    private var voiceCaptureController: VoiceCaptureController? = null

    private val requiredPermissions =
        arrayOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.INTERNET,
        )

    private val permissionLauncher =
        registerForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions(),
        ) { permissions ->
            Log.d(TAG, "Permission results: $permissions")
            val allGranted = permissions.values.all { it }
            Log.d(TAG, "All permissions granted: $allGranted")

            if (!allGranted) {
                Log.w(TAG, "Some runtime permissions were denied")
            }
        }

    // Screen capture permission launcher
    private val screenCaptureLauncher =
        registerForActivityResult(
            ActivityResultContracts.StartActivityForResult(),
        ) { result ->
            if (result.resultCode == RESULT_OK && result.data != null) {
                val service = AuraAccessibilityService.instance
                if (service != null) {
                    try {
                        val success = service.initializeMediaProjection(result.resultCode, result.data!!)
                        
                        if (success) {
                            Log.d(TAG, "✅ Screen capture permission granted and initialized")
                            
                            // Update StateFlow with actual availability status
                            val isAvailable = service.isMediaProjectionAvailable()
                            AuraAccessibilityService.updateScreenCaptureStatus(isAvailable)
                            
                            // Mark as granted in preferences
                            getSharedPreferences("aura_prefs", Context.MODE_PRIVATE)
                                .edit()
                                .putBoolean("screen_capture_granted", true)
                                .apply()
                            
                            // Notify backend that permission was granted
                            AuraAccessibilityService.sendScreenCapturePermissionResult(granted = true)
                            
                            android.widget.Toast.makeText(
                                this,
                                "✅ Screen capture enabled - AURA can now capture screenshots",
                                android.widget.Toast.LENGTH_LONG,
                            ).show()
                        } else {
                            Log.e(TAG, "❌ MediaProjection initialization returned false")
                            AuraAccessibilityService.updateScreenCaptureStatus(false)
                            AuraAccessibilityService.sendScreenCapturePermissionResult(
                                granted = false,
                                error = "MediaProjection initialization failed"
                            )
                            android.widget.Toast.makeText(
                                this,
                                "Failed to initialize screen capture",
                                android.widget.Toast.LENGTH_LONG,
                            ).show()
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "❌ Failed to initialize media projection", e)
                        AuraAccessibilityService.updateScreenCaptureStatus(false)
                        
                        // Notify backend of failure
                        AuraAccessibilityService.sendScreenCapturePermissionResult(
                            granted = false, 
                            error = "Initialization failed: ${e.message}"
                        )
                        
                        android.widget.Toast.makeText(
                            this,
                            "Failed to enable screen capture: ${e.message}",
                            android.widget.Toast.LENGTH_LONG,
                        ).show()
                    }
                } else {
                    Log.e(TAG, "❌ Screen capture permission granted but Accessibility Service is not running")
                    
                    // Notify backend of failure
                    AuraAccessibilityService.sendScreenCapturePermissionResult(
                        granted = false, 
                        error = "Accessibility Service not running"
                    )
                    
                    android.widget.Toast.makeText(
                        this,
                        "⚠️ Please enable Accessibility Service first, then restart the app",
                        android.widget.Toast.LENGTH_LONG,
                    ).show()
                }
            } else {
                Log.w(TAG, "⚠️ Screen capture permission denied - UI-only mode will be used")
                
                // Notify backend that permission was denied
                AuraAccessibilityService.sendScreenCapturePermissionResult(
                    granted = false, 
                    error = "User denied permission"
                )
                
                android.widget.Toast.makeText(
                    this,
                    "Screen capture disabled. AURA will use UI-only mode (no screenshots).",
                    android.widget.Toast.LENGTH_LONG,
                ).show()
            }
            
            // If this was a background request from overlay, move to back instead of finishing.
            // finish() destroys the Activity which invalidates the MediaProjection token on
            // Android 14+ — causing the permission to appear "not retained" immediately after
            // the user taps Allow. moveTaskToBack keeps the token alive in the background.
            if (pendingScreenCaptureRequest) {
                pendingScreenCaptureRequest = false
                moveTaskToBack(true)
            }
        }

    private val overlayPermissionLauncher =
        registerForActivityResult(
            ActivityResultContracts.StartActivityForResult(),
        ) {
            Log.d(TAG, "Overlay permission result")
            // Check if permission was granted and notify user
            if (Settings.canDrawOverlays(this)) {
                Log.i(TAG, "✅ Overlay permission granted")
                android.widget.Toast.makeText(
                    this,
                    "✅ Overlay permission granted! You can now use the floating assistant.",
                    android.widget.Toast.LENGTH_LONG,
                ).show()
            } else {
                Log.w(TAG, "❌ Overlay permission denied")
                android.widget.Toast.makeText(
                    this,
                    "❌ Overlay permission is required for floating assistant",
                    android.widget.Toast.LENGTH_LONG,
                ).show()
            }
        }

    // Add job tracking for refresh operations
    private var refreshJob: Job? = null
    
    // Track if we're showing settings (to prevent auto-overlay launch)
    private var showingSettings = false
    
    // Track if we need to show overlay after unlock
    private var pendingOverlayAfterUnlock = false
    private var pendingAutoStartListening = false
    
    // Track if we're only here to request screen capture (finish after result)
    private var pendingScreenCaptureRequest = false
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        Log.d(TAG, "onCreate: Starting AURA UI")
        
        // Initialize ThemeManager with saved preferences
        ThemeManager.initialize(this)
        
        // Initialize onboarding preferences
        OnboardingPreferences.init(this)

        // Check and initialize accessibility service
        checkAccessibilityService()
        
        // Start visual feedback overlay service
        startVisualFeedbackService()
        
        // Handle wake word unlock request - this activity shows on lock screen
        val unlockAndShowOverlay = intent?.getBooleanExtra("UNLOCK_AND_SHOW_OVERLAY", false) ?: false
        val autoStartListening = intent?.getBooleanExtra("AUTO_START_LISTENING", false) ?: false
        
        if (unlockAndShowOverlay) {
            Log.i(TAG, "🔓 Wake word triggered - showing on lock screen for unlock")
            handleWakeWordUnlockRequest(autoStartListening)
            return
        }
        
        // Handle screen capture permission request from overlay/backend
        val requestScreenCapture = intent?.getBooleanExtra(EXTRA_REQUEST_SCREEN_CAPTURE, false) ?: false
        if (requestScreenCapture) {
            Log.i(TAG, "📸 Screen capture permission request from overlay")
            val requestSource = intent?.getStringExtra(EXTRA_REQUEST_SOURCE)
            val finishAfterPermission =
                intent?.getBooleanExtra(EXTRA_FINISH_AFTER_PERMISSION, requestSource != REQUEST_SOURCE_SETTINGS)
                    ?: (requestSource != REQUEST_SOURCE_SETTINGS)
            pendingScreenCaptureRequest = finishAfterPermission
            // Request screen capture - the result callback will finish the activity
            if (checkAccessibilityService()) {
                requestScreenCapturePermission()
            } else {
                Log.w(TAG, "⚠️ Accessibility service not enabled, cannot request screen capture")
                android.widget.Toast.makeText(
                    this,
                    "Please enable Accessibility Service first",
                    android.widget.Toast.LENGTH_LONG
                ).show()
                finish()
            }
            return
        }

        // Check if we should navigate to settings (from overlay settings button)
        val navigateToSettings = intent?.getBooleanExtra("NAVIGATE_TO_SETTINGS", false) ?: false
        
        if (navigateToSettings) {
            Log.d(TAG, "Opening settings screen from overlay")
            showingSettings = true
            showSettingsUI()
            return
        }

        // Request basic permissions (microphone, overlay) if not granted
        if (!checkPermissions()) {
            Log.d(TAG, "Basic permissions not granted - requesting")
            requestPermissions()
            // Show minimal UI for permission setup
            showPermissionSetupUI()
            return
        }

        // All permissions granted - launch as overlay immediately
        launchAsOverlay()
    }
    
    /**
     * Handle wake word unlock request when device is locked.
     * Shows activity on lock screen and requests unlock.
     */
    private fun handleWakeWordUnlockRequest(autoStartListening: Boolean) {
        // Set flags to show activity on lock screen
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            )
        }
        
        pendingOverlayAfterUnlock = true
        pendingAutoStartListening = autoStartListening
        
        // Request keyguard dismiss
        val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            keyguardManager.requestDismissKeyguard(
                this,
                object : KeyguardManager.KeyguardDismissCallback() {
                    override fun onDismissSucceeded() {
                        Log.i(TAG, "🔓 Keyguard dismissed successfully")
                        lifecycleScope.launch {
                            delay(300) // Let unlock animation complete
                            showOverlayAfterUnlock()
                        }
                    }
                    
                    override fun onDismissCancelled() {
                        Log.i(TAG, "🔒 Unlock cancelled by user")
                        pendingOverlayAfterUnlock = false
                        pendingAutoStartListening = false
                        finish()
                    }
                    
                    override fun onDismissError() {
                        Log.e(TAG, "❌ Error dismissing keyguard")
                        pendingOverlayAfterUnlock = false
                        pendingAutoStartListening = false
                        finish()
                    }
                }
            )
        } else {
            // For older versions, the FLAG_DISMISS_KEYGUARD should trigger unlock
            // Show a minimal UI indicating unlock is needed
            showUnlockPromptUI()
        }
    }
    
    /**
     * Show overlay after device is unlocked via wake word.
     */
    private fun showOverlayAfterUnlock() {
        if (!pendingOverlayAfterUnlock) return
        
        pendingOverlayAfterUnlock = false
        val autoStart = pendingAutoStartListening
        pendingAutoStartListening = false
        
        Log.i(TAG, "🎤 Device unlocked, showing overlay (autoStart=$autoStart)")
        
        if (autoStart) {
            com.aura.aura_ui.overlay.AuraOverlayService.showAndListen(this)
        } else {
            com.aura.aura_ui.overlay.AuraOverlayService.show(this)
        }
        
        // Finish this activity
        finish()
    }
    
    /**
     * Show minimal UI prompting user to unlock (for older Android versions).
     */
    private fun showUnlockPromptUI() {
        setContent {
            AuraUITheme(darkTheme = true) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background.copy(alpha = 0.9f)
                ) {
                    Column(
                        modifier = Modifier.fillMaxSize().padding(32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "🔒 Unlock to use AURA",
                            style = MaterialTheme.typography.headlineMedium,
                            color = MaterialTheme.colorScheme.onBackground
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = "Wake word detected!\nPlease unlock your device to continue.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                            textAlign = TextAlign.Center
                        )
                    }
                }
            }
        }
        
        // Monitor unlock state
        lifecycleScope.launch {
            val keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
            while (keyguardManager.isKeyguardLocked) {
                delay(500)
            }
            // Device unlocked
            showOverlayAfterUnlock()
        }
    }

    /**
     * Launch AURA as a system overlay and minimize the activity.
     * This is the main UX flow - like Google Assistant.
     */
    private fun launchAsOverlay() {
        Log.i(TAG, "🚀 Launching AURA as overlay")
        
        // Start the overlay service
        com.aura.aura_ui.overlay.AuraOverlayService.show(this)

        // Only start wake word service if user has previously enabled it
        val prefs = getSharedPreferences("aura_settings", Context.MODE_PRIVATE)
        val wakeWordEnabled = prefs.getBoolean("wake_word_enabled", false)
        if (wakeWordEnabled) {
            WakeWordListeningService.start(this)
            Log.i(TAG, "🎤 Wake word service started (was enabled)")
        } else {
            Log.i(TAG, "🔇 Wake word service not started (not enabled by user)")
        }
        
        // Initialize backend connection
        initializeBackendConnection()
        
        // Move activity to background so overlay shows over previous app
        moveTaskToBack(true)
        
        // Finish this activity - overlay runs independently
        finish()
    }

    /**
     * Show minimal UI for permission setup when permissions are missing
     */
    private fun showPermissionSetupUI() {
        try {
            enableEdgeToEdge()
            WindowCompat.setDecorFitsSystemWindows(window, false)

            setContent {
                val themeMode by ThemeManager.themeMode.collectAsState()
                val systemDark = isSystemInDarkTheme()
                val useDarkTheme =
                    when (themeMode) {
                        ThemeMode.SYSTEM -> systemDark
                        ThemeMode.DARK -> true
                        ThemeMode.LIGHT -> false
                    }

                AuraUITheme(darkTheme = useDarkTheme) {
                    Surface(
                        modifier = Modifier.fillMaxSize(),
                        color = MaterialTheme.colorScheme.background,
                    ) {
                        PermissionSetupScreen(
                            onPermissionsGranted = {
                                launchAsOverlay()
                            }
                        )
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error showing permission setup UI", e)
        }
    }

    @Composable
    private fun PermissionSetupScreen(onPermissionsGranted: () -> Unit) {
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "AURA Setup",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.onBackground
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Grant permissions to use AURA as your voice assistant",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(32.dp))
            Button(
                onClick = {
                    requestPermissions()
                }
            ) {
                Text("Grant Permissions")
            }
        }
        
        // Check permissions periodically
        LaunchedEffect(Unit) {
            while (true) {
                delay(1000)
                if (checkPermissions()) {
                    onPermissionsGranted()
                    break
                }
            }
        }
    }

    /**
     * Show full settings UI when user taps settings from overlay
     */
    private fun showSettingsUI() {
        try {
            // Temporarily hide overlay while showing settings (no "executing" notification)
            com.aura.aura_ui.overlay.AuraOverlayService.temporarilyHide(this)
            
            enableEdgeToEdge()
            WindowCompat.setDecorFitsSystemWindows(window, false)

            setContent {
                val themeMode by ThemeManager.themeMode.collectAsState()
                val systemDark = isSystemInDarkTheme()
                val useDarkTheme =
                    when (themeMode) {
                        ThemeMode.SYSTEM -> systemDark
                        ThemeMode.DARK -> true
                        ThemeMode.LIGHT -> false
                    }

                AuraUITheme(darkTheme = useDarkTheme) {
                    Surface(
                        modifier = Modifier.fillMaxSize(),
                        color = MaterialTheme.colorScheme.background,
                    ) {
                        SettingsNavigation()
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error showing settings UI", e)
        }
    }

    /**
     * Settings navigation with back to overlay support
     */
    @Composable
    private fun SettingsNavigation() {
        var currentSettingsScreen by remember { mutableStateOf(SettingsScreen.Main) }
        
        when (currentSettingsScreen) {
            SettingsScreen.Main -> {
                AuraSettingsScreen(
                    onNavigateBack = {
                        // Restore and return to overlay
                        showingSettings = false
                        com.aura.aura_ui.overlay.AuraOverlayService.restore(this@MainActivity)
                        launchAsOverlay()
                    },
                    onNavigateToServerConfig = {
                        currentSettingsScreen = SettingsScreen.ServerConfig
                    },
                    onNavigateToVoiceSettings = {
                        currentSettingsScreen = SettingsScreen.VoiceSettings
                    },
                    onNavigateToModelDownload = {
                        currentSettingsScreen = SettingsScreen.ModelDownload
                    },
                    onRequestScreenCapture = {
                        pendingScreenCaptureRequest = false
                        requestScreenCapturePermission()
                    },
                )
            }
            SettingsScreen.ServerConfig -> {
                ServerConfigurationScreen(
                    onNavigateBack = {
                        currentSettingsScreen = SettingsScreen.Main
                    },
                )
            }
            SettingsScreen.VoiceSettings -> {
                VoiceSettingsScreen(
                    onNavigateBack = {
                        currentSettingsScreen = SettingsScreen.Main
                    },
                )
            }
            SettingsScreen.ModelDownload -> {
                ModelDownloadScreen(
                    functionGemmaManager = functionGemmaManager,
                    onNavigateBack = {
                        currentSettingsScreen = SettingsScreen.Main
                    },
                )
            }
        }
    }
    
    private enum class SettingsScreen {
        Main,
        ServerConfig,
        VoiceSettings,
        ModelDownload
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent) // Store the new intent
        
        // Handle wake word unlock request
        if (intent.getBooleanExtra("UNLOCK_AND_SHOW_OVERLAY", false)) {
            Log.d(TAG, "Wake word unlock request via onNewIntent")
            val autoStartListening = intent.getBooleanExtra("AUTO_START_LISTENING", false)
            handleWakeWordUnlockRequest(autoStartListening)
            return
        }
        
        // Handle manual screen capture request from Settings
        if (intent.getBooleanExtra(EXTRA_REQUEST_SCREEN_CAPTURE, false)) {
            val requestSource = intent.getStringExtra(EXTRA_REQUEST_SOURCE)
            val finishAfterPermission =
                intent.getBooleanExtra(EXTRA_FINISH_AFTER_PERMISSION, requestSource != REQUEST_SOURCE_SETTINGS)
            Log.d(TAG, "Screen capture request via onNewIntent. source=$requestSource finishAfter=$finishAfterPermission")
            pendingScreenCaptureRequest = finishAfterPermission
            requestScreenCapturePermission()
        }
        // Handle navigate to settings
        if (intent.getBooleanExtra("NAVIGATE_TO_SETTINGS", false)) {
            Log.d(TAG, "Navigate to settings requested via onNewIntent")
            showingSettings = true
            showSettingsUI()
        }
    }

    override fun onResume() {
        super.onResume()
        // Don't auto-launch overlay if we're showing settings
        if (showingSettings) {
            return
        }
        // If permissions are now granted and we're visible, launch overlay
        if (checkPermissions() && !isFinishing) {
            launchAsOverlay()
        }
    }

    private fun isScreenCaptureGranted(): Boolean {
        return AuraAccessibilityService.instance?.isMediaProjectionAvailable() ?: false
    }

    /**
     * Request screen capture permission for VLM-based screen analysis.
     * Falls back to UI-only mode if permission is denied.
     */
    private fun requestScreenCapturePermission() {
        try {
            Log.d(TAG, "🔍 Screen capture request initiated")

            // Check if accessibility service is running first
            val isAccessibilityEnabled = checkAccessibilityService()
            Log.d(TAG, "Accessibility service status: $isAccessibilityEnabled")

            if (!isAccessibilityEnabled) {
                Log.w(TAG, "⚠️ Accessibility service not enabled - cannot request screen capture")
                android.widget.Toast.makeText(
                    this,
                    "⚠️ Please enable Accessibility Service first:\nSettings → Accessibility → AURA",
                    android.widget.Toast.LENGTH_LONG,
                ).show()

                // Open accessibility settings to help user
                try {
                    val intent =
                        Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                    startActivity(intent)
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to open accessibility settings", e)
                }
                return
            }

            // Check if already granted
            if (isScreenCaptureGranted()) {
                Log.d(TAG, "✅ Screen capture already granted")
                android.widget.Toast.makeText(
                    this,
                    "✅ Screen capture is already enabled",
                    android.widget.Toast.LENGTH_SHORT,
                ).show()
                if (pendingScreenCaptureRequest) {
                    pendingScreenCaptureRequest = false
                    finish()
                }
                return
            }

            val mediaProjectionManager =
                getSystemService(
                    Context.MEDIA_PROJECTION_SERVICE,
                ) as android.media.projection.MediaProjectionManager
            val captureIntent = mediaProjectionManager.createScreenCaptureIntent()

            Log.d(TAG, "📸 Launching screen capture permission dialog...")
            screenCaptureLauncher.launch(captureIntent)
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to request screen capture permission", e)
            android.widget.Toast.makeText(
                this,
                "Failed to request screen capture: ${e.message}",
                android.widget.Toast.LENGTH_LONG,
            ).show()
        }
    }

    /**
     * Check if AURA accessibility service is enabled
     */
    private fun checkAccessibilityService(): Boolean {
        val accessibilityManager = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val enabledServices = accessibilityManager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)

        Log.d(TAG, "Checking accessibility service status...")
        Log.d(TAG, "Package name: $packageName")
        Log.d(TAG, "Enabled services count: ${enabledServices.size}")

        for (service in enabledServices) {
            val serviceName = service.resolveInfo.serviceInfo.name
            val servicePackage = service.resolveInfo.serviceInfo.packageName
            Log.d(TAG, "Found service: $servicePackage/$serviceName")

            // Check for both possible service paths
            if (servicePackage == packageName &&
                (
                    serviceName == "com.aura.aura_ui.accessibility.AuraAccessibilityService" ||
                        serviceName.endsWith("AuraAccessibilityService")
                )
            ) {
                Log.i(TAG, "✅ AURA Accessibility Service is enabled")
                return true
            }
        }

        Log.w(TAG, "⚠️ AURA Accessibility Service is not enabled")
        return false
    }

    /**
     * Start visual feedback overlay service
     */
    private fun startVisualFeedbackService() {
        if (com.aura.aura_ui.overlay.VisualFeedbackOverlayService.canDrawOverlays(this)) {
            startService(Intent(this, com.aura.aura_ui.overlay.VisualFeedbackOverlayService::class.java))
            Log.i(TAG, "✨ Visual feedback overlay service started")
        } else {
            Log.w(TAG, "⚠️ Overlay permission not granted, visual feedback disabled")
        }
    }

    /**
     * Prompt user to enable accessibility service
     */
    private fun promptEnableAccessibilityService() {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
        startActivity(intent)
    }

    /**
     * Initialize backend connection with device information
     */
    private fun initializeBackendConnection() {
        lifecycleScope.launch {
            try {
                val serverUrl = getCurrentServerUrl()
                val deviceInfo = getDeviceInfo()

                // Connect to backend accessibility API
                val success = connectToBackendAccessibilityService(serverUrl, deviceInfo)
                if (success) {
                    Log.i(TAG, "✅ Backend accessibility service connected")

                    // Start periodic UI data sharing if accessibility service is enabled
                    if (checkAccessibilityService()) {
                        // DISABLED: Use Commander-based on-demand UI capture instead
                        // startUIDataSharing()
                        Log.i(TAG, "✅ Using Commander-based on-demand UI capture")
                    }
                } else {
                    Log.w(TAG, "❌ Failed to connect to backend accessibility service")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error initializing backend connection", e)
            }
        }
    }

    /**
     * Get device information for backend registration
     */
    private fun getDeviceInfo(): JSONObject {
        val displayMetrics = resources.displayMetrics

        return JSONObject().apply {
            put("screen_width", displayMetrics.widthPixels)
            put("screen_height", displayMetrics.heightPixels)
            put("density_dpi", displayMetrics.densityDpi)
            put("device_name", "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
            put("android_version", android.os.Build.VERSION.RELEASE)
        }
    }

    /**
     * Connect to backend accessibility service
     */
    private suspend fun connectToBackendAccessibilityService(
        serverUrl: String,
        deviceInfo: JSONObject,
    ): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val requestBody = deviceInfo.toString().toRequestBody("application/json".toMediaType())
                val request =
                    Request.Builder()
                        .url("$serverUrl/accessibility/connect")
                        .post(requestBody)
                        .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.i(TAG, "Device registered with backend accessibility service")
                        true
                    } else {
                        Log.e(TAG, "Failed to register device: ${response.code}")
                        false
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error connecting to backend accessibility service", e)
                false
            }
        }
    }

    /**
     * Note: Replaced by new Perception Controller (see UI Perception Blueprint)
     * Legacy automatic UI data sharing removed - Android must not push UI data
     * autonomously. UI data must be requested explicitly by backend via Perception Controller.
     * MediaProjection setup is preserved for on-demand capture when requested.
     */
    private fun startUIDataSharing() {
        // Automatic UI data sharing disabled - backend must request explicitly
        Log.i(TAG, "⚠️ Automatic UI data sharing disabled - backend must request explicitly")
        // MediaProjection setup is preserved for on-demand capture when requested
    }

    /**
     * Share UI data with backend using the smart hybrid approach
     */
    private suspend fun shareUIDataWithBackend(uiData: Map<String, Any>): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val serverUrl = getCurrentServerUrl()

                // Convert UI data to backend API format
                val requestData =
                    JSONObject().apply {
                        put("screenshot", uiData["screenshot"] as? String ?: "")
                        put("screen_width", uiData["screen_width"] as? Int ?: 1080)
                        put("screen_height", uiData["screen_height"] as? Int ?: 1920)
                        put("timestamp", uiData["timestamp"] as? Long ?: System.currentTimeMillis())
                        put("capture_reason", uiData["capture_reason"] as? String ?: "unknown")
                        put("has_screenshot", uiData["has_screenshot"] as? Boolean ?: false)
                        put("ui_hash", uiData["ui_hash"] as? String ?: "")

                        // Convert UI elements to JSON array
                        val uiElements = uiData["ui_elements"] as? Map<*, *>
                        if (uiElements != null) {
                            put("ui_elements", convertUIElementsToJSON(uiElements))
                        } else {
                            put("ui_elements", JSONArray())
                        }
                    }

                val requestBody = requestData.toString().toRequestBody("application/json".toMediaType())
                val request =
                    Request.Builder()
                        .url("$serverUrl/accessibility/ui-data")
                        .post(requestBody)
                        .addHeader("Content-Type", "application/json")
                        .addHeader("X-Aura-Client", "Android")
                        .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val hasScreenshot = uiData["has_screenshot"] as? Boolean ?: false
                        Log.d(TAG, "✅ UI data sent successfully - Screenshot: $hasScreenshot")
                        true
                    } else {
                        Log.e(TAG, "❌ Failed to send UI data: ${response.code} - ${response.message}")
                        false
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error sharing UI data with backend", e)
                false
            }
        }
    }

    /**
     * Convert UI elements map to JSON format for backend
     * CRITICAL ANR FIX: Added depth and element count limits
     */
    private fun convertUIElementsToJSON(
        uiElements: Map<*, *>,
        currentDepth: Int = 0,
        maxDepth: Int = 10, // Prevent deep recursion
        processedCount: AtomicInteger = AtomicInteger(0),
        maxElements: Int = 100, // Limit total elements
    ): JSONArray {
        return try {
            val jsonArray = JSONArray()

            fun processElement(
                element: Map<*, *>,
                depth: Int,
            ) {
                // CRITICAL: Stop if we've processed too many or gone too deep
                if (depth > maxDepth || processedCount.get() >= maxElements) {
                    return
                }

                val elementJson =
                    JSONObject().apply {
                        put("className", element["className"] ?: "")
                        put("text", element["text"] ?: "")
                        put("contentDescription", element["contentDescription"] ?: "")
                        put("viewIdResourceName", element["viewIdResourceName"] ?: "")
                        put("packageName", element["packageName"] ?: "")
                        put("clickable", element["clickable"] ?: false)
                        put("enabled", element["enabled"] ?: false)
                        put("focusable", element["focusable"] ?: false)
                        put("scrollable", element["scrollable"] ?: false)
                        put("selected", element["selected"] ?: false)
                        put("checkable", element["checkable"] ?: false)
                        put("checked", element["checked"] ?: false)

                        // Handle bounds
                        val bounds = element["bounds"] as? Map<*, *>
                        if (bounds != null) {
                            put(
                                "bounds",
                                JSONObject().apply {
                                    put("left", bounds["left"] ?: 0)
                                    put("top", bounds["top"] ?: 0)
                                    put("right", bounds["right"] ?: 0)
                                    put("bottom", bounds["bottom"] ?: 0)
                                },
                            )
                        }
                    }

                jsonArray.put(elementJson)
                processedCount.incrementAndGet()

                // CRITICAL: Check limit before processing children
                if (processedCount.get() >= maxElements || depth >= maxDepth) {
                    return
                }

                // Process children recursively with depth tracking
                val children = element["children"] as? List<*>
                children?.forEach { child ->
                    if (processedCount.get() < maxElements && child is Map<*, *>) {
                        processElement(child, depth + 1)
                    }
                }
            }

            processElement(uiElements, currentDepth)
            jsonArray
        } catch (e: Exception) {
            Log.e(TAG, "Error converting UI elements to JSON", e)
            JSONArray()
        }
    }

    // Improved server health check with better error handling and user feedback
    private suspend fun checkServerHealth(): String {
        return withContext(Dispatchers.IO) {
            var lastError = ""

            // Get current server URL based on user settings
            val serverUrl = getCurrentServerUrl()
            Log.d(TAG, "Checking server health at: $serverUrl")

            try {
                val request =
                    Request.Builder()
                        .url("$serverUrl/health")
                        .addHeader("Accept", "application/json")
                        .addHeader("User-Agent", "AURA-Android-Client/1.0")
                        .addHeader("Content-Type", "application/json")
                        .build()

                httpClient.newCall(request).execute().use { response ->
                    when {
                        response.isSuccessful -> {
                            val responseBody = response.body?.string() ?: ""
                            Log.i(TAG, "✅ Server health check successful: $responseBody")
                            "✅ Connected to server at $serverUrl"
                        }
                        else -> {
                            lastError = "❌ Server error: ${response.code} ${response.message}"
                            Log.w(TAG, lastError)
                            lastError
                        }
                    }
                }
            } catch (e: Exception) {
                lastError = "❌ Connection failed: ${e.message}"
                Log.e(TAG, "Server health check failed", e)
                lastError
            }
        }
    }

    private suspend fun sendTestCommand(): String {
        return try {
            val serverUrl = getCurrentServerUrl()
            Log.d(TAG, "Sending test command to: $serverUrl")

            val jsonBody =
                JSONObject().apply {
                    put("text_input", "Hello AURA, test connection from Android")
                    put("input_type", "text")
                    put("timestamp", System.currentTimeMillis())
                }

            val requestBody =
                jsonBody.toString()
                    .toRequestBody("application/json".toMediaType())

            val request =
                Request.Builder()
                    .url("$serverUrl/tasks/execute")
                    .post(requestBody)
                    .addHeader("Accept", "application/json")
                    .addHeader("User-Agent", "AURA-Android-Client/1.0")
                    .build()

            withContext(Dispatchers.IO) {
                httpClient.newCall(request).execute().use { response ->
                    val responseBody = response.body?.string() ?: "No response body"
                    Log.d(TAG, "Server response: $responseBody")

                    if (response.isSuccessful) {
                        try {
                            val jsonResponse = JSONObject(responseBody)
                            val spokenResponse = jsonResponse.optString("spoken_response", "✅ Connection successful!")
                            val spokenAudio = jsonResponse.optString("spoken_audio", "")
                            val spokenAudioFormat = jsonResponse.optString("spoken_audio_format", "")

                            // Play audio if available
                            if (spokenAudio.isNotEmpty()) {
                                Log.d(TAG, "🔊 Test command audio response received (format: $spokenAudioFormat)")
                                lifecycleScope.launch {
                                    WavAudioPlayer.playBase64Audio(spokenAudio) {}
                                }
                            }

                            spokenResponse
                        } catch (e: Exception) {
                            "✅ Server responded: $responseBody"
                        }
                    } else {
                        "❌ Error ${response.code}: $responseBody"
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Test command failed", e)
            "❌ ${e.message}"
        }
    }

    @Composable
    private fun AuraApp() {
        // Check if onboarding has been completed
        val hasCompletedOnboarding = remember { OnboardingPreferences.isOnboardingCompleted() }
        
        var currentScreen by remember { 
            mutableStateOf(
                if (hasCompletedOnboarding) AppScreen.Main else AppScreen.Welcome
            ) 
        }
        
        when (currentScreen) {
            AppScreen.Welcome -> {
                AuraWelcomeScreen(
                    onWelcomeComplete = {
                        Log.d(TAG, "Welcome screen completed - marking onboarding as done")
                        OnboardingPreferences.completeOnboarding()
                        currentScreen = AppScreen.Main
                    },
                )
            }
            AppScreen.Main -> {
                AuraVoiceAssistantWrapper(
                    onNavigateToSettings = {
                        Log.d(TAG, "Navigating to settings")
                        currentScreen = AppScreen.Settings
                    },
                )
            }
            AppScreen.Settings -> {
                AuraSettingsScreen(
                    onNavigateBack = {
                        Log.d(TAG, "Returning to main screen from settings")
                        currentScreen = AppScreen.Main
                    },
                    onNavigateToServerConfig = {
                        Log.d(TAG, "Navigating to server configuration")
                        currentScreen = AppScreen.ServerConfig
                    },
                    onNavigateToVoiceSettings = {
                        Log.d(TAG, "Navigating to voice settings")
                        currentScreen = AppScreen.VoiceSettings
                    },
                    onRequestScreenCapture = {
                        pendingScreenCaptureRequest = false
                        requestScreenCapturePermission()
                    },
                )
            }

            AppScreen.ServerConfig -> {
                ServerConfigurationScreen(
                    onNavigateBack = {
                        Log.d(TAG, "Returning to settings from server config")
                        currentScreen = AppScreen.Settings
                    },
                )
            }
            
            AppScreen.VoiceSettings -> {
                VoiceSettingsScreen(
                    onNavigateBack = {
                        Log.d(TAG, "Returning to settings from voice settings")
                        currentScreen = AppScreen.Settings
                    },
                )
            }
        }
    }

    private enum class AppScreen {
        Welcome,
        Main,
        Settings,
        ServerConfig,
        VoiceSettings,
    }
    
    /**
     * New Voice Assistant Overlay Wrapper
     * Replaces the old HomeScreen with Google Assistant-style overlay UI
     */
    @OptIn(ExperimentalLayoutApi::class)
    @Composable
    private fun AuraVoiceAssistantWrapper(onNavigateToSettings: () -> Unit) {
        val conversationViewModel: ConversationViewModel = viewModel()
        val conversationState by conversationViewModel.state.collectAsState()
        val conversationMessages by conversationViewModel.messages.collectAsState()

        var hasAllPermissions by remember { mutableStateOf(false) }
        var isListening by remember { mutableStateOf(false) }
        var partialTranscript by remember { mutableStateOf("") }
        var audioAmplitude by remember { mutableFloatStateOf(0f) }

        // Check permissions and initialize on launch
        LaunchedEffect(Unit) {
            hasAllPermissions = checkPermissions()
            
            // Do initial HTTP health check to update connection state
            val healthResult = checkServerHealth()
            val initialConnected = healthResult.contains("✓") || healthResult.contains("Connected")
            conversationViewModel.updateServerConnection(initialConnected)
            
            // Initialize conversation mode by default
            val serverUrl = getCurrentServerUrl()
            voiceCaptureController = VoiceCaptureController(
                context = this@MainActivity,
                serverUrl = serverUrl,
                viewModel = conversationViewModel,
                scope = lifecycleScope,
                onAmplitudeUpdate = { amplitude ->
                    audioAmplitude = amplitude
                },
                functionGemmaManager = functionGemmaManager
            )
            // WebSocket connect will update connection state via ViewModel
            voiceCaptureController?.connect()
        }
        
        // Periodic server health check every 30 seconds (fallback if WebSocket disconnects)
        LaunchedEffect(Unit) {
            while (true) {
                kotlinx.coroutines.delay(30_000) // 30 seconds
                // Only do HTTP health check if WebSocket reports disconnected
                if (!conversationState.isServerConnected) {
                    val healthResult = checkServerHealth()
                    val isConnected = healthResult.contains("✓") || healthResult.contains("Connected")
                    if (isConnected) {
                        // Server is reachable, try to reconnect WebSocket
                        voiceCaptureController?.connect()
                    }
                    Log.d(TAG, "Periodic health check (was disconnected): connected=$isConnected")
                }
            }
        }
        
        // Update listening state based on conversation phase
        LaunchedEffect(conversationState.conversationState) {
            isListening = conversationState.conversationState == ConversationPhase.LISTENING
            partialTranscript = conversationState.partialTranscript
        }

        // Create overlay state - use ViewModel's connection state for seamless updates
        val overlayState = VoiceAssistantState(
            isVisible = true, // Always visible as main screen
            isListening = isListening,
            isProcessing = conversationState.conversationState == ConversationPhase.THINKING,
            isResponding = conversationState.conversationState == ConversationPhase.RESPONDING,
            partialTranscript = conversationState.partialTranscript,
            messages = conversationMessages,
            serverConnected = conversationState.isServerConnected,
            audioAmplitude = audioAmplitude,
            processingContext = conversationState.processingContext,
            suggestedCommands = conversationState.suggestedCommands,
            recentCommands = conversationState.recentCommands,
        )

        // Create callbacks
        val overlayCallbacks = VoiceAssistantCallbacks(
            onDismiss = {
                // Cancel/stop any ongoing operation
                when (conversationState.conversationState) {
                    ConversationPhase.LISTENING -> {
                        // Stop recording without sending
                        voiceCaptureController?.cancelCapture()
                        conversationViewModel.resetToIdle()
                    }
                    ConversationPhase.THINKING, ConversationPhase.RESPONDING -> {
                        // Cancel processing and reset to idle
                        conversationViewModel.resetToIdle()
                    }
                    else -> {
                        // Already idle - do nothing
                    }
                }
            },
            onMicClick = {
                when (conversationState.conversationState) {
                    ConversationPhase.IDLE -> {
                        voiceCaptureController?.startCapture()
                    }
                    ConversationPhase.LISTENING -> {
                        voiceCaptureController?.stopCapture()
                    }
                    else -> {
                        // Do nothing if thinking/responding
                    }
                }
            },
            onSettingsClick = onNavigateToSettings,
            onTextSubmit = { text ->
                // Handle text input - send as message via WebSocket
                conversationViewModel.addRecentCommand(text)
                voiceCaptureController?.sendTextCommand(text)
            },
            onMessageCopy = { text ->
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val clip = ClipData.newPlainText("AURA Message", text)
                clipboard.setPrimaryClip(clip)
                Toast.makeText(this, "Copied to clipboard", Toast.LENGTH_SHORT).show()
            },
            onMessageRetry = { message ->
                // Retry the user's message
                voiceCaptureController?.sendTextCommand(message.text)
            },
            onMessageShare = { text ->
                val shareIntent = Intent().apply {
                    action = Intent.ACTION_SEND
                    putExtra(Intent.EXTRA_TEXT, text)
                    type = "text/plain"
                }
                startActivity(Intent.createChooser(shareIntent, "Share message via"))
            },
            onMessageDelete = { messageId ->
                conversationViewModel.deleteMessage(messageId)
            },
            onSuggestionClick = { suggestion ->
                conversationViewModel.addRecentCommand(suggestion)
                voiceCaptureController?.sendTextCommand(suggestion)
            },
            onClearChat = {
                conversationViewModel.clearAllMessages()
            },
        )

        // Display the Voice Assistant Overlay
        VoiceAssistantOverlay(
            state = overlayState,
            callbacks = overlayCallbacks,
        )
    }

    // Keep the old wrapper for backward compatibility (can be removed later)
    @OptIn(ExperimentalLayoutApi::class)
    @Composable
    private fun AuraMainScreenWrapper(onNavigateToSettings: () -> Unit) {
        val conversationViewModel: ConversationViewModel = viewModel()
        val conversationState by conversationViewModel.state.collectAsState()
        val conversationMessages by conversationViewModel.messages.collectAsState()

        var hasAllPermissions by remember { mutableStateOf(false) }
        var isListening by remember { mutableStateOf(false) }
        var serverStatus by remember { mutableStateOf("Unknown") }
        var lastResponse by remember { mutableStateOf("No response yet") }
        var isProcessingAudio by remember { mutableStateOf(false) }
        var partialTranscript by remember { mutableStateOf("") }
        var finalTranscript by remember { mutableStateOf("") }
        var isRefreshing by remember { mutableStateOf(false) }
        var isConversationMode by remember { mutableStateOf(false) }
        var audioAmplitude by remember { mutableFloatStateOf(0f) }

        LaunchedEffect(Unit) {
            hasAllPermissions = checkPermissions()
            if (!isRefreshing) {
                isRefreshing = true
                serverStatus = checkServerHealth()
                isRefreshing = false
            }
        }

        val state =
            HomeScreenState(
                hasAllPermissions = hasAllPermissions,
                isListening = isListening,
                serverStatus = serverStatus,
                lastResponse = lastResponse,
                isProcessingAudio = isProcessingAudio,
                partialTranscript = if (isConversationMode) conversationState.partialTranscript else partialTranscript,
                finalTranscript = finalTranscript,
                currentServerUrl = currentServerUrl,
                isRefreshing = isRefreshing,
                conversationPhase = conversationState.conversationState,
                conversationMessages = conversationMessages,
                isConversationMode = isConversationMode,
            )

        val callbacks =
            HomeScreenCallbacks(
                onNavigateToSettings = onNavigateToSettings,
                onRequestPermissions = { requestPermissions() },
                onCheckServerHealth = {
                    lifecycleScope.launch {
                        serverStatus = checkServerHealth()
                    }
                },
                onSendTestCommand = {
                    lifecycleScope.launch {
                        lastResponse = sendTestCommand()
                    }
                },
                onToggleListening = {
                    if (isConversationMode) {
                        // Conversation mode: use VoiceCaptureController
                        when (conversationState.conversationState) {
                            ConversationPhase.IDLE -> {
                                voiceCaptureController?.startCapture()
                            }
                            ConversationPhase.LISTENING -> {
                                voiceCaptureController?.stopCapture()
                            }
                            else -> {
                                // Do nothing if thinking/responding
                            }
                        }
                    } else {
                        // Regular automation mode
                        isListening = !isListening
                        if (isListening) {
                            isProcessingAudio = false
                            startListening()
                        } else {
                            isProcessingAudio = true
                            lastResponse = "Processing audio..."
                            stopListening { response ->
                                lastResponse = response
                                isProcessingAudio = false
                            }
                        }
                    }
                },
                onRefreshConnection = {
                    if (!isRefreshing) {
                        refreshJob?.cancel()
                        refreshJob =
                            lifecycleScope.launch {
                                isRefreshing = true
                                delay(300)
                                try {
                                    serverStatus = checkServerHealth()
                                } finally {
                                    isRefreshing = false
                                }
                            }
                    }
                },
                onOpenNetworkSettings = {
                    val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
                    startActivity(intent)
                },
                onStartConversation = {
                    val intent = Intent(this, VoiceConversationActivity::class.java)
                    startActivity(intent)
                },
                onToggleConversationMode = {
                    isConversationMode = !isConversationMode
                    if (isConversationMode) {
                        lifecycleScope.launch {
                            val serverUrl = getCurrentServerUrl()
                            voiceCaptureController =
                                VoiceCaptureController(
                                    context = this@MainActivity,
                                    serverUrl = serverUrl,
                                    viewModel = conversationViewModel,
                                    scope = lifecycleScope,
                                    onAmplitudeUpdate = { amplitude ->
                                        audioAmplitude = amplitude
                                    },
                                    functionGemmaManager = functionGemmaManager
                                )
                            val connected = voiceCaptureController?.connect() ?: false
                            if (!connected) {
                                isConversationMode = false
                                lastResponse = "Failed to connect for conversation mode"
                            }
                        }
                    } else {
                        voiceCaptureController?.cleanup()
                        voiceCaptureController = null
                    }
                },
                onEndConversation = {
                    voiceCaptureController?.endConversation()
                    voiceCaptureController = null
                    isConversationMode = false
                },
                onStartOverlay = {
                    Log.d(TAG, "🔘 onStartOverlay button clicked")
                    val canDraw = Settings.canDrawOverlays(this@MainActivity)
                    Log.d(TAG, "Overlay permission status: $canDraw")

                    if (canDraw) {
                        Log.d(TAG, "✅ Permission granted, starting AURA overlay service...")
                        try {
                            // Use new AuraOverlayService for true system overlay
                            com.aura.aura_ui.overlay.AuraOverlayService.show(this@MainActivity)
                            Log.d(TAG, "✅ AURA overlay service start command sent")
                            android.widget.Toast.makeText(
                                this@MainActivity,
                                "✨ AURA Assistant started",
                                android.widget.Toast.LENGTH_SHORT,
                            ).show()
                            // Minimize activity to show overlay over other apps
                            moveTaskToBack(true)
                        } catch (e: Exception) {
                            Log.e(TAG, "❌ Failed to start AURA overlay service", e)
                            android.widget.Toast.makeText(
                                this@MainActivity,
                                "❌ Failed to start overlay: ${e.message}",
                                android.widget.Toast.LENGTH_LONG,
                            ).show()
                        }
                    } else {
                        Log.w(TAG, "❌ Overlay permission NOT granted, requesting...")
                        android.widget.Toast.makeText(
                            this@MainActivity,
                            "⚠️ Please grant overlay permission first",
                            android.widget.Toast.LENGTH_LONG,
                        ).show()
                        val intent =
                            Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION).apply {
                                data = Uri.parse("package:$packageName")
                            }
                        overlayPermissionLauncher.launch(intent)
                    }
                },
            )

        HomeScreen(state = state, callbacks = callbacks)
    }

    private fun checkPermissions(): Boolean {
        val audioPermission =
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
        val internetPermission =
            checkSelfPermission(Manifest.permission.INTERNET) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
        val overlayPermission = Settings.canDrawOverlays(this)

        Log.d(TAG, "Permissions - Audio: $audioPermission, Internet: $internetPermission, Overlay: $overlayPermission")

        return audioPermission && internetPermission && overlayPermission
    }

    private fun requestPermissions() {
        Log.d(TAG, "Requesting permissions")
        
        // Build list of permissions based on Android version
        val permissionsList = mutableListOf(Manifest.permission.RECORD_AUDIO)
        
        // Add POST_NOTIFICATIONS for Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissionsList.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        // Add POST_PROMOTED_NOTIFICATIONS for Android 16+ Live Update / Fluid Cloud
        if (Build.VERSION.SDK_INT >= 36) {
            permissionsList.add("android.permission.POST_PROMOTED_NOTIFICATIONS")
        }
        
        permissionLauncher.launch(permissionsList.toTypedArray())

        if (!Settings.canDrawOverlays(this)) {
            val intent =
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION).apply {
                    data = Uri.parse("package:$packageName")
                }
            overlayPermissionLauncher.launch(intent)
        }
    }

    private fun startListening() {
        Log.d(TAG, "Starting voice listening")
        try {
            val sampleRate = 44100
            val channelConfig = AudioFormat.CHANNEL_IN_MONO
            val audioFormat = AudioFormat.ENCODING_PCM_16BIT

            val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
            ) {
                audioRecord =
                    AudioRecord(
                        MediaRecorder.AudioSource.MIC,
                        sampleRate,
                        channelConfig,
                        audioFormat,
                        bufferSize,
                    )

                // Clear previous audio data
                audioData.clear()

                audioRecord?.startRecording()
                isRecording = true

                // Start audio data collection in background thread
                Thread {
                    val buffer = ByteArray(bufferSize)
                    while (isRecording && audioRecord?.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                        val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                        if (bytesRead > 0) {
                            audioData.add(buffer.copyOf(bytesRead))
                        }
                    }
                    Log.d(TAG, "Audio data collection finished. Collected ${audioData.size} chunks")
                }.start()

                Log.d(TAG, "Audio recording started successfully")
            } else {
                Log.w(TAG, "Audio permission not granted")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error starting audio recording", e)
        }
    }

    private fun stopListening(onResult: ((String) -> Unit)? = null) {
        Log.d(TAG, "Stopping voice listening")
        try {
            isRecording = false // Stop the recording loop first
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null

            Log.d(TAG, "Audio recording stopped successfully")

            // Process the collected audio data
            if (audioData.isNotEmpty()) {
                Log.d(TAG, "Processing collected audio data...")
                processAndSendAudio(onResult)
            } else {
                Log.w(TAG, "No audio data collected")
                onResult?.invoke("No audio data recorded")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping audio recording", e)
            onResult?.invoke("Error: ${e.message}")
        }
    }

    private fun processAndSendAudio(onResult: ((String) -> Unit)? = null) {
        lifecycleScope.launch {
            try {
                val totalSize = audioData.sumOf { it.size }
                val combinedAudio = ByteArray(totalSize)
                var offset = 0

                for (chunk in audioData) {
                    chunk.copyInto(combinedAudio, offset)
                    offset += chunk.size
                }

                Log.d(TAG, "Combined audio size: $totalSize bytes")

                val wavAudio = createWavFile(combinedAudio, 44100, 1, 16)
                Log.d(TAG, "WAV audio size: ${wavAudio.size} bytes")

                val base64Audio =
                    android.util.Base64.encodeToString(
                        wavAudio,
                        android.util.Base64.DEFAULT,
                    )

                sendAudioToServer(base64Audio, onResult)
            } catch (e: Exception) {
                Log.e(TAG, "Error processing audio data", e)
                onResult?.invoke("Error processing audio: ${e.message}")
            }
        }
    }

    private fun createWavFile(
        pcmData: ByteArray,
        sampleRate: Int,
        channels: Int,
        bitsPerSample: Int,
    ): ByteArray {
        val headerSize = 44
        val totalAudioLen = pcmData.size
        val totalDataLen = totalAudioLen + headerSize - 8
        val longSampleRate = sampleRate.toLong()
        val byteRate = (longSampleRate * channels * bitsPerSample / 8).toInt()
        val blockAlign = (channels * bitsPerSample / 8).toShort()

        val header = ByteArray(headerSize)

        // RIFF chunk descriptor
        header[0] = 'R'.code.toByte()
        header[1] = 'I'.code.toByte()
        header[2] = 'F'.code.toByte()
        header[3] = 'F'.code.toByte()
        header[4] = (totalDataLen and 0xff).toByte()
        header[5] = ((totalDataLen shr 8) and 0xff).toByte()
        header[6] = ((totalDataLen shr 16) and 0xff).toByte()
        header[7] = ((totalDataLen shr 24) and 0xff).toByte()
        header[8] = 'W'.code.toByte()
        header[9] = 'A'.code.toByte()
        header[10] = 'V'.code.toByte()
        header[11] = 'E'.code.toByte()

        // fmt subchunk
        header[12] = 'f'.code.toByte()
        header[13] = 'm'.code.toByte()
        header[14] = 't'.code.toByte()
        header[15] = ' '.code.toByte()
        header[16] = 16 // subchunk1Size for PCM
        header[17] = 0
        header[18] = 0
        header[19] = 0
        header[20] = 1 // PCM format
        header[21] = 0
        header[22] = channels.toByte()
        header[23] = 0
        header[24] = (longSampleRate and 0xff).toByte()
        header[25] = ((longSampleRate shr 8) and 0xff).toByte()
        header[26] = ((longSampleRate shr 16) and 0xff).toByte()
        header[27] = ((longSampleRate shr 24) and 0xff).toByte()
        header[28] = (byteRate and 0xff).toByte()
        header[29] = ((byteRate shr 8) and 0xff).toByte()
        header[30] = ((byteRate shr 16) and 0xff).toByte()
        header[31] = ((byteRate shr 24) and 0xff).toByte()
        header[32] = blockAlign.toByte()
        header[33] = (blockAlign.toInt() shr 8).toByte()
        header[34] = bitsPerSample.toByte()
        header[35] = 0

        // data subchunk
        header[36] = 'd'.code.toByte()
        header[37] = 'a'.code.toByte()
        header[38] = 't'.code.toByte()
        header[39] = 'a'.code.toByte()
        header[40] = (totalAudioLen and 0xff).toByte()
        header[41] = ((totalAudioLen shr 8) and 0xff).toByte()
        header[42] = ((totalAudioLen shr 16) and 0xff).toByte()
        header[43] = ((totalAudioLen shr 24) and 0xff).toByte()

        // Combine header and PCM data
        val wavFile = ByteArray(headerSize + totalAudioLen)
        System.arraycopy(header, 0, wavFile, 0, headerSize)
        System.arraycopy(pcmData, 0, wavFile, headerSize, totalAudioLen)

        return wavFile
    }

    private suspend fun sendAudioToServer(
        base64Audio: String,
        onResult: ((String) -> Unit)? = null,
    ) {
        return withContext(Dispatchers.IO) {
            try {
                val serverUrl = getCurrentServerUrl()
                Log.d(TAG, "Sending audio to server: $serverUrl")

                val jsonBody =
                    JSONObject().apply {
                        put("audio_data", base64Audio)
                        put("input_type", "audio")
                        put("timestamp", System.currentTimeMillis())
                    }

                val requestBody =
                    jsonBody.toString()
                        .toRequestBody("application/json".toMediaType())

                val request =
                    Request.Builder()
                        .url("$serverUrl/tasks/execute")
                        .post(requestBody)
                        .addHeader("Accept", "application/json")
                        .addHeader("User-Agent", "AURA-Android-Client/1.0")
                        .addHeader("Content-Type", "application/json")
                        .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val responseBody = response.body?.string() ?: ""
                        Log.d(TAG, "✅ Audio sent successfully: $responseBody")

                        withContext(Dispatchers.Main) {
                            try {
                                val jsonResponse = JSONObject(responseBody)
                                val result = jsonResponse.optString("result", responseBody)
                                val status = jsonResponse.optString("status", "completed")
                                val spokenResponse = jsonResponse.optString("spoken_response", "")
                                val spokenAudio = jsonResponse.optString("spoken_audio", "")
                                val spokenAudioFormat = jsonResponse.optString("spoken_audio_format", "")

                                // Play audio if available
                                if (spokenAudio.isNotEmpty()) {
                                    Log.d(TAG, "🔊 Audio response received (format: $spokenAudioFormat)")
                                    lifecycleScope.launch {
                                        WavAudioPlayer.playBase64Audio(spokenAudio) {}
                                    }
                                } else {
                                    Log.w(TAG, "⚠️ No audio in response")
                                }

                                // Display text feedback
                                val displayText =
                                    when {
                                        spokenResponse.isNotEmpty() -> "✅ $status: $spokenResponse"
                                        result.isNotEmpty() -> "✅ $status: $result"
                                        else -> "✅ Command processed successfully"
                                    }

                                onResult?.invoke(displayText)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error parsing response", e)
                                onResult?.invoke("✅ Response: $responseBody")
                            }
                        }
                    } else {
                        Log.e(TAG, "❌ Server error: ${response.code} - ${response.message}")
                        withContext(Dispatchers.Main) {
                            onResult?.invoke("❌ Server error: ${response.code}")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error sending audio to server", e)
                withContext(Dispatchers.Main) {
                    onResult?.invoke("❌ Connection error: ${e.message}")
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        refreshJob?.cancel()
        stopListening()
        Log.d(TAG, "onDestroy: Activity destroyed")
    }
}
