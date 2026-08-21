"""Centralized abuse / rate-limit helpers.

This module ships the minimum Task 18 surface that Task 19 (signup
abuse prevention) depends on:

- ``client_ip(request)`` — derive the calling IP from
  ``HTTP_X_FORWARDED_FOR`` (first hop) or ``REMOTE_ADDR``.
- ``emit_suspicious_activity(...)`` — public helper that logs to the
  ``security.suspicious_activity`` logger at ERROR (so Sentry catches
  it) and drops a structured breadcrumb.
- ``apply_ratelimit(...)`` — a ``django_ratelimit.decorators.ratelimit``
  wrapper that records a ``rate_limit.<scope>`` suspicious-activity
  event each time the limit is crossed.

Task 18 (`feat: API rate limiting`) is the broader owner of this
module; Task 19 ships ONLY the slice needed for signup abuse
prevention. When Task 18 lands, it expands ``unified_exception_handler``,
``RATELIMIT_ABUSE_SCORE_*`` settings, and the abuse-counter machinery.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

import sentry_sdk
from django.conf import settings
from django.utils.module_loading import import_string

from django_ratelimit import ALL
from django_ratelimit.core import is_ratelimited
from django_ratelimit.exceptions import Ratelimited


_suspicious_logger = logging.getLogger("security.suspicious_activity")


def client_ip(request) -> str:
    """Backwards-compatible re-export of ``sterna.client_ip.get_client_ip``.

    Task-29 H1 centralized IP extraction. This wrapper keeps the
    existing import surface stable while pointing all callers to the
    CF-aware implementation.
    """
    from sterna.client_ip import get_client_ip

    return get_client_ip(request)


def _actor_id(request) -> str:
    """Return ``user:<pk>`` when authenticated, else ``ip:<addr>``."""
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"
    return f"ip:{client_ip(request)}"


def emit_suspicious_activity(
    *,
    category: str,
    reason: str,
    request=None,
    actor: Optional[str] = None,
    **extra,
) -> None:
    """Log a structured suspicious_activity event.

    ``category`` is a short namespace (e.g. ``signup_abuse``,
    ``oauth_replay``, ``rate_limit``) that aligns with Sentry alert
    filters. ``reason`` is the specific cause within the category
    (e.g. ``disposable_email``, ``turnstile_failed``).
    """
    if actor is None and request is not None:
        actor = _actor_id(request)
    payload = {
        "actor": actor or "unknown",
        "category": category,
        "reason": reason,
        **extra,
    }
    _suspicious_logger.error(f"{category}.{reason}", extra=payload)
    try:
        sentry_sdk.add_breadcrumb(
            category=category,
            message=f"{category}.{reason}",
            level="warning",
            data=payload,
        )
    except Exception:  # noqa: BLE001 — Sentry no-op safe
        pass


def json_body_field_key(field: str) -> Callable:
    """Return a ``django_ratelimit`` key callable reading ``field`` from
    the request body, JSON-first.

    django_ratelimit's built-in ``post:<field>`` key reads
    ``request.POST``, which is EMPTY for the ``application/json``
    bodies the frontend actually sends — every JSON request then
    hashes the same empty value into ONE shared bucket per group
    (e.g. 3 JSON password resets lock out every other user's reset
    for an hour, site-wide).

    Resolution order:
      1. ``json.loads(request.body)`` — ``request.body`` caches the
         raw bytes on ``request._body`` without consuming the stream,
         so later DRF parsing (``request.data``) still works.
      2. ``request.POST`` — form-encoded fallback.
      3. Client IP — when the field is absent, bucket per-caller
         rather than globally.
    """

    def _key(group, request) -> str:
        value = None
        try:
            body = request.body
            if body:
                data = json.loads(body)
                if isinstance(data, dict):
                    value = data.get(field)
        except Exception:  # noqa: BLE001 — malformed JSON, consumed
            # stream (RawPostDataException), bad encoding: fall back.
            value = None
        if value is None:
            try:
                value = request.POST.get(field)
            except Exception:  # noqa: BLE001
                value = None
        if not value or not isinstance(value, str):
            return f"ip:{client_ip(request)}"
        return f"{field}:{value.strip().lower()}"

    return _key


def apply_ratelimit(
    *,
    key,
    rate: str,
    method=ALL,
    group: Optional[str] = None,
    scope: Optional[str] = None,
    block: bool = True,
) -> Callable:
    """Wrap ``django_ratelimit.ratelimit`` and emit on threshold cross.

    Parameters mirror ``django_ratelimit`` with one addition:

    - ``scope`` is a stable dashed identifier (e.g.
      ``auth.register.ip``) that flows into the
      ``security.suspicious_activity`` event when the limit is hit.
      ``group`` is the bucket name (same call from multiple views may
      share a group). ``scope`` is the per-call label used for alerts.
    """

    def decorator(fn):
        from functools import wraps

        @wraps(fn)
        def _wrapped(request, *args, **kwargs):
            limited = is_ratelimited(
                request=request,
                group=group or scope or fn.__name__,
                fn=fn,
                key=key,
                rate=rate,
                method=method,
                increment=True,
            )
            request.limited = limited or getattr(request, "limited", False)
            if limited and block:
                emit_suspicious_activity(
                    category="rate_limit",
                    reason=scope or group or fn.__name__,
                    request=request,
                )
                cls = getattr(settings, "RATELIMIT_EXCEPTION_CLASS", Ratelimited)
                raise (import_string(cls) if isinstance(cls, str) else cls)()
            return fn(request, *args, **kwargs)

        return _wrapped

    return decorator
