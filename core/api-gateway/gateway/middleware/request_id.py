"""Request ID middleware for request tracing."""

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .._observability import current_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique request ID to each request for tracing.

    Preserves the inbound `X-Request-ID` header when present, otherwise
    mints a fresh UUIDv4. Also writes the value into the shared
    ContextVar so log filters can read it without a request reference.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.state.request_id = request_id
        token = current_request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            current_request_id.reset(token)
        response.headers[self.HEADER_NAME] = request_id
        return response
