package com.aura.aura_ui.presentation.components

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.conversation.ConversationMessage
import com.aura.aura_ui.conversation.MessageStatus
import com.aura.aura_ui.ui.theme.*

/**
 * Professional enhanced message bubble component
 * Features avatar, timestamp, delivery status, and smooth animations
 */
@Composable
fun EnhancedMessageBubble(
    message: ConversationMessage,
    modifier: Modifier = Modifier,
    showAvatar: Boolean = true,
    showTimestamp: Boolean = true,
    animateEntry: Boolean = true,
) {
    val isUser = message.isUser
    
    // Entry animation
    var visible by remember { mutableStateOf(!animateEntry) }
    LaunchedEffect(Unit) { visible = true }
    
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(animationSpec = tween(300)) + 
                slideInHorizontally(
                    animationSpec = tween(300),
                    initialOffsetX = { if (isUser) it else -it }
                ),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
            verticalAlignment = Alignment.Bottom
        ) {
            // Avatar for assistant
            if (!isUser && showAvatar) {
                MessageAvatar(
                    isUser = false,
                    modifier = Modifier.padding(end = 8.dp)
                )
            }
            
            // Message content
            Column(
                horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
                modifier = Modifier.widthIn(max = 300.dp)
            ) {
                // Message bubble
                Surface(
                    shape = RoundedCornerShape(
                        topStart = 20.dp,
                        topEnd = 20.dp,
                        bottomStart = if (isUser) 20.dp else 6.dp,
                        bottomEnd = if (isUser) 6.dp else 20.dp
                    ),
                    color = if (isUser) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    },
                    tonalElevation = if (isUser) 0.dp else 1.dp,
                ) {
                    Column(
                        modifier = Modifier.padding(
                            horizontal = 16.dp,
                            vertical = 12.dp
                        )
                    ) {
                        // Message text
                        Text(
                            text = message.text,
                            style = MaterialTheme.typography.bodyMedium.copy(
                                fontStyle = if (message.isPartial) FontStyle.Italic else FontStyle.Normal,
                                lineHeight = 22.sp
                            ),
                            color = if (isUser) {
                                Color.White
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            }
                        )
                        
                        // Streaming indicator
                        if (message.isStreaming) {
                            Spacer(modifier = Modifier.height(4.dp))
                            StreamingCursor()
                        }
                    }
                }
                
                // Timestamp and status row
                if (showTimestamp || isUser) {
                    Row(
                        modifier = Modifier.padding(top = 4.dp, start = 4.dp, end = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        if (showTimestamp) {
                            Text(
                                text = message.getRelativeTime(),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                            )
                        }
                        
                        // Status indicator for user messages
                        if (isUser) {
                            MessageStatusIcon(status = message.status)
                        }
                    }
                }
            }
            
            // Avatar for user
            if (isUser && showAvatar) {
                MessageAvatar(
                    isUser = true,
                    modifier = Modifier.padding(start = 8.dp)
                )
            }
        }
    }
}

/**
 * Avatar component for message bubbles
 */
@Composable
fun MessageAvatar(
    isUser: Boolean,
    modifier: Modifier = Modifier,
    size: Int = 36,
) {
    Box(
        modifier = modifier
            .size(size.dp)
            .clip(CircleShape)
            .background(
                if (isUser) {
                    Brush.linearGradient(AuraGradients.Primary)
                } else {
                    Brush.linearGradient(
                        listOf(AuraSecondary, AuraTertiary)
                    )
                }
            ),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            imageVector = if (isUser) Icons.Default.Person else Icons.Default.SmartToy,
            contentDescription = if (isUser) "User" else "AURA",
            tint = Color.White,
            modifier = Modifier.size((size * 0.55f).dp)
        )
    }
}

/**
 * Status icon showing message delivery state
 */
@Composable
private fun MessageStatusIcon(status: MessageStatus) {
    val (icon, tint) = when (status) {
        MessageStatus.SENDING -> Icons.Default.Schedule to AuraNeutral400
        MessageStatus.SENT -> Icons.Default.Check to AuraNeutral400
        MessageStatus.DELIVERED -> Icons.Default.CheckCircle to AuraSuccess
        MessageStatus.ERROR -> Icons.Default.Error to AuraError
    }
    
    Icon(
        imageVector = icon,
        contentDescription = status.name,
        modifier = Modifier.size(14.dp),
        tint = tint
    )
}

/**
 * Blinking cursor for streaming messages
 */
@Composable
private fun StreamingCursor() {
    val infiniteTransition = rememberInfiniteTransition(label = "cursor")
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(500, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "cursor_blink"
    )
    
    Box(
        modifier = Modifier
            .width(2.dp)
            .height(16.dp)
            .background(
                MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha)
            )
    )
}

/**
 * Conversation list with all enhanced features
 */
@Composable
fun EnhancedConversationList(
    messages: List<ConversationMessage>,
    modifier: Modifier = Modifier,
    isAITyping: Boolean = false,
    partialTranscript: String = "",
) {
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        messages.forEach { message ->
            EnhancedMessageBubble(
                message = message,
                showAvatar = true,
                showTimestamp = true
            )
        }
        
        // Show partial user transcript
        if (partialTranscript.isNotEmpty()) {
            EnhancedMessageBubble(
                message = ConversationMessage(
                    text = partialTranscript,
                    isUser = true,
                    isPartial = true,
                    status = MessageStatus.SENDING
                ),
                showTimestamp = false
            )
        }
        
        // Show typing indicator when AI is processing
        if (isAITyping) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Start,
                verticalAlignment = Alignment.Bottom
            ) {
                MessageAvatar(
                    isUser = false,
                    modifier = Modifier.padding(end = 8.dp)
                )
                TypingIndicator()
            }
        }
    }
}

/**
 * Message bubble with gradient background for special messages
 */
@Composable
fun GradientMessageBubble(
    text: String,
    modifier: Modifier = Modifier,
    gradientColors: List<Color> = AuraGradients.Primary,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(20.dp),
        color = Color.Transparent
    ) {
        Box(
            modifier = Modifier
                .background(Brush.linearGradient(gradientColors))
                .padding(horizontal = 20.dp, vertical = 14.dp)
        ) {
            Text(
                text = text,
                style = MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.Medium
                ),
                color = Color.White
            )
        }
    }
}

/**
 * Empty conversation state placeholder
 */
@Composable
fun EmptyConversationState(
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Animated AURA icon
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
                .background(
                    Brush.linearGradient(
                        listOf(
                            AuraPrimary.copy(alpha = 0.1f),
                            AuraSecondary.copy(alpha = 0.1f)
                        )
                    )
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = Icons.Default.SmartToy,
                contentDescription = null,
                modifier = Modifier.size(40.dp),
                tint = AuraPrimary
            )
        }
        
        Text(
            text = "Start a conversation",
            style = MaterialTheme.typography.titleMedium.copy(
                fontWeight = FontWeight.SemiBold
            ),
            color = MaterialTheme.colorScheme.onSurface
        )
        
        Text(
            text = "Tap the microphone to speak or try one of these:",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
        )
        
        // Example prompts
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            ExamplePromptChip(text = "\"Open Settings\"")
            ExamplePromptChip(text = "\"What's the weather like?\"")
            ExamplePromptChip(text = "\"Send a message to...\"")
        }
    }
}

@Composable
private fun ExamplePromptChip(text: String) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            style = MaterialTheme.typography.bodySmall.copy(
                fontStyle = FontStyle.Italic
            ),
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
