"""
Tests for rate limiter.
"""

from unittest.mock import patch

from django.test import TestCase

from ..rate_limiter import TokenBucket, RateLimiter
from ..exceptions import RateLimitException


class TestRateLimiter(TestCase):
    """Test cases for rate limiter."""

    def test_token_bucket_consume(self):
        """Test token bucket consumption."""
        bucket = TokenBucket(rate=1.0, capacity=5)  # 1 token/sec, 5 max

        # Should be able to consume initial tokens
        self.assertTrue(bucket.consume(3))
        self.assertEqual(bucket.tokens, 2)

        # Should not be able to consume more than available
        self.assertFalse(bucket.consume(3))

        # Wait and check replenishment
        with patch(
            "time.time", side_effect=[bucket.last_update, bucket.last_update + 2]
        ):
            # After 2 seconds, should have 4 tokens
            self.assertTrue(bucket.consume(2))

    def test_rate_limiter_check(self):
        """Test rate limiter checking."""
        limiter = RateLimiter()

        # First request should pass
        allowed, retry_after = limiter.check_rate_limit("openai/gpt-3.5-turbo")
        self.assertTrue(allowed)
        self.assertIsNone(retry_after)

        # Consume all tokens
        bucket = limiter._get_bucket("openai/gpt-3.5-turbo")
        bucket.tokens = 0

        # Next request should be rate limited
        allowed, retry_after = limiter.check_rate_limit("openai/gpt-3.5-turbo")
        self.assertFalse(allowed)
        self.assertIsNotNone(retry_after)
        self.assertGreater(retry_after, 0)

    def test_wait_if_needed(self):
        """Test waiting for rate limit."""
        limiter = RateLimiter()

        # Consume all tokens
        bucket = limiter._get_bucket("test/model")
        bucket.tokens = 0
        bucket.rate = 10  # Fast replenishment for test

        with patch("time.sleep") as mock_sleep:
            limiter.wait_if_needed("test/model", max_wait=1.0)
            mock_sleep.assert_called_once()

    def test_wait_raises_on_long_wait(self):
        """Test rate limiter raises exception on long wait."""
        limiter = RateLimiter()

        # Consume all tokens with slow replenishment
        bucket = limiter._get_bucket("test/model")
        bucket.tokens = 0
        bucket.rate = 0.01  # Very slow replenishment

        with self.assertRaises(RateLimitException):
            limiter.wait_if_needed("test/model", max_wait=0.1)
