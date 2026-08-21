"""
Development settings for Sterna project.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *

# Debug mode
DEBUG = True

# Preventive guard: a live Stripe key in a non-prod environment means
# real charges/refunds from dev machines. Refuse to boot rather than
# detect after the fact (sanity_check_stripe_mode only runs on deploy).
if STRIPE_API_KEY.startswith("sk_live_"):
    raise ImproperlyConfigured(
        "STRIPE_API_KEY is a LIVE key (sk_live_…) but settings.dev is "
        "loaded. Use a test key (sk_test_…) outside production."
    )

# task-29 H4: dev ergonomics — accept ``dev-*`` JWTs without verification.
# Production hard-blocks this in settings.prod (see DEV_TOKEN_BYPASS=False).
DEV_TOKEN_BYPASS = env.bool("DEV_TOKEN_BYPASS", default=True)

# Development-specific installed apps
INSTALLED_APPS += [
    "django_extensions",
]

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Development database (can override with local settings)
DATABASES["default"].update(
    {
        "NAME": env("DB_NAME", default="sterna_dev"),
        "HOST": env("DB_HOST", default="localhost"),
    }
)

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Use Redis cache from base.py (needed for OAuth state management and sessions)
# CACHES configuration inherited from base.py - don't override

# CORS - Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

# Celery - Use eager mode in development for debugging
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True

# Static files
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, "media_dev")

# Logging - More verbose in development
assert "console" in LOGGING["handlers"], (
    "build_logging_config contract broken: 'console' handler missing"
)
assert "sterna" in LOGGING["loggers"], (
    "build_logging_config contract broken: 'sterna' logger missing"
)
assert "voice_rooms" in LOGGING["loggers"], (
    "build_logging_config contract broken: 'voice_rooms' logger missing"
)
LOGGING["handlers"]["console"]["level"] = "DEBUG"
LOGGING["loggers"]["sterna"]["level"] = "DEBUG"
LOGGING["loggers"]["voice_rooms"]["level"] = "DEBUG"

# Security - Relaxed for development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False

# Django Debug Toolbar (optional)
if env.bool("ENABLE_DEBUG_TOOLBAR", default=False):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
    INTERNAL_IPS = ["127.0.0.1", "localhost"]
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
    }

# Development-specific REST Framework settings
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Loosen throttling in development — keep all scope keys from base
# (support_anon, support_user, etc.) since some views reference them
# explicitly via ScopedRateThrottle and the framework raises
# ImproperlyConfigured if a referenced scope is missing.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
    "anon": "10000/hour",
    "user": "10000/hour",
}

print("=" * 50)
print("RUNNING IN DEVELOPMENT MODE")
print("=" * 50)
