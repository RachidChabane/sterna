"""Redis-backed rate limiter using sliding window algorithm."""

import logging
import time
from dataclasses import dataclass

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    retry_after: float | None = None


class RedisRateLimiter:
    """
    Redis-backed rate limiter using sliding window algorithm.

    Uses Lua scripting for atomic operations.
    """

    # Lua script for atomic rate limit check and increment
    RATE_LIMIT_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])

    -- Remove old entries outside the window
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

    -- Count current requests in window
    local count = redis.call('ZCARD', key)

    if count < limit then
        -- Add new request with unique member
        local member = now .. '-' .. math.random(1000000)
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, window)
        return {1, limit - count - 1, now + window}
    else
        -- Rate limited - calculate reset time
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_at = now + window
        if oldest and oldest[2] then
            reset_at = tonumber(oldest[2]) + window
        end
        return {0, 0, reset_at}
    end
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        default_limit: int = 1000,
        default_window: int = 3600,
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Async Redis client
            default_limit: Default requests per window
            default_window: Default window size in seconds
        """
        self.redis = redis_client
        self.default_limit = default_limit
        self.default_window = default_window
        self._script_sha: str | None = None

        # Endpoint-specific limits: (limit, window_seconds)
        self.endpoint_limits: dict[str, tuple[int, int]] = {
            # LLM endpoints - stricter limits
            "/api/v1/llm/completions": (100, 60),
            "/api/v1/llm/chat": (100, 60),
            # Image generation - very strict
            "/api/v1/images/generate": (20, 60),
            # Auth endpoints - prevent brute force
            "/api/v1/auth/login": (10, 60),
            "/api/v1/auth/register": (5, 60),
            "/api/v1/auth/password-reset": (3, 60),
            # Voice rooms
            "/api/v1/voice": (200, 60),
            # Sandbox execution
            "/api/v1/sandbox/execute": (60, 60),
        }

    async def _ensure_script(self) -> str:
        """Ensure Lua script is loaded and return SHA."""
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(self.RATE_LIMIT_SCRIPT)
        return self._script_sha

    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting."""
        # Normalize endpoint - remove trailing slash, query params
        endpoint_key = endpoint.split("?")[0].rstrip("/")
        return f"ratelimit:{identifier}:{endpoint_key}"

    def _get_limits(self, endpoint: str) -> tuple[int, int]:
        """
        Get limit and window for endpoint.

        Returns:
            Tuple of (limit, window_seconds)
        """
        # Check for specific endpoint limit (prefix match)
        for pattern, limits in self.endpoint_limits.items():
            if endpoint.startswith(pattern):
                return limits

        return (self.default_limit, self.default_window)

    async def check(
        self,
        identifier: str,
        endpoint: str,
    ) -> RateLimitResult:
        """
        Check rate limit for identifier + endpoint combination.

        Args:
            identifier: User ID or IP address
            endpoint: Request path

        Returns:
            RateLimitResult with allowed status and metadata
        """
        try:
            key = self._get_key(identifier, endpoint)
            limit, window = self._get_limits(endpoint)
            now = time.time()

            script_sha = await self._ensure_script()
            result = await self.redis.evalsha(
                script_sha,
                1,
                key,
                str(now),
                str(window),
                str(limit),
            )

            allowed, remaining, reset_at = result

            return RateLimitResult(
                allowed=bool(allowed),
                remaining=int(remaining),
                reset_at=float(reset_at),
                retry_after=float(reset_at - now) if not allowed else None,
            )

        except redis.RedisError as e:
            logger.error(f"Rate limit check failed: {e}")
            # Fail open - allow request if Redis is down
            return RateLimitResult(
                allowed=True,
                remaining=self.default_limit,
                reset_at=time.time() + self.default_window,
            )

    async def reset(self, identifier: str, endpoint: str | None = None) -> None:
        """
        Reset rate limits for identifier.

        Args:
            identifier: User ID or IP address
            endpoint: Specific endpoint to reset, or None for all
        """
        try:
            if endpoint:
                key = self._get_key(identifier, endpoint)
                await self.redis.delete(key)
            else:
                # Reset all for identifier
                pattern = f"ratelimit:{identifier}:*"
                async for key in self.redis.scan_iter(pattern):
                    await self.redis.delete(key)
        except redis.RedisError as e:
            logger.error(f"Rate limit reset failed: {e}")

    async def get_usage(
        self, identifier: str, endpoint: str
    ) -> dict[str, int | None]:
        """
        Get current usage for identifier + endpoint.

        Returns:
            Dict with current count and limit
        """
        try:
            key = self._get_key(identifier, endpoint)
            limit, window = self._get_limits(endpoint)
            now = time.time()

            # Count current requests in window
            count = await self.redis.zcount(key, now - window, now)

            return {
                "current": count,
                "limit": limit,
                "remaining": max(0, limit - count),
                "window": window,
            }
        except redis.RedisError as e:
            logger.error(f"Get usage failed: {e}")
            return {
                "current": None,
                "limit": self.default_limit,
                "remaining": None,
                "window": self.default_window,
            }
