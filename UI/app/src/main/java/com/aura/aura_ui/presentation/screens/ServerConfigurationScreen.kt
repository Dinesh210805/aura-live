package com.aura.aura_ui.presentation.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aura.aura_ui.data.manager.ServerConfigManager
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.presentation.viewmodel.ServerConfigViewModel
import com.aura.aura_ui.ui.theme.AppleColors
import kotlinx.coroutines.launch

/**
 * Server configuration screen styled to match the Apple-inspired Settings screen.
 * Properly uses ThemeManager for light/dark theme support.
 */
@Composable
fun ServerConfigurationScreen(
    onNavigateBack: () -> Unit,
    viewModel: ServerConfigViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val coroutineScope = rememberCoroutineScope()
    val scrollState = rememberScrollState()
    
    // Theme support - same pattern as SettingsScreen
    val systemDark = isSystemInDarkTheme()
    val themeMode by ThemeManager.themeMode.collectAsState()
    val isDark = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> systemDark
    }
    
    // Colors based on theme
    val backgroundColor = if (isDark) AppleColors.Dark.Background else AppleColors.Light.Background
    val groupBackgroundColor = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val separatorColor = if (isDark) AppleColors.Dark.Separator else AppleColors.Light.Separator
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(backgroundColor)
            .systemBarsPadding()
    ) {
        // Navigation Bar - same style as SettingsScreen
        ServerConfigNavigationBar(
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
            
            // Server URL Section
            ServerSettingsGroup(
                title = "SERVER",
                isDark = isDark,
            ) {
                // Server URL Input
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        ServerSettingIcon(
                            icon = Icons.Default.Dns,
                            tint = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo,
                            isDark = isDark,
                        )
                        Text(
                            text = "Server Address",
                            style = MaterialTheme.typography.bodyLarge,
                            color = labelPrimary,
                        )
                    }
                    
                    OutlinedTextField(
                        value = uiState.serverUrl,
                        onValueChange = viewModel::setServerUrl,
                        placeholder = { 
                            Text(
                                "107.78.51.4:8000",
                                color = if (isDark) AppleColors.LabelDark.Tertiary else AppleColors.LabelLight.Tertiary
                            ) 
                        },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        isError = uiState.validationError != null,
                        shape = RoundedCornerShape(12.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = accentColor,
                            unfocusedBorderColor = separatorColor,
                            cursorColor = accentColor,
                            focusedTextColor = labelPrimary,
                            unfocusedTextColor = labelPrimary,
                            focusedContainerColor = if (isDark) AppleColors.Dark.Fill else AppleColors.Light.Fill,
                            unfocusedContainerColor = if (isDark) AppleColors.Dark.Fill else AppleColors.Light.Fill,
                        ),
                    )
                    
                    // Helper text or error
                    Text(
                        text = uiState.validationError ?: "Format: host:port or https://host",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (uiState.validationError != null) {
                            if (isDark) AppleColors.RedDark else AppleColors.Red
                        } else {
                            labelSecondary
                        },
                    )
                }
            }
            
            // Actions Section
            ServerSettingsGroup(
                title = "ACTIONS",
                isDark = isDark,
            ) {
                // Test Connection
                ServerActionRow(
                    icon = Icons.Default.NetworkCheck,
                    iconTint = if (isDark) AppleColors.TealDark else AppleColors.Teal,
                    title = "Test Connection",
                    subtitle = if (uiState.isTestingConnection) "Testing..." else "Verify server is reachable",
                    isDark = isDark,
                    isLoading = uiState.isTestingConnection,
                    onClick = {
                        coroutineScope.launch { viewModel.testConnection() }
                    },
                )
                
                ServerSettingsDivider(isDark)
                
                // Save Settings
                ServerActionRow(
                    icon = Icons.Default.Save,
                    iconTint = if (isDark) AppleColors.GreenDark else AppleColors.Green,
                    title = "Save Settings",
                    subtitle = "Apply server configuration",
                    isDark = isDark,
                    enabled = uiState.serverUrl.isNotBlank() && uiState.validationError == null,
                    onClick = {
                        coroutineScope.launch { viewModel.saveSettings() }
                    },
                )
            }
            
            // Connection Test Result
            uiState.connectionTestResult?.let { result ->
                ServerSettingsGroup(
                    title = "STATUS",
                    isDark = isDark,
                ) {
                    ConnectionResultRow(
                        result = result,
                        isDark = isDark,
                    )
                }
            }
            
            // Current Configuration Section
            if (uiState.savedServerUrl != null) {
                ServerSettingsGroup(
                    title = "CURRENT CONFIGURATION",
                    isDark = isDark,
                ) {
                    ServerInfoRow(
                        title = "Saved Server",
                        value = uiState.savedServerUrl ?: "Not configured",
                        isDark = isDark,
                    )
                    
                    uiState.lastConnectionTest?.let { latency ->
                        ServerSettingsDivider(isDark)
                        ServerInfoRow(
                            title = "Last Test",
                            value = "${latency}ms response",
                            isDark = isDark,
                        )
                    }
                }
            }
            
            // Help Section
            ServerSettingsGroup(
                title = "HELP",
                isDark = isDark,
            ) {
                ServerInfoRow(
                    title = "How to connect",
                    value = "Enter your AURA backend server IP address and port. The server should be running on the same network.",
                    isDark = isDark,
                    isMultiLine = true,
                )
            }
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

// ============================================================================
// NAVIGATION BAR
// ============================================================================

@Composable
private fun ServerConfigNavigationBar(
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
                text = "Settings",
                color = accentColor,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        
        Spacer(modifier = Modifier.weight(1f))
        
        Text(
            text = "Server",
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

// ============================================================================
// SETTINGS COMPONENTS
// ============================================================================

@Composable
private fun ServerSettingsGroup(
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
private fun ServerSettingIcon(
    icon: ImageVector,
    tint: Color,
    isDark: Boolean,
) {
    Box(
        modifier = Modifier
            .size(32.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(tint.copy(alpha = 0.15f)),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(18.dp)
        )
    }
}

@Composable
private fun ServerActionRow(
    icon: ImageVector,
    iconTint: Color,
    title: String,
    subtitle: String,
    isDark: Boolean,
    enabled: Boolean = true,
    isLoading: Boolean = false,
    onClick: () -> Unit,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val labelTertiary = if (isDark) AppleColors.LabelDark.Tertiary else AppleColors.LabelLight.Tertiary
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled && !isLoading, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        ServerSettingIcon(
            icon = icon,
            tint = if (enabled) iconTint else labelTertiary,
            isDark = isDark,
        )
        
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                color = if (enabled) labelPrimary else labelTertiary,
            )
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = labelSecondary,
            )
        }
        
        if (isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.size(20.dp),
                strokeWidth = 2.dp,
                color = iconTint,
            )
        } else {
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = null,
                tint = labelTertiary,
                modifier = Modifier.size(20.dp)
            )
        }
    }
}

@Composable
private fun ServerInfoRow(
    title: String,
    value: String,
    isDark: Boolean,
    isMultiLine: Boolean = false,
) {
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    
    if (isMultiLine) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
                color = labelPrimary,
            )
            Text(
                text = value,
                style = MaterialTheme.typography.bodyMedium,
                color = labelSecondary,
            )
        }
    } else {
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
}

@Composable
private fun ConnectionResultRow(
    result: ServerConfigManager.ConnectionTestResult,
    isDark: Boolean,
) {
    val statusColor = if (result.success) {
        if (isDark) AppleColors.GreenDark else AppleColors.Green
    } else {
        if (isDark) AppleColors.RedDark else AppleColors.Red
    }
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Status icon
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(statusColor.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = if (result.success) Icons.Default.CheckCircle else Icons.Default.Error,
                contentDescription = null,
                tint = statusColor,
                modifier = Modifier.size(18.dp)
            )
        }
        
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = if (result.success) "Connection successful" else "Connection failed",
                style = MaterialTheme.typography.bodyLarge,
                color = labelPrimary,
            )
            Text(
                text = result.message,
                style = MaterialTheme.typography.bodySmall,
                color = labelSecondary,
            )
        }
        
        // Status indicator dot
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(statusColor)
        )
    }
}

@Composable
private fun ServerSettingsDivider(isDark: Boolean) {
    val separatorColor = if (isDark) AppleColors.Dark.Separator else AppleColors.Light.Separator
    
    HorizontalDivider(
        modifier = Modifier.padding(start = 60.dp),
        thickness = 0.5.dp,
        color = separatorColor,
    )
}
