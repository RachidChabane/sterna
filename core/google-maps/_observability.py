"""
Per-service observability bootstrap (structured JSON logging + Sentry).

Intentionally duplicated, byte-for-byte, across the FastAPI/Starlette
microservices under core/ (api-gateway, brave-search, google-maps,
sandbox/orchestrator, user-preferences-service). Each service builds
from its own isolated Docker context (`COPY . .` scoped to that
directory — see each service's Dockerfile), so none of them can import
a shared package at image-build time without a larger change than the
duplication itself (an `additional_contexts` COPY step added to every
Dockerfile, or publishing this module as an installable wheel).

Drift across the five copies fails CI: see
core/api-gateway/tests/test_observability_sync.py, which asserts every
copy is byte-identical to core/api-gateway/gateway/_observability.py
(the canonical copy). To change the shared behavior, edit the
canonical copy first, then copy its exact contents over the other
four locations.

Exposes:
- init_observability(service: str, app_loggers: Iterable[str] = ()) -> None
- current_request_id / current_user_id (per-service ContextVars)
- RedactSensitiveKeysFilter / RequestIDFilter / UserIDFilter /
  ServiceTagFilter
- RequestIDMiddleware
"""

import contextvars
import logging
import os
import re
import uuid
from collections.abc import Iterable
from typing import Any

import sentry_sdk
from pythonjsonlogger.jsonlogger import JsonFormatter
from sentry_sdk.integrations import Integration
from starlette.middleware.base import BaseHTTPMiddleware

current_request_id: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("current_request_id", default=None)
)
current_user_id: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("current_user_id", default=None)
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
    "api_key", "apikey", "password", "passwd", "token", "secret",
    "stripe_publishable_key", "stripe_webhook_secret",
    "stripe_signing_secret", "byok", "field_encryption_key",
    "jwt_secret", "refresh_token", "access_token", "id_token",
    "client_secret", "private_key", "authorization",
    "set-cookie", "cookie",
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
    if isinstance(v, list | tuple):
        cls = type(v)
        return cls(_redact_value(x) for x in v)
    if isinstance(v, str):
        s = v
        for rx in _REGEX_REDACTORS:
            s = rx.sub(_REDACTED, s)
        return s
    return v


class RedactSensitiveKeysFilter(logging.Filter):
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
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None):
            return True
        record.request_id = current_request_id.get() or "-"
        return True


class UserIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "user_id", None):
            return True
        record.user_id = current_user_id.get() or "-"
        return True


class ServiceTagFilter(logging.Filter):
    def __init__(self, service: str):
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


def _init_sentry(
    service: str,
    *,
    extra_integrations: Iterable[Integration] | None = None,
) -> None:
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    env = os.environ.get("ENVIRONMENT", "development")
    sample = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        integrations=list(extra_integrations or []),
        traces_sample_rate=sample,
        send_default_pii=False,
        release=os.environ.get("RELEASE_SHA") or None,
    )
    sentry_sdk.set_tag("service", service)


def init_observability(service: str, app_loggers: Iterable[str] = ()) -> None:
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
    handler.addFilter(ServiceTagFilter(service))
    handler.addFilter(RequestIDFilter())
    handler.addFilter(UserIDFilter())
    handler.addFilter(RedactSensitiveKeysFilter())
    # Handler at DEBUG: logger levels govern what is emitted. A
    # WARNING handler here silently dropped every app INFO event in
    # prod/staging.
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    root.setLevel(logging.WARNING if is_prod else logging.INFO)

    # App logger namespaces pinned at INFO so business events are
    # emitted even with the root at WARNING in prod/staging.
    for name in app_loggers:
        logging.getLogger(name).setLevel(logging.INFO)

    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        integrations: list = [StarletteIntegration(), FastApiIntegration()]
    except Exception:
        integrations = []
    _init_sentry(service, extra_integrations=integrations)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI middleware: read the inbound ``X-Request-ID``
    header (or mint a UUIDv4), expose it on ``request.state`` and on
    the shared ContextVar consumed by RequestIDFilter, and mirror it on
    the response so callers can correlate across services.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request, call_next):
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.state.request_id = request_id
        token = current_request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            current_request_id.reset(token)
        response.headers[self.HEADER_NAME] = request_id
        return response
