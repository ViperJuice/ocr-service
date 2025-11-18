"""
Snapshot Accumulator

Throttles database writes by accumulating text chunks and flushing based on:
- Time threshold (e.g., every 100ms)
- Token threshold (e.g., every 50 tokens)

This prevents database write amplification when streaming large volumes of tokens.
"""
import time
from typing import Optional


class SnapshotAccumulator:
    """Accumulates text chunks and flushes based on time/token thresholds."""

    def __init__(
        self,
        throttle_ms: int = 100,
        throttle_tokens: int = 50,
        force_flush_on_final: bool = True
    ):
        """
        Initialize snapshot accumulator.

        Args:
            throttle_ms: Minimum milliseconds between flushes (default: 100ms)
            throttle_tokens: Maximum tokens before forcing flush (default: 50)
            force_flush_on_final: Always flush on final chunk (default: True)
        """
        self.throttle_ms = throttle_ms
        self.throttle_tokens = throttle_tokens
        self.force_flush_on_final = force_flush_on_final

        # Internal state
        self.buffer = ""
        self.last_flush_time = time.time()
        self.token_count = 0

    def add_chunk(self, chunk: str, is_final: bool = False) -> Optional[str]:
        """
        Add chunk to buffer. Returns accumulated text if threshold met.

        Args:
            chunk: Text chunk to add
            is_final: Whether this is the final chunk in the stream

        Returns:
            Accumulated text if flush threshold met, None otherwise
        """
        # Add chunk to buffer
        self.buffer += chunk
        self.token_count += 1

        # Check if we should flush
        if self._should_flush(is_final):
            return self.flush()

        return None

    def _should_flush(self, is_final: bool = False) -> bool:
        """
        Check if buffer should be flushed.

        Args:
            is_final: Whether this is the final chunk

        Returns:
            True if buffer should be flushed
        """
        # Always flush final chunk
        if is_final and self.force_flush_on_final:
            return True

        # Flush if token threshold exceeded
        if self.token_count >= self.throttle_tokens:
            return True

        # Flush if time threshold exceeded
        current_time = time.time()
        elapsed_ms = (current_time - self.last_flush_time) * 1000
        if elapsed_ms >= self.throttle_ms:
            return True

        return False

    def flush(self) -> str:
        """
        Flush buffer and return accumulated text.

        Returns:
            Accumulated text (may be empty)
        """
        result = self.buffer
        self.buffer = ""
        self.token_count = 0
        self.last_flush_time = time.time()
        return result

    def get_current_snapshot(self) -> str:
        """
        Get current buffer contents without flushing.

        Returns:
            Current accumulated text
        """
        return self.buffer

    def has_buffered_content(self) -> bool:
        """
        Check if there's unflushed content in buffer.

        Returns:
            True if buffer is not empty
        """
        return len(self.buffer) > 0

    def reset(self):
        """Reset accumulator state (for reuse)."""
        self.buffer = ""
        self.token_count = 0
        self.last_flush_time = time.time()
