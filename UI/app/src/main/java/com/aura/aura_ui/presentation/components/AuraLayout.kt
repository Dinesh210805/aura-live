package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.*

/**
 * Professional AURA header with animated gradient background
 */
@Composable
fun AuraHeader(
    modifier: Modifier = Modifier,
    onSettingsClick: (() -> Unit)? = null,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "header_gradient")
    val gradientOffset by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(durationMillis = 3000, easing = EaseInOut),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "gradient_animation",
    )

    Box(
        modifier =
            modifier
                .fillMaxWidth()
                .height(120.dp)
                .background(
                    brush =
                        Brush.linearGradient(
                            colors =
                                listOf(
                                    AuraPrimary.copy(alpha = 0.95f),
                                    AuraSecondary.copy(alpha = 0.85f),
                                    AuraTertiary.copy(alpha = 0.75f),
                                ),
                            start = androidx.compose.ui.geometry.Offset(0f, gradientOffset * 100f),
                            end = androidx.compose.ui.geometry.Offset(gradientOffset * 100f, 100f),
                        ),
                ),
    ) {
        // Background pattern
        Box(
            modifier =
                Modifier
                    .fillMaxSize()
                    .background(
                        brush =
                            Brush.radialGradient(
                                colors =
                                    listOf(
                                        Color.White.copy(alpha = 0.1f),
                                        Color.Transparent,
                                    ),
                                radius = 300f,
                            ),
                    ),
        )

        // Content
        Row(
            modifier =
                Modifier
                    .fillMaxSize()
                    .padding(AuraSpacing.screenPadding),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            // Logo and title section
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(AuraSpacing.md),
            ) {
                // Animated logo
                AuraLogo()

                Column {
                    Text(
                        text = "AURA",
                        style =
                            MaterialTheme.typography.headlineMedium.copy(
                                fontWeight = FontWeight.Bold,
                            ),
                        color = AuraNeutral50,
                    )
                    Text(
                        text = "AI Voice Assistant",
                        style = MaterialTheme.typography.bodyMedium,
                        color = AuraNeutral100.copy(alpha = 0.8f),
                    )
                }
            }

            // Settings button
            onSettingsClick?.let { onClick ->
                AuraIconButton(
                    icon = Icons.Default.Settings,
                    onClick = onClick,
                    backgroundColor = Color.White.copy(alpha = 0.2f),
                    contentColor = AuraNeutral50,
                )
            }
        }
    }
}

/**
 * Animated AURA logo
 */
@Composable
fun AuraLogo(
    modifier: Modifier = Modifier,
    size: androidx.compose.ui.unit.Dp = 48.dp,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "logo_animation")
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(durationMillis = 8000, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "logo_rotation",
    )

    val scale by infiniteTransition.animateFloat(
        initialValue = 0.9f,
        targetValue = 1.1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(durationMillis = 2000, easing = EaseInOut),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "logo_scale",
    )

    Box(
        modifier =
            modifier
                .size(size)
                .clip(RoundedCornerShape(AuraRadius.lg))
                .background(
                    brush =
                        Brush.linearGradient(
                            colors =
                                listOf(
                                    Color.White.copy(alpha = 0.3f),
                                    Color.White.copy(alpha = 0.1f),
                                ),
                        ),
                ),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.Default.RecordVoiceOver,
            contentDescription = "AURA Logo",
            modifier =
                Modifier
                    .size(size * 0.6f)
                    .graphicsLayer {
                        rotationZ = rotation
                        scaleX = scale
                        scaleY = scale
                    },
            tint = AuraNeutral50,
        )
    }
}

/**
 * Professional icon button with custom styling
 */
@Composable
fun AuraIconButton(
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    backgroundColor: Color = MaterialTheme.colorScheme.primaryContainer,
    contentColor: Color = MaterialTheme.colorScheme.onPrimaryContainer,
    size: androidx.compose.ui.unit.Dp = 40.dp,
) {
    IconButton(
        onClick = onClick,
        modifier =
            modifier
                .size(size)
                .clip(RoundedCornerShape(AuraRadius.md))
                .background(backgroundColor),
        enabled = enabled,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = contentColor,
            modifier = Modifier.size(size * 0.5f),
        )
    }
}

/**
 * Professional control panel with action buttons
 */
@Composable
fun AuraControlPanel(
    hasAllPermissions: Boolean,
    isListening: Boolean,
    onRequestPermissions: () -> Unit,
    onStartListening: () -> Unit,
    onStopListening: () -> Unit,
    onTestCommand: () -> Unit,
    onInitializeSession: () -> Unit,
    modifier: Modifier = Modifier,
) {
    AuraCard(
        modifier = modifier,
        title = "Voice Controls",
        subtitle = "Manage AURA voice interactions",
        icon = Icons.Default.ControlCamera,
        cardType = AuraCardType.Primary,
    ) {
        Column(
            verticalArrangement = Arrangement.spacedBy(AuraSpacing.md),
        ) {
            // Primary actions row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(AuraSpacing.md),
            ) {
                if (!hasAllPermissions) {
                    AuraButton(
                        text = "Grant Permissions",
                        onClick = onRequestPermissions,
                        modifier = Modifier.weight(1f),
                        buttonType = AuraButtonType.Warning,
                        icon = Icons.Default.Security,
                    )
                } else {
                    AuraButton(
                        text = "Initialize AURA",
                        onClick = onInitializeSession,
                        modifier = Modifier.weight(1f),
                        buttonType = AuraButtonType.Primary,
                        icon = Icons.Default.PowerSettingsNew,
                    )
                }
            }

            // Voice control actions
            if (hasAllPermissions) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(AuraSpacing.md),
                ) {
                    if (!isListening) {
                        AuraButton(
                            text = "Start Listening",
                            onClick = onStartListening,
                            modifier = Modifier.weight(1f),
                            buttonType = AuraButtonType.Success,
                            icon = Icons.Default.Mic,
                            size = AuraButtonSize.Medium,
                        )
                    } else {
                        AuraButton(
                            text = "Stop Listening",
                            onClick = onStopListening,
                            modifier = Modifier.weight(1f),
                            buttonType = AuraButtonType.Error,
                            icon = Icons.Default.MicOff,
                            size = AuraButtonSize.Medium,
                        )
                    }

                    AuraOutlinedButton(
                        text = "Test",
                        onClick = onTestCommand,
                        modifier = Modifier.weight(1f),
                        icon = Icons.Default.Science,
                        size = AuraButtonSize.Medium,
                    )
                }
            }
        }
    }
}

/**
 * Professional info card with app information
 */
@Composable
fun AuraInfoCard(modifier: Modifier = Modifier) {
    AuraCard(
        modifier = modifier,
        title = "About AURA",
        subtitle = "AI-Powered Voice Assistant",
        icon = Icons.Default.Info,
        cardType = AuraCardType.Gradient,
    ) {
        Column(
            verticalArrangement = Arrangement.spacedBy(AuraSpacing.md),
        ) {
            Text(
                text = "AURA is an advanced AI-powered voice assistant that provides intelligent automation and assistance through natural language interaction.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(AuraSpacing.lg),
            ) {
                AuraFeatureItem(
                    icon = Icons.Default.RecordVoiceOver,
                    title = "Voice Recognition",
                    description = "Advanced speech processing",
                )

                AuraFeatureItem(
                    icon = Icons.Default.Psychology,
                    title = "AI Intelligence",
                    description = "Smart command understanding",
                )

                AuraFeatureItem(
                    icon = Icons.Default.Settings,
                    title = "Device Control",
                    description = "Seamless automation",
                )
            }
        }
    }
}

/**
 * Feature item for info card
 */
@Composable
private fun RowScope.AuraFeatureItem(
    icon: ImageVector,
    title: String,
    description: String,
) {
    Column(
        modifier = Modifier.weight(1f),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(AuraSpacing.xs),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = AuraPrimary,
            modifier = Modifier.size(24.dp),
        )

        Text(
            text = title,
            style =
                MaterialTheme.typography.labelMedium.copy(
                    fontWeight = FontWeight.SemiBold,
                ),
            color = MaterialTheme.colorScheme.onSurface,
        )

        Text(
            text = description,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
