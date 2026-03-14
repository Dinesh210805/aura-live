package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.*

/**
 * Professional loading screen with AURA branding
 */
@Composable
fun AuraLoadingScreen(
    message: String = "Initializing AURA...",
    progress: Float = -1f, // -1 for indeterminate
    modifier: Modifier = Modifier,
) {
    Box(
        modifier =
            modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(AuraSpacing.xxl),
        ) {
            // Animated AURA logo with pulse effect
            AuraAnimatedLogo()

            // Loading indicator
            if (progress >= 0f) {
                CircularProgressIndicator(
                    progress = { progress },
                    modifier = Modifier.size(60.dp),
                    color = AuraPrimary,
                )
            } else {
                AuraIndeterminateLoader(
                    modifier = Modifier.size(60.dp),
                )
            }

            // Loading message
            Text(
                text = message,
                style =
                    MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.Medium,
                    ),
                color = MaterialTheme.colorScheme.onBackground,
            )
        }
    }
}

/**
 * Animated AURA logo for loading screen
 */
@Composable
private fun AuraAnimatedLogo() {
    val infiniteTransition = rememberInfiniteTransition(label = "logo_animation")

    val scale by infiniteTransition.animateFloat(
        initialValue = 0.8f,
        targetValue = 1.2f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(2000, easing = EaseInOut),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "logo_scale",
    )

    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(8000, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "logo_rotation",
    )

    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 0.8f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(1500, easing = EaseInOut),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "logo_glow",
    )

    Box(
        modifier = Modifier.size(120.dp),
        contentAlignment = Alignment.Center,
    ) {
        // Glow effect
        Canvas(
            modifier =
                Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = scale
                        scaleY = scale
                        rotationZ = rotation
                    },
        ) {
            val center = center
            val radius = size.minDimension / 3

            // Outer glow
            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                AuraPrimary.copy(alpha = glowAlpha),
                                Color.Transparent,
                            ),
                        radius = radius * 2,
                    ),
                radius = radius * 2,
                center = center,
            )

            // Inner circle
            drawCircle(
                brush =
                    Brush.linearGradient(
                        colors = AuraGradientPrimary,
                    ),
                radius = radius,
                center = center,
            )
        }

        // Icon
        Icon(
            imageVector = Icons.Default.RecordVoiceOver,
            contentDescription = "AURA",
            modifier =
                Modifier
                    .size(60.dp)
                    .graphicsLayer {
                        scaleX = scale * 0.8f
                        scaleY = scale * 0.8f
                    },
            tint = AuraNeutral50,
        )
    }
}

/**
 * Custom indeterminate loader with AURA styling
 */
@Composable
private fun AuraIndeterminateLoader(modifier: Modifier = Modifier) {
    val infiniteTransition = rememberInfiniteTransition(label = "loader_animation")

    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(1200, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "loader_rotation",
    )

    Canvas(
        modifier = modifier.rotate(rotation),
    ) {
        val strokeWidth = 4.dp.toPx()
        val center = this.center
        val radius = (size.minDimension - strokeWidth) / 2

        // Background circle
        drawCircle(
            color = AuraNeutral300,
            radius = radius,
            center = center,
            style = Stroke(width = strokeWidth),
        )

        // Animated arc
        rotate(degrees = rotation) {
            drawArc(
                brush =
                    Brush.sweepGradient(
                        colors =
                            listOf(
                                Color.Transparent,
                                AuraPrimary,
                                AuraSecondary,
                                Color.Transparent,
                            ),
                    ),
                startAngle = 0f,
                sweepAngle = 120f,
                useCenter = false,
                style =
                    Stroke(
                        width = strokeWidth,
                        cap = StrokeCap.Round,
                    ),
                topLeft =
                    androidx.compose.ui.geometry.Offset(
                        center.x - radius,
                        center.y - radius,
                    ),
                size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
            )
        }
    }
}

/**
 * Professional skeleton loading for cards
 */
@Composable
fun AuraSkeleton(
    modifier: Modifier = Modifier,
    height: androidx.compose.ui.unit.Dp = 20.dp,
    width: androidx.compose.ui.unit.Dp? = null,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "skeleton_animation")

    val shimmer by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(1500, easing = EaseInOut),
                repeatMode = RepeatMode.Reverse,
            ),
        label = "shimmer_animation",
    )

    Box(
        modifier =
            modifier
                .height(height)
                .then(
                    if (width != null) Modifier.width(width) else Modifier.fillMaxWidth(),
                )
                .clip(RoundedCornerShape(AuraRadius.sm))
                .background(
                    brush =
                        Brush.linearGradient(
                            colors =
                                listOf(
                                    AuraNeutral200,
                                    AuraNeutral300.copy(alpha = shimmer),
                                    AuraNeutral200,
                                ),
                        ),
                ),
    )
}

/**
 * Professional empty state component
 */
@Composable
fun AuraEmptyState(
    icon: ImageVector,
    title: String,
    description: String,
    actionText: String? = null,
    onActionClick: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .fillMaxWidth()
                .padding(AuraSpacing.xxxxl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(AuraSpacing.lg),
    ) {
        Box(
            modifier =
                Modifier
                    .size(80.dp)
                    .clip(RoundedCornerShape(AuraRadius.xl))
                    .background(AuraNeutral100),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                modifier = Modifier.size(40.dp),
                tint = AuraNeutral500,
            )
        }

        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(AuraSpacing.sm),
        ) {
            Text(
                text = title,
                style =
                    MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.SemiBold,
                    ),
                color = MaterialTheme.colorScheme.onSurface,
            )

            Text(
                text = description,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (actionText != null && onActionClick != null) {
            AuraButton(
                text = actionText,
                onClick = onActionClick,
                buttonType = AuraButtonType.Primary,
            )
        }
    }
}

/**
 * Professional success state animation
 */
@Composable
fun AuraSuccessAnimation(
    message: String = "Success!",
    onAnimationEnd: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    var isVisible by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        isVisible = true
        kotlinx.coroutines.delay(2000)
        onAnimationEnd()
    }

    AnimatedVisibility(
        visible = isVisible,
        enter =
            scaleIn(
                animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
            ) + fadeIn(),
        exit = scaleOut() + fadeOut(),
        modifier = modifier,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(AuraSpacing.lg),
        ) {
            Box(
                modifier =
                    Modifier
                        .size(80.dp)
                        .clip(RoundedCornerShape(AuraRadius.full))
                        .background(AuraSuccess),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Default.Check,
                    contentDescription = null,
                    modifier = Modifier.size(40.dp),
                    tint = AuraNeutral50,
                )
            }

            Text(
                text = message,
                style =
                    MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.SemiBold,
                    ),
                color = AuraSuccess,
            )
        }
    }
}
