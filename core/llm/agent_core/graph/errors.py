"""Translates a failed provider call into the `error` event a caller sees.

A `ProviderError` carries a transport-level message written for an
operator. What reaches the stream is a sentence written for the person
waiting on the answer, plus the original message as `detail` so the
operator's version is not lost, plus a machine-readable `code` for the
handful of failures a frontend reacts to programmatically.

A turn that ends on an error ends there: an `error` event is terminal
and no `done` event follows it.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Type, TypeVar

from ..events import ErrorCode, ErrorEvent
from ..provider_errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderOverloadedError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
)

SERVICE_UNAVAILABLE_MESSAGE = "The AI service is temporarily unavailable. Please try again."
AUTH_FAILED_MESSAGE = "The AI provider rejected the configured credentials."
QUOTA_EXCEEDED_MESSAGE = "The account has run out of credits for this request."
RATE_LIMITED_MESSAGE = "The AI provider is rate-limiting this account. Please try again shortly."
INVALID_REQUEST_MESSAGE = "The AI provider rejected the request as invalid."

_MESSAGES: Dict[Type[ProviderError], str] = {
    ProviderAuthError: AUTH_FAILED_MESSAGE,
    ProviderQuotaExceededError: QUOTA_EXCEEDED_MESSAGE,
    ProviderRateLimitError: RATE_LIMITED_MESSAGE,
    ProviderInvalidRequestError: INVALID_REQUEST_MESSAGE,
    ProviderOverloadedError: SERVICE_UNAVAILABLE_MESSAGE,
    ProviderTransportError: SERVICE_UNAVAILABLE_MESSAGE,
    ProviderResponseError: SERVICE_UNAVAILABLE_MESSAGE,
}

_CODES: Dict[Type[ProviderError], ErrorCode] = {
    ProviderQuotaExceededError: ErrorCode.QUOTA_EXCEEDED,
}


_Entry = TypeVar("_Entry")


def _lookup(error: ProviderError, table: Mapping[Type[ProviderError], _Entry]) -> Optional[_Entry]:
    """The table entry for the nearest ancestor of `error`'s type."""

    for ancestor in type(error).__mro__:
        if not issubclass(ancestor, ProviderError):
            continue
        entry = table.get(ancestor)
        if entry is not None:
            return entry
    return None


def to_error_event(error: ProviderError) -> ErrorEvent:
    """The terminal `error` event describing a failed provider call."""

    message = _lookup(error, _MESSAGES) or SERVICE_UNAVAILABLE_MESSAGE
    return ErrorEvent(
        error=message,
        detail=error.message or None,
        code=_lookup(error, _CODES),
        extra={"status_code": error.status_code} if error.status_code is not None else None,
    )
