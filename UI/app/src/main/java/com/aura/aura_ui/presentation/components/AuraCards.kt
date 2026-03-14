package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.*

/**
 * Professional AURA Card Component with animations and gradients
 */
@Composable
fun AuraCard(
    modifier: Modifier = Modifier,
    title: String,
    subtitle: String? = null,
    icon: ImageVector? = null,
    cardType: AuraCardType = AuraCardType.Default,
    isLoading: Boolean = false,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit = {},
) {
    val animatedElevation by animateDpAsState(
        targetValue = if (onClick != null) AuraElevation.lg else AuraElevation.md,
        animationSpec = tween(300),
        label = "card_elevation",
    )

    val colors =
        when (cardType) {
            AuraCardType.Success -> Pair(AuraSuccess, AuraSuccessLight)
            AuraCardType.Warning -> Pair(AuraWarning, AuraWarningLight)
            AuraCardType.Error -> Pair(AuraError, AuraErrorLight)
            AuraCardType.Info -> Pair(AuraInfo, AuraInfoLight)
            AuraCardType.Primary -> Pair(AuraPrimary, MaterialTheme.colorScheme.primaryContainer)
            AuraCardType.Default ->
                Pair(
                    MaterialTheme.colorScheme.onSurface,
                    MaterialTheme.colorScheme.surface,
                )
            AuraCardType.Gradient -> Pair(AuraPrimary, AuraSecondary)
        }

    Card(
        modifier =
            modifier
                .fillMaxWidth()
                .shadow(
                    elevation = animatedElevation,
                    shape = RoundedCornerShape(AuraRadius.lg),
                    ambientColor = colors.first.copy(alpha = 0.1f),
                    spotColor = colors.first.copy(alpha = 0.1f),
                )
                .then(
                    if (onClick != null) {
                        Modifier.animateContentSize()
                    } else {
                        Modifier
                    },
                ),
        onClick = onClick ?: {},
        shape = RoundedCornerShape(AuraRadius.lg),
        colors =
            CardDefaults.cardColors(
                containerColor =
                    if (cardType == AuraCardType.Gradient) {
                        Color.Transparent
                    } else {
                        colors.second
                    },
            ),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Box(
            modifier =
                if (cardType == AuraCardType.Gradient) {
                    Modifier.background(
                        brush =
                            Brush.linearGradient(
                                colors = AuraGradientPrimary.map { it.copy(alpha = 0.1f) },
                            ),
                    )
                } else {
                    Modifier
                },
        ) {
            Column(
                modifier = Modifier.padding(AuraSpacing.cardPadding),
                verticalArrangement = Arrangement.spacedBy(AuraSpacing.md),
            ) {
                // Header section
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(AuraSpacing.md),
                ) {
                    // Icon with animated background
                    icon?.let {
                        Box(
                            modifier =
                                Modifier
                                    .size(40.dp)
                                    .clip(RoundedCornerShape(AuraRadius.md))
                                    .background(
                                        colors.first.copy(alpha = 0.1f),
                                    ),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                imageVector = it,
                                contentDescription = null,
                                tint = colors.first,
                                modifier = Modifier.size(20.dp),
                            )
                        }
                    }

                    // Title and subtitle
                    Column(
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(
                            text = title,
                            style =
                                MaterialTheme.typography.titleMedium.copy(
                                    fontWeight = FontWeight.SemiBold,
                                ),
                            color = MaterialTheme.colorScheme.onSurface,
                        )

                        subtitle?.let { subtitle ->
                            Text(
                                text = subtitle,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }

                    // Loading indicator
                    if (isLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            strokeWidth = 2.dp,
                            color = colors.first,
                        )
                    }
                }

                // Content section
                content()
            }
        }
    }
}

/**
 * AURA Card Types for different use cases
 */
enum class AuraCardType {
    Default,
    Primary,
    Success,
    Warning,
    Error,
    Info,
    Gradient,
}

/**
 * Professional status indicator with pulse animation
 */
@Composable
fun AuraStatusIndicator(
    status: String,
    isActive: Boolean = false,
    color: Color = AuraPrimary,
    modifier: Modifier = Modifier,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "status_pulse")
    val alpha by infiniteTransition.animateFloat(
        initialValue = if (isActive) 0.5f else 1f,
        targetValue = if (isActive) 1f else 1f,
        animationSpec =
            if (isActive) {
                infiniteRepeatable(
                    animation = tween(1000, easing = EaseInOut),
                    repeatMode = RepeatMode.Reverse,
                )
            } else {
                infiniteRepeatable(
                    animation = tween(1, easing = LinearEasing),
                    repeatMode = RepeatMode.Restart,
                )
            },
        label = "status_alpha",
    )

    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(AuraSpacing.sm),
    ) {
        Box(
            modifier =
                Modifier
                    .size(8.dp)
                    .clip(RoundedCornerShape(AuraRadius.full))
                    .background(color.copy(alpha = alpha)),
        )

        Text(
            text = status,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Professional metric display with animated value changes
 */
@Composable
fun AuraMetric(
    label: String,
    value: String,
    trend: AuraTrend? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(AuraSpacing.xs),
    ) {
        AnimatedContent(
            targetState = value,
            transitionSpec = {
                slideInVertically { height -> height } + fadeIn() togetherWith
                    slideOutVertically { height -> -height } + fadeOut()
            },
            label = "metric_value",
        ) { targetValue ->
            Text(
                text = targetValue,
                style =
                    MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.Bold,
                    ),
                color = MaterialTheme.colorScheme.onSurface,
            )
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(AuraSpacing.xs),
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            trend?.let { trend ->
                val trendColor =
                    when (trend) {
                        AuraTrend.Up -> AuraSuccess
                        AuraTrend.Down -> AuraError
                        AuraTrend.Stable -> AuraNeutral500
                    }

                Box(
                    modifier =
                        Modifier
                            .size(4.dp)
                            .clip(RoundedCornerShape(AuraRadius.full))
                            .background(trendColor),
                )
            }
        }
    }
}

enum class AuraTrend {
    Up,
    Down,
    Stable,
}
