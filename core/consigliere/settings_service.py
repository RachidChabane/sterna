"""
Minimal Django settings for Consigliere microservice.

This is a stripped-down version of the main settings for running
Consigliere as a standalone microservice.
"""

import os
from pathlib import Path
import environ  # type: ignore[import-untyped]
from datetime import timedelta

from .config import NetworkConfig

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment
env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DJANGO_ENV = os.environ.get("DJANGO_ENV", "dev")

# Security
SECRET_KEY = env(
    "SECRET_KEY", default="django-insecure-development-key-change-this-in-production"
)
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0", "*"])

# Application definition - MINIMAL for Consigliere
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]

# Only apps needed for Consigliere
LOCAL_APPS = [
    "authentication",  # For User model
    "llm",  # For OpenRouter client and model data
    "usage_quota",  # Required by llm.client imports
    "consigliere",  # The Consigliere service itself
    "conversations",  # Conversation storage (PostgreSQL)
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Middleware - Minimal
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "sterna.middleware.request_id.RequestIDMiddleware",
]

ROOT_URLCONF = "consigliere.urls_service"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "consigliere.wsgi_service.application"

# Database - Same as main service (shared database)
# Prefer DATABASE_URL if set, otherwise use individual DB_* vars
DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="sterna_dev"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default="postgres"),
            "HOST": env("DB_HOST", default="postgres"),
            "PORT": env("DB_PORT", default="5432"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {
                "connect_timeout": NetworkConfig.DB_CONNECT_TIMEOUT,
            },
        }
    }

# Redis configuration
# Prefer REDIS_URL if set, otherwise construct from individual vars
REDIS_URL = env("REDIS_URL", default="")
if not REDIS_URL:
    REDIS_HOST = env("REDIS_HOST", default="redis")
    REDIS_PORT = env("REDIS_PORT", default="6379")
    REDIS_DB = env("REDIS_DB", default="0")
    REDIS_PASSWORD = env("REDIS_PASSWORD", default="")
    REDIS_URL = (
        f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        if REDIS_PASSWORD
        else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )
else:
    # Parse REDIS_URL for components needed by other configs
    from urllib.parse import urlparse
    _parsed = urlparse(REDIS_URL)
    REDIS_HOST = _parsed.hostname or "redis"
    REDIS_PORT = str(_parsed.port or 6379)
    REDIS_DB = _parsed.path.lstrip("/") or "0"
    REDIS_PASSWORD = _parsed.password or ""

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "consigliere",
        "TIMEOUT": 300,
    }
}

# Authentication
AUTH_USER_MODEL = "authentication.User"

AUTHENTICATION_BACKENDS = [
    "authentication.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "authentication.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
    "DATE_FORMAT": "%Y-%m-%d",
    "TIME_FORMAT": "%H:%M:%S",
}

# CORS configuration - Allow frontend on :5173 and main web service
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
)
CORS_ALLOW_CREDENTIALS = True

# JWT Configuration
JWT_SECRET_KEY = env("JWT_SECRET_KEY", default=SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=7)
JWT_AUTH_HEADER_PREFIX = "Bearer"

# OpenRouter configuration (for LLM client)
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_API_BASE = env("OPENROUTER_API_BASE", default="https://openrouter.ai/api/v1")
OPENROUTER_DEFAULT_MODEL = env(
    "OPENROUTER_DEFAULT_MODEL", default="openai/gpt-4-turbo-preview"
)

# Structured JSON logging via shared helper.
from sterna.logging import build_logging_config

LOGGING = build_logging_config(env=DJANGO_ENV, service="consigliere")

# Error tracking via shared Sentry initializer.
# No-op when SENTRY_DSN is unset.
if not DEBUG and env("SENTRY_DSN", default=""):
    from sterna.sentry import init_sentry
    from sentry_sdk.integrations.django import DjangoIntegration

    init_sentry(
        service="consigliere",
        extra_integrations=[DjangoIntegration()],
    )

# Security settings
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Session configuration
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # Set to True in production
SESSION_COOKIE_SAMESITE = "Lax"
