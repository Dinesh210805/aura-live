package com.aura.aura_ui.presentation.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.snapping.rememberSnapFlingBehavior
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.SettingsSuggest
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

@Composable
fun AuraWelcomeScreen(
    onWelcomeComplete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var logoVisible by remember { mutableStateOf(false) }
    var titleVisible by remember { mutableStateOf(false) }
    var taglineVisible by remember { mutableStateOf(false) }
    var cardsVisible by remember { mutableStateOf(false) }
    var ctaVisible by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        delay(150)
        logoVisible = true
        delay(250)
        titleVisible = true
        delay(250)
        taglineVisible = true
        delay(300)
        cardsVisible = true
        delay(350)
        ctaVisible = true
    }

    Box(
        modifier =
            modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
    ) {
        WelcomeBackdrop()

        Column(
            modifier =
                Modifier
                    .fillMaxSize()
                    .systemBarsPadding()
                    .padding(horizontal = 24.dp, vertical = 32.dp),
            verticalArrangement = Arrangement.Top,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            HeroSection(
                logoVisible = logoVisible,
                titleVisible = titleVisible,
                taglineVisible = taglineVisible,
            )

            Spacer(modifier = Modifier.height(60.dp))

            FeatureCarousel(
                visible = cardsVisible,
            )

            Spacer(modifier = Modifier.height(60.dp))

            Spacer(modifier = Modifier.weight(1f, fill = true))

            CallToAction(
                visible = ctaVisible,
                onClick = onWelcomeComplete,
            )
        }
    }
}

@Composable
private fun WelcomeBackdrop() {
    val primaryColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.22f)
    val secondaryColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.18f)
    val tertiaryColor = MaterialTheme.colorScheme.tertiary.copy(alpha = 0.14f)

    Box(
        modifier =
            Modifier
                .fillMaxSize(),
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val width = size.width
            val height = size.height

            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                primaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.6f,
                center = Offset(width * 0.25f, height * 0.25f),
            )

            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                secondaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.5f,
                center = Offset(width * 0.8f, height * 0.4f),
            )

            drawCircle(
                brush =
                    Brush.radialGradient(
                        colors =
                            listOf(
                                tertiaryColor,
                                Color.Transparent,
                            ),
                    ),
                radius = width * 0.55f,
                center = Offset(width * 0.5f, height * 0.85f),
            )
        }
    }
}

@Composable
private fun HeroSection(
    logoVisible: Boolean,
    titleVisible: Boolean,
    taglineVisible: Boolean,
) {
    Column(
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(top = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        AnimatedVisibility(
            visible = logoVisible,
            enter =
                fadeIn(animationSpec = tween(600, easing = CubicBezierEasing(0.25f, 0.1f, 0.25f, 1f))) +
                    slideInVertically(initialOffsetY = { it / 2 }, animationSpec = tween(600)),
        ) {
            Surface(
                modifier =
                    Modifier
                        .size(80.dp),
                shape = RoundedCornerShape(24.dp),
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.9f),
                shadowElevation = 12.dp,
                border = BorderStroke(
                    width = 0.5.dp,
                    brush = Brush.linearGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.25f),
                            Color.White.copy(alpha = 0.05f),
                        ),
                    ),
                ),
            ) {
                Box(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .background(
                                brush =
                                    Brush.verticalGradient(
                                        colors =
                                            listOf(
                                                Color.White.copy(alpha = 0.08f),
                                                Color.Transparent,
                                            ),
                                    ),
                            ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "A",
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.background,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }

        AnimatedVisibility(
            visible = titleVisible,
            enter = fadeIn(tween(600)) + slideInVertically(initialOffsetY = { it / 3 }, animationSpec = tween(600)),
        ) {
            Text(
                text = "AURA",
                style =
                    MaterialTheme.typography.displayMedium.copy(
                        fontWeight = FontWeight.Light,
                        letterSpacing = 8.sp,
                    ),
                color = MaterialTheme.colorScheme.onBackground,
            )
        }

        AnimatedVisibility(
            visible = taglineVisible,
            enter = fadeIn(tween(500)) + slideInVertically(initialOffsetY = { it / 4 }, animationSpec = tween(500)),
        ) {
            Text(
                text = "Intelligent. Seamless. Refined.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
                textAlign = TextAlign.Center,
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FeatureCarousel(visible: Boolean) {
    val features =
        remember {
            listOf(
                FeatureDescriptor(
                    title = "Hands-free Control",
                    description = "Conversational navigation with ultra-low latency actions.",
                    icon = Icons.Default.AutoAwesome,
                ),
                FeatureDescriptor(
                    title = "Adaptive Context",
                    description = "Understands UI hierarchy and tailors responses to on-screen elements.",
                    icon = Icons.Default.SettingsSuggest,
                ),
                FeatureDescriptor(
                    title = "Real-time Intelligence",
                    description = "Dynamic intent parsing with millisecond feedback loops.",
                    icon = Icons.Default.Bolt,
                ),
                FeatureDescriptor(
                    title = "Secure Foundation",
                    description = "Privacy-first automation with on-device policy guardrails.",
                    icon = Icons.Default.Lock,
                ),
            )
        }

    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(600)) + slideInVertically(initialOffsetY = { it / 3 }, animationSpec = tween(600)),
        exit = fadeOut(tween(300)) + slideOutVertically(animationSpec = tween(300)),
    ) {
        val listState = rememberLazyListState()
        val flingBehavior = rememberSnapFlingBehavior(lazyListState = listState)
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(20.dp),
            contentPadding = PaddingValues(horizontal = 12.dp),
            state = listState,
            flingBehavior = flingBehavior,
        ) {
            items(features) { feature ->
                FeatureCard(feature = feature)
            }
        }
    }
}

@Composable
private fun FeatureCard(feature: FeatureDescriptor) {
    Surface(
        modifier =
            Modifier
                .width(280.dp)
                .height(180.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.35f),
        shape = RoundedCornerShape(24.dp),
        border =
            BorderStroke(
                width = 0.5.dp,
                brush = Brush.linearGradient(
                    colors = listOf(
                        MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f),
                        MaterialTheme.colorScheme.onSurface.copy(alpha = 0.04f),
                    ),
                ),
            ),
        shadowElevation = 8.dp,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.06f),
                            Color.Transparent,
                        ),
                    ),
                ),
        ) {
            Column(
                modifier =
                    Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                verticalArrangement = Arrangement.SpaceBetween,
                horizontalAlignment = Alignment.Start,
            ) {
                Surface(
                    modifier =
                        Modifier
                            .size(44.dp)
                            .clip(CircleShape),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            imageVector = feature.icon,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                        )
                    }
                }

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = feature.title,
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    Text(
                        text = feature.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                    )
                }
            }
        }
    }
}

@Composable
private fun CallToAction(
    visible: Boolean,
    onClick: () -> Unit,
) {
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(600)) + slideInVertically(initialOffsetY = { it }, animationSpec = tween(600)),
    ) {
        Surface(
            modifier =
                Modifier
                    .fillMaxWidth(0.85f),
            shape = RoundedCornerShape(28.dp),
            color = Color.Transparent,
            shadowElevation = 0.dp,
        ) {
            Button(
                onClick = onClick,
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                shape = RoundedCornerShape(28.dp),
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.onBackground,
                        contentColor = MaterialTheme.colorScheme.background,
                    ),
                contentPadding = PaddingValues(vertical = 0.dp),
                elevation =
                    ButtonDefaults.buttonElevation(
                        defaultElevation = 10.dp,
                        pressedElevation = 2.dp,
                        focusedElevation = 10.dp,
                        hoveredElevation = 12.dp,
                    ),
            ) {
                Text(
                    text = "Get Started",
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                )
            }
        }
    }
}

private data class FeatureDescriptor(
    val title: String,
    val description: String,
    val icon: ImageVector,
)
