package com.aura.aura_ui.overlay

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.view.View
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.DecelerateInterpolator

/**
 * Apple Intelligence style edge glow overlay.
 * 
 * Shows white glow on all 4 edges with inward shadow effect.
 */
class EdgeGlowOverlay(context: Context) : View(context) {
    
    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.WHITE
    }
    
    private val gradientColors = intArrayOf(
        Color.argb(180, 255, 255, 255),  // White with alpha
        Color.argb(80, 255, 255, 255),
        Color.argb(0, 255, 255, 255)     // Transparent
    )
    
    private var glowIntensity = 0f
    private var blurRadius = 30f
    private var spreadWidth = 15f
    private var fadeAnimator: ValueAnimator? = null
    
    init {
        // Make view transparent except for the glow
        setBackgroundColor(Color.TRANSPARENT)
        // Enable hardware acceleration for blur
        setLayerType(LAYER_TYPE_HARDWARE, null)
    }
    
    fun setGlowConfig(color: Int, blurRadius: Float, spread: Float) {
        this.blurRadius = blurRadius
        this.spreadWidth = spread
        gradientColors[0] = Color.argb(180, Color.red(color), Color.green(color), Color.blue(color))
        gradientColors[1] = Color.argb(80, Color.red(color), Color.green(color), Color.blue(color))
        gradientColors[2] = Color.TRANSPARENT
        invalidate()
    }
    
    fun show(fadeInMs: Long = 150, durationMs: Long = 0, fadeOutMs: Long = 300) {
        fadeAnimator?.cancel()
        
        // Fade in
        fadeAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = fadeInMs
            interpolator = DecelerateInterpolator()
            addUpdateListener { animator ->
                glowIntensity = animator.animatedValue as Float
                invalidate()
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    // If duration specified, auto-hide after duration
                    if (durationMs > 0) {
                        postDelayed({ hide(fadeOutMs) }, durationMs)
                    }
                }
            })
            start()
        }
        visibility = VISIBLE
    }
    
    fun hide(fadeOutMs: Long = 300) {
        fadeAnimator?.cancel()
        
        fadeAnimator = ValueAnimator.ofFloat(glowIntensity, 0f).apply {
            duration = fadeOutMs
            interpolator = AccelerateDecelerateInterpolator()
            addUpdateListener { animator ->
                glowIntensity = animator.animatedValue as Float
                invalidate()
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    visibility = GONE
                }
            })
            start()
        }
    }
    
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        
        if (glowIntensity <= 0f) return
        
        val w = width.toFloat()
        val h = height.toFloat()
        val edgeWidth = spreadWidth + blurRadius
        
        // Apply intensity to alpha
        val adjustedColors = gradientColors.map { color ->
            Color.argb(
                (Color.alpha(color) * glowIntensity).toInt(),
                Color.red(color),
                Color.green(color),
                Color.blue(color)
            )
        }.toIntArray()
        
        // Top edge glow (inward)
        val topGradient = LinearGradient(
            0f, 0f, 0f, edgeWidth,
            adjustedColors, null, Shader.TileMode.CLAMP
        )
        glowPaint.shader = topGradient
        canvas.drawRect(0f, 0f, w, edgeWidth, glowPaint)
        
        // Bottom edge glow (inward)
        val bottomGradient = LinearGradient(
            0f, h, 0f, h - edgeWidth,
            adjustedColors, null, Shader.TileMode.CLAMP
        )
        glowPaint.shader = bottomGradient
        canvas.drawRect(0f, h - edgeWidth, w, h, glowPaint)
        
        // Left edge glow (inward)
        val leftGradient = LinearGradient(
            0f, 0f, edgeWidth, 0f,
            adjustedColors, null, Shader.TileMode.CLAMP
        )
        glowPaint.shader = leftGradient
        canvas.drawRect(0f, 0f, edgeWidth, h, glowPaint)
        
        // Right edge glow (inward)
        val rightGradient = LinearGradient(
            w, 0f, w - edgeWidth, 0f,
            adjustedColors, null, Shader.TileMode.CLAMP
        )
        glowPaint.shader = rightGradient
        canvas.drawRect(w - edgeWidth, 0f, w, h, glowPaint)
        
        // Corner glow (radial gradient for smooth corners)
        drawCornerGlow(canvas, 0f, 0f, edgeWidth, adjustedColors, 0) // Top-left
        drawCornerGlow(canvas, w, 0f, edgeWidth, adjustedColors, 1)  // Top-right
        drawCornerGlow(canvas, 0f, h, edgeWidth, adjustedColors, 2)  // Bottom-left
        drawCornerGlow(canvas, w, h, edgeWidth, adjustedColors, 3)   // Bottom-right
    }
    
    private fun drawCornerGlow(
        canvas: Canvas, 
        cx: Float, 
        cy: Float, 
        radius: Float,
        colors: IntArray,
        corner: Int  // 0=TL, 1=TR, 2=BL, 3=BR
    ) {
        val radialGradient = RadialGradient(
            cx, cy, radius,
            colors, null, Shader.TileMode.CLAMP
        )
        glowPaint.shader = radialGradient
        
        // Draw only the quarter that's visible
        val rect = when (corner) {
            0 -> RectF(cx, cy, cx + radius, cy + radius)
            1 -> RectF(cx - radius, cy, cx, cy + radius)
            2 -> RectF(cx, cy - radius, cx + radius, cy)
            3 -> RectF(cx - radius, cy - radius, cx, cy)
            else -> return
        }
        canvas.drawRect(rect, glowPaint)
    }
}