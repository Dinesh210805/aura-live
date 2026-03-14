package com.aura.aura_ui.presentation.overlay

import android.content.Context
import android.graphics.*
import android.view.Gravity
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.FrameLayout
import android.widget.TextView
import com.aura.aura_ui.R
import kotlin.math.*

/**
 * Simple native Android view for expanded panel (no Compose)
 */
class EnhancedExpandedPanel(
    private val context: Context,
    private val onDismiss: () -> Unit,
    private val onStop: () -> Unit,
    private val onSettings: () -> Unit,
) {
    private var panelView: View? = null
    private var currentState: OverlayState = OverlayState.Idle
    private var userText: String = ""
    private var assistantText: String = ""

    private var stateTextView: TextView? = null
    private var userTextView: TextView? = null
    private var assistantTextView: TextView? = null
    private var waveformView: SiriWaveformNativeView? = null

    fun createView(): View {
        val density = context.resources.displayMetrics.density
        val cardWidth = (340 * density).toInt()
        val cardHeight = (200 * density).toInt()

        val container =
            FrameLayout(context).apply {
                layoutParams = FrameLayout.LayoutParams(cardWidth, cardHeight)
                setBackgroundResource(android.R.color.transparent)
            }

        // Glass card background
        val card =
            object : View(context) {
                private val paint =
                    Paint(Paint.ANTI_ALIAS_FLAG).apply {
                        color = Color.parseColor("#DCFFFFFF")
                        style = Paint.Style.FILL
                    }

                override fun onDraw(canvas: Canvas) {
                    val rect = RectF(0f, 0f, width.toFloat(), height.toFloat())
                    canvas.drawRoundRect(rect, 32 * density, 32 * density, paint)
                }
            }.apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                    )
            }
        container.addView(card)

        // Content layout
        val contentLayout =
            FrameLayout(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                    )
                setPadding(
                    (16 * density).toInt(),
                    (16 * density).toInt(),
                    (16 * density).toInt(),
                    (16 * density).toInt(),
                )
            }
        container.addView(contentLayout)

        // Waveform view
        waveformView =
            SiriWaveformNativeView(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        (80 * density).toInt(),
                    ).apply {
                        gravity = Gravity.CENTER
                    }
            }
        contentLayout.addView(waveformView)

        // State text
        stateTextView =
            TextView(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                    ).apply {
                        gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
                        bottomMargin = (12 * density).toInt()
                    }
                textSize = 12f
                setTextColor(Color.parseColor("#8E8E93"))
                text = "Listening..."
            }
        contentLayout.addView(stateTextView)

        // User text
        userTextView =
            TextView(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                    ).apply {
                        gravity = Gravity.CENTER
                        topMargin = (100 * density).toInt()
                    }
                textSize = 14f
                setTextColor(Color.parseColor("#3C3C43"))
                gravity = Gravity.CENTER
                visibility = View.GONE
            }
        contentLayout.addView(userTextView)

        // Assistant text
        assistantTextView =
            TextView(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                    ).apply {
                        gravity = Gravity.CENTER
                        topMargin = (130 * density).toInt()
                    }
                textSize = 14f
                setTextColor(Color.parseColor("#A0A0A0"))
                gravity = Gravity.CENTER
                visibility = View.GONE
            }
        contentLayout.addView(assistantTextView)

        panelView = container
        return container
    }

    fun updateState(state: OverlayState) {
        currentState = state
        stateTextView?.text =
            when (state) {
                OverlayState.Idle -> ""
                OverlayState.Listening -> "Listening..."
                OverlayState.Processing -> "Thinking..."
                OverlayState.Speaking -> ""
                OverlayState.Error -> "Try again"
            }

        waveformView?.setActive(
            state == OverlayState.Listening || state == OverlayState.Speaking,
        )
    }

    fun updateTranscript(
        user: String,
        assistant: String,
    ) {
        userText = user
        assistantText = assistant

        userTextView?.text = user
        userTextView?.visibility = if (user.isNotEmpty()) View.VISIBLE else View.GONE

        assistantTextView?.text = assistant
        assistantTextView?.visibility = if (assistant.isNotEmpty()) View.VISIBLE else View.GONE
    }

    fun show() {
        panelView?.apply {
            visibility = View.VISIBLE
            alpha = 0f
            scaleX = 0.7f
            scaleY = 0.7f
            translationY = 100f

            animate()
                .alpha(1f)
                .scaleX(1f)
                .scaleY(1f)
                .translationY(0f)
                .setDuration(450)
                .setInterpolator(OvershootInterpolator(1.2f))
                .start()
        }
    }

    fun hide() {
        panelView?.apply {
            animate()
                .alpha(0f)
                .scaleX(0.7f)
                .scaleY(0.7f)
                .translationY(100f)
                .setDuration(300)
                .setInterpolator(DecelerateInterpolator())
                .withEndAction {
                    visibility = View.GONE
                }
                .start()
        }
    }

    fun destroy() {
        // Cleanup
    }
}

/**
 * Simple native waveform view
 */
class SiriWaveformNativeView(context: Context) : View(context) {
    private var isActive = false
    private val barCount = 30
    private val paint =
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
        }

    private val siriColors =
        intArrayOf(
            Color.parseColor("#FFFFFF"),
            Color.parseColor("#E0E0E0"),
            Color.parseColor("#C0C0C0"),
            Color.parseColor("#A0A0A0"),
            Color.parseColor("#808080"),
            Color.parseColor("#A0A0A0"),
            Color.parseColor("#C0C0C0"),
            Color.parseColor("#E0E0E0"),
            Color.parseColor("#FFFFFF"),
        )

    private val barHeights = FloatArray(barCount) { 0.3f }
    private var time = 0f

    init {
        post(
            object : Runnable {
                override fun run() {
                    if (isActive) {
                        time += 0.05f
                        for (i in 0 until barCount) {
                            val offset = i * 0.3f
                            val wave = sin(time + offset) * 0.5f + 0.5f
                            barHeights[i] = 0.2f + wave * 0.8f
                        }
                        invalidate()
                    }
                    postDelayed(this, 16)
                }
            },
        )
    }

    fun setActive(active: Boolean) {
        isActive = active
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        if (!isActive) return

        val centerY = height / 2f
        val barWidth = width.toFloat() / barCount
        val maxHeight = height * 0.8f

        for (i in 0 until barCount) {
            val x = i * barWidth + barWidth / 2
            val barHeight = barHeights[i] * maxHeight

            val colorIndex =
                (i.toFloat() / barCount * siriColors.size).toInt()
                    .coerceIn(0, siriColors.size - 1)
            paint.color = siriColors[colorIndex]

            val halfHeight = barHeight / 2
            canvas.drawRoundRect(
                x - barWidth * 0.25f,
                centerY - halfHeight,
                x + barWidth * 0.25f,
                centerY + halfHeight,
                barWidth * 0.25f,
                barWidth * 0.25f,
                paint,
            )
        }
    }
}
