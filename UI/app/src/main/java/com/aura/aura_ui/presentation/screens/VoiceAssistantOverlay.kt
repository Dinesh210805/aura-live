package com.aura.aura_ui.presentation.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.conversation.ConversationMessage
import com.aura.aura_ui.conversation.ConversationPhase
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.presentation.components.*
import com.aura.aura_ui.presentation.utils.AuraHapticType
import com.aura.aura_ui.presentation.utils.rememberHapticFeedback
import com.aura.aura_ui.ui.theme.*
import kotlin.math.roundToInt

// ============================================================================
// AURA VOICE ASSISTANT OVERLAY UI
// Premium Apple-Inspired Design with Modern Voice Assistant UX
// ============================================================================

/**
 * Dynamic color provider for overlay that respects theme settings.
 * Returns colors based on current theme mode (light/dark/system).
 */
@Composable
private fun rememberOverlayColors(): OverlayColorScheme {
    val systemDark = isSystemInDarkTheme()
    val themeMode by ThemeManager.themeMode.collectAsState()
    val isDark = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> systemDark
    }
    
    return remember(isDark) {
        if (isDark) DarkOverlayColors else LightOverlayColors
    }
}

/**
 * Color scheme interface for overlay
 */
private data class OverlayColorScheme(
    val scrim: Color,
    val inputBarBackground: Color,
    val responseSheetBackground: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val dragHandle: Color,
    val iconBackground: Color,
    val accentGreen: Color,
    val accentBlue: Color,
    val accentPurple: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val micActiveGlow: Color,
    val micPulseGlow: Color,
    val userBubbleColor: Color,
    val assistantBubbleColor: Color,
)

/**
 * Dark theme monochrome colors for overlay
 */
private val DarkOverlayColors = OverlayColorScheme(
    scrim = Color.Black.copy(alpha = 0.5f),
    inputBarBackground = Color(0xFF1C1C1C).copy(alpha = 0.92f),
    responseSheetBackground = Color(0xFF1C1C1C).copy(alpha = 0.88f),
    surface = Color(0xFF1C1C1C),
    surfaceVariant = Color(0xFF2C2C2C),
    dragHandle = Color(0xFF484848),
    iconBackground = Color(0xFF2C2C2C),
    accentGreen = Color(0xFFD0D0D0),
    accentBlue = Color(0xFFB0B0B0),
    accentPurple = Color(0xFF909090),
    textPrimary = Color.White,
    textSecondary = Color(0xFFE8E8E8).copy(alpha = 0.6f),
    textTertiary = Color(0xFFE8E8E8).copy(alpha = 0.3f),
    micActiveGlow = Color.White,
    micPulseGlow = Color(0xFFBBBBBB),
    userBubbleColor = Color(0xFF3A3A3A),
    assistantBubbleColor = Color(0xFF2C2C2C),
)

/**
 * Light theme monochrome colors for overlay
 */
private val LightOverlayColors = OverlayColorScheme(
    scrim = Color.Black.copy(alpha = 0.3f),
    inputBarBackground = Color.White.copy(alpha = 0.95f),
    responseSheetBackground = Color(0xFFF2F2F2).copy(alpha = 0.95f),
    surface = Color.White,
    surfaceVariant = Color(0xFFDCDCDC),
    dragHandle = Color(0xFFC6C6C6),
    iconBackground = Color(0xFFDCDCDC),
    accentGreen = Color(0xFF909090),
    accentBlue = Color(0xFF6B6B6B),
    accentPurple = Color(0xFF808080),
    textPrimary = Color.Black,
    textSecondary = Color(0xFF3C3C3C).copy(alpha = 0.6f),
    textTertiary = Color(0xFF3C3C3C).copy(alpha = 0.3f),
    micActiveGlow = Color.Black,
    micPulseGlow = Color(0xFF4A4A4A),
    userBubbleColor = Color(0xFF2A2A2A),
    assistantBubbleColor = Color.White,
)

/**
 * State holder for the Voice Assistant Overlay
 */
data class VoiceAssistantState(
    val isVisible: Boolean = true,
    val isListening: Boolean = false,
    val isProcessing: Boolean = false,
    val isResponding: Boolean = false,
    val partialTranscript: String = "",
    val messages: List<ConversationMessage> = emptyList(),
    val serverConnected: Boolean = false,
    val audioAmplitude: Float = 0f,
    val processingContext: String = "", // "Executing action...", "Analyzing screen...", etc.
    val suggestedCommands: List<String> = emptyList(),
    val recentCommands: List<String> = emptyList(),
    // Agent outputs for thinking trace
    val agentOutputs: List<com.aura.aura_ui.conversation.AgentOutput> = emptyList(),
    val latestAgentOutput: com.aura.aura_ui.conversation.AgentOutput? = null,
    // Task progress skeleton steps
    val taskProgress: com.aura.aura_ui.conversation.TaskProgress? = null,
    // True when a Gemini Live bidirectional session is active (session persists across turns)
    val isGeminiLiveSession: Boolean = false,
)

/**
 * Callbacks for Voice Assistant interactions
 */
data class VoiceAssistantCallbacks(
    val onDismiss: () -> Unit = {},
    val onMicClick: () -> Unit = {},
    val onSettingsClick: () -> Unit = {},
    val onTextSubmit: (String) -> Unit = {},
    val onMessageCopy: (String) -> Unit = {},
    val onMessageRetry: (ConversationMessage) -> Unit = {},
    val onMessageShare: (String) -> Unit = {},
    val onMessageDelete: (String) -> Unit = {},
    val onSuggestionClick: (String) -> Unit = {},
    val onClearChat: () -> Unit = {},
)

/**
 * Main Voice Assistant Overlay Composable
 * Displays a Google Assistant-style floating overlay
 */
@Composable
fun VoiceAssistantOverlay(
    state: VoiceAssistantState,
    callbacks: VoiceAssistantCallbacks,
    modifier: Modifier = Modifier,
) {
    val configuration = LocalConfiguration.current
    val screenHeight = configuration.screenHeightDp.dp
    val density = LocalDensity.current
    
    // Get theme-aware colors
    val colors = rememberOverlayColors()
    
    // Sheet expansion state
    var sheetExpanded by remember { mutableStateOf(false) }
    val collapsedHeight = screenHeight * 0.35f
    val expandedHeight = screenHeight * 0.75f
    
    // Drag offset for sheet
    var dragOffset by remember { mutableFloatStateOf(0f) }
    val currentSheetHeight by animateDpAsState(
        targetValue = if (sheetExpanded) expandedHeight else collapsedHeight,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessLow
        ),
        label = "sheet_height"
    )
    
    // Draggable state for the response sheet
    val draggableState = rememberDraggableState { delta ->
        dragOffset += delta
        // Determine if we should expand or collapse based on drag direction
        if (dragOffset < -100) {
            sheetExpanded = true
            dragOffset = 0f
        } else if (dragOffset > 100) {
            sheetExpanded = false
            dragOffset = 0f
        }
    }

    AnimatedVisibility(
        visible = state.isVisible,
        enter = fadeIn(animationSpec = tween(300)),
        exit = fadeOut(animationSpec = tween(300)),
        modifier = modifier
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(colors.scrim)
                // CRITICAL: imePadding() moves content up when keyboard appears
                .imePadding()
        ) {
            // Background dismiss area (only the empty space)
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null,
                        onClick = callbacks.onDismiss
                    )
            )
            
            // Content Column (above dismiss layer)
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Bottom
            ) {
                // Response Sheet (Expandable Card) with server status inside
                ResponseSheet(
                    state = state,
                    callbacks = callbacks,
                    colors = colors,
                    sheetHeight = currentSheetHeight,
                    isExpanded = sheetExpanded,
                    draggableState = draggableState,
                    onExpandToggle = { sheetExpanded = !sheetExpanded },
                    onSettingsClick = callbacks.onSettingsClick,
                    modifier = Modifier.padding(horizontal = 12.dp)
                )
                
                Spacer(modifier = Modifier.height(8.dp))
                
                // Input Bar (Compact Floating Pill)
                InputBar(
                    state = state,
                    colors = colors,
                    onMicClick = callbacks.onMicClick,
                    onTextSubmit = callbacks.onTextSubmit,
                    onDismiss = callbacks.onDismiss,
                    onSettingsClick = callbacks.onSettingsClick,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)
                )
            }
        }
    }
}

/**
 * Expandable Response Sheet showing conversation
 */
@Composable
private fun ResponseSheet(
    state: VoiceAssistantState,
    callbacks: VoiceAssistantCallbacks,
    colors: OverlayColorScheme,
    sheetHeight: Dp,
    isExpanded: Boolean,
    draggableState: androidx.compose.foundation.gestures.DraggableState,
    onExpandToggle: () -> Unit,
    onSettingsClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    
    // Auto-scroll to bottom when new messages arrive
    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.size - 1)
        }
    }
    
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .height(sheetHeight)
            .draggable(
                state = draggableState,
                orientation = Orientation.Vertical,
            ),
        shape = RoundedCornerShape(28.dp),
        color = colors.responseSheetBackground,
        tonalElevation = 8.dp,
        shadowElevation = 16.dp
    ) {
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            // Drag Handle
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onExpandToggle)
                    .padding(vertical = 12.dp),
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        .width(36.dp)
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(colors.dragHandle)
                )
            }
            
            // Header with status indicator
            SheetHeader(
                isExpanded = isExpanded,
                messageCount = state.messages.size,
                serverConnected = state.serverConnected,
                colors = colors,
                onSettingsClick = onSettingsClick,
                onClearChat = callbacks.onClearChat,
            )
            
            // Content
            if (state.messages.isEmpty() && !state.isListening && !state.isProcessing) {
                EmptyOverlayState(
                    suggestedCommands = state.suggestedCommands,
                    recentCommands = state.recentCommands,
                    colors = colors,
                    onSuggestionClick = callbacks.onSuggestionClick,
                    modifier = Modifier.weight(1f)
                )
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(state.messages) { message ->
                        OverlayMessageBubble(
                            message = message,
                            colors = colors,
                            onCopy = { callbacks.onMessageCopy(message.text) },
                            onRetry = { callbacks.onMessageRetry(message) },
                            onShare = { callbacks.onMessageShare(message.text) },
                            onDelete = { callbacks.onMessageDelete(message.id) }
                        )
                    }
                    
                    // Show live thinking section only during actual task processing.
                    // For Gemini Live conversational responses, audio plays immediately —
                    // no "Thinking" UI needed during RESPONDING (Gemini already speaking).
                    val showThinking = state.isProcessing &&
                        (!state.isGeminiLiveSession || state.agentOutputs.isNotEmpty())
                    if (showThinking) {
                        item {
                            LiveThinkingSection(
                                agentOutputs = state.agentOutputs,
                                processingContext = state.processingContext,
                                colors = colors
                            )
                        }
                    }
                    
                    // Show skeleton steps when task_progress arrives
                    val tp = state.taskProgress
                    if (tp != null && tp.tasks.isNotEmpty() && !tp.isComplete) {
                        item {
                            SkeletonStepsSection(
                                taskProgress = tp,
                                colors = colors
                            )
                        }
                    }
                    
                    // Show partial transcript while listening OR while AI responds.
                    // The final confirmed transcript arrives at turn_complete (after audio
                    // finishes). Keeping the partial visible during RESPONDING lets the
                    // user see what they said while the AI is speaking. It is cleared
                    // automatically when the final transcript bubble is added to messages.
                    if (state.partialTranscript.isNotBlank()) {
                        item {
                            OverlayMessageBubble(
                                message = ConversationMessage(
                                    text = state.partialTranscript,
                                    isUser = true,
                                    isPartial = true
                                ),
                                colors = colors,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Sheet header with AURA branding and connection status
 */
@Composable
private fun SheetHeader(
    isExpanded: Boolean,
    messageCount: Int,
    serverConnected: Boolean,
    colors: OverlayColorScheme,
    onSettingsClick: () -> Unit,
    onClearChat: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // AURA Icon
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .clip(CircleShape)
                    .background(
                        Brush.linearGradient(
                            listOf(AuraPrimary, AuraSecondary)
                        )
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.AutoAwesome,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(16.dp)
                )
            }
            
            Column {
                Text(
                    text = "AURA",
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontWeight = FontWeight.SemiBold,
                        letterSpacing = 1.sp
                    ),
                    color = colors.textPrimary
                )
                // Connection status indicator
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(
                                if (serverConnected) colors.accentGreen 
                                else AuraError
                            )
                    )
                    Text(
                        text = if (serverConnected) "Online" else "Offline",
                        style = MaterialTheme.typography.labelSmall,
                        color = colors.textSecondary
                    )
                    if (messageCount > 0) {
                        Text(
                            text = "• $messageCount messages",
                            style = MaterialTheme.typography.labelSmall,
                            color = colors.textTertiary
                        )
                    }
                }
            }
        }
        
        Row(
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Clear chat button (shown when messages exist)
            if (messageCount > 0) {
                IconButton(
                    onClick = onClearChat,
                    modifier = Modifier.size(36.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.DeleteSweep,
                        contentDescription = "Clear chat",
                        tint = colors.textSecondary,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            
            // Settings button
            IconButton(
                onClick = onSettingsClick,
                modifier = Modifier.size(36.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = "Settings",
                    tint = colors.textSecondary,
                    modifier = Modifier.size(20.dp)
                )
            }
            
            // Expand/Collapse indicator
            Icon(
                imageVector = if (isExpanded) Icons.Default.ExpandMore else Icons.Default.ExpandLess,
                contentDescription = if (isExpanded) "Collapse" else "Expand",
                tint = colors.textSecondary,
                modifier = Modifier.size(24.dp)
            )
        }
    }
}

/**
 * Empty state when no conversation
 */
@Composable
private fun EmptyOverlayState(
    suggestedCommands: List<String>,
    recentCommands: List<String>,
    colors: OverlayColorScheme,
    onSuggestionClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Animated AURA orb
        Box(
            modifier = Modifier
                .size(64.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(
                            AuraPrimary.copy(alpha = 0.3f),
                            AuraSecondary.copy(alpha = 0.1f),
                            Color.Transparent
                        )
                    )
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = Icons.Default.AutoAwesome,
                contentDescription = null,
                tint = AuraPrimary,
                modifier = Modifier.size(32.dp)
            )
        }
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Hi, I'm AURA",
            style = MaterialTheme.typography.titleLarge.copy(
                fontWeight = FontWeight.Medium
            ),
            color = colors.textPrimary,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(8.dp))
        
        Text(
            text = "Tap the mic and ask me anything",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.textSecondary,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        // Horizontally scrollable suggestions
        if (suggestedCommands.isNotEmpty() || recentCommands.isNotEmpty()) {
            HorizontalSuggestions(
                suggestedCommands = suggestedCommands,
                recentCommands = recentCommands,
                colors = colors,
                onSuggestionClick = onSuggestionClick
            )
        }
    }
}

/**
 * Message bubble for overlay with action buttons
 */
@Composable
private fun OverlayMessageBubble(
    message: ConversationMessage,
    colors: OverlayColorScheme,
    onCopy: () -> Unit = {},
    onRetry: () -> Unit = {},
    onShare: () -> Unit = {},
    onDelete: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val isUser = message.isUser
    var showActions by remember { mutableStateOf(false) }
    val hapticFeedback = rememberHapticFeedback()
    
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Column(horizontalAlignment = if (isUser) Alignment.End else Alignment.Start) {
            Surface(
                shape = RoundedCornerShape(
                    topStart = 18.dp,
                    topEnd = 18.dp,
                    bottomStart = if (isUser) 18.dp else 4.dp,
                    bottomEnd = if (isUser) 4.dp else 18.dp
                ),
                color = if (isUser) {
                    colors.userBubbleColor.copy(alpha = if (message.isPartial) 0.6f else 1f)
                } else {
                    colors.assistantBubbleColor
                },
                modifier = Modifier
                    .widthIn(max = 280.dp)
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null
                    ) {
                        if (!message.isPartial) {
                            showActions = !showActions
                        }
                    }
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)
                ) {
                    Text(
                        text = message.text,
                        style = MaterialTheme.typography.bodyMedium.copy(
                            lineHeight = 20.sp
                        ),
                        color = if (isUser) Color.White else colors.textPrimary
                    )
                    
                    // Timestamp for non-partial messages
                    if (!message.isPartial) {
                        Text(
                            text = message.getRelativeTime(),
                            style = MaterialTheme.typography.labelSmall,
                            color = if (isUser) {
                                Color.White.copy(alpha = 0.7f)
                            } else {
                                colors.textSecondary
                            },
                            modifier = Modifier.padding(top = 4.dp)
                        )
                    }
                }
            }
            
            // Message Actions
            AnimatedVisibility(
                visible = showActions && !message.isPartial,
                enter = fadeIn() + slideInVertically(),
                exit = fadeOut() + slideOutVertically()
            ) {
                MessageActions(
                    isUser = isUser,
                    colors = colors,
                    onCopy = {
                        hapticFeedback(AuraHapticType.LIGHT)
                        onCopy()
                        showActions = false
                    },
                    onRetry = {
                        hapticFeedback(AuraHapticType.MEDIUM)
                        onRetry()
                        showActions = false
                    },
                    onShare = {
                        hapticFeedback(AuraHapticType.LIGHT)
                        onShare()
                        showActions = false
                    },
                    onDelete = {
                        hapticFeedback(AuraHapticType.MEDIUM)
                        onDelete()
                        showActions = false
                    },
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }
    }
}

/**
 * Skeleton steps section - Shows the planned steps from task_progress.
 * Briefly displayed before auto-minimize.
 */
@Composable
private fun SkeletonStepsSection(
    taskProgress: com.aura.aura_ui.conversation.TaskProgress,
    colors: OverlayColorScheme,
    modifier: Modifier = Modifier,
) {
    val enterTransition = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        enterTransition.animateTo(1f, animationSpec = tween(400))
    }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .alpha(enterTransition.value)
            .clip(RoundedCornerShape(16.dp))
            .background(colors.assistantBubbleColor.copy(alpha = 0.6f))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        // Goal header
        Text(
            text = taskProgress.goal,
            style = MaterialTheme.typography.labelMedium,
            color = colors.textPrimary,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )

        // Step items
        taskProgress.tasks.forEachIndexed { index, step ->
            val isCurrent = index + 1 == taskProgress.current
            val isDone = index + 1 < taskProgress.current

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                // Step indicator
                Box(
                    modifier = Modifier
                        .size(20.dp)
                        .clip(CircleShape)
                        .background(
                            when {
                                isDone -> AuraPrimary.copy(alpha = 0.8f)
                                isCurrent -> AuraPrimary
                                else -> colors.textSecondary.copy(alpha = 0.2f)
                            }
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    if (isDone) {
                        Icon(
                            imageVector = Icons.Default.Check,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(12.dp)
                        )
                    } else {
                        Text(
                            text = "${index + 1}",
                            style = MaterialTheme.typography.labelSmall,
                            color = if (isCurrent) Color.White else colors.textSecondary,
                            fontSize = 10.sp,
                        )
                    }
                }

                // Step description
                Text(
                    text = step,
                    style = MaterialTheme.typography.bodySmall,
                    color = when {
                        isDone -> colors.textSecondary.copy(alpha = 0.6f)
                        isCurrent -> colors.textPrimary
                        else -> colors.textSecondary.copy(alpha = 0.7f)
                    },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textDecoration = if (isDone) TextDecoration.LineThrough else TextDecoration.None,
                    fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal,
                )
            }
        }
    }
}

/**
 * Live thinking section - Shows real-time agent pipeline outputs during processing.
 * Toggle button (expanded by default) reveals the thinking trace.
 */
@Composable
private fun LiveThinkingSection(
    agentOutputs: List<com.aura.aura_ui.conversation.AgentOutput>,
    processingContext: String,
    colors: OverlayColorScheme,
    modifier: Modifier = Modifier,
) {
    var isExpanded by remember { mutableStateOf(true) } // Open by default
    
    val infiniteTransition = rememberInfiniteTransition(label = "thinking_live")
    
    // Pulsing indicator
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.5f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )
    
    // Shimmer effect
    val shimmerOffset by infiniteTransition.animateFloat(
        initialValue = -1f,
        targetValue = 2f,
        animationSpec = infiniteRepeatable(
            animation = tween(1500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "shimmer"
    )
    
    // Rotation for expand icon
    val rotationAngle by animateFloatAsState(
        targetValue = if (isExpanded) 180f else 0f,
        animationSpec = tween(300, easing = FastOutSlowInEasing),
        label = "rotation"
    )
    
    // Auto-scroll to latest output
    val listState = rememberLazyListState()
    LaunchedEffect(agentOutputs.size) {
        if (agentOutputs.isNotEmpty() && isExpanded) {
            listState.animateScrollToItem(agentOutputs.size - 1)
        }
    }

    Column(
        modifier = modifier.fillMaxWidth()
    ) {
        // Header bar — tap to toggle
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp, bottomStart = if (isExpanded) 0.dp else 16.dp, bottomEnd = if (isExpanded) 0.dp else 16.dp),
            color = colors.surfaceVariant.copy(alpha = 0.95f),
            shadowElevation = 4.dp,
        ) {
            Box {
                // Shimmer overlay
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .clip(RoundedCornerShape(16.dp))
                        .background(
                            brush = Brush.linearGradient(
                                colors = listOf(
                                    Color.Transparent,
                                    colors.accentBlue.copy(alpha = 0.08f),
                                    colors.accentPurple.copy(alpha = 0.12f),
                                    colors.accentBlue.copy(alpha = 0.08f),
                                    Color.Transparent
                                ),
                                start = Offset(x = shimmerOffset * 300f, y = 0f),
                                end = Offset(x = (shimmerOffset + 0.5f) * 300f, y = 50f)
                            )
                        )
                )
                
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { isExpanded = !isExpanded }
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    // Animated thinking orb
                    Box(contentAlignment = Alignment.Center) {
                        Box(
                            modifier = Modifier
                                .size(14.dp)
                                .alpha(pulseAlpha * 0.4f)
                                .scale(1f + pulseAlpha * 0.15f)
                                .clip(CircleShape)
                                .background(colors.accentBlue.copy(alpha = 0.3f))
                        )
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .alpha(0.7f + pulseAlpha * 0.3f)
                                .clip(CircleShape)
                                .background(colors.accentBlue)
                        )
                    }
                    
                    Text(
                        text = if (agentOutputs.isEmpty()) "Thinking..." else agentOutputs.last().output.take(40),
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontWeight = FontWeight.Medium
                        ),
                        color = colors.textPrimary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    
                    // Toggle icon
                    Icon(
                        imageVector = Icons.Default.KeyboardArrowDown,
                        contentDescription = if (isExpanded) "Collapse" else "Expand",
                        tint = colors.textSecondary,
                        modifier = Modifier
                            .size(20.dp)
                            .graphicsLayer { rotationZ = rotationAngle }
                    )
                }
            }
        }
        
        // Expanded content — agent output stream
        AnimatedVisibility(
            visible = isExpanded,
            enter = fadeIn(animationSpec = tween(200)) + expandVertically(animationSpec = tween(300)),
            exit = fadeOut(animationSpec = tween(150)) + shrinkVertically(animationSpec = tween(250))
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(bottomStart = 16.dp, bottomEnd = 16.dp),
                color = colors.surface.copy(alpha = 0.6f),
                tonalElevation = 1.dp,
            ) {
                if (agentOutputs.isEmpty()) {
                    // No outputs yet — show waiting state
                    Row(
                        modifier = Modifier.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = colors.accentBlue
                        )
                        Text(
                            text = processingContext.ifBlank { "Processing your request..." },
                            style = MaterialTheme.typography.bodySmall,
                            color = colors.textSecondary
                        )
                    }
                } else {
                    LazyColumn(
                        state = listState,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 200.dp),
                        contentPadding = PaddingValues(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        items(agentOutputs.size) { index ->
                            val output = agentOutputs[index]
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.Top
                            ) {
                                // Agent badge
                                Text(
                                    text = output.agent,
                                    style = MaterialTheme.typography.labelSmall.copy(
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 10.sp
                                    ),
                                    color = colors.accentBlue,
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(colors.accentBlue.copy(alpha = 0.1f))
                                        .padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                                
                                // Output text
                                Text(
                                    text = output.output,
                                    style = MaterialTheme.typography.bodySmall.copy(
                                        lineHeight = 16.sp
                                    ),
                                    color = colors.textSecondary,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

// Custom easing functions for premium animations
private val EaseInOutBack = CubicBezierEasing(0.68f, -0.2f, 0.32f, 1.2f)
private val EaseOutSine = CubicBezierEasing(0.39f, 0.575f, 0.565f, 1f)

/**
 * Bottom Input Bar (Compact Floating Pill)
 */
@Composable
private fun InputBar(
    state: VoiceAssistantState,
    colors: OverlayColorScheme,
    onMicClick: () -> Unit,
    onTextSubmit: (String) -> Unit,
    onDismiss: () -> Unit,
    onSettingsClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var textInput by remember { mutableStateOf("") }
    val hapticFeedback = rememberHapticFeedback()
    
    // Mic button animation
    val infiniteTransition = rememberInfiniteTransition(label = "mic_glow")
    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow"
    )
    
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        color = colors.inputBarBackground,
        tonalElevation = 4.dp,
        shadowElevation = 8.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Close/Dismiss button
            IconButton(
                onClick = onDismiss,
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(colors.iconBackground)
            ) {
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = "Close",
                    tint = colors.textSecondary,
                    modifier = Modifier.size(20.dp)
                )
            }
            
            // Voice waveform or text input field
            // In Gemini Live session: show wave for all active phases
            val showWave = state.isListening ||
                (state.isGeminiLiveSession && (state.isProcessing || state.isResponding))
            if (showWave) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.Center
                ) {
                    VoiceWaveformVisualizer(
                        amplitude = if (state.isListening) state.audioAmplitude else 0f,
                        colors = colors,
                        modifier = Modifier.fillMaxWidth()
                    )
                    // Phase verb shown beneath the waveform.
                    // LISTENING with no transcript → empty: the waveform animation already
                    // communicates listening state; showing "Listening" alongside the mic
                    // button is redundant and the user explicitly doesn't want it.
                    val phaseLabel = when {
                        state.isListening && state.partialTranscript.isNotBlank() ->
                            state.partialTranscript
                        state.isListening -> ""
                        state.isProcessing -> if (state.isGeminiLiveSession) "Executing task..." else "Thinking..."
                        state.isResponding -> "Speaking..."
                        else -> ""
                    }
                    if (phaseLabel.isNotBlank()) {
                        Text(
                            text = phaseLabel,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (state.isListening && state.partialTranscript.isNotBlank())
                                colors.textPrimary
                            else
                                colors.textSecondary,
                            maxLines = 1,
                            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 4.dp, vertical = 2.dp)
                        )
                    }
                }
            } else {
                TextField(
                    value = textInput,
                    onValueChange = { textInput = it },
                    placeholder = {
                        Text(
                            text = "Ask AURA",
                            color = colors.textSecondary,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    },
                    modifier = Modifier.weight(1f),
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        disabledContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = colors.accentBlue,
                        focusedTextColor = colors.textPrimary,
                        unfocusedTextColor = colors.textPrimary
                    ),
                    textStyle = MaterialTheme.typography.bodyMedium,
                    singleLine = true
                )
            }
            
            // Mic Button (Primary Action) with premium animations
            Box(
                contentAlignment = Alignment.Center
            ) {
                // Multiple pulsating rings when listening or during active Gemini Live session
                if (state.isListening || (state.isGeminiLiveSession && (state.isProcessing || state.isResponding))) {
                    // Outer ring 1
                    val ring1Scale by infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1.8f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart
                        ),
                        label = "ring1_scale"
                    )
                    val ring1Alpha by infiniteTransition.animateFloat(
                        initialValue = 0.6f,
                        targetValue = 0f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart
                        ),
                        label = "ring1_alpha"
                    )
                    
                    // Outer ring 2 (delayed)
                    val ring2Scale by infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1.6f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart,
                            initialStartOffset = StartOffset(400)
                        ),
                        label = "ring2_scale"
                    )
                    val ring2Alpha by infiniteTransition.animateFloat(
                        initialValue = 0.5f,
                        targetValue = 0f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart,
                            initialStartOffset = StartOffset(400)
                        ),
                        label = "ring2_alpha"
                    )
                    
                    // Outer ring 3 (more delayed)
                    val ring3Scale by infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1.4f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart,
                            initialStartOffset = StartOffset(800)
                        ),
                        label = "ring3_scale"
                    )
                    val ring3Alpha by infiniteTransition.animateFloat(
                        initialValue = 0.4f,
                        targetValue = 0f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(1200, easing = EaseOutSine),
                            repeatMode = RepeatMode.Restart,
                            initialStartOffset = StartOffset(800)
                        ),
                        label = "ring3_alpha"
                    )
                    
                    // Ring 1
                    Box(
                        modifier = Modifier
                            .size(44.dp)
                            .graphicsLayer {
                                scaleX = ring1Scale
                                scaleY = ring1Scale
                                alpha = ring1Alpha
                            }
                            .clip(CircleShape)
                            .background(
                                brush = Brush.radialGradient(
                                    colors = listOf(
                                        colors.accentPurple.copy(alpha = 0.8f),
                                        colors.accentBlue.copy(alpha = 0.4f),
                                        Color.Transparent
                                    )
                                )
                            )
                    )
                    
                    // Ring 2
                    Box(
                        modifier = Modifier
                            .size(44.dp)
                            .graphicsLayer {
                                scaleX = ring2Scale
                                scaleY = ring2Scale
                                alpha = ring2Alpha
                            }
                            .clip(CircleShape)
                            .background(
                                brush = Brush.radialGradient(
                                    colors = listOf(
                                        colors.accentBlue.copy(alpha = 0.7f),
                                        colors.micPulseGlow.copy(alpha = 0.3f),
                                        Color.Transparent
                                    )
                                )
                            )
                    )
                    
                    // Ring 3
                    Box(
                        modifier = Modifier
                            .size(44.dp)
                            .graphicsLayer {
                                scaleX = ring3Scale
                                scaleY = ring3Scale
                                alpha = ring3Alpha
                            }
                            .clip(CircleShape)
                            .background(
                                brush = Brush.radialGradient(
                                    colors = listOf(
                                        colors.accentGreen.copy(alpha = 0.6f),
                                        colors.accentBlue.copy(alpha = 0.2f),
                                        Color.Transparent
                                    )
                                )
                            )
                    )
                    
                    // Inner glow
                    Box(
                        modifier = Modifier
                            .size(52.dp)
                            .graphicsLayer { alpha = glowAlpha * 0.6f }
                            .clip(CircleShape)
                            .background(
                                brush = Brush.radialGradient(
                                    colors = listOf(
                                        colors.micActiveGlow.copy(alpha = 0.5f),
                                        Color.Transparent
                                    )
                                )
                            )
                    )
                }
                
                // Breathing animation for idle state
                val idleScale by infiniteTransition.animateFloat(
                    initialValue = 1f,
                    targetValue = 1.05f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(2000, easing = EaseInOutSine),
                        repeatMode = RepeatMode.Reverse
                    ),
                    label = "idle_scale"
                )
                
                // In Gemini Live session: button is always "End Session" (red stop)
                // Outside session: mic button (white) when idle, blue/purple stop when listening
                val isSessionActive = state.isGeminiLiveSession
                val isAnyActive = state.isListening || state.isProcessing || state.isResponding
                IconButton(
                    onClick = {
                        if (isSessionActive || state.isListening) {
                            hapticFeedback(AuraHapticType.RECORDING_STOP)
                        } else {
                            hapticFeedback(AuraHapticType.RECORDING_START)
                        }
                        onMicClick()
                    },
                    modifier = Modifier
                        .size(44.dp)
                        .graphicsLayer {
                            if (!isAnyActive && !isSessionActive) {
                                scaleX = idleScale
                                scaleY = idleScale
                            }
                        }
                        .clip(CircleShape)
                        .background(
                            when {
                                isSessionActive -> Brush.linearGradient(
                                    colors = listOf(
                                        Color(0xFFE53935), // red — end session
                                        Color(0xFFB71C1C)
                                    )
                                )
                                state.isListening -> Brush.linearGradient(
                                    colors = listOf(
                                        colors.accentBlue,
                                        colors.accentPurple
                                    )
                                )
                                else -> Brush.linearGradient(
                                    colors = listOf(Color.White, Color.White)
                                )
                            }
                        )
                ) {
                    Icon(
                        imageVector = if (isSessionActive || state.isListening) Icons.Default.Stop else Icons.Default.Mic,
                        contentDescription = if (isSessionActive) "End Session" else if (state.isListening) "Stop" else "Speak",
                        tint = if (isSessionActive || state.isListening) Color.White else Color.Black,
                        modifier = Modifier.size(22.dp)
                    )
                }
            }
            
            // Send button (shown when text is entered)
            AnimatedVisibility(visible = textInput.isNotBlank()) {
                IconButton(
                    onClick = {
                        hapticFeedback(AuraHapticType.MEDIUM)
                        onTextSubmit(textInput)
                        textInput = ""
                    },
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(colors.accentBlue)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.Send,
                        contentDescription = "Send",
                        tint = Color.White,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
        }
    }
}

// ============================================================================
// NEW COMPONENTS
// ============================================================================

/**
 * Voice Waveform Visualizer - Spectrogram-style with bars responding to speech amplitude
 */
@Composable
private fun VoiceWaveformVisualizer(
    amplitude: Float,
    colors: OverlayColorScheme,
    modifier: Modifier = Modifier,
) {
    val barCount = 24  // More bars for spectrogram look
    val infiniteTransition = rememberInfiniteTransition(label = "waveform")
    
    // Simulated frequency band amplitudes - each bar gets a slightly different response
    // This creates a spectrogram-like effect where different "frequencies" respond differently
    val barHeights = remember { mutableStateListOf<Float>().apply { repeat(barCount) { add(0.1f) } } }
    
    // Update bar heights based on amplitude with frequency-band simulation
    LaunchedEffect(amplitude) {
        val normalizedAmp = amplitude.coerceIn(0f, 1f)
        barHeights.forEachIndexed { index, _ ->
            // Simulate different frequency bands responding to audio
            // Middle frequencies (speech) are more prominent
            val centerWeight = 1f - kotlin.math.abs(index - barCount / 2f) / (barCount / 2f)
            val frequencyResponse = 0.3f + (centerWeight * 0.7f)
            
            // Add some randomness for natural look
            val randomVariation = (Math.random() * 0.4 - 0.2).toFloat()
            val targetHeight = (normalizedAmp * frequencyResponse + randomVariation).coerceIn(0.08f, 1f)
            
            // Smooth transition
            barHeights[index] = barHeights[index] + (targetHeight - barHeights[index]) * 0.5f
        }
    }
    
    // Continuous animation for when there's no amplitude input (idle state)
    val idleWavePhase by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = (2 * kotlin.math.PI).toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(2000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "idle_wave"
    )
    
    // Outer glow pulse
    val glowPulse by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 0.8f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow_pulse"
    )
    
    Box(
        modifier = modifier
            .height(48.dp)
            .fillMaxWidth(),
        contentAlignment = Alignment.Center
    ) {
        // Background glow effect
        Box(
            modifier = Modifier
                .fillMaxWidth(0.85f)
                .height(44.dp)
                .graphicsLayer { alpha = glowPulse * amplitude.coerceIn(0.3f, 1f) }
                .background(
                    brush = Brush.horizontalGradient(
                        colors = listOf(
                            Color.Transparent,
                            colors.textSecondary.copy(alpha = 0.15f),
                            colors.textSecondary.copy(alpha = 0.25f),
                            colors.textSecondary.copy(alpha = 0.15f),
                            Color.Transparent
                        )
                    ),
                    shape = RoundedCornerShape(22.dp)
                )
        )
        
        // Spectrogram-style animated bars
        Row(
            modifier = Modifier.padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically
        ) {
            repeat(barCount) { index ->
                // Calculate height based on amplitude or idle animation
                val baseHeight = if (amplitude > 0.05f) {
                    barHeights.getOrElse(index) { 0.1f }
                } else {
                    // Idle sine wave animation when no audio
                    val phase = idleWavePhase + (index * 0.3f)
                    0.15f + kotlin.math.sin(phase).toFloat() * 0.1f
                }
                
                // Animate height changes smoothly
                val animatedHeight by animateFloatAsState(
                    targetValue = baseHeight,
                    animationSpec = tween(50, easing = LinearEasing),
                    label = "bar_height_$index"
                )
                
                // Use textSecondary color (same as "Ask AURA" placeholder)
                val barColor = colors.textSecondary
                
                // Intensity based on height for glow effect
                val intensity = animatedHeight.coerceIn(0.3f, 1f)
                
                Box(
                    modifier = Modifier
                        .width(4.dp)
                        .fillMaxHeight(animatedHeight.coerceIn(0.08f, 0.95f))
                        .clip(RoundedCornerShape(2.dp))
                        .background(
                            brush = Brush.verticalGradient(
                                colors = listOf(
                                    barColor.copy(alpha = intensity),
                                    barColor.copy(alpha = intensity * 0.5f)
                                )
                            )
                        )
                )
            }
        }
    }
}

// Color interpolation helper
private fun lerp(start: Color, end: Color, fraction: Float): Color {
    return Color(
        red = start.red + (end.red - start.red) * fraction,
        green = start.green + (end.green - start.green) * fraction,
        blue = start.blue + (end.blue - start.blue) * fraction,
        alpha = start.alpha + (end.alpha - start.alpha) * fraction
    )
}

/**
 * Message action buttons
 */
@Composable
private fun MessageActions(
    isUser: Boolean,
    colors: OverlayColorScheme,
    onCopy: () -> Unit,
    onRetry: () -> Unit,
    onShare: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = colors.surfaceVariant.copy(alpha = 0.8f),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            MessageActionButton(
                icon = Icons.Default.ContentCopy,
                contentDescription = "Copy",
                tint = colors.textSecondary,
                onClick = onCopy
            )
            
            if (isUser) {
                MessageActionButton(
                    icon = Icons.Default.Refresh,
                    contentDescription = "Retry",
                    tint = colors.textSecondary,
                    onClick = onRetry
                )
            }
            
            MessageActionButton(
                icon = Icons.Default.Share,
                contentDescription = "Share",
                tint = colors.textSecondary,
                onClick = onShare
            )
            
            MessageActionButton(
                icon = Icons.Default.Delete,
                contentDescription = "Delete",
                tint = colors.textSecondary,
                onClick = onDelete
            )
        }
    }
}

@Composable
private fun MessageActionButton(
    icon: ImageVector,
    contentDescription: String,
    tint: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    IconButton(
        onClick = onClick,
        modifier = modifier.size(32.dp)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = contentDescription,
            tint = tint,
            modifier = Modifier.size(18.dp)
        )
    }
}

/**
 * Quick Actions Section with suggestions and recent commands
 */
@Composable
private fun QuickActionsSection(
    suggestedCommands: List<String>,
    recentCommands: List<String>,
    colors: OverlayColorScheme,
    onSuggestionClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Suggested Commands
        if (suggestedCommands.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = "Try saying:",
                    style = MaterialTheme.typography.labelMedium,
                    color = colors.textSecondary,
                    modifier = Modifier.padding(horizontal = 4.dp)
                )
                
                suggestedCommands.take(3).forEach { command ->
                    SuggestionChip(
                        text = command,
                        colors = colors,
                        onClick = { onSuggestionClick(command) }
                    )
                }
            }
        }
        
        // Recent Commands
        if (recentCommands.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = "Recent:",
                    style = MaterialTheme.typography.labelMedium,
                    color = colors.textSecondary,
                    modifier = Modifier.padding(horizontal = 4.dp)
                )
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 4.dp)
                ) {
                    recentCommands.take(2).forEach { command ->
                        RecentCommandChip(
                            text = command,
                            colors = colors,
                            onClick = { onSuggestionClick(command) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SuggestionChip(
    text: String,
    colors: OverlayColorScheme,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val hapticFeedback = rememberHapticFeedback()
    
    Surface(
        onClick = {
            hapticFeedback(AuraHapticType.LIGHT)
            onClick()
        },
        shape = RoundedCornerShape(16.dp),
        color = colors.surfaceVariant.copy(alpha = 0.9f),
        border = BorderStroke(1.dp, colors.accentBlue.copy(alpha = 0.5f)),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.Lightbulb,
                contentDescription = null,
                tint = colors.accentBlue,
                modifier = Modifier.size(16.dp)
            )
            Text(
                text = text,
                style = MaterialTheme.typography.bodyMedium,
                color = colors.textPrimary
            )
        }
    }
}

@Composable
private fun RecentCommandChip(
    text: String,
    colors: OverlayColorScheme,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val hapticFeedback = rememberHapticFeedback()
    
    Surface(
        onClick = {
            hapticFeedback(AuraHapticType.LIGHT)
            onClick()
        },
        shape = RoundedCornerShape(12.dp),
        color = colors.accentBlue.copy(alpha = 0.3f),
        border = BorderStroke(1.dp, colors.accentBlue.copy(alpha = 0.4f)),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.History,
                contentDescription = null,
                tint = colors.accentBlue,
                modifier = Modifier.size(14.dp)
            )
            Text(
                text = text,
                style = MaterialTheme.typography.bodySmall,
                color = colors.textPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

/**
 * Horizontally scrollable suggestions
 */
@Composable
private fun HorizontalSuggestions(
    suggestedCommands: List<String>,
    recentCommands: List<String>,
    colors: OverlayColorScheme,
    onSuggestionClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Suggested commands
        if (suggestedCommands.isNotEmpty()) {
            Text(
                text = "Try saying:",
                style = MaterialTheme.typography.labelMedium,
                color = colors.textSecondary
            )
            
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(horizontal = 16.dp)
            ) {
                items(suggestedCommands) { command ->
                    SuggestionChip(
                        text = command,
                        colors = colors,
                        onClick = { onSuggestionClick(command) }
                    )
                }
            }
        }
        
        // Recent commands
        if (recentCommands.isNotEmpty()) {
            Text(
                text = "Recent:",
                style = MaterialTheme.typography.labelMedium,
                color = colors.textSecondary
            )
            
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(horizontal = 16.dp)
            ) {
                items(recentCommands) { command ->
                    RecentCommandChip(
                        text = command,
                        colors = colors,
                        onClick = { onSuggestionClick(command) }
                    )
                }
            }
        }
    }
}

// ============================================================================
// PREVIEW
// ============================================================================

@Preview(showBackground = true, backgroundColor = 0xFF000000)
@Composable
private fun VoiceAssistantOverlayPreview() {
    val sampleMessages = listOf(
        ConversationMessage(
            text = "Open the camera app",
            isUser = true
        ),
        ConversationMessage(
            text = "Opening Camera app for you...",
            isUser = false
        ),
        ConversationMessage(
            text = "What's on my screen?",
            isUser = true
        ),
        ConversationMessage(
            text = "I can see the Camera app is now open. You're viewing through the main camera. Would you like me to take a photo or switch cameras?",
            isUser = false
        )
    )
    
    MaterialTheme {
        VoiceAssistantOverlay(
            state = VoiceAssistantState(
                isVisible = true,
                messages = sampleMessages,
                serverConnected = true
            ),
            callbacks = VoiceAssistantCallbacks()
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF000000)
@Composable
private fun VoiceAssistantOverlayListeningPreview() {
    MaterialTheme {
        VoiceAssistantOverlay(
            state = VoiceAssistantState(
                isVisible = true,
                isListening = true,
                partialTranscript = "Open the...",
                audioAmplitude = 0.7f,
                suggestedCommands = listOf("Open camera", "Turn on WiFi", "What's on screen?"),
                recentCommands = listOf("Open settings", "Call mom")
            ),
            callbacks = VoiceAssistantCallbacks()
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF000000)
@Composable
private fun VoiceAssistantOverlayProcessingPreview() {
    MaterialTheme {
        VoiceAssistantOverlay(
            state = VoiceAssistantState(
                isVisible = true,
                isProcessing = true,
                processingContext = "Analyzing screen...",
                messages = listOf(
                    ConversationMessage(
                        text = "What's on my screen?",
                        isUser = true
                    )
                ),
                serverConnected = true
            ),
            callbacks = VoiceAssistantCallbacks()
        )
    }
}
