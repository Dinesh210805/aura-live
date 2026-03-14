package com.aura.aura_ui.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Simple WAV audio player that uses AudioTrack for reliable playback.
 * Handles WAV files from Groq TTS and other sources.
 */
object WavAudioPlayer {
    private const val TAG = "WavAudioPlayer"

    /**
     * WAV header information
     */
    data class WavHeader(
        val audioFormat: Int, // 1 = PCM
        val numChannels: Int, // 1 = mono, 2 = stereo
        val sampleRate: Int, // e.g., 24000, 44100
        val bitsPerSample: Int, // 8 or 16
        val dataOffset: Int, // where PCM data starts
        val dataSize: Int, // size of PCM data
    )

    /**
     * Parse WAV header from byte array
     */
    fun parseWavHeader(wavData: ByteArray): WavHeader? {
        try {
            if (wavData.size < 44) {
                Log.e(TAG, "WAV data too small: ${wavData.size} bytes")
                return null
            }

            val buffer = ByteBuffer.wrap(wavData).order(ByteOrder.LITTLE_ENDIAN)

            // Read RIFF header
            val riff = ByteArray(4)
            buffer.get(riff)
            if (String(riff) != "RIFF") {
                Log.e(TAG, "Invalid RIFF header: ${String(riff)}")
                return null
            }

            buffer.getInt() // file size - 8

            val wave = ByteArray(4)
            buffer.get(wave)
            if (String(wave) != "WAVE") {
                Log.e(TAG, "Invalid WAVE header: ${String(wave)}")
                return null
            }

            // Parse chunks
            var audioFormat = 1
            var numChannels = 1
            var sampleRate = 24000
            var bitsPerSample = 16
            var dataOffset = 0
            var dataSize = 0

            while (buffer.remaining() >= 8) {
                val chunkId = ByteArray(4)
                buffer.get(chunkId)
                val chunkIdStr = String(chunkId)
                val chunkSize = buffer.getInt()

                Log.d(TAG, "Chunk: '$chunkIdStr', size: $chunkSize, pos: ${buffer.position()}")

                when (chunkIdStr) {
                    "fmt " -> {
                        if (chunkSize >= 16) {
                            audioFormat = buffer.getShort().toInt() and 0xFFFF
                            numChannels = buffer.getShort().toInt() and 0xFFFF
                            sampleRate = buffer.getInt()
                            buffer.getInt() // byteRate
                            buffer.getShort() // blockAlign
                            bitsPerSample = buffer.getShort().toInt() and 0xFFFF

                            // Skip extra fmt bytes if present
                            val extraBytes = chunkSize - 16
                            if (extraBytes > 0 && buffer.remaining() >= extraBytes) {
                                buffer.position(buffer.position() + extraBytes)
                            }

                            Log.d(TAG, "Format: PCM=$audioFormat, ch=$numChannels, rate=$sampleRate, bits=$bitsPerSample")
                        }
                    }
                    "data" -> {
                        dataOffset = buffer.position()
                        // Handle special cases where chunkSize is -1 (0xFFFFFFFF) or invalid
                        // This can happen with streaming audio or when size is unknown
                        dataSize =
                            if (chunkSize <= 0 || chunkSize > wavData.size) {
                                // Use remaining data from current position to end of file
                                wavData.size - dataOffset
                            } else {
                                minOf(chunkSize, buffer.remaining())
                            }
                        Log.d(TAG, "Data: offset=$dataOffset, size=$dataSize (chunkSize was $chunkSize)")
                        break // Found data chunk, stop parsing
                    }
                    else -> {
                        // Skip unknown chunks
                        if (buffer.remaining() >= chunkSize) {
                            buffer.position(buffer.position() + chunkSize)
                        } else {
                            break
                        }
                    }
                }
            }

            if (dataOffset == 0 || dataSize == 0) {
                Log.e(TAG, "No data chunk found")
                return null
            }

            return WavHeader(audioFormat, numChannels, sampleRate, bitsPerSample, dataOffset, dataSize)
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing WAV header: ${e.message}", e)
            return null
        }
    }

    /**
     * Play WAV audio from base64 encoded string
     */
    suspend fun playBase64Audio(
        base64Audio: String,
        onComplete: () -> Unit,
    ) {
        withContext(Dispatchers.IO) {
            try {
                Log.d(TAG, "🔊 Decoding base64 audio (${base64Audio.length} chars)...")

                val audioData = Base64.decode(base64Audio, Base64.DEFAULT)
                Log.d(TAG, "📦 Decoded: ${audioData.size} bytes")

                playWavData(audioData, onComplete)
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error decoding audio: ${e.message}", e)
                withContext(Dispatchers.Main) { onComplete() }
            }
        }
    }

    /**
     * Play WAV audio from byte array
     */
    suspend fun playWavData(
        wavData: ByteArray,
        onComplete: () -> Unit,
    ) {
        withContext(Dispatchers.IO) {
            var audioTrack: AudioTrack? = null

            try {
                val header = parseWavHeader(wavData)
                if (header == null) {
                    Log.e(TAG, "❌ Failed to parse WAV header")
                    withContext(Dispatchers.Main) { onComplete() }
                    return@withContext
                }

                // Only support PCM format
                if (header.audioFormat != 1) {
                    Log.e(TAG, "❌ Unsupported audio format: ${header.audioFormat} (only PCM=1 supported)")
                    withContext(Dispatchers.Main) { onComplete() }
                    return@withContext
                }

                // Configure channel
                val channelConfig =
                    when (header.numChannels) {
                        1 -> AudioFormat.CHANNEL_OUT_MONO
                        2 -> AudioFormat.CHANNEL_OUT_STEREO
                        else -> {
                            Log.e(TAG, "❌ Unsupported channel count: ${header.numChannels}")
                            withContext(Dispatchers.Main) { onComplete() }
                            return@withContext
                        }
                    }

                // Configure encoding
                val encoding =
                    when (header.bitsPerSample) {
                        8 -> AudioFormat.ENCODING_PCM_8BIT
                        16 -> AudioFormat.ENCODING_PCM_16BIT
                        else -> {
                            Log.e(TAG, "❌ Unsupported bits per sample: ${header.bitsPerSample}")
                            withContext(Dispatchers.Main) { onComplete() }
                            return@withContext
                        }
                    }

                // Calculate buffer size
                val minBufferSize = AudioTrack.getMinBufferSize(header.sampleRate, channelConfig, encoding)
                val bufferSize = maxOf(minBufferSize, header.dataSize)

                Log.d(
                    TAG,
                    "🎵 Creating AudioTrack: ${header.sampleRate}Hz, ${header.numChannels}ch, ${header.bitsPerSample}bit, buffer=$bufferSize",
                )

                // Create AudioTrack with MODE_STATIC for one-shot playback
                audioTrack =
                    AudioTrack.Builder()
                        .setAudioAttributes(
                            AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .build(),
                        )
                        .setAudioFormat(
                            AudioFormat.Builder()
                                .setEncoding(encoding)
                                .setSampleRate(header.sampleRate)
                                .setChannelMask(channelConfig)
                                .build(),
                        )
                        .setBufferSizeInBytes(bufferSize)
                        .setTransferMode(AudioTrack.MODE_STATIC)
                        .build()

                // Extract PCM data with safety checks
                val actualDataEnd = minOf(header.dataOffset + header.dataSize, wavData.size)
                if (header.dataOffset >= wavData.size || header.dataOffset >= actualDataEnd) {
                    Log.e(TAG, "❌ Invalid data range: offset=${header.dataOffset}, end=$actualDataEnd, wavSize=${wavData.size}")
                    withContext(Dispatchers.Main) { onComplete() }
                    return@withContext
                }

                val pcmData = wavData.copyOfRange(header.dataOffset, actualDataEnd)

                Log.d(TAG, "📝 Writing ${pcmData.size} bytes of PCM data...")

                // Write all data at once (MODE_STATIC)
                val written = audioTrack.write(pcmData, 0, pcmData.size)
                if (written < 0) {
                    Log.e(TAG, "❌ AudioTrack write failed: $written")
                    audioTrack.release()
                    withContext(Dispatchers.Main) { onComplete() }
                    return@withContext
                }

                Log.d(TAG, "✅ Wrote $written bytes, starting playback...")

                // Calculate duration
                val bytesPerSample = header.bitsPerSample / 8
                val bytesPerFrame = bytesPerSample * header.numChannels
                val totalFrames = pcmData.size / bytesPerFrame
                val durationMs = (totalFrames * 1000L) / header.sampleRate

                Log.d(TAG, "▶️ Playing audio: $totalFrames frames, ~${durationMs}ms")

                // Set notification for end of playback
                audioTrack.notificationMarkerPosition = totalFrames
                audioTrack.setPlaybackPositionUpdateListener(
                    object : AudioTrack.OnPlaybackPositionUpdateListener {
                        override fun onMarkerReached(track: AudioTrack?) {
                            Log.d(TAG, "✅ Playback marker reached")
                        }

                        override fun onPeriodicNotification(track: AudioTrack?) {}
                    },
                )

                // Start playback
                audioTrack.play()

                // Wait for playback to complete (with timeout)
                val startTime = System.currentTimeMillis()
                val timeout = durationMs + 2000 // Add 2 second buffer

                while (audioTrack.playbackHeadPosition < totalFrames) {
                    if (System.currentTimeMillis() - startTime > timeout) {
                        Log.w(TAG, "⚠️ Playback timeout after ${timeout}ms")
                        break
                    }
                    delay(50)
                }

                Log.d(TAG, "✅ Audio playback completed")
            } catch (e: Exception) {
                Log.e(TAG, "❌ AudioTrack playback error: ${e.message}", e)
            } finally {
                try {
                    audioTrack?.stop()
                    audioTrack?.release()
                } catch (e: Exception) {
                    Log.w(TAG, "Error releasing AudioTrack: ${e.message}")
                }
                withContext(Dispatchers.Main) { onComplete() }
            }
        }
    }
}
