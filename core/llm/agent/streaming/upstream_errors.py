"""Classification of upstream errors both streaming paths must react to.

The two paths recover from an over-long context differently -- the Direct
Client trims the oldest messages and retries, the LangChain path
summarizes and replays -- but they must agree on *what counts as* a 413,
so that predicate has one definition here.

The string-only variant is deliberately separate: it exists for wrappers
that raise a plain exception carrying no `status_code`, and widening it to
consult attributes would change which branch such an error takes.
"""

HTTP_REQUEST_ENTITY_TOO_LARGE = 413
_TOO_LARGE_MESSAGE_MARKER = "request entity too large"


def is_request_too_large_message(error_str: str) -> bool:
    """413 detection from the error text alone."""
    return (
        str(HTTP_REQUEST_ENTITY_TOO_LARGE) in error_str
        or _TOO_LARGE_MESSAGE_MARKER in error_str.lower()
    )


def is_request_too_large(error: Exception) -> bool:
    """Whether an upstream error is 'Request Entity Too Large'.

    Consults the exception's status/code attributes first, then falls back
    to its text -- providers are inconsistent about which they populate.
    """
    error_code = getattr(error, 'status_code', None) or getattr(error, 'code', None)
    return (
        error_code == HTTP_REQUEST_ENTITY_TOO_LARGE
        or is_request_too_large_message(str(error))
    )
