package com.aura.aura_ui.presentation.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.aura.aura_ui.ui.theme.AuraNeutral200
import com.aura.aura_ui.ui.theme.AuraNeutral300

/**
 * Professional shimmer loading effect component
 * Creates a smooth, animated loading placeholder
 */
@Composable
fun ShimmerEffect(
    modifier: Modifier = Modifier,
    baseColor: Color = AuraNeutral200,
    highlightColor: Color = AuraNeutral300,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "shimmer")
    
    val shimmerTranslate by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1000f,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = 1200,
                easing = LinearEasing
            ),
            repeatMode = RepeatMode.Restart
        ),
        label = "shimmer_translate"
    )
    
    val shimmerColors = listOf(
        baseColor.copy(alpha = 0.6f),
        highlightColor.copy(alpha = 0.2f),
        baseColor.copy(alpha = 0.6f),
    )
    
    val brush = Brush.linearGradient(
        colors = shimmerColors,
        start = Offset(shimmerTranslate - 500f, shimmerTranslate - 500f),
        end = Offset(shimmerTranslate, shimmerTranslate)
    )
    
    Box(
        modifier = modifier.background(brush)
    )
}

/**
 * Shimmer placeholder for text content
 */
@Composable
fun ShimmerTextPlaceholder(
    modifier: Modifier = Modifier,
    lines: Int = 3,
    lineHeight: Dp = 16.dp,
    lineSpacing: Dp = 8.dp,
) {
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(lineSpacing)
    ) {
        repeat(lines) { index ->
            val widthFraction = when {
                index == lines - 1 -> 0.6f // Last line shorter
                index % 2 == 0 -> 1f
                else -> 0.85f
            }
            
            ShimmerEffect(
                modifier = Modifier
                    .fillMaxWidth(widthFraction)
                    .height(lineHeight)
                    .clip(RoundedCornerShape(4.dp))
            )
        }
    }
}

/**
 * Shimmer placeholder for message bubbles
 */
@Composable
fun ShimmerMessageBubble(
    modifier: Modifier = Modifier,
    isUser: Boolean = false,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        if (!isUser) {
            // Avatar placeholder
            ShimmerEffect(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
            )
            Spacer(modifier = Modifier.width(8.dp))
        }
        
        Column(
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            ShimmerEffect(
                modifier = Modifier
                    .fillMaxWidth(0.8f)
                    .height(16.dp)
                    .clip(RoundedCornerShape(4.dp))
            )
            Spacer(modifier = Modifier.height(6.dp))
            ShimmerEffect(
                modifier = Modifier
                    .fillMaxWidth(0.6f)
                    .height(16.dp)
                    .clip(RoundedCornerShape(4.dp))
            )
        }
        
        if (isUser) {
            Spacer(modifier = Modifier.width(8.dp))
            // Avatar placeholder
            ShimmerEffect(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
            )
        }
    }
}

/**
 * Shimmer placeholder for cards
 */
@Composable
fun ShimmerCard(
    modifier: Modifier = Modifier,
    hasIcon: Boolean = true,
    hasSubtitle: Boolean = true,
    contentLines: Int = 2,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (hasIcon) {
                ShimmerEffect(
                    modifier = Modifier
                        .size(40.dp)
                        .clip(RoundedCornerShape(8.dp))
                )
            }
            
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                ShimmerEffect(
                    modifier = Modifier
                        .fillMaxWidth(0.7f)
                        .height(18.dp)
                        .clip(RoundedCornerShape(4.dp))
                )
                
                if (hasSubtitle) {
                    ShimmerEffect(
                        modifier = Modifier
                            .fillMaxWidth(0.5f)
                            .height(14.dp)
                            .clip(RoundedCornerShape(4.dp))
                    )
                }
            }
        }
        
        if (contentLines > 0) {
            ShimmerTextPlaceholder(
                lines = contentLines,
                lineHeight = 14.dp
            )
        }
    }
}

/**
 * Shimmer placeholder for the conversation list
 */
@Composable
fun ShimmerConversationList(
    modifier: Modifier = Modifier,
    messageCount: Int = 4,
) {
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        repeat(messageCount) { index ->
            ShimmerMessageBubble(isUser = index % 2 == 0)
        }
    }
}

/**
 * Shimmer overlay for content that's loading
 */
@Composable
fun ShimmerOverlay(
    modifier: Modifier = Modifier,
    isLoading: Boolean = true,
    content: @Composable () -> Unit,
) {
    Box(modifier = modifier) {
        content()
        
        if (isLoading) {
            ShimmerEffect(
                modifier = Modifier
                    .matchParentSize()
                    .clip(RoundedCornerShape(12.dp)),
                baseColor = Color.White.copy(alpha = 0.3f),
                highlightColor = Color.White.copy(alpha = 0.6f)
            )
        }
    }
}

/**
 * Pulsing skeleton loader for circular elements
 */
@Composable
fun PulsingCircleSkeleton(
    modifier: Modifier = Modifier,
    size: Dp = 48.dp,
    color: Color = AuraNeutral200,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 0.7f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "alpha"
    )
    
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(color.copy(alpha = alpha))
    )
}
