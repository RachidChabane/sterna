"""API Gateway configuration."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Placeholder JWT secrets that must never sign a real token. The
# "django-insecure" prefix mirrors the marker core/sterna/settings uses
# for the Django SECRET_KEY (see prod.py) — the dev docker-compose stack
# feeds the *same* shared secret to both services, so a value carrying
# that prefix is exactly as insecure here as it is there.
_INSECURE_JWT_SECRETS = frozenset({"", "change-me-in-production"})
_INSECURE_JWT_SECRET_PREFIX = "django-insecure"

# The only `environment` value the insecure-secret bypass is honored in.
# Mirrors prod.py's DEV_TOKEN_BYPASS = False: prod hard-rejects the
# escape hatch "even if env vars are misconfigured" — here that means a
# stray GATEWAY_ALLOW_INSECURE_JWT_SECRET=true in a staging/production
# configmap must stay inert rather than reopen the hole.
_DEVELOPMENT_ENVIRONMENT = "development"


class Settings(BaseSettings):
    """Gateway configuration from environment variables."""

    # JWT Settings
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # Escape hatch for local development ONLY. When False (the default),
    # the gateway refuses to start on an unset/placeholder JWT secret —
    # the same fail-loud philosophy as core/sterna/settings/prod.py's
    # "django-insecure" SECRET_KEY guard, applied here because there is
    # no separate prod settings module to gate the check on. The dev
    # docker-compose stack sets this explicitly so local dev keeps
    # working off the shared "django-insecure-development-key" default.
    allow_insecure_jwt_secret: bool = False

    # Redis Settings
    redis_url: str = "redis://redis:6379/0"

    # Rate Limiting
    rate_limit_enabled: bool = True
    default_rate_limit: int = 1000  # per hour
    default_burst_size: int = 50

    # Backend Service Routes
    # Format: "gateway_prefix": {"backend": "url", "rewrite": "backend_prefix"}
    # If rewrite is empty, the prefix is stripped entirely
    # If rewrite is None/missing, the full path is forwarded as-is
    routes: dict[str, str] = {
        # Web backend - map /api/v1/* to /api/* (strip v1 prefix)
        "/api/v1/auth": "http://web:8000",
        "/api/v1/llm": "http://web:8000",
        "/api/v1/voice": "http://web:8000",
        "/api/v1/code": "http://web:8000",
        "/api/v1/mcp": "http://web:8000",
        "/api/v1/settings": "http://web:8000",
        "/api/v1/audit": "http://web:8000",
        "/api/v1/knowledge": "http://web:8000",
        # Separate services - prefix stripped entirely
        "/api/v1/preferences": "http://user-preferences:8000",
        "/api/v1/sandbox": "http://orchestrator:8003",
        "/api/v1/search": "http://brave-search:8004",
        "/api/v1/maps": "http://google-maps:8005",
        # Health endpoints
        "/api/health": "http://web:8000",
        "/health": "http://web:8000",
        # Fallback for /api without v1
        "/api": "http://web:8000",
    }

    # Path rewrite rules: gateway_prefix -> backend_prefix
    # If not listed, prefix is stripped (for separate services)
    route_rewrites: dict[str, str] = {
        # Web backend routes - strip v1 prefix
        "/api/v1/auth": "/api/auth",
        "/api/v1/llm": "/api/llm",
        "/api/v1/voice": "/api/voice-rooms",
        "/api/v1/code": "/api/code",
        "/api/v1/mcp": "/api/mcp",
        "/api/v1/settings": "/api/settings",
        "/api/v1/audit": "/api/audit",
        "/api/v1/knowledge": "/api/knowledge",
        "/api/health": "/api/health",
        "/health": "/api/health",
        "/api": "/api",
        # User preferences service - expects /api/v1/preferences/...
        "/api/v1/preferences": "/api/v1/preferences",
        # Services that strip prefix entirely (empty string)
        "/api/v1/sandbox": "",
        "/api/v1/search": "",
        "/api/v1/maps": "",
    }

    # Public paths (no auth required)
    # Include both /api/ and /api/v1/ versions since frontend uses /api/ base
    public_paths: list[str] = [
        "/health",
        "/ready",
        "/metrics",
        # Auth endpoints (v1 prefix)
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/token",
        "/api/v1/auth/token/refresh",
        "/api/v1/auth/password-reset",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/resend-verification",
        # Auth endpoints (no v1 prefix - frontend uses /api base)
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/token",
        "/api/auth/token/refresh",
        "/api/auth/password-reset",
        "/api/auth/verify-email",
        "/api/auth/resend-verification",
        # Cookie consent — GET/POST anonymous before signup
        "/api/v1/auth/consent",
        "/api/auth/consent",
        # OAuth callbacks (v1 prefix)
        "/api/v1/auth/google",
        "/api/v1/auth/google/callback",
        "/api/v1/auth/github",
        "/api/v1/auth/github/callback",
        # OAuth callbacks (no v1 prefix)
        "/api/auth/google",
        "/api/auth/google/callback",
        "/api/auth/github",
        "/api/auth/github/callback",
        # Public avatar endpoint (browser img tags don't send auth headers)
        "/api/v1/auth/avatar",
        "/api/auth/avatar",
        # Health checks
        "/api/health",
        "/api/v1/health",
    ]

    # CORS. Credentialed requests (cookies/Authorization headers) can
    # never be paired with a wildcard origin — browsers reject it, and
    # relying on it would silently degrade to reflecting any Origin.
    # No default list: an environment that forgets to set
    # GATEWAY_CORS_ORIGINS must fail loud at boot (see the validator
    # below), not silently boot with someone else's dev origins. Every
    # environment — dev compose included — sets GATEWAY_CORS_ORIGINS as
    # a JSON array (e.g. '["https://app.example.com"]'), the same
    # JSON-env convention as GATEWAY_ROUTES/GATEWAY_PUBLIC_PATHS.
    cors_origins: list[str] = []
    cors_allow_credentials: bool = True

    # Environment
    environment: str = "development"
    debug: bool = False

    # Timeouts
    proxy_timeout: float = 30.0
    proxy_connect_timeout: float = 5.0

    # Per-route timeout overrides (path prefix -> timeout in seconds)
    # For long-running operations like cloning repos, coding agent, etc.
    route_timeouts: dict[str, float] = {
        "/api/code-sessions/conversations": 300.0,  # 5 min for clone operations
        "/api/code-sessions/coding-agent": 600.0,  # 10 min for coding agent progress
        "/api/v1/sandbox/coding-agent": 900.0,  # 15 min for coding agent execution
        "/api/v1/sandbox/fs": 120.0,  # 2 min for filesystem operations
        "/api/llm/chat": 300.0,  # 5 min for LLM streaming
    }

    @model_validator(mode="after")
    def _require_real_jwt_secret(self) -> "Settings":
        """Fail closed on boot rather than sign tokens with a guessable key."""
        bypass_active = (
            self.allow_insecure_jwt_secret
            and self.environment == _DEVELOPMENT_ENVIRONMENT
        )
        if bypass_active:
            return self
        secret = self.jwt_secret_key.strip()
        if secret in _INSECURE_JWT_SECRETS or secret.startswith(
            _INSECURE_JWT_SECRET_PREFIX
        ):
            raise ValueError(
                "GATEWAY_JWT_SECRET_KEY is unset or using a known-insecure "
                "placeholder — refusing to start, since anyone could forge "
                "tokens signed with it. Set a real secret (e.g. `python -c "
                "\"import secrets; print(secrets.token_urlsafe(64))\"`), or "
                "for local development only, set "
                "GATEWAY_ALLOW_INSECURE_JWT_SECRET=true AND "
                f'GATEWAY_ENVIRONMENT="{_DEVELOPMENT_ENVIRONMENT}" — the '
                "bypass is inert everywhere else, so a stray flag left in "
                "a staging/production config can never reopen this."
            )
        return self

    @model_validator(mode="after")
    def _require_explicit_cors_origins_with_credentials(self) -> "Settings":
        """Credentialed CORS must never echo/allow a wildcard origin."""
        if self.cors_allow_credentials and (
            not self.cors_origins or "*" in self.cors_origins
        ):
            raise ValueError(
                "GATEWAY_CORS_ORIGINS must be an explicit list of origins "
                "when GATEWAY_CORS_ALLOW_CREDENTIALS is true — wildcard "
                "('*') origins cannot be combined with credentialed "
                "requests. Set GATEWAY_CORS_ORIGINS to a JSON array (e.g. "
                '\'["https://app.example.com"]\'), or set '
                "GATEWAY_CORS_ALLOW_CREDENTIALS=false if the API truly "
                "needs to be open to any origin without cookies/auth "
                "headers."
            )
        return self

    class Config:
        env_file = ".env"
        env_prefix = "GATEWAY_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
