"""Audio buffer for WebSocket streaming."""


class AudioBuffer:
    """Buffer for managing streaming audio chunks."""

    def __init__(self):
        self.chunks = []
        self.total_size = 0
        self.max_buffer_size = 1024 * 1024  # 1MB buffer

    def add_chunk(self, chunk: bytes) -> bool:
        """Add audio chunk to buffer. Returns True if buffer is ready for processing."""
        if len(chunk) == 0:
            return False

        self.chunks.append(chunk)
        self.total_size += len(chunk)

        return self.total_size >= 16000  # ~1 second of audio at 16kHz

    def get_audio_data(self) -> bytes:
        """Get combined audio data and reset buffer."""
        if not self.chunks:
            return b""

        audio_data = b"".join(self.chunks)
        self.chunks.clear()
        self.total_size = 0
        return audio_data

    def clear(self):
        """Clear the buffer."""
        self.chunks.clear()
        self.total_size = 0
