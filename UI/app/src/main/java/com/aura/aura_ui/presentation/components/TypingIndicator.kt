package com.aura.aura_ui.presentation.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.ui.theme.*
import kotlinx.coroutines.delay

/**
 * Professional typing indicator component
 * Shows animated dots to indicate AI is composing a response
 */
@Composable
fun TypingIndicator(
    modifier: Modifier = Modifier,
    dotColor: Color = MaterialTheme.colorScheme.primary,
    dotSize: Int = 8,
    dotCount: Int = 3,
    showLabel: Boolean = true,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "typing")
    
    // Create staggered animations for each dot
    val dotAnimations = List(dotCount) { index ->
        infiniteTransition.animateFloat(
            initialValue = 0f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = keyframes {
                    durationMillis = 1200
                    0f at 0
                    1f at 300
                    0f at 600
                    0f at 1200
                },
                repeatMode = RepeatMode.Restart,
                initialStartOffset = StartOffset(index * 150)
            ),
            label = "dot_$index"
        )
    }

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(
            topStart = 16.dp,
            topEnd = 16.dp,
            bottomStart = 4.dp,
            bottomEnd = 16.dp
        ),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.Start,
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            if (showLabel) {
                Text(
                    text = "AURA is typing",
                    style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = FontWeight.Medium,
                        letterSpacing = 0.5.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
            
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                dotAnimations.forEach { animation ->
                    Box(
                        modifier = Modifier
                            .size(dotSize.dp)
                            .scale(0.6f + animation.value * 0.4f)
                            .alpha(0.4f + animation.value * 0.6f)
                            .clip(CircleShape)
                            .background(dotColor)
                    )
                }
            }
        }
    }
}

/**
 * Compact typing indicator without label
 */
@Composable
fun CompactTypingIndicator(
    modifier: Modifier = Modifier,
    dotColor: Color = MaterialTheme.colorScheme.primary,
) {
    TypingIndicator(
        modifier = modifier,
        dotColor = dotColor,
        dotSize = 6,
        showLabel = false
    )
}

/**
 * Thinking indicator with modern glass morphism design and smooth animations
 */
@Composable
fun ThinkingIndicator(
    modifier: Modifier = Modifier,
    text: String = "Processing...",
    color: Color = AuraProcessing,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "thinking")
    
    // Pulsing glow animation
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 0.8f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )
    
    // Animated dots
    val dotProgress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 3f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "dots"
    )

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.7f),
        tonalElevation = 2.dp,
        shadowElevation = 4.dp,
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Animated pulsing orb with glow effect
            Box(
                contentAlignment = Alignment.Center
            ) {
                // Outer glow ring
                Box(
                    modifier = Modifier
                        .size(20.dp)
                        .alpha(pulseAlpha * 0.4f)
                        .scale(1f + pulseAlpha * 0.3f)
                        .clip(CircleShape)
                        .background(color.copy(alpha = 0.3f))
                )
                // Inner solid circle
                Box(
                    modifier = Modifier
                        .size(14.dp)
                        .alpha(0.6f + pulseAlpha * 0.4f)
                        .clip(CircleShape)
                        .background(color)
                )
            }
            
            // Animated text with dots - use monospace-style spacing to prevent shift
            val dots = ".".repeat(dotProgress.toInt().coerceIn(0, 3))
            val paddedDots = dots.padEnd(3, ' ')
            Text(
                text = text.removeSuffix("...") + paddedDots,
                style = MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.Medium,
                    letterSpacing = 0.3.sp
                ),
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.85f)
            )
        }
    }
}

/**
 * Status indicator showing connection/processing states
 */
@Composable
fun StatusIndicator(
    modifier: Modifier = Modifier,
    status: IndicatorStatus = IndicatorStatus.IDLE,
    label: String? = null,
) {
    val color = when (status) {
        IndicatorStatus.IDLE -> AuraIdle
        IndicatorStatus.CONNECTING -> AuraConnecting
        IndicatorStatus.ACTIVE -> AuraListening
        IndicatorStatus.PROCESSING -> AuraProcessing
        IndicatorStatus.SUCCESS -> AuraSuccess
        IndicatorStatus.ERROR -> AuraError
    }
    
    val infiniteTransition = rememberInfiniteTransition(label = "status")
    
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (status == IndicatorStatus.PROCESSING || status == IndicatorStatus.CONNECTING) 1.3f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(600, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "scale"
    )

    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .scale(pulseScale)
                .clip(CircleShape)
                .background(color)
        )
        
        label?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.labelMedium,
                color = color
            )
        }
    }
}

enum class IndicatorStatus {
    IDLE,
    CONNECTING,
    ACTIVE,
    PROCESSING,
    SUCCESS,
    ERROR
}

/**
 * Streaming text animation that reveals text character by character
 */
@Composable
fun StreamingText(
    text: String,
    modifier: Modifier = Modifier,
    delayPerChar: Long = 30L,
    onComplete: () -> Unit = {},
) {
    var displayedText by remember(text) { mutableStateOf("") }
    
    LaunchedEffect(text) {
        displayedText = ""
        text.forEachIndexed { index, _ ->
            delay(delayPerChar)
            displayedText = text.substring(0, index + 1)
        }
        onComplete()
    }
    
    Text(
        text = displayedText,
        modifier = modifier,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurface
    )
}
