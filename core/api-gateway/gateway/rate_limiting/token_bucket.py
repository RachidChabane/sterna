"""Token bucket algorithm for in-memory rate limiting."""

import time
from threading import Lock


class TokenBucket:
    """
    Token bucket implementation for rate limiting.

    Provides smooth rate limiting with burst allowance.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens replenished per second
            capacity: Maximum bucket capacity (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if not enough tokens
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Replenish tokens based on elapsed time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            # Try to consume
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    def time_until_tokens(self, tokens: int = 1) -> float:
        """
        Calculate time until tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens are available, 0 if available now
        """
        with self.lock:
            # Update current token count
            now = time.time()
            elapsed = now - self.last_update
            current_tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if current_tokens >= tokens:
                return 0.0

            deficit = tokens - current_tokens
            return deficit / self.rate

    @property
    def available_tokens(self) -> float:
        """Get current number of available tokens."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            return min(self.capacity, self.tokens + elapsed * self.rate)
