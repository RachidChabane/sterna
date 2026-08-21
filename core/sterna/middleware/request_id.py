"""
Request ID middleware + ContextVar source of truth.

Generates a UUIDv4 per request, accepts an inbound X-Request-ID
header for cross-service correlation, mirrors it on the outbound
response, and exposes it via a ContextVar so async code paths and
log filters can read it without a `request` reference.
"""

import contextvars
import uuid
from typing import Optional

from django.utils.deprecation import MiddlewareMixin

HEADER = "X-Request-ID"

current_request_id: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("current_request_id", default=None)
)
current_user_id: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("current_user_id", default=None)
)


def get_request_id(request) -> Optional[str]:
    """Read the request_id off a Django request, falling back to the
    ContextVar. Use in views/services that already have a request."""
    return getattr(request, "request_id", None) or current_request_id.get()


def request_id_headers(headers: Optional[dict] = None) -> dict:
    """Return a copy of ``headers`` with the current request id injected
    as ``X-Request-ID`` (when one is set in the ContextVar).

    Use at every Django -> downstream-service HTTP call site so the
    request id propagates across the fleet. No-op when no request id is
    active (e.g. management commands) or when the caller already set
    the header explicitly.
    """
    out = dict(headers or {})
    rid = current_request_id.get()
    if rid and HEADER not in out:
        out[HEADER] = rid
    return out


class RequestIDMiddleware(MiddlewareMixin):
    """Django middleware: stamp request_id, expose on response."""

    def process_request(self, request):
        request_id = request.headers.get(HEADER) or str(uuid.uuid4())
        request.request_id = request_id
        request._request_id_token = current_request_id.set(request_id)

    @staticmethod
    def _reset_context(request):
        """Reset both ContextVars exactly once per request.

        When a view raises, Django runs BOTH process_exception and
        process_response — nulling the token attribute after the first
        reset prevents a double ``Token.reset`` (RuntimeError: Token
        has already been used once).

        Under ASGI MiddlewareMixin runs process_request and
        process_response in different thread executors, so the Token
        from .set() may live in a different Context than .reset() sees
        (ValueError). Swallow that case; the per-request Context dies
        anyway.
        """
        rid_token = getattr(request, "_request_id_token", None)
        if rid_token is not None:
            request._request_id_token = None
            try:
                current_request_id.reset(rid_token)
            except (ValueError, RuntimeError):
                pass
        uid_token = getattr(request, "_user_id_token", None)
        if uid_token is not None:
            request._user_id_token = None
            try:
                current_user_id.reset(uid_token)
            except (ValueError, RuntimeError):
                pass

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", None)
        if request_id:
            response[HEADER] = request_id
        self._reset_context(request)
        return response

    def process_exception(self, request, exception):
        self._reset_context(request)
        return None
