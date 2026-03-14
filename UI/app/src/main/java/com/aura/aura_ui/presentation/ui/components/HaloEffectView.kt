package com.aura.aura_ui.presentation.ui.components

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import com.aura.aura_ui.domain.model.VoiceSessionState
import com.aura.aura_ui.presentation.ui.theme.AuraColors
import com.aura.aura_ui.presentation.ui.theme.AuraDimensions
import kotlin.math.*

/**
 * Custom view for halo effect animation around the mic button
 */
class HaloEffectView
    @JvmOverloads
    constructor(
        context: Context,
        attrs: AttributeSet? = null,
        defStyleAttr: Int = 0,
    ) : View(context, attrs, defStyleAttr) {
        private val innerPaint =
            Paint().apply {
                isAntiAlias = true
                style = Paint.Style.FILL
            }

        private val outerPaint =
            Paint().apply {
                isAntiAlias = true
                style = Paint.Style.FILL
            }

        private var amplitude: Float = 0f
        private var sessionState: VoiceSessionState = VoiceSessionState.Idle
        private var animationPhase: Float = 0f

        private val innerRadius = AuraDimensions.HaloInnerRadius.value * resources.displayMetrics.density
        private val outerRadius = AuraDimensions.HaloOuterRadius.value * resources.displayMetrics.density

        fun updateAmplitude(amplitude: Float) {
            this.amplitude = amplitude.coerceIn(0f, 1f)
            invalidate()
        }

        fun updateSessionState(state: VoiceSessionState) {
            sessionState = state
            updatePaintColors()
            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)

            val centerX = width / 2f
            val centerY = height / 2f

            when (sessionState) {
                is VoiceSessionState.Idle -> drawIdleHalo(canvas, centerX, centerY)
                is VoiceSessionState.Listening -> drawListeningHalo(canvas, centerX, centerY)
                is VoiceSessionState.Processing -> drawProcessingHalo(canvas, centerX, centerY)
                is VoiceSessionState.Responding -> drawRespondingHalo(canvas, centerX, centerY)
                is VoiceSessionState.Error -> drawErrorHalo(canvas, centerX, centerY)
                is VoiceSessionState.Initializing -> drawProcessingHalo(canvas, centerX, centerY)
                is VoiceSessionState.Connecting -> drawIdleHalo(canvas, centerX, centerY)
            }

            // Update animation phase for continuous animations
            animationPhase = (animationPhase + 0.05f) % (2 * PI.toFloat())

            // Continue animation for active states
            if (sessionState !is VoiceSessionState.Idle) {
                postInvalidateDelayed(16) // ~60 FPS
            }
        }

        private fun drawIdleHalo(
            canvas: Canvas,
            centerX: Float,
            centerY: Float,
        ) {
            // Subtle breathing effect
            val breathingScale = 1f + (sin(animationPhase) * 0.05f)
            val radius = innerRadius * breathingScale

            canvas.drawCircle(centerX, centerY, radius, innerPaint)

            // Continue breathing animation
            postInvalidateDelayed(33) // ~30 FPS for idle
        }

        private fun drawListeningHalo(
            canvas: Canvas,
            centerX: Float,
            centerY: Float,
        ) {
            // Amplitude-driven pulse
            val pulseScale = 1f + (amplitude * 0.4f)
            val innerRadiusScaled = innerRadius * pulseScale
            val outerRadiusScaled = outerRadius * pulseScale

            // Draw outer halo with gradient
            val gradient =
                RadialGradient(
                    centerX,
                    centerY,
                    outerRadiusScaled,
                    intArrayOf(
                        Color.TRANSPARENT,
                        AuraColors.SuccessGreen.value.toInt() and 0x80FFFFFF.toInt(),
                        Color.TRANSPARENT,
                    ),
                    floatArrayOf(0f, 0.5f, 1f),
                    Shader.TileMode.CLAMP,
                )
            outerPaint.shader = gradient
            canvas.drawCircle(centerX, centerY, outerRadiusScaled, outerPaint)

            // Draw inner core
            canvas.drawCircle(centerX, centerY, innerRadiusScaled, innerPaint)
        }

        private fun drawProcessingHalo(
            canvas: Canvas,
            centerX: Float,
            centerY: Float,
        ) {
            // Rotating arc animation
            val sweepAngle = 120f
            val startAngle = animationPhase * (180f / PI.toFloat()) % 360f

            val rect =
                RectF(
                    centerX - innerRadius,
                    centerY - innerRadius,
                    centerX + innerRadius,
                    centerY + innerRadius,
                )

            canvas.drawArc(rect, startAngle, sweepAngle, false, innerPaint)
        }

        private fun drawRespondingHalo(
            canvas: Canvas,
            centerX: Float,
            centerY: Float,
        ) {
            // Expanding rings synchronized with TTS
            val expansionScale = 1f + (amplitude * 0.6f)
            val radius = innerRadius * expansionScale

            // Multiple concentric rings for rich effect
            for (i in 1..3) {
                val ringRadius = radius * (1f + i * 0.2f)
                val alpha = (255 * (1f - i * 0.2f)).toInt()

                val paint =
                    Paint(innerPaint).apply {
                        this.alpha = alpha
                    }

                canvas.drawCircle(centerX, centerY, ringRadius, paint)
            }
        }

        private fun drawErrorHalo(
            canvas: Canvas,
            centerX: Float,
            centerY: Float,
        ) {
            // Rapid pulse effect
            val pulseIntensity = abs(sin(animationPhase * 3f)) // 3x faster pulse
            val radius = innerRadius * (1f + pulseIntensity * 0.3f)

            canvas.drawCircle(centerX, centerY, radius, innerPaint)
        }

        private fun updatePaintColors() {
            val baseColor =
                when (sessionState) {
                    is VoiceSessionState.Idle -> AuraColors.PrimaryBlue
                    is VoiceSessionState.Listening -> AuraColors.SuccessGreen
                    is VoiceSessionState.Processing -> AuraColors.WarningOrange
                    is VoiceSessionState.Responding -> AuraColors.AccentPurple
                    is VoiceSessionState.Error -> AuraColors.ErrorRed
                    is VoiceSessionState.Initializing -> AuraColors.WarningOrange
                    is VoiceSessionState.Connecting -> AuraColors.PrimaryBlue
                }

            innerPaint.color = baseColor.value.toInt()
            outerPaint.color = baseColor.copy(alpha = 0.5f).value.toInt()
        }
    }

/**
 * Convert Compose Color to Android Color int with proper alpha handling
 */
private val androidx.compose.ui.graphics.Color.value: ULong
    get() = this.value
