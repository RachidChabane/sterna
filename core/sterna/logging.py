"""
Structured JSON logging for the Sterna fleet.

Two entry points:
- build_logging_config(env, service) -> dict[str, Any]
  Returns a Django LOGGING dict.
- init_root_logger(service) -> None
  Imperative root-logger config for non-Django (FastAPI) services.

Shared building blocks:
- RedactSensitiveKeysFilter: walks LogRecord __dict__ and scrubs
  known-sensitive keys (api_key, token, password, ...) including a
  regex pass over rendered messages for raw bearer tokens, Stripe /
  OpenRouter / OpenAI / Anthropic keys, and JWTs.
- RequestIDFilter / UserIDFilter: stamp the current request_id /
  user_id from ContextVars onto every record.
"""

import logging
import os
import re
from typing import Any, Iterable

from pythonjsonlogger.jsonlogger import JsonFormatter

# App logger namespaces that must emit INFO-level business events
# (billing.usage_recorded, billing.quota_exceeded, auth.*, audit.*)
# even when the root logger sits at WARNING in prod/staging. The
# console handler stays at DEBUG so that LOGGER levels govern what is
# emitted; without explicit entries here, app INFO events propagate to
# the WARNING root and are silently dropped.
APP_LOGGERS = (
    "sterna",
    "usage_quota",
    "authentication",
    "llm",
    "audit_logging",
    "conversations",
    "notifications",
    "voice_rooms",
)


_BEARER_TOKEN_RE = re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE)
_STRIPE_KEY_RE = re.compile(r"sk_(?:live|test)_[A-Za-z0-9]+")
_OPENROUTER_KEY_RE = re.compile(r"sk-or-v\d+-[A-Za-z0-9]+")
_OPENAI_KEY_RE = re.compile(r"sk-(?:proj|svcacct)?-?[A-Za-z0-9_-]{20,}")
_ANTHROPIC_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_REGEX_REDACTORS = (
    _BEARER_TOKEN_RE,
    _STRIPE_KEY_RE,
    _OPENROUTER_KEY_RE,
    _ANTHROPIC_KEY_RE,
    _JWT_RE,
    _OPENAI_KEY_RE,
)
_REDACTED = "***REDACTED***"

SENSITIVE_KEY_PATTERNS = (
    "api_key",
    "apikey",
    "password",
    "passwd",
    "token",
    "secret",
    "stripe_publishable_key",
    "stripe_webhook_secret",
    "stripe_signing_secret",
    "byok",
    "field_encryption_key",
    "jwt_secret",
    "refresh_token",
    "access_token",
    "id_token",
    "client_secret",
    "private_key",
    "authorization",
    "set-cookie",
    "cookie",
)

_STDLIB_LOGRECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "taskName",
    "getMessage", "message", "asctime",
})


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(pat in k for pat in SENSITIVE_KEY_PATTERNS)


def _redact_value(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: (_REDACTED if _is_sensitive(k) else _redact_value(val))
                for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        cls = type(v)
        return cls(_redact_value(x) for x in v)
    if isinstance(v, str):
        s = v
        for rx in _REGEX_REDACTORS:
            s = rx.sub(_REDACTED, s)
        return s
    return v


def redact_sensitive(value: Any) -> Any:
    """Public entry point for the sensitive-key / secret-regex scrub.

    Recursively redacts dict values under known-sensitive keys
    (``SENSITIVE_KEY_PATTERNS``) and regex-scrubs raw secrets (bearer
    tokens, API keys, JWTs) out of strings. Non-container values pass
    through unchanged. Reused outside logging (e.g. the audit
    middleware scrubs query params before persisting them) so the
    sensitive-key list lives in exactly one place.
    """
    return _redact_value(value)


class RedactSensitiveKeysFilter(logging.Filter):
    """Redact known-sensitive keys from any log record's `extra` (which
    stdlib logging flattens onto record.__dict__) and from positional
    args. The formatter performs a final regex pass on the rendered
    message body."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__.keys()):
            if key in _STDLIB_LOGRECORD_ATTRS:
                continue
            value = record.__dict__[key]
            if _is_sensitive(key):
                record.__dict__[key] = _REDACTED
            else:
                record.__dict__[key] = _redact_value(value)

        if record.args:
            record.args = _redact_value(record.args)
        return True


class RequestIDFilter(logging.Filter):
    """Stamp the current request_id (from middleware ContextVar) onto
    every log record. Falls back to '-' when unset. Defers to an
    explicit `extra={"request_id": ...}` passed by the caller."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None):
            return True
        try:
            from sterna.middleware.request_id import current_request_id
            value = current_request_id.get()
        except Exception:
            value = None
        record.request_id = value or "-"
        return True


class UserIDFilter(logging.Filter):
    """Stamp the current authenticated user_id from a ContextVar onto
    every log record. Falls back to '-' when unset. Defers to an
    explicit `extra={"user_id": ...}` passed by the caller."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "user_id", None):
            return True
        try:
            from sterna.middleware.request_id import current_user_id
            value = current_user_id.get()
        except Exception:
            value = None
        record.user_id = value or "-"
        return True


class ServiceTagFilter(logging.Filter):
    """Stamp a fixed `service` name onto every record. Configured once
    per Django settings file via build_logging_config(service=...)."""

    def __init__(self, service: str = "web"):
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "service", None):
            record.service = self.service
        return True


_JSON_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "%(request_id)s %(user_id)s %(message)s"
)


class _RedactingJsonFormatter(JsonFormatter):
    """Final-pass redaction: regex-scrub the rendered message string
    AFTER args have been merged in via getMessage(). Catches secrets
    embedded in f-strings (which bake into record.msg verbatim)."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        for key in ("msg", "message"):
            value = log_record.get(key)
            if isinstance(value, str):
                for rx in _REGEX_REDACTORS:
                    value = rx.sub(_REDACTED, value)
                log_record[key] = value


def _make_json_formatter() -> _RedactingJsonFormatter:
    return _RedactingJsonFormatter(
        fmt=_JSON_FORMAT,
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
            "message": "msg",
        },
        json_ensure_ascii=False,
    )


def build_logging_config(env: str, service: str) -> dict:
    """Return a Django LOGGING dict.

    env: 'dev' | 'staging' | 'prod' | 'production' | 'test'
    service: name used to scope the app logger.

    Behavior:
      - prod/staging: JSON to stdout, WARNING default, INFO for app loggers.
      - dev: human-readable to stdout, DEBUG/INFO for app loggers.
      - test: null handler only (so pytest capture isn't polluted).
    """
    if env == "test":
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {"null": {"class": "logging.NullHandler"}},
            "root": {"handlers": ["null"], "level": "CRITICAL"},
        }

    is_prod = env in ("prod", "production", "staging")
    formatter_name = "json" if is_prod else "human"

    # Explicit app loggers pinned at INFO. The console handler sits at
    # DEBUG so LOGGER levels alone govern emission; the root stays at
    # WARNING in prod/staging to keep third-party noise out. Without
    # these entries, app INFO events (billing.usage_recorded,
    # billing.quota_exceeded, ...) propagate to the WARNING root and
    # are silently dropped in prod/staging.
    loggers: dict = {
        "django": {
            "handlers": ["console"],
            "level": "WARNING" if is_prod else "INFO",
            "propagate": False,
        },
    }
    for name in (*APP_LOGGERS, service):
        loggers[name] = {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": _make_json_formatter,
            },
            "human": {
                "format": (
                    "%(asctime)s %(levelname)-7s %(name)s "
                    "rid=%(request_id)s uid=%(user_id)s %(message)s"
                ),
            },
        },
        "filters": {
            "request_id": {"()": "sterna.logging.RequestIDFilter"},
            "user_id": {"()": "sterna.logging.UserIDFilter"},
            "redact": {"()": "sterna.logging.RedactSensitiveKeysFilter"},
            "service_tag": {
                "()": "sterna.logging.ServiceTagFilter",
                "service": service,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                # Always DEBUG: logger levels govern what is emitted.
                # A WARNING handler here silently dropped every app
                # INFO event in prod/staging.
                "level": "DEBUG",
                "formatter": formatter_name,
                "filters": ["service_tag", "request_id", "user_id", "redact"],
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "WARNING" if is_prod else "INFO",
        },
        "loggers": loggers,
    }


def init_root_logger(service: str, app_loggers: Iterable[str] = ()) -> None:
    """Imperative root-logger config for non-Django services. Idempotent.

    Clears pre-existing handlers (uvicorn / basicConfig may have added
    some), installs a single StreamHandler with JSON formatter (in
    prod/staging) or human formatter (in dev), and attaches the
    standard filter set.

    ``app_loggers`` names logger namespaces pinned at INFO so that app
    business events are emitted even when the root sits at WARNING in
    prod/staging. The handler itself stays at DEBUG — logger levels
    govern emission.
    """
    env = os.environ.get("ENVIRONMENT", "dev")
    is_prod = env in ("prod", "production", "staging")
    root = logging.getLogger()

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    if is_prod:
        handler.setFormatter(_make_json_formatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s "
            "rid=%(request_id)s uid=%(user_id)s %(message)s"
        ))
    handler.addFilter(RequestIDFilter())
    handler.addFilter(UserIDFilter())
    handler.addFilter(RedactSensitiveKeysFilter())
    # Handler at DEBUG: logger levels govern what is emitted.
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    root.setLevel(logging.WARNING if is_prod else logging.INFO)

    for name in app_loggers:
        logging.getLogger(name).setLevel(logging.INFO)

    class _ServiceTag(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.service = service
            return True

    handler.addFilter(_ServiceTag())
