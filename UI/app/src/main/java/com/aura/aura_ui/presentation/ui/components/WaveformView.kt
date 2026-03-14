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
 * Custom view for waveform visualization during voice capture
 */
class WaveformView
    @JvmOverloads
    constructor(
        context: Context,
        attrs: AttributeSet? = null,
        defStyleAttr: Int = 0,
    ) : View(context, attrs, defStyleAttr) {
        private val paint =
            Paint().apply {
                isAntiAlias = true
                strokeCap = Paint.Cap.ROUND
                strokeWidth = AuraDimensions.WaveformBarWidth.value * resources.displayMetrics.density
            }

        private var amplitudes = FloatArray(12) { 0f }
        private var targetAmplitudes = FloatArray(12) { 0f }
        private var sessionState: VoiceSessionState = VoiceSessionState.Idle

        private val minHeight = AuraDimensions.WaveformBarMinHeight.value * resources.displayMetrics.density
        private val maxHeight = AuraDimensions.WaveformBarMaxHeight.value * resources.displayMetrics.density

        fun updateAmplitude(amplitude: Float) {
            // Distribute amplitude across bars with some randomness for visual appeal
            for (i in targetAmplitudes.indices) {
                val randomFactor = 0.7f + (Math.random().toFloat() * 0.3f)
                targetAmplitudes[i] = amplitude * randomFactor
            }
            invalidate()
        }

        fun updateSessionState(state: VoiceSessionState) {
            sessionState = state
            paint.color = getStateColor(state)
            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)

            val centerX = width / 2f
            val centerY = height / 2f
            val radius = min(width, height) / 3f

            // Smooth animation towards target amplitudes
            var hasChanges = false
            for (i in amplitudes.indices) {
                val diff = targetAmplitudes[i] - amplitudes[i]
                if (abs(diff) > 0.01f) {
                    amplitudes[i] += diff * 0.3f // Smoothing factor
                    hasChanges = true
                }
            }

            // Draw waveform bars in circular pattern
            for (i in amplitudes.indices) {
                val angle = (i * 30f) * (PI / 180f).toFloat() // 30 degrees between bars
                val barHeight = minHeight + (amplitudes[i] * (maxHeight - minHeight))

                val startX = centerX + cos(angle) * radius
                val startY = centerY + sin(angle) * radius
                val endX = centerX + cos(angle) * (radius + barHeight)
                val endY = centerY + sin(angle) * (radius + barHeight)

                canvas.drawLine(startX, startY, endX, endY, paint)
            }

            // Continue animation if values are still changing
            if (hasChanges) {
                postInvalidateDelayed(16) // ~60 FPS
            }
        }

        private fun getStateColor(state: VoiceSessionState): Int {
            return when (state) {
                is VoiceSessionState.Idle -> AuraColors.PrimaryBlue.value.toInt()
                is VoiceSessionState.Listening -> AuraColors.SuccessGreen.value.toInt()
                is VoiceSessionState.Processing -> AuraColors.WarningOrange.value.toInt()
                is VoiceSessionState.Responding -> AuraColors.AccentPurple.value.toInt()
                is VoiceSessionState.Error -> AuraColors.ErrorRed.value.toInt()
                is VoiceSessionState.Initializing -> AuraColors.WarningOrange.value.toInt()
                is VoiceSessionState.Connecting -> AuraColors.PrimaryBlue.value.toInt()
            }
        }
    }

/**
 * Convert Compose Color to Android Color int
 */
private val androidx.compose.ui.graphics.Color.value: ULong
    get() = this.value
