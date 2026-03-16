package com.aura.aura_ui.presentation.screens

import android.content.Context
import android.media.MediaPlayer
import android.util.Log
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aura.aura_ui.R
import com.aura.aura_ui.data.network.TTSVoiceDto
import com.aura.aura_ui.data.preferences.ThemeManager
import com.aura.aura_ui.data.preferences.ThemeManager.ThemeMode
import com.aura.aura_ui.presentation.utils.AuraHapticType
import com.aura.aura_ui.presentation.utils.rememberHapticFeedback
import com.aura.aura_ui.ui.theme.AppleColors

private const val TAG = "VoiceSettingsScreen"
private const val PREFS_NAME = "aura_voice_settings"
private const val KEY_SELECTED_VOICE = "selected_voice_id"
private const val DEFAULT_VOICE = "en-US-AriaNeural"
private const val KEY_GEMINI_LIVE_VOICE = "gemini_live_voice"
private const val DEFAULT_GEMINI_VOICE = "Charon"

// Gemini Live prebuilt voice definitions
private data class GeminiVoice(val name: String, val description: String, val gender: String)

private val GEMINI_LIVE_VOICES = listOf(
    GeminiVoice("Charon",         "Deep & authoritative",    "male"),
    GeminiVoice("Fenrir",         "Expressive & animated",   "male"),
    GeminiVoice("Puck",           "Upbeat & bright",         "male"),
    GeminiVoice("Gacrux",         "Mature & measured",       "male"),
    GeminiVoice("Achird",         "Casual & friendly",       "male"),
    GeminiVoice("Zubenelgenubi",  "Relaxed & casual",        "male"),
    GeminiVoice("Aoede",          "Bright & clear",          "female"),
    GeminiVoice("Kore",           "Firm & confident",        "female"),
    GeminiVoice("Schedar",        "Even & composed",         "female"),
    GeminiVoice("Pulcherrima",    "Forward & expressive",    "female"),
)

// Local voice definitions - no backend needed
private val LOCAL_VOICES = listOf(
    TTSVoiceDto(
        id = "en-US-AriaNeural",
        name = "Aria",
        description = "Friendly & warm female voice",
        gender = "female",
        accent = "American",
        previewText = "Welcome boss! How can I help you today?"
    ),
    TTSVoiceDto(
        id = "en-US-GuyNeural",
        name = "Guy",
        description = "Professional male voice",
        gender = "male",
        accent = "American",
        previewText = "Hey there boss! I'm ready to assist you."
    ),
    TTSVoiceDto(
        id = "en-US-JennyNeural",
        name = "Jenny",
        description = "Cheerful & energetic female voice",
        gender = "female",
        accent = "American",
        previewText = "Hi boss! Let's get things done together!"
    ),
    TTSVoiceDto(
        id = "en-US-ChristopherNeural",
        name = "Christopher",
        description = "Calm & confident male voice",
        gender = "male",
        accent = "American",
        previewText = "Good to see you boss! What's on the agenda?"
    ),
    TTSVoiceDto(
        id = "en-GB-SoniaNeural",
        name = "Sonia",
        description = "Elegant British female voice",
        gender = "female",
        accent = "British",
        previewText = "Hello boss! Shall we get started?"
    ),
    TTSVoiceDto(
        id = "en-GB-RyanNeural",
        name = "Ryan",
        description = "Sophisticated British male voice",
        gender = "male",
        accent = "British",
        previewText = "At your service, boss! How may I assist you?"
    ),
    TTSVoiceDto(
        id = "en-AU-NatashaNeural",
        name = "Natasha",
        description = "Friendly Australian female voice",
        gender = "female",
        accent = "Australian",
        previewText = "G'day boss! Ready when you are!"
    ),
    TTSVoiceDto(
        id = "en-US-EmmaNeural",
        name = "Emma",
        description = "Clear & articulate female voice",
        gender = "female",
        accent = "American",
        previewText = "Hello boss! I'm here to make your life easier."
    ),
)

// Map voice IDs to local raw resource IDs (pre-bundled audio files)
private val VOICE_PREVIEW_RESOURCES = mapOf(
    "en-US-AriaNeural" to R.raw.voice_preview_en_us_arianeural,
    "en-US-GuyNeural" to R.raw.voice_preview_en_us_guyneural,
    "en-US-JennyNeural" to R.raw.voice_preview_en_us_jennyneural,
    "en-US-ChristopherNeural" to R.raw.voice_preview_en_us_christopherneural,
    "en-GB-SoniaNeural" to R.raw.voice_preview_en_gb_sonianeural,
    "en-GB-RyanNeural" to R.raw.voice_preview_en_gb_ryanneural,
    "en-AU-NatashaNeural" to R.raw.voice_preview_en_au_natashaneural,
    "en-US-EmmaNeural" to R.raw.voice_preview_en_us_emmaneural,
)

/**
 * Apple-Inspired Voice Settings Screen
 * Allows users to select and preview TTS voices
 */
@Composable
fun VoiceSettingsScreen(
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val systemDark = isSystemInDarkTheme()
    val themeMode by ThemeManager.themeMode.collectAsState()
    
    val isDark = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> systemDark
    }
    
    val context = LocalContext.current
    
    // Haptic feedback
    val hapticFeedback = rememberHapticFeedback()
    
    // State - use local voices, no loading needed
    val voices = remember { LOCAL_VOICES }
    val prefs = remember { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    var currentVoiceId by remember { mutableStateOf(prefs.getString(KEY_SELECTED_VOICE, DEFAULT_VOICE) ?: DEFAULT_VOICE) }
    var geminiLiveVoice by remember { mutableStateOf(prefs.getString(KEY_GEMINI_LIVE_VOICE, DEFAULT_GEMINI_VOICE) ?: DEFAULT_GEMINI_VOICE) }
    var previewingVoiceId by remember { mutableStateOf<String?>(null) }
    var isPlaying by remember { mutableStateOf(false) }
    var mediaPlayer by remember { mutableStateOf<MediaPlayer?>(null) }
    
    // Cleanup media player on dispose
    DisposableEffect(Unit) {
        onDispose {
            mediaPlayer?.release()
        }
    }
    
    // Colors
    val backgroundColor = if (isDark) AppleColors.Dark.Background else AppleColors.Light.Background
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo
    

    
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(backgroundColor)
            .systemBarsPadding()
    ) {
        // Navigation Bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = {
                hapticFeedback(AuraHapticType.SELECTION)
                onNavigateBack()
            }) {
                Icon(
                    imageVector = Icons.Default.ArrowBackIosNew,
                    contentDescription = "Back",
                    tint = accentColor,
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "Settings",
                    color = accentColor,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            
            Spacer(modifier = Modifier.weight(1f))
            
            Text(
                text = "Voice",
                style = MaterialTheme.typography.titleMedium.copy(
                    fontWeight = FontWeight.SemiBold
                ),
                color = labelPrimary,
            )
            
            Spacer(modifier = Modifier.weight(1f))
            Spacer(modifier = Modifier.width(80.dp))
        }
        
        // Content - voices are local, no loading needed
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Current voice highlight
            item {
                Spacer(modifier = Modifier.height(8.dp))
                val currentVoice = voices.find { it.id == currentVoiceId }
                if (currentVoice != null) {
                    CurrentVoiceHeader(
                        voice = currentVoice,
                        isDark = isDark,
                        isPreviewing = previewingVoiceId == currentVoice.id && isPlaying,
                        onPreview = {
                            // Stop any currently playing audio
                            mediaPlayer?.release()
                            
                            val resourceId = VOICE_PREVIEW_RESOURCES[currentVoice.id]
                            if (resourceId != null) {
                                previewingVoiceId = currentVoice.id
                                isPlaying = true
                                
                                try {
                                    val player = MediaPlayer.create(context, resourceId)
                                    mediaPlayer = player
                                    player.setOnCompletionListener {
                                        isPlaying = false
                                        previewingVoiceId = null
                                        player.release()
                                        mediaPlayer = null
                                    }
                                    player.start()
                                } catch (e: Exception) {
                                    Log.e(TAG, "Failed to play preview", e)
                                    isPlaying = false
                                    previewingVoiceId = null
                                }
                            }
                        },
                        onStop = {
                            mediaPlayer?.stop()
                            mediaPlayer?.release()
                            mediaPlayer = null
                            isPlaying = false
                            previewingVoiceId = null
                        }
                    )
                }
            }
            
            item {
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "ALL VOICES",
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontWeight = FontWeight.Normal,
                        letterSpacing = 0.5.sp
                    ),
                    color = labelSecondary,
                    modifier = Modifier.padding(start = 16.dp, bottom = 4.dp)
                )
            }
            
            items(voices) { voice ->
                        VoiceCard(
                            voice = voice,
                            isSelected = voice.id == currentVoiceId,
                            isPreviewing = previewingVoiceId == voice.id && isPlaying,
                            isDark = isDark,
                            onSelect = {
                                // Haptic feedback for selection
                                hapticFeedback(AuraHapticType.LIGHT)
                                // Save selection locally
                                prefs.edit().putString(KEY_SELECTED_VOICE, voice.id).apply()
                                currentVoiceId = voice.id
                                Log.d(TAG, "Voice selected: ${voice.id}")
                            },
                            onPreview = {
                                // Stop any currently playing audio
                                mediaPlayer?.release()
                                
                                // Get local resource for this voice
                                val resourceId = VOICE_PREVIEW_RESOURCES[voice.id]
                                if (resourceId != null) {
                                    previewingVoiceId = voice.id
                                    isPlaying = true
                                    
                                    try {
                                        val player = MediaPlayer.create(context, resourceId)
                                        mediaPlayer = player
                                        player.setOnCompletionListener {
                                            isPlaying = false
                                            previewingVoiceId = null
                                            player.release()
                                            mediaPlayer = null
                                        }
                                        player.start()
                                    } catch (e: Exception) {
                                        Log.e(TAG, "Failed to play preview", e)
                                        isPlaying = false
                                        previewingVoiceId = null
                                    }
                                } else {
                                    Log.e(TAG, "No preview resource for voice: ${voice.id}")
                                }
                            }
                        )
                    }
                    
                    // ── Gemini Live Voice section ─────────────────────────────
                    item {
                        Spacer(modifier = Modifier.height(24.dp))
                        Text(
                            text = "GEMINI LIVE VOICE",
                            style = MaterialTheme.typography.bodySmall.copy(
                                fontWeight = FontWeight.Normal,
                                letterSpacing = 0.5.sp
                            ),
                            color = labelSecondary,
                            modifier = Modifier.padding(start = 16.dp, bottom = 4.dp)
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Used when Gemini Live Mode is enabled in Settings",
                            style = MaterialTheme.typography.labelSmall,
                            color = labelSecondary.copy(alpha = 0.7f),
                            modifier = Modifier.padding(start = 16.dp, bottom = 8.dp)
                        )
                    }

                    items(GEMINI_LIVE_VOICES) { voice ->
                        GeminiVoiceCard(
                            voice = voice,
                            isSelected = voice.name == geminiLiveVoice,
                            isDark = isDark,
                            onSelect = {
                                hapticFeedback(AuraHapticType.LIGHT)
                                prefs.edit().putString(KEY_GEMINI_LIVE_VOICE, voice.name).apply()
                                geminiLiveVoice = voice.name
                                Log.d(TAG, "Gemini Live voice selected: ${voice.name}")
                            }
                        )
                    }

                    item {
                        Spacer(modifier = Modifier.height(32.dp))
                    }
                }
    }
}

/**
 * Header showing the currently selected voice with prominent styling
 */
@Composable
private fun CurrentVoiceHeader(
    voice: TTSVoiceDto,
    isDark: Boolean,
    isPreviewing: Boolean,
    onPreview: () -> Unit,
    onStop: () -> Unit,
) {
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo
    val genderColor = when (voice.gender.lowercase()) {
        "female" -> if (isDark) AppleColors.PinkDark else AppleColors.Pink
        else -> if (isDark) AppleColors.BlueDark else AppleColors.Blue
    }
    
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = groupBackground,
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Avatar with gradient ring
            Box(
                modifier = Modifier
                    .size(80.dp)
                    .clip(CircleShape)
                    .border(3.dp, accentColor, CircleShape)
                    .background(genderColor.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.RecordVoiceOver,
                    contentDescription = null,
                    tint = genderColor,
                    modifier = Modifier.size(40.dp)
                )
            }
            
            Spacer(modifier = Modifier.height(12.dp))
            
            Text(
                text = "Current Voice",
                style = MaterialTheme.typography.labelMedium,
                color = labelSecondary,
            )
            
            Text(
                text = voice.name,
                style = MaterialTheme.typography.headlineSmall.copy(
                    fontWeight = FontWeight.Bold
                ),
                color = labelPrimary,
            )
            
            Spacer(modifier = Modifier.height(4.dp))
            
            Text(
                text = voice.description,
                style = MaterialTheme.typography.bodyMedium,
                color = labelSecondary,
            )
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Play/Stop button
            Button(
                onClick = if (isPreviewing) onStop else onPreview,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isPreviewing) 
                        (if (isDark) AppleColors.RedDark else AppleColors.Red)
                    else accentColor
                ),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(0.6f)
            ) {
                Icon(
                    imageVector = if (isPreviewing) Icons.Default.Stop else Icons.Default.PlayArrow,
                    contentDescription = if (isPreviewing) "Stop" else "Preview",
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = if (isPreviewing) "Stop Preview" else "Play Preview",
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }
    }
}

@Composable
private fun GeminiVoiceCard(
    voice: GeminiVoice,
    isSelected: Boolean,
    isDark: Boolean,
    onSelect: () -> Unit,
) {
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) Color(0xFF4285F4) else Color(0xFF1A73E8) // Google blue for Gemini
    val selectedBorderColor by animateColorAsState(
        targetValue = if (isSelected) accentColor else Color.Transparent,
        animationSpec = tween(200),
        label = "gemini_border_color"
    )
    val genderColor = if (voice.gender == "female") {
        if (isDark) AppleColors.PinkDark else AppleColors.Pink
    } else {
        if (isDark) AppleColors.BlueDark else AppleColors.Blue
    }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = if (isSelected) 2.dp else 0.dp,
                color = selectedBorderColor,
                shape = RoundedCornerShape(12.dp)
            )
            .clickable(onClick = onSelect),
        color = groupBackground,
        shape = RoundedCornerShape(12.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Avatar
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(genderColor.copy(alpha = 0.12f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.AutoAwesome,
                    contentDescription = null,
                    tint = accentColor,
                    modifier = Modifier.size(26.dp)
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Voice info
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = voice.name,
                        style = MaterialTheme.typography.bodyLarge.copy(
                            fontWeight = FontWeight.SemiBold
                        ),
                        color = labelPrimary,
                    )
                    if (isSelected) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Icon(
                            imageVector = Icons.Default.CheckCircle,
                            contentDescription = "Selected",
                            tint = accentColor,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = voice.description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = labelSecondary,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = genderColor.copy(alpha = 0.15f),
                ) {
                    Text(
                        text = voice.gender.replaceFirstChar { it.uppercaseChar() },
                        style = MaterialTheme.typography.labelSmall,
                        color = genderColor,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun VoiceCard(
    voice: TTSVoiceDto,
    isSelected: Boolean,
    isPreviewing: Boolean,
    isDark: Boolean,
    onSelect: () -> Unit,
    onPreview: () -> Unit,
) {
    val groupBackground = if (isDark) AppleColors.Dark.Surface else AppleColors.Light.Surface
    val labelPrimary = if (isDark) AppleColors.LabelDark.Primary else AppleColors.LabelLight.Primary
    val labelSecondary = if (isDark) AppleColors.LabelDark.Secondary else AppleColors.LabelLight.Secondary
    val accentColor = if (isDark) AppleColors.IndigoDark else AppleColors.Indigo
    val selectedBorderColor by animateColorAsState(
        targetValue = if (isSelected) accentColor else Color.Transparent,
        animationSpec = tween(200),
        label = "border_color"
    )
    
    // Gender icon colors
    val genderColor = when (voice.gender.lowercase()) {
        "female" -> if (isDark) AppleColors.PinkDark else AppleColors.Pink
        else -> if (isDark) AppleColors.BlueDark else AppleColors.Blue
    }
    
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = if (isSelected) 2.dp else 0.dp,
                color = selectedBorderColor,
                shape = RoundedCornerShape(12.dp)
            )
            .clickable(onClick = onSelect),
        color = groupBackground,
        shape = RoundedCornerShape(12.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Avatar
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(genderColor.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = if (voice.gender.lowercase() == "female") 
                        Icons.Default.Face else Icons.Default.Face,
                    contentDescription = null,
                    tint = genderColor,
                    modifier = Modifier.size(28.dp)
                )
            }
            
            Spacer(modifier = Modifier.width(16.dp))
            
            // Voice Info
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = voice.name,
                        style = MaterialTheme.typography.bodyLarge.copy(
                            fontWeight = FontWeight.SemiBold
                        ),
                        color = labelPrimary,
                    )
                    if (isSelected) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Icon(
                            imageVector = Icons.Default.CheckCircle,
                            contentDescription = "Selected",
                            tint = accentColor,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = voice.description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = labelSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Accent chip
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = if (isDark) AppleColors.Dark.Fill else AppleColors.Light.Fill,
                    ) {
                        Text(
                            text = voice.accent,
                            style = MaterialTheme.typography.labelSmall,
                            color = labelSecondary,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                    // Gender chip
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = genderColor.copy(alpha = 0.15f),
                    ) {
                        Text(
                            text = voice.gender.replaceFirstChar { it.uppercaseChar() },
                            style = MaterialTheme.typography.labelSmall,
                            color = genderColor,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.width(12.dp))
            
            // Preview button
            IconButton(
                onClick = onPreview,
                modifier = Modifier
                    .size(44.dp)
                    .clip(CircleShape)
                    .background(accentColor.copy(alpha = 0.1f))
            ) {
                if (isPreviewing) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color = accentColor,
                    )
                } else {
                    Icon(
                        imageVector = Icons.Default.PlayArrow,
                        contentDescription = "Preview voice",
                        tint = accentColor,
                        modifier = Modifier.size(24.dp)
                    )
                }
            }
        }
    }
}


