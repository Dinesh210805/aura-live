package com.aura.aura_ui.presentation.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.conversation.ConversationMessage
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.presentation.components.SoundWaveVisualization
import com.aura.aura_ui.presentation.utils.AuraHapticType
import com.aura.aura_ui.presentation.utils.rememberHapticFeedback
import com.aura.aura_ui.ui.theme.*
import kotlin.math.roundToInt

// ============================================================================
// FLOATING ASSISTANT BUBBLE
// A compact, draggable bubble that can be placed anywhere on screen
// Similar to Facebook Messenger chat heads or Google Assistant mini mode
// ============================================================================

private object BubbleColors {
    val Background = Color(0xFF1A1A2E)
    val Surface = Color(0xFF16213E)
    val Primary = Color(0xFF6366F1)
    val PrimaryGlow = Color(0xFF818CF8)
    val TextPrimary = Color.White
    val TextSecondary = Color(0xFFB0B0B0)
    val Listening = Color(0xFF10B981)
    val Processing = Color(0xFFF59E0B)
    val Error = Color(0xFFEF4444)
}

/**
 * State for the floating bubble
 */
data class FloatingBubbleState(
    val isExpanded: Boolean = false,
    val isListening: Boolean = false,
    val isProcessing: Boolean = false,
    val lastMessage: String = "",
    val lastResponse: String = "",
    val partialTranscript: String = "",
    val phase: ConversationPhase = ConversationPhase.IDLE,
    val audioAmplitude: Float = 0f,
)

/**
 * Callbacks for the floating bubble
 */
data class FloatingBubbleCallbacks(
    val onTap: () -> Unit = {},
    val onMicClick: () -> Unit = {},
    val onExpand: () -> Unit = {},
    val onCollapse: () -> Unit = {},
    val onDismiss: () -> Unit = {},
)

/**
 * Floating Assistant Bubble Composable
 * A draggable, expandable bubble for quick voice interactions
 */
@Composable
fun FloatingAssistantBubble(
    state: FloatingBubbleState,
    callbacks: FloatingBubbleCallbacks,
    modifier: Modifier = Modifier,
) {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val screenWidth = with(density) { configuration.screenWidthDp.dp.toPx() }
    val screenHeight = with(density) { configuration.screenHeightDp.dp.toPx() }
    
    // Position state for dragging
    var offsetX by remember { mutableFloatStateOf(screenWidth - 200f) }
    var offsetY by remember { mutableFloatStateOf(screenHeight * 0.7f) }
    
    // Animation for expansion
    val expandedSize by animateDpAsState(
        targetValue = if (state.isExpanded) 320.dp else 64.dp,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessLow
        ),
        label = "bubble_size"
    )
    
    // Bubble must stay collapsed while the AI is actively working.
    // THINKING / RESPONDING / any isProcessing state = no user interaction needed.
    val forceCollapsed = state.isProcessing ||
        state.phase == ConversationPhase.THINKING ||
        state.phase == ConversationPhase.RESPONDING

    Box(
        modifier = modifier
            .offset { IntOffset(offsetX.roundToInt(), offsetY.roundToInt()) }
            .pointerInput(Unit) {
                detectDragGestures { change, dragAmount ->
                    change.consume()
                    offsetX = (offsetX + dragAmount.x).coerceIn(0f, screenWidth - 200f)
                    offsetY = (offsetY + dragAmount.y).coerceIn(0f, screenHeight - 300f)
                }
            }
    ) {
        AnimatedContent(
            targetState = state.isExpanded && !forceCollapsed,
            transitionSpec = {
                fadeIn(animationSpec = tween(200)) togetherWith
                        fadeOut(animationSpec = tween(200))
            },
            label = "bubble_content"
        ) { expanded ->
            if (expanded) {
                ExpandedBubble(
                    state = state,
                    callbacks = callbacks
                )
            } else {
                CollapsedBubble(
                    state = state,
                    onClick = callbacks.onExpand
                )
            }
        }
    }
}

/**
 * Collapsed bubble - just a floating orb
 */
@Composable
private fun CollapsedBubble(
    state: FloatingBubbleState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "bubble_pulse")
    
    // Pulse animation based on state
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (state.isListening || state.isProcessing) 1.15f else 1.05f,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = if (state.isListening) 600 else 2000,
                easing = EaseInOutSine
            ),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )
    
    // Glow animation
    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 0.8f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow"
    )
    
    val stateColor = when {
        state.isListening -> BubbleColors.Listening
        state.isProcessing -> BubbleColors.Processing
        state.phase == ConversationPhase.ERROR -> BubbleColors.Error
        else -> BubbleColors.Primary
    }
    
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // Orb
        Box(
            modifier = Modifier
                .size(64.dp)
                .graphicsLayer {
                    scaleX = pulseScale
                    scaleY = pulseScale
                }
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            // Outer glow
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .graphicsLayer { alpha = glowAlpha }
                    .shadow(16.dp, CircleShape)
                    .clip(CircleShape)
                    .background(
                        Brush.radialGradient(
                            colors = listOf(
                                stateColor.copy(alpha = 0.6f),
                                stateColor.copy(alpha = 0.1f),
                                Color.Transparent
                            )
                        )
                    )
            )

            // Main bubble
            Surface(
                modifier = Modifier.size(56.dp),
                shape = CircleShape,
                color = BubbleColors.Background,
                shadowElevation = 8.dp,
                tonalElevation = 4.dp
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            Brush.radialGradient(
                                colors = listOf(
                                    stateColor.copy(alpha = 0.2f),
                                    BubbleColors.Background
                                )
                            )
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = when {
                            // GraphicEq = sound-bar waveform — no mic icon alongside text
                            state.isListening -> Icons.Default.GraphicEq
                            // VolumeUp makes it clear AURA is currently speaking
                            state.phase == ConversationPhase.RESPONDING -> Icons.Default.VolumeUp
                            // AutoAwesome covers THINKING, EXECUTING, IDLE
                            else -> Icons.Default.AutoAwesome
                        },
                        contentDescription = "AURA",
                        tint = stateColor,
                        modifier = Modifier.size(28.dp)
                    )
                }
            }
        }

        // Phase alert pill — compact label shown beneath the orb, no expansion needed
        LiveAlertPill(state = state, stateColor = stateColor)
    }
}

/**
 * Expanded bubble with chat and controls
 */
@Composable
private fun ExpandedBubble(
    state: FloatingBubbleState,
    callbacks: FloatingBubbleCallbacks,
    modifier: Modifier = Modifier,
) {
    val hapticFeedback = rememberHapticFeedback()
    
    Surface(
        modifier = modifier.width(300.dp),
        shape = RoundedCornerShape(24.dp),
        color = BubbleColors.Background,
        shadowElevation = 16.dp,
        tonalElevation = 8.dp
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header with collapse button
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(32.dp)
                            .clip(CircleShape)
                            .background(
                                Brush.linearGradient(
                                    listOf(AuraPrimary, AuraSecondary)
                                )
                            ),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.AutoAwesome,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    
                    Text(
                        text = "AURA",
                        style = MaterialTheme.typography.titleMedium.copy(
                            fontWeight = FontWeight.SemiBold
                        ),
                        color = BubbleColors.TextPrimary
                    )
                }
                
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    IconButton(
                        onClick = callbacks.onCollapse,
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Remove,
                            contentDescription = "Minimize",
                            tint = BubbleColors.TextSecondary,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    
                    IconButton(
                        onClick = callbacks.onDismiss,
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = BubbleColors.TextSecondary,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
            }
            
            // Chat content area
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 80.dp, max = 200.dp),
                shape = RoundedCornerShape(16.dp),
                color = BubbleColors.Surface
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Last user message
                    if (state.lastMessage.isNotEmpty()) {
                        BubbleMessage(
                            text = state.lastMessage,
                            isUser = true
                        )
                    }
                    
                    // Partial transcript
                    if (state.partialTranscript.isNotEmpty()) {
                        BubbleMessage(
                            text = state.partialTranscript,
                            isUser = true,
                            isPartial = true
                        )
                    }
                    
                    // Processing indicator
                    if (state.isProcessing) {
                        BubbleProcessingIndicator()
                    }
                    
                    // Last response
                    if (state.lastResponse.isNotEmpty() && !state.isProcessing) {
                        BubbleMessage(
                            text = state.lastResponse,
                            isUser = false
                        )
                    }
                    
                    // Empty state
                    if (state.lastMessage.isEmpty() && state.partialTranscript.isEmpty() && !state.isProcessing) {
                        Text(
                            text = "Tap mic to speak",
                            style = MaterialTheme.typography.bodyMedium,
                            color = BubbleColors.TextSecondary,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
            
            // Waveform when listening
            AnimatedVisibility(
                visible = state.isListening,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                SoundWaveVisualization(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(32.dp),
                    isActive = true,
                    amplitude = state.audioAmplitude,
                    waveColor = BubbleColors.Listening
                )
            }
            
            // Mic button
            Box(
                modifier = Modifier.fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                val stateColor = when {
                    state.isListening -> BubbleColors.Listening
                    state.isProcessing -> BubbleColors.Processing
                    else -> BubbleColors.Primary
                }
                
                Button(
                    onClick = {
                        if (state.isListening) {
                            hapticFeedback(AuraHapticType.RECORDING_STOP)
                        } else {
                            hapticFeedback(AuraHapticType.RECORDING_START)
                        }
                        callbacks.onMicClick()
                    },
                    modifier = Modifier.size(56.dp),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = stateColor
                    ),
                    elevation = ButtonDefaults.buttonElevation(
                        defaultElevation = 4.dp,
                        pressedElevation = 8.dp
                    )
                ) {
                    Icon(
                        imageVector = if (state.isListening) Icons.Default.Stop else Icons.Default.Mic,
                        contentDescription = if (state.isListening) "Stop" else "Speak",
                        tint = Color.White,
                        modifier = Modifier.size(28.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun BubbleMessage(
    text: String,
    isUser: Boolean,
    isPartial: Boolean = false,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall.copy(
                fontWeight = if (isPartial) FontWeight.Normal else FontWeight.Medium
            ),
            color = if (isPartial) {
                BubbleColors.TextSecondary
            } else if (isUser) {
                BubbleColors.Primary
            } else {
                BubbleColors.TextPrimary
            },
            maxLines = 3,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
private fun BubbleProcessingIndicator(
    modifier: Modifier = Modifier,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "processing")
    
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        repeat(3) { index ->
            val alpha by infiniteTransition.animateFloat(
                initialValue = 0.3f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(500),
                    repeatMode = RepeatMode.Reverse,
                    initialStartOffset = StartOffset(index * 100)
                ),
                label = "dot_$index"
            )
            
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .graphicsLayer { this.alpha = alpha }
                    .clip(CircleShape)
                    .background(BubbleColors.Processing)
            )
        }
        
        Spacer(modifier = Modifier.width(8.dp))
        
        Text(
            text = "Thinking...",
            style = MaterialTheme.typography.labelSmall,
            color = BubbleColors.Processing
        )
    }
}

// ============================================================================
// LIVE ALERT PILL
// Compact phase-label shown beneath the collapsed orb.
// Defines the verb for each phase — no expansion required.
// ============================================================================

/**
 * Phase alert verbs:
 *   LISTENING  → "Listening" (or partial transcript if available)
 *   THINKING   → "Thinking..."
 *   EXECUTING  → "Executing..."   (isProcessing outside Gemini Live)
 *   RESPONDING → "Speaking"
 *   ERROR      → "Error"
 *   IDLE       → (hidden)
 */
@Composable
private fun LiveAlertPill(
    state: FloatingBubbleState,
    stateColor: Color,
    modifier: Modifier = Modifier,
) {
    val alertText = when {
        state.phase == ConversationPhase.LISTENING && state.partialTranscript.isNotBlank() ->
            state.partialTranscript
                .take(22)
                .let { if (state.partialTranscript.length > 22) "$it…" else it }
        state.phase == ConversationPhase.LISTENING -> "Listening"
        state.isProcessing -> "Executing..."
        state.phase == ConversationPhase.THINKING -> "Thinking..."
        state.phase == ConversationPhase.RESPONDING -> "Speaking"
        state.phase == ConversationPhase.ERROR -> "Error"
        else -> ""
    }

    AnimatedVisibility(
        visible = alertText.isNotBlank(),
        enter = fadeIn(animationSpec = tween(200)) + expandVertically(),
        exit = fadeOut(animationSpec = tween(150)) + shrinkVertically(),
        modifier = modifier,
    ) {
        Text(
            text = alertText,
            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Medium),
            color = stateColor,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(stateColor.copy(alpha = 0.15f))
                .padding(horizontal = 8.dp, vertical = 3.dp)
        )
    }
}

// ============================================================================
// PREVIEWS
// ============================================================================

@Preview
@Composable
private fun CollapsedBubblePreview() {
    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.DarkGray),
            contentAlignment = Alignment.Center
        ) {
            CollapsedBubble(
                state = FloatingBubbleState(),
                onClick = {}
            )
        }
    }
}

@Preview
@Composable
private fun CollapsedBubbleListeningPreview() {
    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.DarkGray),
            contentAlignment = Alignment.Center
        ) {
            CollapsedBubble(
                state = FloatingBubbleState(isListening = true),
                onClick = {}
            )
        }
    }
}

@Preview
@Composable
private fun ExpandedBubblePreview() {
    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.DarkGray)
                .padding(16.dp),
            contentAlignment = Alignment.Center
        ) {
            ExpandedBubble(
                state = FloatingBubbleState(
                    isExpanded = true,
                    lastMessage = "What's the weather?",
                    lastResponse = "It's currently 72°F and sunny in your area."
                ),
                callbacks = FloatingBubbleCallbacks()
            )
        }
    }
}

@Preview
@Composable
private fun ExpandedBubbleListeningPreview() {
    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.DarkGray)
                .padding(16.dp),
            contentAlignment = Alignment.Center
        ) {
            ExpandedBubble(
                state = FloatingBubbleState(
                    isExpanded = true,
                    isListening = true,
                    partialTranscript = "Open the...",
                    audioAmplitude = 0.6f
                ),
                callbacks = FloatingBubbleCallbacks()
            )
        }
    }
}
