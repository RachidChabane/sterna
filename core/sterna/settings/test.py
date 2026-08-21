"""
Test settings for Sterna project.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403 — inherit INSTALLED_APPS, MIDDLEWARE, ROOT_URLCONF, AUTH_USER_MODEL, etc.

# Preventive guard: never let a test run see a live Stripe key.
if STRIPE_API_KEY.startswith("sk_live_"):
    raise ImproperlyConfigured(
        "STRIPE_API_KEY is a LIVE key (sk_live_…) but settings.test is "
        "loaded. Refusing to run tests against live Stripe."
    )
# Blank the Stripe credentials entirely so no test suite can ever hit
# real Stripe, whatever the developer's .env contains. Tests that need
# a key set one explicitly (e.g. 'sk_test_FAKE' via the settings
# fixture / override_settings).
STRIPE_API_KEY = ""
STRIPE_WEBHOOK_SECRET = ""
STRIPE_LIVE_MODE = False

# Test configuration
DEBUG = False
TESTING = True

# task-29 H4: tests rely on ``dev-`` tokens for orchestrator-side
# fixtures. Keep the bypass on in the test settings only.
DEV_TOKEN_BYPASS = True

# Use in-memory database for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use locmem cache for tests (supports sessions)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


# Disable migrations for tests (except for datasets which needs them)
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


# Enable migrations only for apps that need them
MIGRATION_MODULES = {
    app: None
    for app in [
        "admin",
        "auth",
        "contenttypes",
        "sessions",
        "messages",
        "staticfiles",
        "corsheaders",
        "rest_framework",
        "authentication",
        "llm",
        "storage",
        "audit_logging",  # Migrations off (contenttypes chain), but the app,
        # its middleware and its tables all stay live in tests — the
        # test runner's run_syncdb creates the tables from models.
        "support",  # FK to auth user; disable to avoid contenttypes dependency chain
        "knowledge_base",  # Has HnswIndex (pgvector) which emits PG-only DDL
    ]
}

# Password hashers - Use fast hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Celery - Always eager for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Media files for tests
MEDIA_ROOT = os.path.join(BASE_DIR, "test_media")

# Static files
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Disable throttling in tests
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []

# Structured JSON logging via shared helper.
from sterna.logging import build_logging_config

LOGGING = build_logging_config(env="test", service="web")

# Security - Relaxed for tests
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Test-specific settings
SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# CORS - Allow all for tests
CORS_ALLOW_ALL_ORIGINS = True

# Disable rate limiting for tests
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": None,
    "user": None,
}
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["support_anon"] = None
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["support_user"] = None

# Deterministic dummy OpenRouter key: tests never make real calls (all
# HTTP is mocked), but APIKeyResolver requires a key to be present.
# Without this, the suite only passes on machines whose environment
# happens to carry a real key — and fails in CI, which carries none.
OPENROUTER_API_KEY = "sk-or-v1-test-dummy-never-used"
