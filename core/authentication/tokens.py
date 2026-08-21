"""One-shot signed JWT for account-deletion cancel link."""

from typing import Optional, Tuple

import jwt
from django.conf import settings
from django.utils import timezone


CANCEL_TOKEN_TYPE = "cancel_deletion"


def create_cancel_deletion_token(deletion_request) -> str:
    """Returns a JWT valid until the request's scheduled_for time."""
    payload = {
        "type": CANCEL_TOKEN_TYPE,
        "request_id": str(deletion_request.id),
        "jti": deletion_request.cancel_token_jti,
        "iat": timezone.now(),
        "exp": deletion_request.scheduled_for,
    }
    return jwt.encode(
        payload,
        getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY),
        algorithm=getattr(settings, "JWT_ALGORITHM", "HS256"),
    )


def verify_cancel_deletion_token(token: str) -> Optional[Tuple[str, str]]:
    """Returns (request_id, jti) if valid; None otherwise.

    "One-shot" semantics are enforced at the view layer by checking
    AccountDeletionRequest.status == PENDING — once it is CANCELED or
    COMPLETED, re-use of the same token fails with the 400 from the
    view, not a 401 here.
    """
    try:
        payload = jwt.decode(
            token,
            getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY),
            algorithms=[getattr(settings, "JWT_ALGORITHM", "HS256")],
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != CANCEL_TOKEN_TYPE:
        return None
    rid = payload.get("request_id")
    jti = payload.get("jti")
    if not rid or not jti:
        return None
    return (rid, jti)
