"""Tests for rate limiting."""

import time

import pytest

from gateway.rate_limiting.token_bucket import TokenBucket


class TestTokenBucket:
    """Test token bucket algorithm."""

    def test_consume_available_tokens(self):
        """Test consuming when tokens are available."""
        bucket = TokenBucket(rate=10.0, capacity=10)

        assert bucket.consume(1) is True
        assert bucket.consume(1) is True

    def test_consume_exceeds_capacity(self):
        """Test consuming more than capacity."""
        bucket = TokenBucket(rate=10.0, capacity=5)

        # Consume all tokens
        for _ in range(5):
            assert bucket.consume(1) is True

        # Next should fail
        assert bucket.consume(1) is False

    def test_tokens_replenish(self):
        """Test that tokens replenish over time."""
        bucket = TokenBucket(rate=100.0, capacity=10)  # 100 per second

        # Consume all
        for _ in range(10):
            bucket.consume(1)

        assert bucket.consume(1) is False

        # Wait for replenishment (0.1 sec = 10 tokens at 100/sec)
        time.sleep(0.15)

        assert bucket.consume(1) is True

    def test_time_until_tokens(self):
        """Test calculating time until tokens available."""
        bucket = TokenBucket(rate=10.0, capacity=10)

        # Consume all
        for _ in range(10):
            bucket.consume(1)

        # Should need to wait ~0.1 seconds for 1 token
        wait_time = bucket.time_until_tokens(1)
        assert 0.05 < wait_time < 0.2

    def test_time_until_tokens_when_available(self):
        """Test time_until_tokens when tokens are available."""
        bucket = TokenBucket(rate=10.0, capacity=10)

        wait_time = bucket.time_until_tokens(1)
        assert wait_time == 0.0

    def test_available_tokens_property(self):
        """Test available_tokens property."""
        bucket = TokenBucket(rate=10.0, capacity=10)

        # Initially full
        assert bucket.available_tokens == 10.0

        # After consuming
        bucket.consume(3)
        assert bucket.available_tokens == pytest.approx(7.0, abs=0.5)

    def test_burst_capacity(self):
        """Test burst capacity allows immediate consumption."""
        bucket = TokenBucket(rate=1.0, capacity=100)  # 1 per sec, but 100 burst

        # Should be able to consume 100 immediately
        for _ in range(100):
            assert bucket.consume(1) is True

        # But 101st should fail
        assert bucket.consume(1) is False
