package com.aura.aura_ui.presentation.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.sin

/**
 * Gemini-style animated thinking loader
 */
@Composable
fun GeminiStyleLoader(
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.primary,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "gemini_loader")

    val animatedProgress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(2000, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "progress",
    )

    Box(
        modifier =
            modifier
                .size(120.dp)
                .padding(16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val width = size.width
            val height = size.height
            val centerY = height / 2f
            val numberOfDots = 5
            val dotRadius = 8f
            val spacing = width / (numberOfDots + 1)

            for (i in 0 until numberOfDots) {
                val x = spacing * (i + 1)

                // Wave effect with phase shift for each dot
                val phase = animatedProgress * 2 * PI - (i * 0.3)
                val amplitude = 20f
                val y = centerY + (amplitude * sin(phase).toFloat())

                // Pulsing alpha
                val alphaPhase = (animatedProgress + i * 0.15f) % 1f
                val alpha = 0.3f + (0.7f * sin(alphaPhase * PI).toFloat())

                // Pulsing size
                val sizePhase = (animatedProgress + i * 0.2f) % 1f
                val radius = dotRadius * (0.7f + 0.6f * sin(sizePhase * PI).toFloat())

                drawCircle(
                    color = color.copy(alpha = alpha),
                    radius = radius,
                    center = Offset(x, y),
                )
            }
        }
    }
}

/**
 * Three-dot pulsing loader (simpler version)
 */
@Composable
fun ThreeDotLoader(
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.primary,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "three_dot")

    Row(
        modifier = modifier.height(40.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(3) { index ->
            val animatedScale by infiniteTransition.animateFloat(
                initialValue = 0.5f,
                targetValue = 1.2f,
                animationSpec =
                    infiniteRepeatable(
                        animation =
                            tween(
                                durationMillis = 600,
                                delayMillis = index * 150,
                                easing = FastOutSlowInEasing,
                            ),
                        repeatMode = RepeatMode.Reverse,
                    ),
                label = "dot_$index",
            )

            Canvas(modifier = Modifier.size(12.dp)) {
                drawCircle(
                    color = color,
                    radius = size.minDimension / 2 * animatedScale,
                )
            }
        }
    }
}

/**
 * Circular progress indicator with gradient
 */
@Composable
fun CircularThinkingLoader(
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.primary,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "circular")

    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(1200, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "rotation",
    )

    Canvas(
        modifier = modifier.size(48.dp),
    ) {
        val strokeWidth = 6f
        val radius = (size.minDimension - strokeWidth) / 2
        val centerX = size.width / 2
        val centerY = size.height / 2

        // Background circle (faint)
        drawCircle(
            color = color.copy(alpha = 0.2f),
            radius = radius,
            center = Offset(centerX, centerY),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = strokeWidth),
        )

        // Rotating arc
        val sweepAngle = 280f
        drawArc(
            color = color,
            startAngle = rotation,
            sweepAngle = sweepAngle,
            useCenter = false,
            topLeft = Offset(centerX - radius, centerY - radius),
            size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
            style =
                androidx.compose.ui.graphics.drawscope.Stroke(
                    width = strokeWidth,
                    cap = androidx.compose.ui.graphics.StrokeCap.Round,
                ),
        )
    }
}
