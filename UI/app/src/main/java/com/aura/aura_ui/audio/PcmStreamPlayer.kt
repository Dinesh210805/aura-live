package com.aura.aura_ui.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log

/**
 * Streaming PCM audio player for Gemini Live audio responses.
 *
 * Uses AudioTrack.MODE_STREAM so chunks can be written incrementally as they
 * arrive from the WebSocket — no need to buffer the entire clip before playback.
 *
 * Gemini Live 2.0 outputs 24 kHz mono 16-bit little-endian PCM.
 *
 * Thread-safety: start() and stop() are @Synchronized. writeChunk() captures
 * a local reference to audioTrack so it is safe to call concurrently with stop().
 */
class PcmStreamPlayer {

    companion object {
        private const val TAG = "PcmStreamPlayer"

        /** Gemini Live 2.0 audio output format. */
        const val SAMPLE_RATE = 24000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_OUT_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    }

    @Volatile
    private var audioTrack: AudioTrack? = null

    val isPlaying: Boolean get() = audioTrack != null

    /**
     * Allocate and start the AudioTrack. Safe to call multiple times —
     * calling [start] while already playing is a no-op.
     * Thread-safe: synchronized on this instance.
     */
    @Synchronized
    fun start() {
        if (audioTrack != null) return

        val minBuffer = AudioTrack.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        if (minBuffer == AudioTrack.ERROR || minBuffer == AudioTrack.ERROR_BAD_VALUE) {
            Log.e(TAG, "AudioTrack.getMinBufferSize failed: $minBuffer")
            return
        }
        // 4× minBuffer gives comfortable headroom for network jitter.
        val bufferSize = maxOf(minBuffer * 4, 16384)

        try {
            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AUDIO_FORMAT)
                        .setSampleRate(SAMPLE_RATE)
                        .setChannelMask(CHANNEL_CONFIG)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack?.play()
            Log.d(TAG, "PcmStreamPlayer started: ${SAMPLE_RATE} Hz mono 16-bit, buffer=$bufferSize bytes")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create AudioTrack: ${e.message}", e)
            audioTrack = null
        }
    }

    /**
     * Write raw PCM bytes to the AudioTrack.
     * Call this from a background thread (write() blocks while the buffer fills up).
     *
     * Captures audioTrack reference locally so concurrent stop() calls are safe.
     *
     * @param pcmBytes raw 24 kHz mono 16-bit little-endian PCM data.
     */
    fun writeChunk(pcmBytes: ByteArray) {
        val track = audioTrack ?: return  // safe: @Volatile read

        var offset = 0
        while (offset < pcmBytes.size) {
            val written = track.write(pcmBytes, offset, pcmBytes.size - offset)
            when {
                written > 0 -> offset += written
                written == AudioTrack.ERROR_INVALID_OPERATION -> {
                    Log.w(TAG, "AudioTrack.write: INVALID_OPERATION — track stopped?")
                    break
                }
                else -> break
            }
        }
    }

    /**
     * Stop playback and release the AudioTrack.
     * Safe to call even if already stopped.
     * Thread-safe: synchronized on this instance.
     */
    @Synchronized
    fun stop() {
        val track = audioTrack ?: return
        audioTrack = null
        try {
            track.stop()
            track.flush()
            track.release()
            Log.d(TAG, "PcmStreamPlayer stopped")
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping PcmStreamPlayer: ${e.message}")
        }
    }
}
