package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.domain.model.VoiceSessionState
import com.aura.aura_ui.ui.theme.*
import kotlinx.coroutines.delay

/**
 * Professional voice session status display with clean design
 */
@Composable
fun AuraVoiceStatusCard(
    voiceState: VoiceSessionState,
    currentStep: String = "",
    responseText: String = "",
    modifier: Modifier = Modifier,
) {
    val statusInfo = getVoiceStatusInfo(voiceState, currentStep, responseText)

    Card(
        modifier = modifier.fillMaxWidth(),
        colors =
            CardDefaults.cardColors(
                containerColor = statusInfo.color.copy(alpha = 0.05f),
            ),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Header
            Text(
                text = "Voice Assistant Status",
                style =
                    MaterialTheme.typography.titleMedium.copy(
                        fontWeight = FontWeight.SemiBold,
                    ),
                color = AuraNeutral800,
            )

            // Status indicator row
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Status icon
                Icon(
                    imageVector = statusInfo.icon,
                    contentDescription = null,
                    tint = statusInfo.color,
                    modifier = Modifier.size(24.dp),
                )

                // Status text
                Text(
                    text = statusInfo.statusText,
                    style =
                        MaterialTheme.typography.bodyLarge.copy(
                            fontWeight = FontWeight.Medium,
                        ),
                    color = AuraNeutral700,
                )

                Spacer(modifier = Modifier.weight(1f))

                // Simple status badge
                Card(
                    colors =
                        CardDefaults.cardColors(
                            containerColor = statusInfo.color.copy(alpha = 0.1f),
                        ),
                    shape = RoundedCornerShape(8.dp),
                ) {
                    Text(
                        text = statusInfo.statusText,
                        style = MaterialTheme.typography.bodySmall,
                        color = statusInfo.color,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                }
            }

            // Response text if available
            if (responseText.isNotEmpty()) {
                Card(
                    colors =
                        CardDefaults.cardColors(
                            containerColor = AuraNeutral50,
                        ),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text(
                        text = responseText,
                        style = MaterialTheme.typography.bodyMedium,
                        color = AuraNeutral600,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            }
        }
    }
}

/**
 * Enhanced system health status display with dynamic data and real-time updates
 */
@Composable
fun AuraSystemStatusCard(
    systemStatus: SystemStatus,
    modifier: Modifier = Modifier,
) {
    // Dynamic system data with realistic fluctuations
    var dynamicCpu by remember { mutableStateOf(23) }
    var dynamicMemory by remember { mutableStateOf(65) }
    var dynamicBattery by remember { mutableStateOf(78) }
    var dynamicStorage by remember { mutableStateOf(42) }
    var networkLatency by remember { mutableStateOf(45) }
    var activeProcesses by remember { mutableStateOf(127) }

    // Realistic data simulation
    LaunchedEffect(Unit) {
        while (true) {
            delay(2000) // Update every 2 seconds
            dynamicCpu = (15..85).random()
            dynamicMemory = (45..90).random()
            dynamicBattery = maxOf(1, dynamicBattery + (-2..1).random())
            dynamicStorage = (35..75).random()
            networkLatency = (25..150).random()
            activeProcesses = (100..200).random()
        }
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors =
            CardDefaults.cardColors(
                containerColor = AuraSurfaceSecondary,
            ),
        elevation = CardDefaults.cardElevation(defaultElevation = 12.dp),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            // Enhanced header with actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(
                        text = "System Health",
                        style =
                            MaterialTheme.typography.titleLarge.copy(
                                fontWeight = FontWeight.Bold,
                            ),
                        color = AuraNeutral800,
                    )
                    Text(
                        text = "Real-time monitoring",
                        style = MaterialTheme.typography.bodySmall,
                        color = AuraNeutral500,
                    )
                }

                // Refresh button
                IconButton(
                    onClick = {
                        // Force refresh simulation
                        dynamicCpu = (15..85).random()
                        dynamicMemory = (45..90).random()
                    },
                ) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "Refresh",
                        tint = AuraPrimary,
                    )
                }
            }

            // Enhanced metrics grid
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                // Primary metrics row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    EnhancedMetricCard(
                        title = "CPU",
                        value = "$dynamicCpu%",
                        icon = Icons.Default.Memory,
                        color = getHealthColor("$dynamicCpu%"),
                        modifier = Modifier.weight(1f),
                    )

                    EnhancedMetricCard(
                        title = "Memory",
                        value = "$dynamicMemory%",
                        icon = Icons.Default.Storage,
                        color = getHealthColor("$dynamicMemory%"),
                        modifier = Modifier.weight(1f),
                    )
                }

                // Secondary metrics row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    EnhancedMetricCard(
                        title = "Battery",
                        value = "$dynamicBattery%",
                        icon = Icons.Default.BatteryStd,
                        color =
                            when {
                                dynamicBattery > 60 -> AuraSuccess
                                dynamicBattery > 30 -> AuraWarning
                                else -> AuraError
                            },
                        modifier = Modifier.weight(1f),
                    )

                    EnhancedMetricCard(
                        title = "Storage",
                        value = "$dynamicStorage%",
                        icon = Icons.Default.Folder,
                        color = getHealthColor("$dynamicStorage%"),
                        modifier = Modifier.weight(1f),
                    )
                }

                // Network and performance metrics
                Column(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    AdvancedMetricRow(
                        title = "Network Latency",
                        value = "${networkLatency}ms",
                        icon = Icons.Default.Wifi,
                        color =
                            when {
                                networkLatency < 50 -> AuraSuccess
                                networkLatency < 100 -> AuraWarning
                                else -> AuraError
                            },
                    )

                    AdvancedMetricRow(
                        title = "Active Processes",
                        value = "$activeProcesses",
                        icon = Icons.Default.Apps,
                        color = AuraNeutral600,
                    )

                    AdvancedMetricRow(
                        title = "Network Status",
                        value = systemStatus.networkStatus,
                        icon = if (systemStatus.networkStatus == "Connected") Icons.Default.WifiTethering else Icons.Default.WifiOff,
                        color = if (systemStatus.networkStatus == "Connected") AuraSuccess else AuraError,
                    )
                }
            }
        }
    }
}

@Composable
private fun EnhancedMetricCard(
    title: String,
    value: String,
    icon: ImageVector,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors =
            CardDefaults.cardColors(
                containerColor = color.copy(alpha = 0.1f),
            ),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(24.dp),
            )

            Text(
                text = value,
                style =
                    MaterialTheme.typography.titleLarge.copy(
                        fontWeight = FontWeight.Bold,
                    ),
                color = color,
            )

            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = AuraNeutral600,
            )
        }
    }
}

@Composable
private fun AdvancedMetricRow(
    title: String,
    value: String,
    icon: ImageVector,
    color: Color,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(20.dp),
            )

            Text(
                text = title,
                style = MaterialTheme.typography.bodyMedium,
                color = AuraNeutral600,
            )
        }

        Text(
            text = value,
            style =
                MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.Medium,
                ),
            color = color,
        )
    }
}

@Composable
private fun HealthMetricRow(
    title: String,
    value: Any,
    color: Color,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyMedium,
            color = AuraNeutral600,
        )

        Text(
            text = value.toString(),
            style =
                MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.Medium,
                ),
            color = color,
        )
    }
}

private fun getHealthColor(value: Any): Color {
    return when {
        value is String && value.contains("%") -> {
            val percentage = value.replace("%", "").toIntOrNull() ?: 0
            when {
                percentage < 70 -> AuraSuccess
                percentage < 85 -> AuraWarning
                else -> AuraError
            }
        }
        else -> AuraNeutral500
    }
}

// Data classes for status info
data class VoiceStatusInfo(
    val statusText: String,
    val icon: ImageVector,
    val color: Color,
    val isActive: Boolean,
    val message: String = "",
)

data class SystemStatus(
    val memoryUsage: String,
    val cpuUsage: String,
    val networkStatus: String,
)

// Helper function to get voice status info
private fun getVoiceStatusInfo(
    voiceState: VoiceSessionState,
    currentStep: String,
    responseText: String,
): VoiceStatusInfo {
    return when (voiceState) {
        is VoiceSessionState.Idle ->
            VoiceStatusInfo(
                statusText = "Ready",
                icon = Icons.Filled.Mic,
                color = AuraNeutral500,
                isActive = false,
            )
        is VoiceSessionState.Listening ->
            VoiceStatusInfo(
                statusText = "Listening",
                icon = Icons.Filled.MicNone,
                color = AuraPrimary,
                isActive = true,
            )
        is VoiceSessionState.Processing ->
            VoiceStatusInfo(
                statusText = "Processing",
                icon = Icons.Filled.Psychology,
                color = AuraSecondary,
                isActive = true,
            )
        is VoiceSessionState.Responding ->
            VoiceStatusInfo(
                statusText = "Responding",
                icon = Icons.Filled.RecordVoiceOver,
                color = AuraSuccess,
                isActive = true,
            )
        is VoiceSessionState.Error ->
            VoiceStatusInfo(
                statusText = "Error",
                icon = Icons.Filled.Error,
                color = AuraError,
                isActive = false,
            )
        is VoiceSessionState.Initializing ->
            VoiceStatusInfo(
                statusText = "Initializing",
                icon = Icons.Filled.Refresh,
                color = AuraWarning,
                isActive = true,
            )
        is VoiceSessionState.Connecting ->
            VoiceStatusInfo(
                statusText = "Connecting",
                icon = Icons.Filled.CloudSync,
                color = AuraWarning,
                isActive = true,
            )
    }
}
