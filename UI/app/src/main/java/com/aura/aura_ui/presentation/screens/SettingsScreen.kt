package com.aura.aura_ui.presentation.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.*
import androidx.compose.material.ripple.LocalRippleTheme
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.presentation.utils.AuraHapticType
import com.aura.aura_ui.presentation.utils.rememberHapticFeedback
import com.aura.aura_ui.services.WakeWordListeningService
import com.aura.aura_ui.ui.theme.AppleColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Apple-Inspired Settings Screen
 * Clean, minimal, premium aesthetic following iOS Settings design
 */
@Composable
fun AuraSettingsScreen(
    onNavigateBack: () -> Unit,
    onNavigateToServerConfig: () -> Unit = {},
    onNavigateToVoiceSettings: () -> Unit = {},
    onNavigateToModelDownload: () -> Unit = {},
    onRequestScreenCapture: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val systemDark = isSystemInDarkTheme()
    val themeMode by ThemeManager.themeMode.collectAsState()
    val voiceSensitivity by ThemeManager.voiceActivationSensitivity.collectAsState()
    val wakeWordEnabled by ThemeManager.enableWakeWord.collectAsState()
    val haptics by ThemeManager.enableHapticFeedback.collectAsState()
    val notifications by ThemeManager.enableNotifications.collectAsState()
    val screenCapture by ThemeManager.enableScreenCapture.collectAsState()
    
    // Track actual MediaProjection availability using StateFlow (updates immediately on permission change)
    val isScreenCaptureAvailable by AuraAccessibilityService.screenCaptureAvailable.collectAsState()
    val lifecycleOwner = LocalLifecycleOwner.current
    
    // Also check on resume for cases where status changed externally
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                // Sync StateFlow with actual status on resume
                val actualStatus = AuraAccessibilityService.instance?.isMediaProjectionAvailable() ?: false
                AuraAccessibilityService.updateScreenCaptureStatus(actualStatus)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }
    
    // Determine actual dark mode based on theme setting
    val isDark = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> systemDark
    }

    val context = LocalContext.current
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()
    
    // Gemini Live mode preference (stored in aura_settings SharedPreferences)
    val auraPrefs = remember { context.getSharedPreferences("aura_settings", android.content.Context.MODE_PRIVATE) }
    var geminiLiveEnabled by remember { mutableStateOf(auraPrefs.getBoolean("use_gemini_live", false)) }

    // Selected voice state - read from SharedPreferences
    val voicePrefs = remember { context.getSharedPreferences("aura_voice_settings", android.content.Context.MODE_PRIVATE) }
    var selectedVoiceName by remember {
        val voiceId = voicePrefs.getString("selected_voice_id", "en-US-AriaNeural") ?: "en-US-AriaNeural"
        mutableStateOf(getVoiceDisplayName(voiceId))
    }
    
    // Refresh voice name when returning from voice settings
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                val voiceId = voicePrefs.getString("selected_voice_id", "en-US-AriaNeural") ?: "en-US-AriaNeural"
                selectedVoiceName = getVoiceDisplayName(voiceId)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }
    
    // Server health state
    var serverStatus by remember { mutableStateOf("Tap to check") }
    var isCheckingServer by remember { mutableStateOf(false) }
    var isServerConnected by remember { mutableStateOf(false) }
    
    // Colors based on theme
    val backgroundColor = if (isDark) AppleColors.Dark.Background else AppleColors.Light.Background
    val groupBackgroundColor = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val separatorColor = if (isDark) AppleColors.Dark.Separator else AppleColors.Light.Separator
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(backgroundColor)
            .systemBarsPadding()
    ) {
        // Navigation Bar
        AppleNavigationBar(
            title = "Settings",
            onBackClick = onNavigateBack,
            isDark = isDark,
        )
        
        // Scrollable Content
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp)
        ) {
            Spacer(modifier = Modifier.height(8.dp))
            
            // Server Connection Section
            SettingsGroup(
                title = "CONNECTION",
                isDark = isDark,
            ) {
                // Server Status Row
                SettingsRow(
                    icon = Icons.Default.Cloud,
                    iconTint = if (isServerConnected) AppleColors.Green else AppleColors.Orange,
                    title = "Server Status",
                    subtitle = serverStatus,
                    isDark = isDark,
                    onClick = {
                        scope.launch {
                            isCheckingServer = true
                            serverStatus = "Checking..."
                            val result = checkServerHealth()
                            serverStatus = result
                            isServerConnected = result.contains("✓")
                            isCheckingServer = false
                        }
                    },
                    trailing = {
                        if (isCheckingServer) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                            )
                        } else {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = null,
                                tint = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                )
                
                SettingsDivider(isDark)
                
                // Server Configuration
                SettingsNavigationRow(
                    icon = Icons.Default.Settings,
                    title = "Server Configuration",
                    isDark = isDark,
                    onClick = onNavigateToServerConfig,
                )
            }
            
            // Appearance Section
            SettingsGroup(
                title = "APPEARANCE",
                isDark = isDark,
            ) {
                SettingsRow(
                    icon = Icons.Default.Palette,
                    iconTint = if (isDark) AppleColors.PurpleDark else AppleColors.Purple,
                    title = "Theme",
                    isDark = isDark,
                    trailing = {
                        AppleSegmentedControl(
                            options = listOf("Auto", "Light", "Dark"),
                            selectedIndex = when (themeMode) {
                                ThemeMode.SYSTEM -> 0
                                ThemeMode.LIGHT -> 1
                                ThemeMode.DARK -> 2
                            },
                            onSelectionChanged = { index ->
                                ThemeManager.updateThemeMode(
                                    when (index) {
                                        0 -> ThemeMode.SYSTEM
                                        1 -> ThemeMode.LIGHT
                                        else -> ThemeMode.DARK
                                    }
                                )
                            },
                            isDark = isDark,
                        )
                    }
                )
            }
            
            // Voice Settings Section
            SettingsGroup(
                title = "VOICE",
                isDark = isDark,
            ) {
                // Voice Selection - navigate to voice settings screen
                SettingsNavigationRow(
                    icon = Icons.Default.RecordVoiceOver,
                    title = "Assistant Voice",
                    subtitle = selectedVoiceName,
                    isDark = isDark,
                    onClick = onNavigateToVoiceSettings,
                    iconTintOverride = if (isDark) AppleColors.TealDark else AppleColors.Teal,
                )
                
                SettingsDivider(isDark)
                
                // Wake Word Toggle
                SettingsToggleRow(
                    icon = Icons.Default.Hearing,
                    iconTint = if (isDark) AppleColors.PurpleDark else AppleColors.Purple,
                    title = "\"Hey AURA\" Wake Word",
                    isEnabled = wakeWordEnabled,
                    onToggle = { enabled ->
                        ThemeManager.updateWakeWord(enabled)
                        if (enabled) {
                            WakeWordListeningService.start(context)
                        } else {
                            WakeWordListeningService.stop(context)
                        }
                    },
                    isDark = isDark,
                )

                SettingsDivider(isDark)

                // Gemini Live toggle — routes mic through /ws/live bidirectional stream
                SettingsToggleRow(
                    icon = Icons.Default.AutoAwesome,
                    iconTint = if (isDark) Color(0xFF4285F4) else Color(0xFF1A73E8),
                    title = "Gemini Live Mode",
                    subtitle = "Bidirectional audio via Gemini 2.0",
                    isEnabled = geminiLiveEnabled,
                    onToggle = { enabled ->
                        geminiLiveEnabled = enabled
                        auraPrefs.edit().putBoolean("use_gemini_live", enabled).apply()
                    },
                    isDark = isDark,
                )

                SettingsDivider(isDark)
                
                Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Mic,
                                contentDescription = null,
                                tint = if (isDark) AppleColors.TealDark else AppleColors.Teal,
                                modifier = Modifier.size(24.dp)
                            )
                            Text(
                                text = "Voice Sensitivity",
                                style = MaterialTheme.typography.bodyLarge,
                                color = labelPrimary,
                            )
                        }
                        Text(
                            text = "${(voiceSensitivity * 100).toInt()}%",
                            style = MaterialTheme.typography.bodyMedium,
                            color = labelSecondary,
                        )
                    }
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Slider(
                        value = voiceSensitivity,
                        onValueChange = ThemeManager::updateVoiceActivationSensitivity,
                        valueRange = 0.2f..1f,
                        colors = SliderDefaults.colors(
                            thumbColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                            activeTrackColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                            inactiveTrackColor = if (isDark) AppleColors.Dark.Fill else AppleColors.Light.Fill,
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
            
            // AI Model Section
            SettingsGroup(
                title = "AI MODEL",
                isDark = isDark,
            ) {
                SettingsNavigationRow(
                    icon = Icons.Default.Psychology,
                    title = "On-Device Model",
                    subtitle = "Function Gemma — local commands",
                    isDark = isDark,
                    onClick = onNavigateToModelDownload,
                    iconTintOverride = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                )
            }
            
            // Preferences Section
            SettingsGroup(
                title = "PREFERENCES",
                isDark = isDark,
            ) {
                SettingsToggleRow(
                    icon = Icons.Default.Notifications,
                    iconTint = if (isDark) AppleColors.RedDark else AppleColors.Red,
                    title = "Notifications",
                    isEnabled = notifications,
                    onToggle = ThemeManager::updateNotifications,
                    isDark = isDark,
                )
                
                SettingsDivider(isDark)
                
                SettingsToggleRow(
                    icon = Icons.Default.Vibration,
                    iconTint = if (isDark) AppleColors.OrangeDark else AppleColors.Orange,
                    title = "Haptic Feedback",
                    isEnabled = haptics,
                    onToggle = ThemeManager::updateHapticFeedback,
                    isDark = isDark,
                )
                
                SettingsDivider(isDark)
                
                // Screen Capture - shows actual MediaProjection status
                SettingsToggleRow(
                    icon = Icons.Default.Screenshot,
                    iconTint = if (isDark) AppleColors.GreenDark else AppleColors.Green,
                    title = "Screen Capture",
                    subtitle = if (isScreenCaptureAvailable) "Enabled" else "Tap to enable",
                    isEnabled = isScreenCaptureAvailable,
                    onToggle = { enabled ->
                        if (enabled && !isScreenCaptureAvailable) {
                            onRequestScreenCapture()
                        }
                        // Update preference (will be used when permission is granted)
                        ThemeManager.updateScreenCapture(enabled)
                    },
                    isDark = isDark,
                )
            }
            
            // Permissions Section
            val permissionStatuses = rememberPermissionStatuses()
            SettingsGroup(
                title = "PERMISSIONS",
                isDark = isDark,
            ) {
                permissionStatuses.forEachIndexed { index, status ->
                    SettingsPermissionRow(
                        title = status.title,
                        isEnabled = status.enabled,
                        isDark = isDark,
                        onClick = status.onClick,
                    )
                    if (index < permissionStatuses.size - 1) {
                        SettingsDivider(isDark)
                    }
                }
            }
            
            // App Info Section
            SettingsGroup(
                title = "ABOUT",
                isDark = isDark,
            ) {
                SettingsInfoRow(
                    title = "Version",
                    value = "2.0.0",
                    isDark = isDark,
                )
                
                SettingsDivider(isDark)
                
                SettingsInfoRow(
                    title = "Build",
                    value = "2026.01.14",
                    isDark = isDark,
                )
            }
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

// ============================================================================
// APPLE-STYLE COMPONENTS
// ============================================================================

@Composable
private fun AppleNavigationBar(
    title: String,
    onBackClick: () -> Unit,
    isDark: Boolean,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Back button
        TextButton(onClick = onBackClick) {
            Icon(
                imageVector = Icons.Default.ArrowBackIosNew,
                contentDescription = "Back",
                tint = accentColor,
                modifier = Modifier.size(20.dp)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text(
                text = "Back",
                color = accentColor,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        
        Spacer(modifier = Modifier.weight(1f))
        
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium.copy(
                fontWeight = FontWeight.SemiBold
            ),
            color = labelPrimary,
        )
        
        Spacer(modifier = Modifier.weight(1f))
        
        // Placeholder for symmetry
        Spacer(modifier = Modifier.width(80.dp))
    }
}

@Composable
private fun SettingsGroup(
    title: String,
    isDark: Boolean,
    content: @Composable ColumnScope.() -> Unit,
) {
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    
    Column {
        // Section header
        Text(
            text = title,
            style = MaterialTheme.typography.bodySmall.copy(
                fontWeight = FontWeight.Normal,
                letterSpacing = 0.5.sp
            ),
            color = labelSecondary,
            modifier = Modifier.padding(start = 16.dp, bottom = 8.dp)
        )
        
        // Group container
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            color = groupBackground,
        ) {
            Column {
                content()
            }
        }
    }
}

@Composable
private fun SettingsRow(
    icon: ImageVector,
    iconTint: Color,
    title: String,
    subtitle: String? = null,
    isDark: Boolean,
    onClick: (() -> Unit)? = null,
    trailing: @Composable (() -> Unit)? = null,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(
                if (onClick != null) {
                    Modifier.clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = ripple(color = if (isDark) Color.White.copy(alpha = 0.1f) else Color.Black.copy(alpha = 0.1f)),
                        onClick = onClick
                    )
                } else Modifier
            )
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Icon
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(iconTint.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = iconTint,
                modifier = Modifier.size(18.dp)
            )
        }
        
        // Title and subtitle
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                color = labelPrimary,
            )
            if (subtitle != null) {
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = labelSecondary,
                )
            }
        }
        
        // Trailing content
        trailing?.invoke()
    }
}

@Composable
private fun SettingsNavigationRow(
    icon: ImageVector,
    title: String,
    isDark: Boolean,
    onClick: () -> Unit,
    subtitle: String? = null,
    iconTintOverride: Color? = null,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val labelTertiary = if (isDark) AppleColors.LabelDark.Tertiary else AppleColors.LabelLight.Tertiary
    val iconTint = iconTintOverride ?: if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val hapticFeedback = rememberHapticFeedback()
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable {
                hapticFeedback(AuraHapticType.SELECTION)
                onClick()
            }
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(iconTint.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = iconTint,
                modifier = Modifier.size(18.dp)
            )
        }
        
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                color = labelPrimary,
            )
            if (subtitle != null) {
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = labelSecondary,
                )
            }
        }
        
        Icon(
            imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
            contentDescription = null,
            tint = labelTertiary,
            modifier = Modifier.size(20.dp)
        )
    }
}

@Composable
private fun SettingsToggleRow(
    icon: ImageVector,
    iconTint: Color,
    title: String,
    isEnabled: Boolean,
    onToggle: (Boolean) -> Unit,
    isDark: Boolean,
    subtitle: String? = null,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val hapticFeedback = rememberHapticFeedback()
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable {
                hapticFeedback(AuraHapticType.MEDIUM)
                onToggle(!isEnabled)
            }
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(iconTint.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = iconTint,
                modifier = Modifier.size(18.dp)
            )
        }
        
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                color = labelPrimary,
            )
            if (subtitle != null) {
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = labelSecondary,
                )
            }
        }
        
        AppleSwitch(
            checked = isEnabled,
            onCheckedChange = onToggle,
        )
    }
}

@Composable
private fun SettingsPermissionRow(
    title: String,
    isEnabled: Boolean,
    isDark: Boolean,
    onClick: () -> Unit,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val statusColor = if (isEnabled) {
        if (isDark) AppleColors.GreenDark else AppleColors.Green
    } else {
        if (isDark) AppleColors.RedDark else AppleColors.Red
    }
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyLarge,
            color = labelPrimary,
            modifier = Modifier.weight(1f)
        )
        
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(statusColor)
            )
            Text(
                text = if (isEnabled) "Enabled" else "Disabled",
                style = MaterialTheme.typography.bodyMedium,
                color = statusColor,
            )
        }
    }
}

@Composable
private fun SettingsInfoRow(
    title: String,
    value: String,
    isDark: Boolean,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyLarge,
            color = labelPrimary,
            modifier = Modifier.weight(1f)
        )
        
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = labelSecondary,
        )
    }
}

@Composable
private fun SettingsDivider(isDark: Boolean) {
    val separatorColor = if (isDark) AppleColors.Dark.Separator else AppleColors.Light.Separator
    
    HorizontalDivider(
        modifier = Modifier.padding(start = 60.dp),
        thickness = 0.5.dp,
        color = separatorColor,
    )
}

@Composable
private fun AppleSwitch(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    val onColor = MaterialTheme.colorScheme.onBackground
    val offColor = MaterialTheme.colorScheme.surfaceVariant
    val trackColor by animateColorAsState(
        targetValue = if (checked) onColor else offColor,
        animationSpec = tween(200),
        label = "switch_track"
    )
    
    Switch(
        checked = checked,
        onCheckedChange = onCheckedChange,
        colors = SwitchDefaults.colors(
            checkedThumbColor = MaterialTheme.colorScheme.background,
            checkedTrackColor = trackColor,
            uncheckedThumbColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            uncheckedTrackColor = trackColor,
            uncheckedBorderColor = Color.Transparent,
            checkedBorderColor = Color.Transparent,
        )
    )
}

@Composable
private fun AppleSegmentedControl(
    options: List<String>,
    selectedIndex: Int,
    onSelectionChanged: (Int) -> Unit,
    isDark: Boolean,
) {
    val backgroundColor = if (isDark) AppleColors.Dark.Fill else AppleColors.Light.Fill
    val selectedBackground = if (isDark) AppleColors.Dark.SurfaceSecondary else Color.White
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = backgroundColor,
    ) {
        Row(
            modifier = Modifier.padding(2.dp),
            horizontalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            options.forEachIndexed { index, option ->
                val isSelected = index == selectedIndex
                
                Surface(
                    modifier = Modifier
                        .clickable { onSelectionChanged(index) },
                    shape = RoundedCornerShape(6.dp),
                    color = if (isSelected) selectedBackground else Color.Transparent,
                    shadowElevation = if (isSelected) 1.dp else 0.dp,
                ) {
                    Text(
                        text = option,
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal
                        ),
                        color = labelPrimary,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                    )
                }
            }
        }
    }
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

private suspend fun checkServerHealth(): String {
    return withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(5, TimeUnit.SECONDS)
                .build()
            
            val urls = listOf(
                "http://10.193.156.197:8000",
                "http://192.168.1.41:8000",
                "http://192.168.43.1:8000",
                "http://10.0.2.2:8000",
            )
            
            for (url in urls) {
                try {
                    val request = Request.Builder()
                        .url("$url/health")
                        .build()
                    
                    client.newCall(request).execute().use { response ->
                        if (response.isSuccessful) {
                            return@withContext "✓ Connected"
                        }
                    }
                } catch (e: Exception) {
                    continue
                }
            }
            
            "✗ Not connected"
        } catch (e: Exception) {
            "✗ Error"
        }
    }
}

private data class PermissionStatus(
    val title: String,
    val enabled: Boolean,
    val onClick: () -> Unit,
)

@Composable
private fun rememberPermissionStatuses(): List<PermissionStatus> {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var statuses by remember { mutableStateOf(calculatePermissionStatuses(context)) }

    DisposableEffect(lifecycleOwner, context) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                statuses = calculatePermissionStatuses(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    return statuses
}

private fun calculatePermissionStatuses(context: android.content.Context): List<PermissionStatus> {
    val packageName = context.packageName

    return listOf(
        PermissionStatus(
            title = "Microphone",
            enabled = ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.RECORD_AUDIO,
            ) == PackageManager.PERMISSION_GRANTED,
        ) {
            context.startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.fromParts("package", packageName, null)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
        },
        PermissionStatus(
            title = "Overlay",
            enabled = Settings.canDrawOverlays(context),
        ) {
            context.startActivity(
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
        },
        PermissionStatus(
            title = "Accessibility",
            enabled = isAuraAccessibilityEnabled(context),
        ) {
            context.startActivity(
                Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
        },
        PermissionStatus(
            title = "Notifications",
            enabled = NotificationManagerCompat.from(context).areNotificationsEnabled(),
        ) {
            context.startActivity(
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                    putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
        },
        PermissionStatus(
            title = "Screen Capture",
            enabled = AuraAccessibilityService.instance?.isMediaProjectionAvailable() ?: false,
        ) {
            // Start MainActivity with flag to request screen capture permission
            val intent = android.content.Intent(context, com.aura.aura_ui.MainActivity::class.java).apply {
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                putExtra("REQUEST_SCREEN_CAPTURE", true)
            }
            context.startActivity(intent)
        },
    )
}

private fun isAuraAccessibilityEnabled(context: android.content.Context): Boolean {
    val expectedComponent = "${context.packageName}/${AuraAccessibilityService::class.qualifiedName}"
    val enabledServices = Settings.Secure.getString(
        context.contentResolver,
        Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
    ) ?: return false
    return enabledServices.split(':').any { it.equals(expectedComponent, ignoreCase = true) }
}

/**
 * Get display name for a voice ID
 */
private fun getVoiceDisplayName(voiceId: String): String {
    return when (voiceId) {
        "en-US-AriaNeural" -> "Aria"
        "en-US-GuyNeural" -> "Guy"
        "en-US-JennyNeural" -> "Jenny"
        "en-US-ChristopherNeural" -> "Christopher"
        "en-GB-SoniaNeural" -> "Sonia"
        "en-GB-RyanNeural" -> "Ryan"
        "en-AU-NatashaNeural" -> "Natasha"
        "en-US-EmmaNeural" -> "Emma"
        else -> voiceId.substringAfter("-").substringBefore("Neural")
    }
}
