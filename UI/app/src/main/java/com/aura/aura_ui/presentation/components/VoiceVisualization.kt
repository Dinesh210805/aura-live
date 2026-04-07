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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.ui.theme.*
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.sin
import kotlinx.coroutines.delay

/** Amplitude below this value is treated as silence — no waveform motion. */
private const val SILENCE_THRESHOLD = 0.04f

/**
 * Bar-based waveform that reacts ONLY to actual voice input.
 *
 * A single [animateFloatAsState] tracks amplitude, dropping to 0 when
 * [isActive] is false or [amplitude] stays below [SILENCE_THRESHOLD].
 * Bar heights are derived via a gaussian envelope so the centre bars
 * are tallest, giving a natural "voice hill" shape.
 */
@Composable
fun VoiceWaveform(
    modifier: Modifier = Modifier,
    amplitude: Float = 0f,
    isActive: Boolean = false,
    barCount: Int = 5,
    primaryColor: Color = MaterialTheme.colorScheme.primary,
    secondaryColor: Color = MaterialTheme.colorScheme.secondary,
) {
    val smoothAmplitude by animateFloatAsState(
        targetValue = if (isActive && amplitude > SILENCE_THRESHOLD) amplitude.coerceIn(0f, 1f) else 0f,
        animationSpec = spring(dampingRatio = 0.6f, stiffness = Spring.StiffnessMediumLow),
        label = "waveform_amp",
    )

    val isSpeaking = isActive && smoothAmplitude > SILENCE_THRESHOLD / 2f

    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(barCount) { index ->
            val centre = (barCount - 1) / 2f
            val dist = if (centre > 0f) abs(index - centre) / centre else 0f
            val gaussian = exp(-dist * dist * 1.5).toFloat()
            val heightDp = (6f + smoothAmplitude * 44f * gaussian).coerceAtLeast(6f)

            Box(
                modifier = Modifier
                    .width(6.dp)
                    .height(heightDp.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(
                        if (isSpeaking) {
                            Brush.verticalGradient(listOf(primaryColor, secondaryColor))
                        } else {
                            Brush.verticalGradient(
                                listOf(primaryColor.copy(alpha = 0.3f), secondaryColor.copy(alpha = 0.3f)),
                            )
                        },
                    ),
            )
        }
    }
}

/**
 * Circular voice orb providing phase-based ambient feedback.
 * Pulse / glow / rotation are intentional ambient animations, not silence bugs.
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

    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (phase != ConversationPhase.IDLE) 1.15f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulse",
    )

    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(3000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "rotation",
    )

    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.2f,
        targetValue = 0.6f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "glow",
    )

    Canvas(modifier = modifier.size(200.dp)) {
        val cx = size.width / 2
        val cy = size.height / 2
        val maxR = size.minDimension / 2

        for (i in 3 downTo 1) {
            drawCircle(
                color = color.copy(alpha = glowAlpha * (1f - i * 0.2f)),
                radius = maxR * (0.5f + i * 0.15f) * pulseScale,
                center = Offset(cx, cy),
            )
        }

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(color.copy(alpha = 0.8f), color.copy(alpha = 0.4f), Color.Transparent),
                center = Offset(cx, cy),
                radius = maxR * 0.6f * pulseScale,
            ),
            radius = maxR * 0.5f * pulseScale,
            center = Offset(cx, cy),
        )

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color.White.copy(alpha = 0.9f), color.copy(alpha = 0.6f), Color.Transparent),
                center = Offset(cx, cy),
                radius = maxR * 0.25f,
            ),
            radius = maxR * 0.2f,
            center = Offset(cx, cy),
        )

        if (phase == ConversationPhase.THINKING) {
            val arcR = maxR * 0.7f
            drawArc(
                color = color,
                startAngle = rotation,
                sweepAngle = 90f,
                useCenter = false,
                topLeft = Offset(cx - arcR, cy - arcR),
                size = Size(arcR * 2, arcR * 2),
                style = Stroke(width = 4.dp.toPx(), cap = StrokeCap.Round),
            )
        }

        if (phase == ConversationPhase.LISTENING && amplitude > 0.1f) {
            drawCircle(
                color = color.copy(alpha = amplitude * 0.5f),
                radius = maxR * 0.65f + amplitude * 20,
                center = Offset(cx, cy),
                style = Stroke(width = 2.dp.toPx()),
            )
        }
    }
}

/**
 * Sinusoidal soundwave visualization.
 *
 * **Bug fix:** the travelling-wave [phase] advances ONLY when [isActive] is
 * true AND [amplitude] exceeds [SILENCE_THRESHOLD].  Previously the phase
 * used `infiniteRepeatable` which ran unconditionally, making the wave drift
 * even during silence.
 *
 * Two mechanisms together enforce true silence behaviour:
 * 1. [smoothAmplitude] collapses to 0 via [animateFloatAsState] → wave height → 0.
 * 2. The `LaunchedEffect` loop skips phase advancement below threshold → wave freezes.
 */
@Composable
fun SoundWaveVisualization(
    modifier: Modifier = Modifier,
    isActive: Boolean = false,
    amplitude: Float = 0f,
    waveColor: Color = MaterialTheme.colorScheme.primary,
) {
    val smoothAmplitude by animateFloatAsState(
        targetValue = if (isActive && amplitude > SILENCE_THRESHOLD) amplitude.coerceIn(0f, 1f) else 0f,
        animationSpec = tween(durationMillis = 180),
        label = "smooth_amp",
    )

    var phase by remember { mutableStateOf(0f) }
    val latestIsActive = rememberUpdatedState(isActive)
    val latestAmplitude = rememberUpdatedState(amplitude)

    LaunchedEffect(Unit) {
        while (true) {
            if (latestIsActive.value && latestAmplitude.value > SILENCE_THRESHOLD) {
                phase = (phase + 0.08f) % (2f * PI.toFloat())
            }
            delay(16L) // ~60 fps
        }
    }

    Canvas(modifier = modifier.fillMaxWidth().height(60.dp)) {
        val amp = smoothAmplitude

        if (amp < 0.01f) {
            drawLine(
                color = waveColor.copy(alpha = 0.15f),
                start = Offset(0f, size.height / 2),
                end = Offset(size.width, size.height / 2),
                strokeWidth = 1.5.dp.toPx(),
                cap = StrokeCap.Round,
            )
            return@Canvas
        }

        val waveHeight = size.height * 0.42f * amp
        val cy = size.height / 2f

        val path = Path()
        path.moveTo(0f, cy)
        for (x in 0..size.width.toInt() step 4) {
            val nx = x / size.width
            val y = cy + sin(nx * 4f * PI + phase).toFloat() * waveHeight *
                (0.5f + 0.5f * sin(nx * 2f * PI + phase * 0.5f).toFloat())
            path.lineTo(x.toFloat(), y)
        }
        drawPath(path, waveColor, style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round))

        val path2 = Path()
        path2.moveTo(0f, cy)
        for (x in 0..size.width.toInt() step 4) {
            val nx = x / size.width
            val y = cy + sin(nx * 3f * PI + phase + PI.toFloat() / 4f).toFloat() * waveHeight * 0.55f
            path2.lineTo(x.toFloat(), y)
        }
        drawPath(path2, waveColor.copy(alpha = 0.45f), style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round))
    }
}

/**
 * Compact audio level indicator bars.
 */
@Composable
fun AudioLevelIndicator(
    modifier: Modifier = Modifier,
    level: Float = 0f,
    barCount: Int = 8,
    activeColor: Color = AuraListening,
    inactiveColor: Color = AuraNeutral300,
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom,
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
                    .background(if (isActive) activeColor else inactiveColor.copy(alpha = 0.3f)),
            )
        }
    }
}
