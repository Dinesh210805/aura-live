package com.aura.aura_ui.presentation.screens

import android.content.Intent
import android.provider.Settings
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.conversation.ConversationMessage
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.presentation.components.*
import com.aura.aura_ui.presentation.utils.AuraHapticType
import com.aura.aura_ui.presentation.utils.HapticUtils
import com.aura.aura_ui.presentation.utils.rememberHapticFeedback

/**
 * Home screen UI state holder
 */
data class HomeScreenState(
    val hasAllPermissions: Boolean = false,
    val isListening: Boolean = false,
    val serverStatus: String = "Unknown",
    val lastResponse: String = "No response yet",
    val isProcessingAudio: Boolean = false,
    val partialTranscript: String = "",
    val finalTranscript: String = "",
    val audioAmplitude: Float = 0f, // Audio amplitude for voice visualization
    val currentServerUrl: String = "",
    val isRefreshing: Boolean = false,
    // Conversation mode state
    val conversationPhase: ConversationPhase = ConversationPhase.IDLE,
    val conversationMessages: List<ConversationMessage> = emptyList(),
    val isConversationMode: Boolean = false,
)

/**
 * Home screen callbacks
 */
data class HomeScreenCallbacks(
    val onNavigateToSettings: () -> Unit,
    val onRequestPermissions: () -> Unit,
    val onCheckServerHealth: () -> Unit,
    val onSendTestCommand: () -> Unit,
    val onToggleListening: () -> Unit,
    val onRefreshConnection: () -> Unit,
    val onOpenNetworkSettings: () -> Unit,
    val onStartConversation: () -> Unit,
    // New unified conversation callbacks
    val onToggleConversationMode: () -> Unit = {},
    val onEndConversation: () -> Unit = {},
    val onStartOverlay: () -> Unit = {},
)

/**
 * Main home screen composable
 */
@Composable
fun HomeScreen(
    state: HomeScreenState,
    callbacks: HomeScreenCallbacks,
    modifier: Modifier = Modifier,
) {
    val scrollState = rememberScrollState()

    val pulseAnimation = rememberInfiniteTransition(label = "pulse")
    val pulseScale by pulseAnimation.animateFloat(
        initialValue = 0.95f,
        targetValue = 1.1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(durationMillis = 900, easing = CubicBezierEasing(0.25f, 0.1f, 0.25f, 1f)),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "pulseScale",
    )

    val listeningAnimation = rememberInfiniteTransition(label = "listening")
    val listeningAlpha by listeningAnimation.animateFloat(
        initialValue = 0.35f,
        targetValue = 0.85f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(durationMillis = 720, easing = LinearOutSlowInEasing),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "listeningAlpha",
    )

    Box(
        modifier =
            modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
    ) {
        HomeScreenBackdrop()

        Column(
            modifier =
                Modifier
                    .fillMaxSize()
                    .verticalScroll(scrollState)
                    .padding(top = 48.dp, start = 24.dp, end = 24.dp, bottom = 32.dp)
                    .widthIn(max = 720.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            HomeScreenHeader(
                onNavigateToSettings = callbacks.onNavigateToSettings,
            )

            VoiceControlPanel(
                state = state,
                pulseScale = pulseScale,
                listeningAlpha = listeningAlpha,
                onToggleListening = callbacks.onToggleListening,
                onStartConversation = callbacks.onStartConversation,
            )

            // Show conversation transcript when in conversation mode
            if (state.isConversationMode && state.conversationMessages.isNotEmpty()) {
                ConversationTranscriptPanel(
                    messages = state.conversationMessages,
                    partialTranscript = state.partialTranscript,
                    isAITyping = state.conversationPhase == ConversationPhase.THINKING || 
                                 state.conversationPhase == ConversationPhase.RESPONDING
                )
            } else {
                // Show regular transcription/response panels
                if (state.partialTranscript.isNotEmpty() || state.finalTranscript.isNotEmpty()) {
                    TranscriptionPanel(
                        partialTranscript = state.partialTranscript,
                        finalTranscript = state.finalTranscript,
                        isProcessing = state.isProcessingAudio
                    )
                }

                if (state.lastResponse != "No response yet") {
                    ResponsePanel(
                        response = state.lastResponse,
                    )
                }
            }

            ControlsPanel(
                state = state,
                callbacks = callbacks,
            )

            if (!state.serverStatus.contains("Connected")) {
                ServerGuidancePanel(
                    serverStatus = state.serverStatus,
                    currentServerUrl = state.currentServerUrl,
                    isRefreshing = state.isRefreshing,
                    onRetryConnection = callbacks.onRefreshConnection,
                    onOpenNetworkSettings = callbacks.onOpenNetworkSettings,
                )
            }

            Spacer(modifier = Modifier.height(48.dp))
        }
    }
}

@Composable
private fun HomeScreenHeader(onNavigateToSettings: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                text = "AURA",
                style =
                    MaterialTheme.typography.displayMedium.copy(
                        fontWeight = FontWeight.ExtraLight,
                        letterSpacing = 8.sp,
                    ),
                color = MaterialTheme.colorScheme.onBackground,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = "Voice-Driven Android Assistant",
                style =
                    MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = FontWeight.Light,
                        letterSpacing = 1.2.sp,
                    ),
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Surface(
            modifier = Modifier.size(48.dp),
            shape = RoundedCornerShape(14.dp),
            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.35f),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.2f)),
        ) {
            IconButton(onClick = onNavigateToSettings) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = "Settings",
                    tint = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.size(22.dp),
                )
            }
        }
    }
}

@Composable
private fun VoiceControlPanel(
    state: HomeScreenState,
    pulseScale: Float,
    listeningAlpha: Float,
    onToggleListening: () -> Unit,
    onStartConversation: () -> Unit,
) {
    val view = LocalView.current
    val hapticFeedback = rememberHapticFeedback()
    
    // Determine current conversation phase for visualization
    val currentPhase = when {
        state.isProcessingAudio -> ConversationPhase.THINKING
        state.isListening -> ConversationPhase.LISTENING
        state.conversationPhase == ConversationPhase.RESPONDING -> ConversationPhase.RESPONDING
        else -> ConversationPhase.IDLE
    }
    
    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
        contentPadding = PaddingValues(28.dp),
    ) {
        // Status label with indicator
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            StatusIndicator(
                status = when {
                    state.isProcessingAudio -> IndicatorStatus.PROCESSING
                    state.isListening -> IndicatorStatus.ACTIVE
                    state.serverStatus.contains("Connected") -> IndicatorStatus.SUCCESS
                    else -> IndicatorStatus.IDLE
                }
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = when {
                    state.isProcessingAudio -> "PROCESSING"
                    state.isListening -> "LISTENING"
                    else -> "READY"
                },
                style = MaterialTheme.typography.labelLarge.copy(
                    fontWeight = FontWeight.Medium,
                    letterSpacing = 2.sp,
                ),
                color = when {
                    state.isProcessingAudio -> MaterialTheme.colorScheme.tertiary
                    state.isListening -> MaterialTheme.colorScheme.error
                    else -> MaterialTheme.colorScheme.primary
                },
            )
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp),
            contentAlignment = Alignment.Center,
        ) {
            // Voice Orb visualization behind button
            VoiceOrb(
                modifier = Modifier.size(200.dp),
                phase = currentPhase,
                amplitude = state.audioAmplitude
            )
            
            // Main mic button
            Button(
                onClick = {
                    // Trigger haptic feedback
                    if (state.isListening) {
                        hapticFeedback(AuraHapticType.RECORDING_STOP)
                    } else {
                        hapticFeedback(AuraHapticType.RECORDING_START)
                    }
                    onToggleListening()
                },
                shape = CircleShape,
                modifier = Modifier.size(100.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (state.isListening) {
                        MaterialTheme.colorScheme.error.copy(alpha = 0.9f)
                    } else {
                        MaterialTheme.colorScheme.primary
                    },
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ),
                elevation = ButtonDefaults.buttonElevation(
                    defaultElevation = 6.dp,
                    pressedElevation = 12.dp,
                ),
                border = BorderStroke(
                    2.dp, 
                    MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.15f)
                ),
            ) {
                Icon(
                    imageVector = if (state.isListening) Icons.Default.MicOff else Icons.Default.Mic,
                    contentDescription = if (state.isListening) "Stop Listening" else "Start Listening",
                    modifier = Modifier.size(36.dp),
                )
            }
        }
        
        // Sound wave visualization when listening
        AnimatedVisibility(
            visible = state.isListening,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically()
        ) {
            SoundWaveVisualization(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                isActive = state.isListening,
                amplitude = state.audioAmplitude,
                waveColor = MaterialTheme.colorScheme.primary
            )
        }

        Text(
            text =
                when {
                    state.isConversationMode && state.conversationPhase == ConversationPhase.LISTENING -> "Listening... (auto-stop enabled)"
                    state.isConversationMode && state.conversationPhase == ConversationPhase.THINKING -> "Processing your request..."
                    state.isConversationMode && state.conversationPhase == ConversationPhase.RESPONDING -> "AURA is responding..."
                    state.isConversationMode -> "Tap to speak"
                    state.isProcessingAudio -> "Analyzing your command"
                    state.isListening -> "Speak your command"
                    else -> "Press to activate voice input"
                },
            style =
                MaterialTheme.typography.bodySmall.copy(
                    fontWeight = FontWeight.Light,
                    letterSpacing = 0.5.sp,
                ),
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            StatusChip(
                icon = Icons.Default.CheckCircle,
                label = "Permissions",
                value = if (state.hasAllPermissions) "Active" else "Required",
                tone = if (state.hasAllPermissions) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                modifier = Modifier.weight(1f),
            )
            StatusChip(
                icon = Icons.Default.CloudDone,
                label = "Backend",
                value = if (state.serverStatus.contains("Connected")) "Online" else "Offline",
                tone =
                    if (state.serverStatus.contains(
                            "Connected",
                        )
                    ) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.tertiary
                    },
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun ConversationTranscriptPanel(
    messages: List<ConversationMessage>,
    partialTranscript: String,
    isAITyping: Boolean = false,
) {
    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Conversation",
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurface,
            )
            
            // Message count badge
            if (messages.isNotEmpty()) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = "${messages.size}",
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }
        }

        if (messages.isEmpty() && partialTranscript.isEmpty()) {
            // Empty state with suggestions
            EmptyConversationState()
        } else {
            // Enhanced conversation list with avatars and timestamps
            EnhancedConversationList(
                messages = messages.takeLast(5),
                isAITyping = isAITyping,
                partialTranscript = partialTranscript
            )
        }
    }
}

@Composable
private fun TranscriptionPanel(
    partialTranscript: String,
    finalTranscript: String,
    isProcessing: Boolean = false,
) {
    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Live Transcription",
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurface,
            )
            
            if (isProcessing) {
                ThinkingIndicator(
                    text = "Transcribing",
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
        
        if (partialTranscript.isNotEmpty()) {
            // Animated partial transcript
            AnimatedVisibility(
                visible = partialTranscript.isNotEmpty(),
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = partialTranscript,
                        modifier = Modifier.padding(12.dp),
                        style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
        
        if (finalTranscript.isNotEmpty()) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant
            ) {
                Text(
                    text = finalTranscript,
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ResponsePanel(response: String) {
    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Latest Response",
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurface,
            )
            
            // AURA badge
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = MaterialTheme.colorScheme.secondary.copy(alpha = 0.1f)
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.SmartToy,
                        contentDescription = null,
                        modifier = Modifier.size(12.dp),
                        tint = MaterialTheme.colorScheme.secondary
                    )
                    Text(
                        text = "AURA",
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                        color = MaterialTheme.colorScheme.secondary
                    )
                }
            }
        }
        
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        ) {
            Text(
                text = response,
                modifier = Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 24.sp),
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun ControlsPanel(
    state: HomeScreenState,
    callbacks: HomeScreenCallbacks,
) {
    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Controls",
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
            color = MaterialTheme.colorScheme.onSurface,
        )

        if (!state.hasAllPermissions) {
            EnhancedButton(
                onClick = callbacks.onRequestPermissions,
                icon = Icons.Default.Security,
                text = "Grant Permissions",
                accentColor = MaterialTheme.colorScheme.error,
            )
        }

        EnhancedButton(
            onClick = callbacks.onCheckServerHealth,
            icon = Icons.Default.NetworkCheck,
            text = "Test Server Connection",
            accentColor = MaterialTheme.colorScheme.primary,
        )

        EnhancedButton(
            onClick = callbacks.onStartOverlay,
            icon = Icons.Default.BubbleChart,
            text = "Start Floating Assistant",
            accentColor = MaterialTheme.colorScheme.secondary,
            enabled = state.hasAllPermissions,
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    text = "Conversation Mode",
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    text = if (state.isConversationMode) "Continuous conversation enabled" else "Single-command mode",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                )
            }
            Switch(
                checked = state.isConversationMode,
                onCheckedChange = { callbacks.onToggleConversationMode() },
                enabled = !state.isListening,
            )
        }

        EnhancedButton(
            onClick = callbacks.onSendTestCommand,
            icon = Icons.Default.PlayArrow,
            text = "Send Test Command",
            enabled = state.hasAllPermissions && state.serverStatus.contains("Connected"),
            isOutlined = true,
            accentColor = MaterialTheme.colorScheme.primary,
        )
    }
}

@Composable
private fun ServerGuidancePanel(
    serverStatus: String,
    currentServerUrl: String,
    isRefreshing: Boolean,
    onRetryConnection: () -> Unit,
    onOpenNetworkSettings: () -> Unit,
) {
    val context = LocalContext.current

    GlassPanel(
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Server Guidance",
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
            color = MaterialTheme.colorScheme.error,
        )
        Text(
            text = "Connection Status: $serverStatus",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = "Current Server: $currentServerUrl",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        )
        Text(
            text = "Ensure the backend is reachable on port 8000 and the device shares the same network.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedButton(
                onClick = onRetryConnection,
                enabled = !isRefreshing,
                modifier = Modifier.weight(1f),
            ) {
                if (isRefreshing) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                } else {
                    Icon(Icons.Default.Refresh, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Text("Retry")
            }

            OutlinedButton(
                onClick = {
                    val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
                    context.startActivity(intent)
                },
                modifier = Modifier.weight(1f),
            ) {
                Icon(Icons.Default.Settings, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text("Network")
            }
        }
    }
}

@Composable
private fun HomeScreenBackdrop(modifier: Modifier = Modifier) {
    val primaryColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.25f)
    val secondaryColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.18f)
    val tertiaryColor = MaterialTheme.colorScheme.tertiary.copy(alpha = 0.16f)

    Box(
        modifier =
            modifier
                .fillMaxSize(),
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val width = size.width
            val height = size.height
            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                primaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.6f,
                center = Offset(width * 0.25f, height * 0.2f),
            )
            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                secondaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.5f,
                center = Offset(width * 0.8f, height * 0.35f),
            )
            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                tertiaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.55f,
                center = Offset(width * 0.5f, height * 0.85f),
            )
        }
    }
}

@Composable
private fun GlassPanel(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(28.dp),
    contentPadding: PaddingValues = PaddingValues(24.dp),
    glowColor: Color = MaterialTheme.colorScheme.onBackground,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(
        modifier = modifier,
        shape = shape,
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.55f),
        border = BorderStroke(
            width = 0.5.dp, 
            brush = Brush.linearGradient(
                colors = listOf(
                    MaterialTheme.colorScheme.onSurface.copy(alpha = 0.15f),
                    MaterialTheme.colorScheme.onSurface.copy(alpha = 0.04f),
                    MaterialTheme.colorScheme.onSurface.copy(alpha = 0.10f),
                )
            )
        ),
        shadowElevation = 12.dp,
        tonalElevation = 1.dp,
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    brush = Brush.verticalGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.05f),
                            Color.Transparent,
                            Color.Black.copy(alpha = 0.02f),
                        )
                    )
                )
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(contentPadding),
                verticalArrangement = Arrangement.spacedBy(16.dp),
                content = content,
            )
        }
    }
}

@Composable
private fun StatusChip(
    icon: ImageVector,
    label: String,
    value: String,
    tone: Color,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.3f),
        border = BorderStroke(1.dp, tone.copy(alpha = 0.3f)),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = tone,
                    modifier = Modifier.size(18.dp),
                )
                Text(
                    text = label,
                    style =
                        MaterialTheme.typography.labelMedium.copy(
                            fontWeight = FontWeight.Medium,
                            letterSpacing = 0.6.sp,
                        ),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                )
            }
            Text(
                text = value,
                style =
                    MaterialTheme.typography.labelLarge.copy(
                        fontWeight = FontWeight.SemiBold,
                    ),
                color = tone,
                modifier = Modifier.padding(start = 26.dp),
            )
        }
    }
}

@Composable
private fun EnhancedButton(
    onClick: () -> Unit,
    icon: ImageVector,
    text: String,
    enabled: Boolean = true,
    isOutlined: Boolean = false,
    accentColor: Color = MaterialTheme.colorScheme.primary,
) {
    val hapticFeedback = rememberHapticFeedback()
    
    val baseModifier = Modifier
        .fillMaxWidth()
        .height(56.dp)

    val wrappedOnClick: () -> Unit = {
        hapticFeedback(AuraHapticType.MEDIUM)
        onClick()
    }

    if (isOutlined) {
        OutlinedButton(
            onClick = wrappedOnClick,
            modifier = baseModifier,
            enabled = enabled,
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(
                width = 1.5.dp, 
                color = if (enabled) accentColor.copy(alpha = 0.6f) else accentColor.copy(alpha = 0.2f)
            ),
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = accentColor,
                disabledContentColor = accentColor.copy(alpha = 0.4f)
            ),
        ) {
            Icon(
                imageVector = icon, 
                contentDescription = null,
                modifier = Modifier.size(20.dp)
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = text, 
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 0.5.sp
            )
        }
    } else {
        Button(
            onClick = wrappedOnClick,
            modifier = baseModifier,
            enabled = enabled,
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = accentColor,
                contentColor = MaterialTheme.colorScheme.onPrimary,
                disabledContainerColor = accentColor.copy(alpha = 0.3f),
                disabledContentColor = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.6f)
            ),
            elevation = ButtonDefaults.buttonElevation(
                defaultElevation = 4.dp,
                pressedElevation = 8.dp,
                disabledElevation = 0.dp
            ),
        ) {
            Icon(
                imageVector = icon, 
                contentDescription = null,
                modifier = Modifier.size(20.dp)
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = text, 
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 0.5.sp
            )
        }
    }
}
