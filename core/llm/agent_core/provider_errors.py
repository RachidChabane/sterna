"""The error taxonomy a `ModelProvider` raises for a failed request.

Every failure the port can produce collapses to one of a small set of
typed exceptions, so the agent execution loop can react to a rate
limit, an overload, or an authentication failure without parsing
provider-specific status codes or message text itself.
"""

from __future__ import annotations

from typing import Optional


class ProviderError(Exception):
    """Base class for every error a `ModelProvider` raises.

    `status_code` is the HTTP status the provider returned, when the
    failure came from an HTTP response; it is `None` for a failure
    detected some other way (a malformed mid-stream payload, for
    instance).
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProviderAuthError(ProviderError):
    """The request was rejected for missing or invalid credentials."""


class ProviderQuotaExceededError(ProviderError):
    """The account has run out of credits to spend on this request."""


class ProviderRateLimitError(ProviderError):
    """The caller is being rate-limited.

    `retry_after` is the number of seconds the provider asked the
    caller to wait, taken from the response's `Retry-After` header
    when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


class ProviderOverloadedError(ProviderError):
    """The provider or an upstream model backend is temporarily unable to serve the request."""


class ProviderInvalidRequestError(ProviderError):
    """The request itself was rejected as malformed."""


class ProviderResponseError(ProviderError):
    """The provider returned a failure this taxonomy has no dedicated class for."""


class ProviderTransportError(ProviderError):
    """The connection to the provider failed before a mapped response was received.

    Covers a connection failure, a timeout, or a mid-stream
    disconnect — anything the transport itself raised rather than an
    HTTP response the provider returned.
    """


_RATE_LIMIT_STATUS_CODES = frozenset({429})
_AUTH_STATUS_CODES = frozenset({401, 403})
_QUOTA_STATUS_CODES = frozenset({402})
_INVALID_REQUEST_STATUS_CODES = frozenset({400})
_OVERLOADED_STATUS_CODES = frozenset({500, 502, 503, 524, 529})


def map_status_to_error(
    status_code: int,
    message: str,
    *,
    retry_after: Optional[float] = None,
) -> ProviderError:
    """Translate an HTTP status code (and its message) into a typed `ProviderError`.

    Used both for a failed HTTP response and for a mid-stream error
    payload, which carries the same status-code space in its `code`
    field.
    """
    if status_code in _RATE_LIMIT_STATUS_CODES:
        return ProviderRateLimitError(message, status_code=status_code, retry_after=retry_after)
    if status_code in _AUTH_STATUS_CODES:
        return ProviderAuthError(message, status_code=status_code)
    if status_code in _QUOTA_STATUS_CODES:
        return ProviderQuotaExceededError(message, status_code=status_code)
    if status_code in _INVALID_REQUEST_STATUS_CODES:
        return ProviderInvalidRequestError(message, status_code=status_code)
    if status_code in _OVERLOADED_STATUS_CODES:
        return ProviderOverloadedError(message, status_code=status_code)
    return ProviderResponseError(message, status_code=status_code)
