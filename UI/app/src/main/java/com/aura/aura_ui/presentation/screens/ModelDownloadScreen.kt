package com.aura.aura_ui.presentation.screens

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.functiongemma.FunctionGemmaManager
import com.aura.aura_ui.functiongemma.MODEL_SIZE_BYTES
import com.aura.aura_ui.functiongemma.ModelState
import com.aura.aura_ui.ui.theme.AppleColors
import kotlinx.coroutines.launch

/**
 * Settings screen for downloading and managing the local Function Gemma AI model.
 * Matches AURA's Apple-inspired settings design.
 */
@Composable
fun ModelDownloadScreen(
    functionGemmaManager: FunctionGemmaManager,
    onNavigateBack: () -> Unit,
) {
    val systemDark = isSystemInDarkTheme()
    val themeMode by ThemeManager.themeMode.collectAsState()
    val isDark = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> systemDark
    }

    val state by functionGemmaManager.state.collectAsState()
    val progress by functionGemmaManager.downloadProgress.collectAsState()
    val errorMessage by functionGemmaManager.errorMessage.collectAsState()
    val pipelineEnabled by functionGemmaManager.pipelineEnabled.collectAsState()
    val scope = rememberCoroutineScope()
    val usingGalleryModel = remember(state) { functionGemmaManager.isUsingGalleryModel() }
    var hfToken by remember { mutableStateOf("") }
    var tokenVisible by remember { mutableStateOf(false) }

    val backgroundColor = if (isDark) AppleColors.Dark.Background else AppleColors.Light.Background
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(backgroundColor)
            .systemBarsPadding()
    ) {
        // Navigation Bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onNavigateBack) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = accentColor,
                )
            }
            Text(
                text = "AI Model",
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                color = labelPrimary,
                modifier = Modifier.padding(start = 4.dp),
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Spacer(modifier = Modifier.height(8.dp))

            // Model Info Card
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                color = groupBackground,
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Box(
                            modifier = Modifier
                                .size(48.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(accentColor.copy(alpha = 0.15f)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                imageVector = Icons.Default.Psychology,
                                contentDescription = null,
                                tint = accentColor,
                                modifier = Modifier.size(28.dp),
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Function Gemma",
                                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                                color = labelPrimary,
                            )
                            Text(
                                text = "On-device command classifier • 270M params",
                                style = MaterialTheme.typography.bodySmall,
                                color = labelSecondary,
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        text = "Enables instant local handling of device commands like flashlight, volume, brightness, app launching, and more — without sending data to the server.",
                        style = MaterialTheme.typography.bodySmall,
                        color = labelSecondary,
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Size info
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            text = "Model size",
                            style = MaterialTheme.typography.bodySmall,
                            color = labelSecondary,
                        )
                        Text(
                            text = formatBytes(MODEL_SIZE_BYTES),
                            style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                            color = labelPrimary,
                        )
                    }

                    if (state == ModelState.DOWNLOADED || state == ModelState.READY) {
                        val sizeOnDisk = functionGemmaManager.getModelSizeOnDisk()
                        if (sizeOnDisk > 0) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(
                                    text = "On disk",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = labelSecondary,
                                )
                                Text(
                                    text = formatBytes(sizeOnDisk),
                                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                                    color = labelPrimary,
                                )
                            }
                        }
                    }
                }
            }

            // Experimental / Developer toggle
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                color = groupBackground,
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            modifier = Modifier.weight(1f),
                        ) {
                            Icon(
                                imageVector = Icons.Default.Build,
                                contentDescription = null,
                                tint = if (isDark) AppleColors.OrangeDark else AppleColors.Orange,
                                modifier = Modifier.size(18.dp),
                            )
                            Column {
                                Text(
                                    text = "Local Pipeline",
                                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                                    color = labelPrimary,
                                )
                                Text(
                                    text = "Experimental — under active development",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = if (isDark) AppleColors.OrangeDark else AppleColors.Orange,
                                )
                            }
                        }
                        Switch(
                            checked = pipelineEnabled,
                            onCheckedChange = { functionGemmaManager.setPipelineEnabled(it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = if (isDark) AppleColors.OrangeDark else AppleColors.Orange,
                            ),
                        )
                    }
                    if (!pipelineEnabled) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Pipeline disabled — all commands will be routed to the server.",
                            style = MaterialTheme.typography.bodySmall,
                            color = labelSecondary,
                        )
                    }
                }
            }

            // Status + Action Section
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                color = groupBackground,
            ) {
                Column(
                    modifier = Modifier
                        .padding(16.dp)
                        .animateContentSize(),
                ) {
                    // Status badge
                    StatusBadge(state = state, isDark = isDark, usingGallery = usingGalleryModel)

                    Spacer(modifier = Modifier.height(12.dp))

                    when (state) {
                        ModelState.NOT_DOWNLOADED -> {
                            // HuggingFace token input (required — model is gated)
                            OutlinedTextField(
                                value = hfToken,
                                onValueChange = { hfToken = it },
                                label = { Text("HuggingFace Token") },
                                placeholder = { Text("hf_...") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                visualTransformation = if (tokenVisible) VisualTransformation.None else PasswordVisualTransformation(),
                                trailingIcon = {
                                    IconButton(onClick = { tokenVisible = !tokenVisible }) {
                                        Icon(
                                            if (tokenVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                            contentDescription = if (tokenVisible) "Hide token" else "Show token",
                                            tint = labelSecondary,
                                        )
                                    }
                                },
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = accentColor,
                                    unfocusedBorderColor = labelSecondary.copy(alpha = 0.3f),
                                    focusedLabelColor = accentColor,
                                    unfocusedLabelColor = labelSecondary,
                                    cursorColor = accentColor,
                                ),
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Get a free READ token at huggingface.co/settings/tokens",
                                style = MaterialTheme.typography.labelSmall,
                                color = labelSecondary,
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            Button(
                                onClick = {
                                    scope.launch {
                                        functionGemmaManager.downloadAndInitialize(hfToken.trim().takeIf { it.isNotEmpty() })
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = accentColor),
                            ) {
                                Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("Download Model (${formatBytes(MODEL_SIZE_BYTES)})")
                            }
                        }

                        ModelState.DOWNLOADING -> {
                            LinearProgressIndicator(
                                progress = { progress },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(6.dp)
                                    .clip(RoundedCornerShape(3.dp)),
                                color = accentColor,
                                trackColor = accentColor.copy(alpha = 0.15f),
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "${(progress * 100).toInt()}% — ${formatBytes((progress * MODEL_SIZE_BYTES).toLong())} / ${formatBytes(MODEL_SIZE_BYTES)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = labelSecondary,
                            )
                        }

                        ModelState.DOWNLOADED -> {
                            if (usingGalleryModel) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(accentColor.copy(alpha = 0.08f))
                                        .padding(horizontal = 12.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    Icon(
                                        Icons.Default.CheckCircle,
                                        contentDescription = null,
                                        tint = if (isDark) AppleColors.GreenDark else AppleColors.Green,
                                        modifier = Modifier.size(18.dp),
                                    )
                                    Text(
                                        text = "Found in Google Edge AI Gallery — no download needed",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = labelPrimary,
                                    )
                                }
                                Spacer(modifier = Modifier.height(8.dp))
                            }

                            Button(
                                onClick = {
                                    scope.launch { functionGemmaManager.initializeEngine() }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = accentColor),
                            ) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("Initialize Model")
                            }

                            if (!usingGalleryModel) {
                                Spacer(modifier = Modifier.height(8.dp))
                                OutlinedButton(
                                    onClick = { functionGemmaManager.deleteModel() },
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(10.dp),
                                    colors = ButtonDefaults.outlinedButtonColors(
                                        contentColor = if (isDark) AppleColors.RedDark else AppleColors.Red,
                                    ),
                                ) {
                                    Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("Delete Model")
                                }
                            }
                        }

                        ModelState.INITIALIZING -> {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(12.dp),
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp),
                                    strokeWidth = 2.dp,
                                    color = accentColor,
                                )
                                Text(
                                    text = "Loading model into memory…",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = labelSecondary,
                                )
                            }
                        }

                        ModelState.READY -> {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Icon(
                                    Icons.Default.CheckCircle,
                                    contentDescription = null,
                                    tint = if (isDark) AppleColors.GreenDark else AppleColors.Green,
                                    modifier = Modifier.size(20.dp),
                                )
                                Text(
                                    text = "Model active — commands are processed locally",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = labelPrimary,
                                )
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            OutlinedButton(
                                onClick = { functionGemmaManager.deleteModel() },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.outlinedButtonColors(
                                    contentColor = if (isDark) AppleColors.RedDark else AppleColors.Red,
                                ),
                            ) {
                                Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("Delete Model")
                            }
                        }

                        ModelState.ERROR -> {
                            Text(
                                text = errorMessage ?: "Unknown error",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (isDark) AppleColors.RedDark else AppleColors.Red,
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            // Show token field again on error so user can fix it
                            OutlinedTextField(
                                value = hfToken,
                                onValueChange = { hfToken = it },
                                label = { Text("HuggingFace Token") },
                                placeholder = { Text("hf_...") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                visualTransformation = if (tokenVisible) VisualTransformation.None else PasswordVisualTransformation(),
                                trailingIcon = {
                                    IconButton(onClick = { tokenVisible = !tokenVisible }) {
                                        Icon(
                                            if (tokenVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                            contentDescription = null,
                                            tint = labelSecondary,
                                        )
                                    }
                                },
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = accentColor,
                                    unfocusedBorderColor = labelSecondary.copy(alpha = 0.3f),
                                    focusedLabelColor = accentColor,
                                    unfocusedLabelColor = labelSecondary,
                                    cursorColor = accentColor,
                                ),
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(
                                onClick = {
                                    scope.launch {
                                        functionGemmaManager.downloadAndInitialize(hfToken.trim().takeIf { it.isNotEmpty() })
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = accentColor),
                            ) {
                                Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("Retry")
                            }
                        }
                    }
                }
            }

            // Capabilities Info Section
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                color = groupBackground,
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "LOCAL CAPABILITIES",
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontWeight = FontWeight.Normal,
                            letterSpacing = 0.5.sp,
                        ),
                        color = labelSecondary,
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    val capabilities = listOf(
                        "Flashlight on/off" to Icons.Default.FlashlightOn,
                        "Volume up/down/mute" to Icons.Default.VolumeUp,
                        "Brightness control" to Icons.Default.BrightnessHigh,
                        "Do Not Disturb" to Icons.Default.DoNotDisturb,
                        "Auto-rotate toggle" to Icons.Default.ScreenRotation,
                        "Open apps by name" to Icons.Default.Apps,
                        "Show location on map" to Icons.Default.Map,
                        "WiFi / Bluetooth settings" to Icons.Default.Wifi,
                        "Send email (compose)" to Icons.Default.Email,
                        "Create contact" to Icons.Default.PersonAdd,
                        "Calendar events" to Icons.Default.CalendarMonth,
                        "Set alarm / timer" to Icons.Default.Alarm,
                    )

                    capabilities.forEach { (label, icon) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Icon(
                                imageVector = icon,
                                contentDescription = null,
                                tint = accentColor,
                                modifier = Modifier.size(16.dp),
                            )
                            Text(
                                text = label,
                                style = MaterialTheme.typography.bodyMedium,
                                color = labelPrimary,
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun StatusBadge(state: ModelState, isDark: Boolean, usingGallery: Boolean = false) {
    val (text, color) = when (state) {
        ModelState.NOT_DOWNLOADED -> "Not Downloaded" to (if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary)
        ModelState.DOWNLOADING -> "Downloading…" to (if (isDark) AppleColors.OrangeDark else AppleColors.Orange)
        ModelState.DOWNLOADED -> (if (usingGallery) "Edge AI Gallery Model" else "Downloaded — Not Active") to (if (isDark) AppleColors.OrangeDark else AppleColors.Orange)
        ModelState.INITIALIZING -> "Initializing…" to (if (isDark) AppleColors.IndigoDark else AppleColors.Indigo)
        ModelState.READY -> "Active" to (if (isDark) AppleColors.GreenDark else AppleColors.Green)
        ModelState.ERROR -> "Error" to (if (isDark) AppleColors.RedDark else AppleColors.Red)
    }

    Surface(
        shape = RoundedCornerShape(6.dp),
        color = color.copy(alpha = 0.15f),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Medium),
            color = color,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

private fun formatBytes(bytes: Long): String {
    return when {
        bytes >= 1_000_000_000 -> String.format("%.1f GB", bytes / 1_000_000_000.0)
        bytes >= 1_000_000 -> String.format("%.0f MB", bytes / 1_000_000.0)
        bytes >= 1_000 -> String.format("%.0f KB", bytes / 1_000.0)
        else -> "$bytes B"
    }
}
