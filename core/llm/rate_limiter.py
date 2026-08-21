"""
Rate limiter for OpenRouter API calls with per-model limits.
"""

import time
import logging
from typing import Dict, Optional, Tuple
from threading import Lock

from django.core.cache import cache

from .exceptions import RateLimitException
from .constants import DEFAULT_RATE_LIMIT, DEFAULT_BURST_SIZE

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens replenished per second
            capacity: Maximum bucket capacity (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False otherwise
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
            Seconds until tokens are available
        """
        with self.lock:
            if self.tokens >= tokens:
                return 0

            deficit = tokens - self.tokens
            return deficit / self.rate


class RateLimiter:
    """
    Rate limiter for OpenRouter API with per-model limits.

    Uses both in-memory token buckets and Redis for distributed rate limiting.
    """

    CACHE_KEY_PREFIX = "openrouter:ratelimit:"

    def __init__(self):
        """Initialize rate limiter."""
        self.buckets: Dict[str, TokenBucket] = {}
        self.lock = Lock()

        # Default limits per model tier
        self.model_limits = {
            # Fast models with higher limits
            "gpt-3.5-turbo": (100, 20),  # (rate/sec, burst)
            "claude-instant": (100, 20),
            "gemini-flash": (100, 20),
            # Balanced models
            "gpt-4-turbo": (50, 10),
            "claude-3-haiku": (50, 10),
            "gemini-pro": (50, 10),
            # Quality models with lower limits
            "gpt-4": (20, 5),
            "claude-3-opus": (20, 5),
            "gemini-ultra": (20, 5),
            # Default for unknown models
            "default": (DEFAULT_RATE_LIMIT / 60, DEFAULT_BURST_SIZE),
        }

    def _get_bucket(self, model_id: str) -> TokenBucket:
        """Get or create token bucket for a model."""
        with self.lock:
            if model_id not in self.buckets:
                # Extract base model name
                base_model = model_id.split("/")[-1] if "/" in model_id else model_id

                # Find matching limit config
                rate, capacity = self.model_limits.get("default")
                for model_pattern, limits in self.model_limits.items():
                    if model_pattern in base_model.lower():
                        rate, capacity = limits
                        break

                self.buckets[model_id] = TokenBucket(rate, capacity)

            return self.buckets[model_id]

    def check_rate_limit(
        self, model_id: str, project_id: Optional[str] = None, tokens: int = 1
    ) -> Tuple[bool, Optional[float]]:
        """
        Check if request is within rate limits.

        Args:
            model_id: Model identifier
            project_id: Optional project ID for project-level limits
            tokens: Number of tokens to consume

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        # Check distributed rate limit first (if Redis available)
        if self._check_distributed_limit(model_id, project_id):
            # Then check local token bucket
            bucket = self._get_bucket(model_id)
            if bucket.consume(tokens):
                return True, None
            else:
                retry_after = bucket.time_until_tokens(tokens)
                return False, retry_after

        # Distributed limit exceeded
        return False, 60.0  # Default retry after 60 seconds

    def _check_distributed_limit(
        self, model_id: str, project_id: Optional[str] = None
    ) -> bool:
        """
        Check distributed rate limit using Redis.

        Uses sliding window algorithm for accuracy.
        """
        try:
            # Create cache key
            if project_id:
                cache_key = f"{self.CACHE_KEY_PREFIX}{project_id}:{model_id}"
            else:
                cache_key = f"{self.CACHE_KEY_PREFIX}global:{model_id}"

            # Current window
            now = time.time()
            now - 60  # 1-minute window

            # Get request count in current window
            request_count = cache.get(f"{cache_key}:count", 0)

            # Get limit for this model
            base_model = model_id.split("/")[-1] if "/" in model_id else model_id
            rate_limit = DEFAULT_RATE_LIMIT

            for model_pattern in self.model_limits:
                if model_pattern in base_model.lower():
                    # Convert per-second rate to per-minute
                    rate_limit = int(self.model_limits[model_pattern][0] * 60)
                    break

            if request_count >= rate_limit:
                logger.warning(
                    f"Rate limit exceeded for {model_id}: "
                    f"{request_count}/{rate_limit} requests in window"
                )
                return False

            # Increment counter
            cache.set(
                f"{cache_key}:count",
                request_count + 1,
                timeout=60,  # Expire after 1 minute
            )

            return True

        except Exception as e:
            # If Redis fails, fall back to allowing request
            logger.error(f"Distributed rate limit check failed: {e}")
            return True

    def wait_if_needed(
        self, model_id: str, project_id: Optional[str] = None, max_wait: float = 60.0
    ):
        """
        Wait if rate limited, up to max_wait seconds.

        Args:
            model_id: Model identifier
            project_id: Optional project ID
            max_wait: Maximum seconds to wait

        Raises:
            RateLimitException: If wait time exceeds max_wait
        """
        allowed, retry_after = self.check_rate_limit(model_id, project_id)

        if not allowed:
            if retry_after and retry_after <= max_wait:
                logger.info(f"Rate limited for {model_id}, waiting {retry_after:.2f}s")
                time.sleep(retry_after)
            else:
                raise RateLimitException(
                    f"Rate limit exceeded for {model_id}. "
                    f"Retry after {retry_after:.2f} seconds"
                )

    def reset_limits(self, model_id: Optional[str] = None):
        """
        Reset rate limits for testing or admin purposes.

        Args:
            model_id: Specific model to reset, or None for all
        """
        with self.lock:
            if model_id:
                if model_id in self.buckets:
                    del self.buckets[model_id]
                # Clear Redis counters
                cache.delete_pattern(f"{self.CACHE_KEY_PREFIX}*:{model_id}:*")
            else:
                self.buckets.clear()
                # Clear all Redis counters
                cache.delete_pattern(f"{self.CACHE_KEY_PREFIX}*")

    def get_limits_info(self, model_id: str) -> Dict[str, any]:
        """
        Get current rate limit information for a model.

        Args:
            model_id: Model identifier

        Returns:
            Dictionary with limit information
        """
        bucket = self._get_bucket(model_id)

        with bucket.lock:
            # Update tokens to current state
            now = time.time()
            elapsed = now - bucket.last_update
            current_tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.rate)

            return {
                "model_id": model_id,
                "rate_per_second": bucket.rate,
                "burst_capacity": bucket.capacity,
                "current_tokens": current_tokens,
                "tokens_available": current_tokens >= 1,
                "time_until_available": bucket.time_until_tokens(1)
                if current_tokens < 1
                else 0,
            }
