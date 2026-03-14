package com.aura.aura_ui.presentation.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput

/**
 * Professional micro-interactions for UI elements
 * Provides polished scale, bounce, and other animations
 */

/**
 * Scale press animation - element shrinks slightly when pressed
 */
fun Modifier.scalePressAnimation(
    pressScale: Float = 0.96f,
    animationDuration: Int = 100,
): Modifier = composed {
    val interactionSource = remember { MutableInteractionSource() }
    val isPressed by interactionSource.collectIsPressedAsState()
    
    val scale by animateFloatAsState(
        targetValue = if (isPressed) pressScale else 1f,
        animationSpec = tween(animationDuration, easing = FastOutSlowInEasing),
        label = "scale_press"
    )
    
    this
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .clickable(
            interactionSource = interactionSource,
            indication = null,
            onClick = {}
        )
}

/**
 * Bounce click animation with callback
 */
@Composable
fun Modifier.bounceClick(
    onClick: () -> Unit,
    enabled: Boolean = true,
    bounceScale: Float = 0.92f,
): Modifier {
    var isPressed by remember { mutableStateOf(false) }
    
    val scale by animateFloatAsState(
        targetValue = if (isPressed) bounceScale else 1f,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessLow
        ),
        label = "bounce"
    )
    
    return this
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .pointerInput(enabled) {
            if (enabled) {
                detectTapGestures(
                    onPress = {
                        isPressed = true
                        tryAwaitRelease()
                        isPressed = false
                    },
                    onTap = { onClick() }
                )
            }
        }
}

/**
 * Pulsing animation for attention-grabbing elements
 */
fun Modifier.pulsingAnimation(
    enabled: Boolean = true,
    minScale: Float = 0.95f,
    maxScale: Float = 1.05f,
    duration: Int = 1000,
): Modifier = composed {
    if (!enabled) return@composed this
    
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val scale by infiniteTransition.animateFloat(
        initialValue = minScale,
        targetValue = maxScale,
        animationSpec = infiniteRepeatable(
            animation = tween(duration, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse_scale"
    )
    
    this.scale(scale)
}

/**
 * Shake animation for error feedback
 */
@Composable
fun Modifier.shakeAnimation(
    trigger: Boolean,
    onAnimationComplete: () -> Unit = {},
): Modifier {
    val shakeOffset by animateFloatAsState(
        targetValue = if (trigger) 1f else 0f,
        animationSpec = if (trigger) {
            keyframes {
                durationMillis = 400
                0f at 0
                -10f at 50
                10f at 100
                -10f at 150
                10f at 200
                -5f at 250
                5f at 300
                0f at 400
            }
        } else {
            tween(0)
        },
        finishedListener = { if (trigger) onAnimationComplete() },
        label = "shake"
    )
    
    return this.graphicsLayer {
        translationX = shakeOffset
    }
}

/**
 * Fade in animation when appearing
 */
fun Modifier.fadeInAnimation(
    duration: Int = 300,
    delay: Int = 0,
): Modifier = composed {
    var visible by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        visible = true
    }
    
    val alpha by animateFloatAsState(
        targetValue = if (visible) 1f else 0f,
        animationSpec = tween(
            durationMillis = duration,
            delayMillis = delay,
            easing = EaseOut
        ),
        label = "fade_in"
    )
    
    this.graphicsLayer { this.alpha = alpha }
}

/**
 * Slide up and fade in animation
 */
fun Modifier.slideUpFadeIn(
    duration: Int = 400,
    delay: Int = 0,
    slideDistance: Float = 30f,
): Modifier = composed {
    var visible by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        visible = true
    }
    
    val animatedAlpha by animateFloatAsState(
        targetValue = if (visible) 1f else 0f,
        animationSpec = tween(duration, delay, EaseOut),
        label = "alpha"
    )
    
    val animatedOffset by animateFloatAsState(
        targetValue = if (visible) 0f else slideDistance,
        animationSpec = tween(duration, delay, EaseOut),
        label = "offset"
    )
    
    this.graphicsLayer {
        alpha = animatedAlpha
        translationY = animatedOffset
    }
}

/**
 * Rotation animation for loading or processing states
 */
fun Modifier.rotatingAnimation(
    enabled: Boolean = true,
    duration: Int = 1000,
): Modifier = composed {
    if (!enabled) return@composed this
    
    val infiniteTransition = rememberInfiniteTransition(label = "rotation")
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(duration, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rotation"
    )
    
    this.graphicsLayer { rotationZ = rotation }
}

/**
 * Breathing glow animation for highlighted elements
 */
fun Modifier.breathingAnimation(
    enabled: Boolean = true,
    minAlpha: Float = 0.5f,
    maxAlpha: Float = 1f,
    duration: Int = 1500,
): Modifier = composed {
    if (!enabled) return@composed this
    
    val infiniteTransition = rememberInfiniteTransition(label = "breathing")
    val alpha by infiniteTransition.animateFloat(
        initialValue = minAlpha,
        targetValue = maxAlpha,
        animationSpec = infiniteRepeatable(
            animation = tween(duration, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "breathing_alpha"
    )
    
    this.graphicsLayer { this.alpha = alpha }
}

/**
 * Staggered list item animation helper
 * Use index to create cascading animations
 */
fun Modifier.staggeredAnimation(
    index: Int,
    baseDelay: Int = 50,
    duration: Int = 300,
): Modifier = composed {
    val delay = index * baseDelay
    
    var visible by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        visible = true
    }
    
    val animatedAlpha by animateFloatAsState(
        targetValue = if (visible) 1f else 0f,
        animationSpec = tween(duration, delay, EaseOut),
        label = "stagger_alpha"
    )
    
    val animatedOffset by animateFloatAsState(
        targetValue = if (visible) 0f else 20f,
        animationSpec = tween(duration, delay, EaseOut),
        label = "stagger_offset"
    )
    
    this.graphicsLayer {
        alpha = animatedAlpha
        translationY = animatedOffset
    }
}
