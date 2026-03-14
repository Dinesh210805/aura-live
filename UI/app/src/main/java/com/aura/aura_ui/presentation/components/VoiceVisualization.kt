package com.aura.aura_ui.presentation.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.ui.theme.*
import kotlin.math.PI
import kotlin.math.sin

/**
 * Professional voice waveform visualization component
 * Displays animated bars that respond to audio amplitude
 */
@Composable
fun VoiceWaveform(
    modifier: Modifier = Modifier,
    amplitude: Float = 0.5f,
    isActive: Boolean = false,
    barCount: Int = 5,
    primaryColor: Color = MaterialTheme.colorScheme.primary,
    secondaryColor: Color = MaterialTheme.colorScheme.secondary,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "waveform")
    
    // Create animated values for each bar with different phases
    val animatedAmplitudes = List(barCount) { index ->
        infiniteTransition.animateFloat(
            initialValue = 0.3f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(
                    durationMillis = 600 + (index * 100),
                    easing = EaseInOutSine
                ),
                repeatMode = RepeatMode.Reverse
            ),
            label = "bar_$index"
        )
    }

    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        animatedAmplitudes.forEachIndexed { index, animatedValue ->
            val barHeight = if (isActive) {
                (20 + (animatedValue.value * amplitude * 30)).dp
            } else {
                8.dp
            }
            
            val barColor = if (isActive) {
                Brush.verticalGradient(
                    colors = listOf(primaryColor, secondaryColor)
                )
            } else {
                Brush.verticalGradient(
                    colors = listOf(
                        primaryColor.copy(alpha = 0.3f),
                        secondaryColor.copy(alpha = 0.3f)
                    )
                )
            }
            
            Box(
                modifier = Modifier
                    .width(6.dp)
                    .height(barHeight)
                    .clip(RoundedCornerShape(3.dp))
                    .background(barColor)
            )
        }
    }
}

/**
 * Circular voice visualization orb for the main mic button
 * Provides immersive visual feedback during voice interaction
 */
@Composable
fun VoiceOrb(
    modifier: Modifier = Modifier,
    phase: ConversationPhase = ConversationPhase.IDLE,
    amplitude: Float = 0.5f,
) {
    val color = when (phase) {
        ConversationPhase.IDLE -> AuraIdle
        ConversationPhase.LISTENING -> AuraListening
        ConversationPhase.THINKING -> AuraProcessing
        ConversationPhase.RESPONDING -> AuraResponding
        ConversationPhase.ERROR -> AuraError
    }
    
    val infiniteTransition = rememberInfiniteTransition(label = "orb")
    
    // Pulse animation for active states
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (phase != ConversationPhase.IDLE) 1.15f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )
    
    // Rotation for processing state
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(3000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rotation"
    )
    
    // Breathing glow animation
    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.2f,
        targetValue = 0.6f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow"
    )

    Canvas(modifier = modifier.size(200.dp)) {
        val centerX = size.width / 2
        val centerY = size.height / 2
        val maxRadius = size.minDimension / 2
        
        // Outer glow rings
        for (i in 3 downTo 1) {
            val ringRadius = maxRadius * (0.5f + i * 0.15f) * pulseScale
            val ringAlpha = glowAlpha * (1f - i * 0.2f)
            
            drawCircle(
                color = color.copy(alpha = ringAlpha),
                radius = ringRadius,
                center = Offset(centerX, centerY)
            )
        }
        
        // Main orb with gradient
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    color.copy(alpha = 0.8f),
                    color.copy(alpha = 0.4f),
                    Color.Transparent
                ),
                center = Offset(centerX, centerY),
                radius = maxRadius * 0.6f * pulseScale
            ),
            radius = maxRadius * 0.5f * pulseScale,
            center = Offset(centerX, centerY)
        )
        
        // Inner bright core
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color.White.copy(alpha = 0.9f),
                    color.copy(alpha = 0.6f),
                    Color.Transparent
                ),
                center = Offset(centerX, centerY),
                radius = maxRadius * 0.25f
            ),
            radius = maxRadius * 0.2f,
            center = Offset(centerX, centerY)
        )
        
        // Rotating arc for processing state
        if (phase == ConversationPhase.THINKING) {
            val arcRadius = maxRadius * 0.7f
            drawArc(
                color = color,
                startAngle = rotation,
                sweepAngle = 90f,
                useCenter = false,
                topLeft = Offset(centerX - arcRadius, centerY - arcRadius),
                size = Size(arcRadius * 2, arcRadius * 2),
                style = Stroke(width = 4.dp.toPx(), cap = StrokeCap.Round)
            )
        }
        
        // Amplitude-reactive wave pattern for listening
        if (phase == ConversationPhase.LISTENING && amplitude > 0.1f) {
            val waveRadius = maxRadius * 0.65f + (amplitude * 20)
            drawCircle(
                color = color.copy(alpha = amplitude * 0.5f),
                radius = waveRadius,
                center = Offset(centerX, centerY),
                style = Stroke(width = 2.dp.toPx())
            )
        }
    }
}

/**
 * Soundwave visualization showing audio activity
 */
@Composable
fun SoundWaveVisualization(
    modifier: Modifier = Modifier,
    isActive: Boolean = false,
    amplitude: Float = 0.5f,
    waveColor: Color = MaterialTheme.colorScheme.primary,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "soundwave")
    
    val phase by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 2 * PI.toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(1500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "wave_phase"
    )

    Canvas(modifier = modifier.fillMaxWidth().height(60.dp)) {
        if (!isActive) {
            // Draw flat line when inactive
            drawLine(
                color = waveColor.copy(alpha = 0.3f),
                start = Offset(0f, size.height / 2),
                end = Offset(size.width, size.height / 2),
                strokeWidth = 2.dp.toPx(),
                cap = StrokeCap.Round
            )
            return@Canvas
        }
        
        val path = Path()
        val waveHeight = size.height * 0.4f * amplitude
        val centerY = size.height / 2
        
        path.moveTo(0f, centerY)
        
        for (x in 0..size.width.toInt() step 4) {
            val normalizedX = x / size.width
            val y = centerY + sin(normalizedX * 4 * PI + phase) * waveHeight * 
                    (0.5f + 0.5f * sin(normalizedX * 2 * PI + phase * 0.5f))
            path.lineTo(x.toFloat(), y.toFloat())
        }
        
        drawPath(
            path = path,
            color = waveColor,
            style = Stroke(
                width = 3.dp.toPx(),
                cap = StrokeCap.Round
            )
        )
        
        // Secondary wave with offset
        val path2 = Path()
        path2.moveTo(0f, centerY)
        
        for (x in 0..size.width.toInt() step 4) {
            val normalizedX = x / size.width
            val y = centerY + sin(normalizedX * 3 * PI + phase + PI / 4) * waveHeight * 0.6f
            path2.lineTo(x.toFloat(), y.toFloat())
        }
        
        drawPath(
            path = path2,
            color = waveColor.copy(alpha = 0.5f),
            style = Stroke(
                width = 2.dp.toPx(),
                cap = StrokeCap.Round
            )
        )
    }
}

/**
 * Compact audio level indicator bars
 */
@Composable
fun AudioLevelIndicator(
    modifier: Modifier = Modifier,
    level: Float = 0f, // 0-1 range
    barCount: Int = 8,
    activeColor: Color = AuraListening,
    inactiveColor: Color = AuraNeutral300,
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        repeat(barCount) { index ->
            val threshold = (index + 1f) / barCount
            val isActive = level >= threshold
            val barHeight = (8 + index * 4).dp
            
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .height(barHeight)
                    .clip(RoundedCornerShape(2.dp))
                    .background(
                        if (isActive) activeColor else inactiveColor.copy(alpha = 0.3f)
                    )
            )
        }
    }
}
