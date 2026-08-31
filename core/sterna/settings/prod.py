"""
Production settings for Sterna project.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

# Security
DEBUG = False

# SECRET_KEY signs sessions AND (via the JWT_SECRET_KEY fallback in
# base.py) every JWT. Prod must never boot on the base.py
# "django-insecure-…" development default: require the env var and
# reject any value carrying the insecure marker prefix.
SECRET_KEY = env("SECRET_KEY")  # ImproperlyConfigured if unset
if SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured(
        "SECRET_KEY starts with 'django-insecure' — refusing to boot "
        "prod/staging on a development key. Set a real SECRET_KEY."
    )

# Recompute the JWT signing key against the prod SECRET_KEY (base.py
# computed its fallback from the base default) and apply the same
# insecure-marker check.
JWT_SECRET_KEY = env("JWT_SECRET_KEY", default=SECRET_KEY)
if JWT_SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured(
        "JWT_SECRET_KEY starts with 'django-insecure' — refusing to "
        "sign JWTs with a development key in prod/staging."
    )

# Field-level encryption keys protect OAuth tokens, MCP connector
# credentials and BYOK provider keys at rest. base.py ships a Fernet
# key that is public in this repository as the development default,
# so prod must require the env var and reject that key outright.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")  # ImproperlyConfigured if unset
if FIELD_ENCRYPTION_KEY == DEV_FIELD_ENCRYPTION_KEY:
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY is the public development key — refusing to "
        "encrypt production secrets with it. Generate a real key with: "
        "python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )

# BYOK keys rotate independently of FIELD_ENCRYPTION_KEY; falling back
# to it is acceptable, falling back to the public dev key is not.
BYOK_ENCRYPTION_KEY = env("BYOK_ENCRYPTION_KEY", default=FIELD_ENCRYPTION_KEY)
if BYOK_ENCRYPTION_KEY == DEV_FIELD_ENCRYPTION_KEY:
    raise ImproperlyConfigured(
        "BYOK_ENCRYPTION_KEY is the public development key — refusing to "
        "encrypt BYOK provider keys with it."
    )

# task-29 H1 + H4: prod must require CF-Connecting-IP for trustworthy
# rate-limit keying, and must hard-reject dev-token JWT bypass even
# if env vars are misconfigured.
CF_REQUIRE_HEADER = env.bool("CF_REQUIRE_HEADER", default=True)
DEV_TOKEN_BYPASS = False

# Production hosts — fail loud if unset (a "*" wildcard default would
# disable Host-header validation for every prod pod). Celery workers /
# beat never serve HTTP, so they may boot with WORKER_MODE=true to
# skip the requirement (the K8s manifests already inject ALLOWED_HOSTS
# from api-secrets into web, celery-worker, celery-beat and
# consigliere, so this escape hatch is only for launch commands that
# genuinely cannot receive the var).
if env.bool("WORKER_MODE", default=False):
    ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
else:
    ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # ImproperlyConfigured if unset

# Force HTTPS - disabled for K8s health probes which use HTTP
# TLS termination happens at the ingress/cloudflare level
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Production database
DATABASES["default"].update(
    {
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "connect_timeout": 10,
            "sslmode": "require",
        },
    }
)

# Cache configuration with Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
            },
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        },
        "KEY_PREFIX": "sterna_prod",
        "TIMEOUT": 300,
    }
}

# Email - Resend transactional provider
EMAIL_BACKEND = "notifications.email_backend.ResendEmailBackend"
RESEND_API_KEY = env("RESEND_API_KEY")  # fail loud if missing
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")  # fail loud if missing
SUPPORT_EMAIL = env("SUPPORT_EMAIL", default="support@example.com")
BRAND_NAME = env("BRAND_NAME", default="Sterna")

# Cloudflare Turnstile (CAPTCHA) — task 19. Fail loud if missing in prod.
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY")
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY")

# Stripe billing (task 11). Fail loud if missing in prod or staging.
# WEBHOOK_SECRET is wired in the manifest as `optional: true` (task 13
# fills it); ops MUST include the key in the Scaleway payload (empty
# string is fine) so K8s injects the env var.
STRIPE_API_KEY = env("STRIPE_API_KEY")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
STRIPE_LIVE_MODE = STRIPE_API_KEY.startswith("sk_live_")

# Static files - Use CDN in production
STATIC_URL = env("STATIC_URL", default="/static/")
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Media files - Use S3 in production
if AWS_ACCESS_KEY_ID:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    STATICFILES_STORAGE = "storages.backends.s3boto3.S3StaticStorage"

# Logging — structured JSON via shared helper.
from sterna.logging import build_logging_config

LOGGING = build_logging_config(env="prod", service="web")

# REST Framework - Production settings
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
]

# CORS - Restrict in production
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'")
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_IMG_SRC = ("'self'", "data:", "https:")

# Performance optimizations
CONN_MAX_AGE = 600

# Error tracking via shared Sentry initializer.
# No-op when SENTRY_DSN is unset.
from sterna.sentry import init_sentry
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

init_sentry(
    service="web",
    extra_integrations=[
        DjangoIntegration(),
        CeleryIntegration(),
        RedisIntegration(),
    ],
)
