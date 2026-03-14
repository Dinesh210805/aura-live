package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.*

/**
 * Professional AURA Button Component with advanced animations
 */
@Composable
fun AuraButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    isLoading: Boolean = false,
    buttonType: AuraButtonType = AuraButtonType.Primary,
    size: AuraButtonSize = AuraButtonSize.Medium,
    icon: ImageVector? = null,
    iconPosition: AuraIconPosition = AuraIconPosition.Start,
) {
    val haptic = LocalHapticFeedback.current
    val interactionSource = remember { MutableInteractionSource() }

    val scale by animateFloatAsState(
        targetValue = if (enabled && !isLoading) 1f else 0.95f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "button_scale",
    )

    val colors = getButtonColors(buttonType)
    val dimensions = getButtonDimensions(size)

    Button(
        onClick = {
            if (enabled && !isLoading) {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            }
        },
        modifier =
            modifier
                .scale(scale)
                .height(dimensions.height)
                .shadow(
                    elevation = if (enabled) AuraElevation.sm else AuraElevation.none,
                    shape = RoundedCornerShape(dimensions.cornerRadius),
                    ambientColor = colors.primary.copy(alpha = 0.1f),
                ),
        enabled = enabled && !isLoading,
        shape = RoundedCornerShape(dimensions.cornerRadius),
        colors =
            ButtonDefaults.buttonColors(
                containerColor =
                    if (buttonType == AuraButtonType.Gradient) {
                        Color.Transparent
                    } else {
                        colors.primary
                    },
                contentColor = colors.onPrimary,
                disabledContainerColor = AuraNeutral300,
                disabledContentColor = AuraNeutral500,
            ),
        contentPadding =
            PaddingValues(
                horizontal = dimensions.horizontalPadding,
                vertical = dimensions.verticalPadding,
            ),
        interactionSource = interactionSource,
        elevation =
            ButtonDefaults.buttonElevation(
                defaultElevation = 0.dp,
                pressedElevation = 0.dp,
                disabledElevation = 0.dp,
            ),
    ) {
        Box(
            modifier =
                if (buttonType == AuraButtonType.Gradient) {
                    Modifier
                        .fillMaxSize()
                        .background(
                            brush =
                                Brush.linearGradient(
                                    colors = AuraGradientPrimary,
                                ),
                            shape = RoundedCornerShape(dimensions.cornerRadius),
                        )
                } else {
                    Modifier.fillMaxSize()
                },
            contentAlignment = Alignment.Center,
        ) {
            AnimatedContent(
                targetState = isLoading,
                transitionSpec = {
                    fadeIn(animationSpec = tween(150)) togetherWith
                        fadeOut(animationSpec = tween(150))
                },
                label = "button_content",
            ) { loading ->
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(dimensions.iconSize),
                        strokeWidth = 2.dp,
                        color = colors.onPrimary,
                    )
                } else {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(AuraSpacing.sm),
                    ) {
                        if (icon != null && iconPosition == AuraIconPosition.Start) {
                            Icon(
                                imageVector = icon,
                                contentDescription = null,
                                modifier = Modifier.size(dimensions.iconSize),
                                tint = colors.onPrimary,
                            )
                        }

                        Text(
                            text = text,
                            style = dimensions.textStyle,
                            fontWeight = FontWeight.SemiBold,
                            color = colors.onPrimary,
                        )

                        if (icon != null && iconPosition == AuraIconPosition.End) {
                            Icon(
                                imageVector = icon,
                                contentDescription = null,
                                modifier = Modifier.size(dimensions.iconSize),
                                tint = colors.onPrimary,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Professional Outlined Button
 */
@Composable
fun AuraOutlinedButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    isLoading: Boolean = false,
    size: AuraButtonSize = AuraButtonSize.Medium,
    icon: ImageVector? = null,
) {
    val haptic = LocalHapticFeedback.current
    val dimensions = getButtonDimensions(size)

    OutlinedButton(
        onClick = {
            if (enabled && !isLoading) {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            }
        },
        modifier = modifier.height(dimensions.height),
        enabled = enabled && !isLoading,
        shape = RoundedCornerShape(dimensions.cornerRadius),
        colors =
            ButtonDefaults.outlinedButtonColors(
                contentColor = AuraPrimary,
                disabledContentColor = AuraNeutral500,
            ),
        border =
            BorderStroke(
                width = 1.dp,
                color = if (enabled) AuraPrimary else AuraNeutral300,
            ),
        contentPadding =
            PaddingValues(
                horizontal = dimensions.horizontalPadding,
                vertical = dimensions.verticalPadding,
            ),
    ) {
        AnimatedContent(
            targetState = isLoading,
            transitionSpec = {
                fadeIn() togetherWith fadeOut()
            },
            label = "outlined_button_content",
        ) { loading ->
            if (loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(dimensions.iconSize),
                    strokeWidth = 2.dp,
                    color = AuraPrimary,
                )
            } else {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(AuraSpacing.sm),
                ) {
                    icon?.let {
                        Icon(
                            imageVector = it,
                            contentDescription = null,
                            modifier = Modifier.size(dimensions.iconSize),
                        )
                    }

                    Text(
                        text = text,
                        style = dimensions.textStyle,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

/**
 * Professional Floating Action Button
 */
@Composable
fun AuraFloatingButton(
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    backgroundColor: Color = AuraPrimary,
) {
    val haptic = LocalHapticFeedback.current
    val scale by animateFloatAsState(
        targetValue = if (enabled) 1f else 0.8f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "fab_scale",
    )

    FloatingActionButton(
        onClick = {
            if (enabled) {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            }
        },
        modifier =
            modifier
                .scale(scale)
                .shadow(
                    elevation = AuraElevation.lg,
                    shape = RoundedCornerShape(AuraRadius.lg),
                    ambientColor = backgroundColor.copy(alpha = 0.2f),
                ),
        containerColor = backgroundColor,
        contentColor = AuraNeutral50,
        elevation =
            FloatingActionButtonDefaults.elevation(
                defaultElevation = 0.dp,
                pressedElevation = 0.dp,
            ),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            modifier = Modifier.size(24.dp),
        )
    }
}

// Button type definitions
enum class AuraButtonType {
    Primary,
    Secondary,
    Success,
    Warning,
    Error,
    Gradient,
    Ghost,
}

enum class AuraButtonSize {
    Small,
    Medium,
    Large,
}

enum class AuraIconPosition {
    Start,
    End,
}

// Color schemes for different button types
private data class ButtonColors(
    val primary: Color,
    val onPrimary: Color,
)

@Composable
private fun getButtonColors(type: AuraButtonType): ButtonColors {
    return when (type) {
        AuraButtonType.Primary -> ButtonColors(AuraPrimary, AuraNeutral50)
        AuraButtonType.Secondary -> ButtonColors(AuraSecondary, AuraNeutral50)
        AuraButtonType.Success -> ButtonColors(AuraSuccess, AuraNeutral50)
        AuraButtonType.Warning -> ButtonColors(AuraWarning, AuraNeutral900)
        AuraButtonType.Error -> ButtonColors(AuraError, AuraNeutral50)
        AuraButtonType.Gradient -> ButtonColors(Color.Transparent, AuraNeutral50)
        AuraButtonType.Ghost -> ButtonColors(Color.Transparent, AuraPrimary)
    }
}

// Button dimensions for different sizes
private data class ButtonDimensions(
    val height: androidx.compose.ui.unit.Dp,
    val horizontalPadding: androidx.compose.ui.unit.Dp,
    val verticalPadding: androidx.compose.ui.unit.Dp,
    val cornerRadius: androidx.compose.ui.unit.Dp,
    val iconSize: androidx.compose.ui.unit.Dp,
    val textStyle: androidx.compose.ui.text.TextStyle,
)

@Composable
private fun getButtonDimensions(size: AuraButtonSize): ButtonDimensions {
    return when (size) {
        AuraButtonSize.Small ->
            ButtonDimensions(
                height = 36.dp,
                horizontalPadding = AuraSpacing.md,
                verticalPadding = AuraSpacing.sm,
                cornerRadius = AuraRadius.sm,
                iconSize = 16.dp,
                textStyle = MaterialTheme.typography.labelMedium,
            )
        AuraButtonSize.Medium ->
            ButtonDimensions(
                height = 44.dp,
                horizontalPadding = AuraSpacing.lg,
                verticalPadding = AuraSpacing.md,
                cornerRadius = AuraRadius.md,
                iconSize = 18.dp,
                textStyle = MaterialTheme.typography.labelLarge,
            )
        AuraButtonSize.Large ->
            ButtonDimensions(
                height = 52.dp,
                horizontalPadding = AuraSpacing.xl,
                verticalPadding = AuraSpacing.lg,
                cornerRadius = AuraRadius.lg,
                iconSize = 20.dp,
                textStyle = MaterialTheme.typography.titleSmall,
            )
    }
}
