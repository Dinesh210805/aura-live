package com.aura.aura_ui.presentation.overlay

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.os.Build
import android.provider.Settings
import android.util.Log
import android.view.*
import android.view.animation.*
import android.widget.FrameLayout
import com.aura.aura_ui.domain.model.VoiceSessionState
import kotlin.math.*

/**
 * Siri-style floating overlay with beautiful gradient orb design
 */
class FloatingMicOverlay(
    private val context: Context,
    private val onMicClick: () -> Unit,
    private val onMicLongClick: () -> Unit,
    private val onPositionChanged: (Float, Float) -> Unit,
) {
    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var overlayView: View? = null
    private var siriOrbView: SiriOrbView? = null
    private var expandedPanel: EnhancedExpandedPanel? = null
    private var expandedPanelView: View? = null
    private var isExpanded = false
    private var overlayState: OverlayState = OverlayState.Idle

    private var isDragging = false
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var lastTapTime = 0L

    companion object {
        private const val TAG = "FloatingMicOverlay"
        private const val ORB_SIZE_DP = 90
        private const val DOUBLE_TAP_THRESHOLD = 300L
    }

    fun show() {
        if (overlayView != null) {
            Log.w(TAG, "Overlay already shown, skipping")
            return
        }

        if (!Settings.canDrawOverlays(context)) {
            Log.e(TAG, "❌ Cannot draw overlays - permission not granted")
            return
        }

        Log.d(TAG, "Creating Siri-style overlay...")
        overlayView = createOverlayView()

        val layoutParams = createLayoutParams()

        // Exclude from screen capture (Android 13+) - MUST be set before addView
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            try {
                val privateFlagsField = WindowManager.LayoutParams::class.java.getDeclaredField("privateFlags")
                privateFlagsField.isAccessible = true
                val currentFlags = privateFlagsField.getInt(layoutParams)
                privateFlagsField.setInt(layoutParams, currentFlags or 0x00000080)
            } catch (e: Exception) {
                Log.w(TAG, "Could not exclude overlay from capture: ${e.message}")
            }
        }
        
        try {
            windowManager.addView(overlayView, layoutParams)
            
            Log.d(TAG, "✅ Siri orb overlay added successfully")

            animateEntrance()

            expandedPanel =
                EnhancedExpandedPanel(
                    context = context,
                    onDismiss = ::collapsePanel,
                    onStop = { },
                    onSettings = { },
                )

            Log.i(TAG, "✅ Siri-style overlay shown successfully")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to show overlay: ${e.message}", e)
            overlayView = null
        }
    }

    fun hide() {
        animateExit {
            expandedPanel?.destroy()
            expandedPanelView?.let { windowManager.removeView(it) }
            overlayView?.let { windowManager.removeView(it) }
            overlayView = null
            siriOrbView = null
            expandedPanel = null
            expandedPanelView = null
            isExpanded = false
        }
    }

    fun expandPanel() {
        if (overlayState == OverlayState.Processing) {
            Log.d(TAG, "Ignored expandPanel() while processing")
            return
        }
        if (isExpanded || expandedPanel == null) return

        isExpanded = true
        expandedPanelView = expandedPanel?.createView()

        expandedPanelView?.let { view ->
            val params = createExpandedPanelLayoutParams()
            
            // Exclude from screen capture (Android 13+) - MUST be set before addView
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                try {
                    val privateFlagsField = WindowManager.LayoutParams::class.java.getDeclaredField("privateFlags")
                    privateFlagsField.isAccessible = true
                    val currentFlags = privateFlagsField.getInt(params)
                    privateFlagsField.setInt(params, currentFlags or 0x00000080)
                } catch (e: Exception) {
                    Log.w(TAG, "Could not exclude expanded panel from capture: ${e.message}")
                }
            }
            
            try {
                windowManager.addView(view, params)
                
                expandedPanel?.show()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to expand panel", e)
            }
        }
    }

    fun collapsePanel() {
        if (!isExpanded) return
        isExpanded = false
        expandedPanel?.hide()

        expandedPanelView?.postDelayed({
            try {
                expandedPanelView?.let { windowManager.removeView(it) }
            } catch (e: Exception) {
            }
            expandedPanelView = null
        }, 250)
    }

    fun updateExpandedState(state: OverlayState) {
        overlayState = state
        // Per Google Live Update design guidelines: the bubble must NOT expand
        // during automation (Processing). Force-collapse and let the system
        // Live Update notification chip carry the status instead.
        if (state == OverlayState.Processing && isExpanded) {
            collapsePanel()
        }
        expandedPanel?.updateState(state)
    }

    fun updateTranscript(
        userText: String,
        assistantText: String,
    ) {
        expandedPanel?.updateTranscript(userText, assistantText)
    }

    fun updateSessionState(state: VoiceSessionState) {
        siriOrbView?.updateSessionState(state)
    }

    fun updateAmplitude(amplitude: Float) {
        siriOrbView?.updateAmplitude(amplitude)
    }

    fun updatePosition(
        x: Float,
        y: Float,
    ) {
        overlayView?.let { view ->
            val params = view.layoutParams as WindowManager.LayoutParams
            params.x = x.toInt()
            params.y = y.toInt()
            windowManager.updateViewLayout(view, params)
        }
    }

    private fun createOverlayView(): View {
        val container =
            object : FrameLayout(context) {
                override fun performClick(): Boolean {
                    super.performClick()
                    return true
                }
            }.apply {
                val orbSizePx = (ORB_SIZE_DP * context.resources.displayMetrics.density).toInt()
                layoutParams = FrameLayout.LayoutParams(orbSizePx, orbSizePx)
            }

        // Create the beautiful Siri-style orb
        siriOrbView =
            SiriOrbView(context).apply {
                layoutParams =
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                    )

                setOnClickListener {
                    if (!isDragging) {
                        performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)

                        // Check for double tap
                        val currentTime = System.currentTimeMillis()
                        if (currentTime - lastTapTime < DOUBLE_TAP_THRESHOLD) {
                            expandPanel()
                        } else {
                            onMicClick()
                        }
                        lastTapTime = currentTime
                    }
                }

                setOnLongClickListener {
                    performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    onMicLongClick()
                    true
                }
            }
        container.addView(siriOrbView)

        container.setOnTouchListener(createTouchListener())
        return container
    }

    private fun createLayoutParams(): WindowManager.LayoutParams {
        val type =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            }

        return WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = 30
        }
    }

    private fun createExpandedPanelLayoutParams(): WindowManager.LayoutParams {
        val type =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            }

        return WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = 150
        }
    }

    private fun createTouchListener(): View.OnTouchListener {
        return View.OnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    isDragging = false
                    val params = view.layoutParams as WindowManager.LayoutParams
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }

                MotionEvent.ACTION_MOVE -> {
                    val deltaX = event.rawX - initialTouchX
                    val deltaY = event.rawY - initialTouchY

                    if (!isDragging && (abs(deltaX) > 10 || abs(deltaY) > 10)) {
                        isDragging = true
                        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    }

                    if (isDragging) {
                        val params = view.layoutParams as WindowManager.LayoutParams
                        params.x = (initialX + deltaX).toInt()
                        params.y = (initialY + deltaY).toInt()

                        val displayMetrics = context.resources.displayMetrics
                        val screenWidth = displayMetrics.widthPixels
                        val screenHeight = displayMetrics.heightPixels

                        params.x = params.x.coerceIn(-view.width / 2, screenWidth - view.width / 2)
                        params.y = params.y.coerceIn(0, screenHeight - view.height)

                        windowManager.updateViewLayout(view, params)
                        onPositionChanged(params.x.toFloat(), params.y.toFloat())
                    }
                    true
                }

                MotionEvent.ACTION_UP -> {
                    if (isDragging) {
                        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        magneticSnapToCenter(view)
                        isDragging = false
                        true
                    } else {
                        view.performClick()
                    }
                }

                else -> false
            }
        }
    }

    private fun magneticSnapToCenter(view: View) {
        val params = view.layoutParams as WindowManager.LayoutParams

        // Snap to center horizontally like Siri
        val targetX = 0

        val animator = ValueAnimator.ofInt(params.x, targetX)
        animator.duration = 400
        animator.interpolator = OvershootInterpolator(1.2f)
        animator.addUpdateListener { animation ->
            params.x = animation.animatedValue as Int
            windowManager.updateViewLayout(view, params)
        }
        animator.start()

        onPositionChanged(targetX.toFloat(), params.y.toFloat())
    }

    private fun animateEntrance() {
        Log.d(TAG, "animateEntrance() called")
        overlayView?.apply {
            alpha = 0f
            scaleX = 0f
            scaleY = 0f

            animate()
                .alpha(1f)
                .scaleX(1f)
                .scaleY(1f)
                .setDuration(800)
                .setInterpolator(OvershootInterpolator(1.2f))
                .withEndAction {
                    Log.d(TAG, "✅ Entrance animation completed")
                }
                .start()
        }
    }

    private fun animateExit(onComplete: () -> Unit) {
        overlayView?.animate()
            ?.alpha(0f)
            ?.scaleX(0f)
            ?.scaleY(0f)
            ?.setDuration(400)
            ?.setInterpolator(AnticipateInterpolator(1.5f))
            ?.withEndAction(onComplete)
            ?.start()
    }
}

/**
 * Siri's iconic multicolor waveform orb
 */
class SiriOrbView(context: Context) : View(context) {
    private var amplitude = 0f
    private var currentState: VoiceSessionState = VoiceSessionState.Idle

    // Monochrome gradient palette
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

    private val waveformPaint =
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            strokeCap = Paint.Cap.ROUND
        }

    private val orbPaint =
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
        }

    // Animation values for waveform
    private var time = 0f
    private val waveformBars = 30
    private val barHeights = FloatArray(waveformBars) { 0.3f }

    private val waveformAnimator =
        ValueAnimator.ofFloat(0f, Float.MAX_VALUE).apply {
            duration = Long.MAX_VALUE
            interpolator = LinearInterpolator()
            addUpdateListener {
                time += 0.05f
                // Update each bar with smooth sine wave animation
                for (i in 0 until waveformBars) {
                    val offset = i * 0.3f
                    val wave = sin(time + offset) * 0.5f + 0.5f
                    barHeights[i] = 0.2f + wave * 0.8f * (1f + amplitude)
                }
                invalidate()
            }
            start()
        }

    init {
        setLayerType(LAYER_TYPE_SOFTWARE, null)
        isClickable = true
        isFocusable = true
    }

    fun updateSessionState(state: VoiceSessionState) {
        currentState = state

        // Shake animation on error
        if (state is VoiceSessionState.Error) {
            shakeAnimation()
        }

        invalidate()
    }

    fun updateAmplitude(amp: Float) {
        amplitude = amp.coerceIn(0f, 1f)
        invalidate()
    }

    private fun shakeAnimation() {
        val shakeValues = floatArrayOf(-10f, 10f, -8f, 8f, -5f, 5f, 0f)
        val animator = ValueAnimator.ofFloat(*shakeValues)
        animator.duration = 500
        animator.addUpdateListener {
            translationX = it.animatedValue as Float
        }
        animator.start()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val centerX = width / 2f
        val centerY = height / 2f
        val maxBarHeight = height / 2.5f

        when {
            // Waveform ONLY during active audio: user speaking or AI speaking.
            // Processing (automation) must NOT trigger the waveform — the orb
            // must stay compact per Google Live Update design guidelines.
            currentState is VoiceSessionState.Listening ||
            currentState is VoiceSessionState.Responding -> {
                val barWidth = width.toFloat() / waveformBars
                for (i in 0 until waveformBars) {
                    val x = i * barWidth + barWidth / 2
                    val barHeight = barHeights[i] * maxBarHeight * (1f + amplitude * 0.5f)
                    val colorIndex = (i.toFloat() / waveformBars * siriColors.size).toInt()
                        .coerceIn(0, siriColors.size - 1)
                    waveformPaint.color = siriColors[colorIndex]
                    val halfHeight = barHeight / 2
                    canvas.drawRoundRect(
                        x - barWidth * 0.25f,
                        centerY - halfHeight,
                        x + barWidth * 0.25f,
                        centerY + halfHeight,
                        barWidth * 0.25f,
                        barWidth * 0.25f,
                        waveformPaint,
                    )
                }
            }

            // Processing (automation running): compact pulsing ring — stays the
            // same size as the idle orb. The Live Update notification chip in the
            // status bar carries the execution status instead.
            currentState is VoiceSessionState.Processing -> {
                val radius = min(width, height) / 3f
                val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }

                // Subtle amber glow to signal "working" without expanding
                glowPaint.color = Color.parseColor("#30F59E0B")
                canvas.drawCircle(centerX, centerY, radius * 1.4f, glowPaint)
                glowPaint.color = Color.parseColor("#50F59E0B")
                canvas.drawCircle(centerX, centerY, radius * 1.1f, glowPaint)

                // Solid amber orb — same compact size as idle
                orbPaint.shader = null
                orbPaint.color = Color.parseColor("#F59E0B")
                canvas.drawCircle(centerX, centerY, radius, orbPaint)

                // Glass highlight
                val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    color = Color.WHITE; alpha = 60
                }
                canvas.drawCircle(
                    centerX - radius * 0.3f, centerY - radius * 0.3f,
                    radius * 0.4f, highlightPaint,
                )
            }

            // Idle: simple glowing orb (Siri-style)
            else -> {
                val radius = min(width, height) / 3f
                val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
                glowPaint.color = Color.parseColor("#20FFFFFF")
                canvas.drawCircle(centerX, centerY, radius * 1.4f, glowPaint)
                glowPaint.color = Color.parseColor("#40C0C0C0")
                canvas.drawCircle(centerX, centerY, radius * 1.2f, glowPaint)

                val gradient = SweepGradient(centerX, centerY, siriColors, null)
                orbPaint.shader = gradient
                canvas.drawCircle(centerX, centerY, radius, orbPaint)

                val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    color = Color.WHITE; alpha = 80
                }
                canvas.drawCircle(
                    centerX - radius * 0.3f, centerY - radius * 0.3f,
                    radius * 0.4f, highlightPaint,
                )
            }
        }
    }
}

class OverlayPermissionException(message: String, cause: Throwable? = null) :
    Exception(message, cause)
