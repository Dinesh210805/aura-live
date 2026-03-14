package com.aura.aura_ui.presentation.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Message
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp

/**
 * AURA Icon System
 * Provides consistent iconography across the AURA application
 */

@Composable
fun AuraIcon(
    icon: ImageVector,
    contentDescription: String? = null,
    modifier: Modifier = Modifier,
    tint: Color = LocalContentColor.current,
    size: AuraIconSize = AuraIconSize.Medium,
    animated: Boolean = false,
    animationType: AuraIconAnimation = AuraIconAnimation.None,
) {
    val animationValue =
        if (animated) {
            when (animationType) {
                AuraIconAnimation.Pulse -> {
                    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
                    infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1.2f,
                        animationSpec =
                            infiniteRepeatable(
                                animation = tween(1000),
                                repeatMode = RepeatMode.Reverse,
                            ),
                        label = "pulse",
                    ).value
                }
                AuraIconAnimation.Rotate -> {
                    val infiniteTransition = rememberInfiniteTransition(label = "rotate")
                    infiniteTransition.animateFloat(
                        initialValue = 0f,
                        targetValue = 360f,
                        animationSpec =
                            infiniteRepeatable(
                                animation = tween(2000, easing = LinearEasing),
                            ),
                        label = "rotate",
                    ).value
                }
                else -> 1f
            }
        } else {
            1f
        }

    Icon(
        imageVector = icon,
        contentDescription = contentDescription,
        modifier =
            modifier
                .size(size.dp)
                .graphicsLayer {
                    when (animationType) {
                        AuraIconAnimation.Pulse -> {
                            scaleX = animationValue
                            scaleY = animationValue
                        }
                        AuraIconAnimation.Rotate -> rotationZ = animationValue
                        else -> {}
                    }
                },
        tint = tint,
    )
}

enum class AuraIconSize(val dp: androidx.compose.ui.unit.Dp) {
    Small(16.dp),
    Medium(24.dp),
    Large(32.dp),
    XLarge(48.dp),
}

object AuraIconSizeConstants {
    val SM = AuraIconSize.Small
    val MD = AuraIconSize.Medium
    val LG = AuraIconSize.Large
    val XL = AuraIconSize.XLarge
}

object AuraProfessionalIcons {
    val Microphone = Icons.Default.Mic
    val Settings = Icons.Default.Settings
    val Voice = Icons.Default.RecordVoiceOver
    val VoiceControl = Icons.Default.RecordVoiceOver
    val Assistant = Icons.Default.AssistantPhoto
    val Phone = Icons.Default.Phone
    val Message = Icons.AutoMirrored.Filled.Message
    val Play = Icons.Default.PlayArrow
    val Stop = Icons.Default.Stop
    val Menu = Icons.Default.Menu
    val AIBrain = Icons.Default.Psychology
    val Dashboard = Icons.Default.Dashboard
    val Analytics = Icons.Default.Analytics
    val Automation = Icons.Default.SmartToy
    val Notifications = Icons.Default.Notifications
}

object AuraIconSystem {
    val Primary = Icons.Default.AssistantPhoto
    val Secondary = Icons.Default.Mic

    object Size {
        val SM = AuraIconSize.Small
        val MD = AuraIconSize.Medium
        val LG = AuraIconSize.Large
        val XL = AuraIconSize.XLarge
    }
}

enum class AuraIconAnimation {
    None,
    Pulse,
    Rotate,
    Scale,
    Fade,
}

@Composable
fun AuraTypewriterText(
    text: String,
    modifier: Modifier = Modifier,
    style: androidx.compose.ui.text.TextStyle = LocalTextStyle.current,
    color: Color = LocalContentColor.current,
    typingSpeed: Int = 50,
) {
    var displayText by remember { mutableStateOf("") }
    var currentIndex by remember { mutableStateOf(0) }

    LaunchedEffect(text) {
        displayText = ""
        currentIndex = 0

        while (currentIndex < text.length) {
            kotlinx.coroutines.delay(typingSpeed.toLong())
            displayText = text.substring(0, currentIndex + 1)
            currentIndex++
        }
    }

    Text(
        text = displayText,
        modifier = modifier,
        style = style.copy(color = color),
    )
}

// Flash icon system
object Flash {
    val On = Icons.Default.FlashOn
    val Off = Icons.Default.FlashOff
}

@Composable
fun AuraStaggeredAnimation(
    itemCount: Int,
    visible: Boolean = true,
    staggerDelay: Long = 100,
    content: @Composable (index: Int, modifier: Modifier) -> Unit,
) {
    val visibleStates =
        remember {
            mutableStateListOf<Boolean>().apply {
                repeat(itemCount) { add(false) }
            }
        }

    LaunchedEffect(visible, itemCount) {
        if (visible) {
            visibleStates.fill(false)
            for (i in 0 until itemCount) {
                kotlinx.coroutines.delay(staggerDelay)
                if (i < visibleStates.size) {
                    visibleStates[i] = true
                }
            }
        } else {
            visibleStates.fill(false)
        }
    }

    Column {
        repeat(itemCount) { index ->
            androidx.compose.animation.AnimatedVisibility(
                visible = if (index < visibleStates.size) visibleStates[index] else false,
                enter =
                    androidx.compose.animation.fadeIn(
                        animationSpec = tween(300),
                    ) +
                        androidx.compose.animation.slideInVertically(
                            animationSpec = tween(300),
                            initialOffsetY = { it / 2 },
                        ),
            ) {
                content(index, Modifier)
            }
        }
    }
}

@Composable
fun <T> List<T>.forEachIndexedComposable(content: @Composable (index: Int, item: T) -> Unit) {
    this.forEachIndexed { index, item ->
        content(index, item)
    }
}

object MD {
    val size = AuraIconSize.Medium.dp
    val iconSize = AuraIconSize.Medium
}
