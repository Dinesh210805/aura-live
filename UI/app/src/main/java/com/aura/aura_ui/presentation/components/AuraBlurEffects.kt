package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.filled.RemoveCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.graphics.*
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.*

/**
 * Professional Glass Morphism and Blur Effects
 * Inspired by iOS and modern Android apps
 */

@Composable
fun AuraGlassMorphismCard(
    modifier: Modifier = Modifier,
    backgroundColor: Color = AuraNeutral50.copy(alpha = 0.8f),
    borderColor: Color = AuraNeutral300.copy(alpha = 0.5f),
    blurRadius: androidx.compose.ui.unit.Dp = 20.dp,
    content: @Composable BoxScope.() -> Unit,
) {
    Card(
        modifier =
            modifier
                .blur(radius = blurRadius),
        colors =
            CardDefaults.cardColors(
                containerColor = backgroundColor,
            ),
        border =
            androidx.compose.foundation.BorderStroke(
                width = 1.dp,
                color = borderColor,
            ),
        shape = RoundedCornerShape(AuraRadius.lg),
        elevation =
            CardDefaults.cardElevation(
                defaultElevation = AuraElevation.md,
            ),
    ) {
        Box(
            modifier =
                Modifier
                    .background(
                        brush =
                            Brush.verticalGradient(
                                colors =
                                    listOf(
                                        backgroundColor.copy(alpha = 0.9f),
                                        backgroundColor.copy(alpha = 0.6f),
                                    ),
                            ),
                    ),
        ) {
            content()
        }
    }
}

@Composable
fun AuraFrostedGlass(
    modifier: Modifier = Modifier,
    frostedColor: Color = AuraNeutral50.copy(alpha = 0.7f),
    content: @Composable BoxScope.() -> Unit,
) {
    Box(
        modifier =
            modifier
                .background(
                    color = frostedColor,
                    shape = RoundedCornerShape(AuraRadius.lg),
                )
                .blur(radius = 12.dp),
    ) {
        content()
    }
}

/**
 * Advanced backdrop blur for overlays
 */
@Composable
fun AuraBackdropBlur(
    modifier: Modifier = Modifier,
    blurRadius: androidx.compose.ui.unit.Dp = 16.dp,
    backgroundColor: Color = AuraNeutral900.copy(alpha = 0.3f),
    content: @Composable BoxScope.() -> Unit,
) {
    Box(
        modifier =
            modifier
                .background(backgroundColor)
                .blur(radius = blurRadius),
    ) {
        content()
    }
}

/**
 * Professional notification card with blur effect
 */
@Composable
fun AuraBlurredNotification(
    title: String,
    message: String,
    modifier: Modifier = Modifier,
    backgroundColor: Color = AuraNeutral50.copy(alpha = 0.95f),
    visible: Boolean = true,
    onDismiss: (() -> Unit)? = null,
) {
    AnimatedVisibility(
        visible = visible,
        enter =
            slideInVertically(
                initialOffsetY = { -it },
                animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
            ) + fadeIn(),
        exit =
            slideOutVertically(
                targetOffsetY = { -it },
                animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
            ) + fadeOut(),
        modifier = modifier,
    ) {
        AuraGlassMorphismCard(
            backgroundColor = backgroundColor,
            blurRadius = 20.dp,
        ) {
            Row(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .padding(AuraSpacing.lg),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(AuraSpacing.xs),
                ) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleMedium,
                        color = AuraNeutral900,
                    )
                    Text(
                        text = message,
                        style = MaterialTheme.typography.bodyMedium,
                        color = AuraNeutral700,
                    )
                }

                onDismiss?.let { dismiss ->
                    IconButton(onClick = dismiss) {
                        androidx.compose.material3.Icon(
                            imageVector = androidx.compose.material.icons.Icons.Default.RemoveCircle,
                            contentDescription = "Dismiss",
                            tint = AuraNeutral600,
                        )
                    }
                }
            }
        }
    }
}

/**
 * Parallax scrolling effect
 */
@Composable
fun AuraParallaxBackground(
    modifier: Modifier = Modifier,
    scrollOffset: Float = 0f,
    parallaxRatio: Float = 0.5f,
    content: @Composable BoxScope.() -> Unit,
) {
    Box(
        modifier =
            modifier
                .graphicsLayer {
                    translationY = -scrollOffset * parallaxRatio
                },
    ) {
        content()
    }
}
