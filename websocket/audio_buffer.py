"""Audio buffer for WebSocket streaming."""


class AudioBuffer:
    """Buffer for managing streaming audio chunks with overflow protection."""

    def __init__(self, threshold: int = 16000, max_size: int = 1024 * 1024):
        self.chunks = []
        self.total_size = 0
        self.threshold = threshold
        self.max_size = max_size

    def add_chunk(self, chunk: bytes) -> bool:
        """
        Add audio chunk to buffer.

        Args:
            chunk: Audio data chunk

        Returns:
            True if buffer is ready for processing (total >= threshold)
        """
        if len(chunk) == 0:
            return False

        if self.total_size + len(chunk) > self.max_size:
            from utils.logger import get_logger
            get_logger(__name__).warning("AudioBuffer full, clearing old data")
            self.clear()

        self.chunks.append(chunk)
        self.total_size += len(chunk)

        return self.total_size >= self.threshold

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
