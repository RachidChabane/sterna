"""
Internal service authentication utilities.

Provides token-based authentication for service-to-service communication,
specifically for the orchestrator calling Django backend endpoints.

This adds a layer of security beyond network isolation:
1. Validates that requests come from authorized internal services
2. Provides audit trail capability
3. Allows fine-grained service permissions in the future
"""

import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class ServiceAuthenticationFailed(Exception):
    """Raised when service authentication fails."""
    pass


def get_service_token() -> str | None:
    """
    Get the configured internal service token from settings.

    Returns:
        Service token string or None if not configured
    """
    return getattr(settings, 'INTERNAL_SERVICE_TOKEN', None)


def verify_service_token(
    request,
    required: bool = True,
) -> bool:
    """
    Verify that a request contains a valid internal service token.

    The token should be passed in the X-Service-Token header.

    Args:
        request: Django/DRF request object
        required: If True, raise exception on failure. If False, return bool.

    Returns:
        True if valid, False if invalid (when required=False)

    Raises:
        ServiceAuthenticationFailed: If required=True and verification fails
    """
    expected_token = get_service_token()

    # If no token is configured, behavior depends on DEBUG mode
    if not expected_token:
        debug_mode = getattr(settings, 'DEBUG', False)
        if debug_mode:
            # In debug mode without token, allow the request but log warning
            logger.warning(
                "INTERNAL_SERVICE_TOKEN not configured - allowing request in DEBUG mode. "
                "Set INTERNAL_SERVICE_TOKEN in production!"
            )
            return True
        else:
            # In production without token configured, deny all internal requests
            logger.error(
                "INTERNAL_SERVICE_TOKEN not configured in production. "
                "Internal service requests are blocked."
            )
            if required:
                raise ServiceAuthenticationFailed(
                    "Internal service authentication not configured"
                )
            return False

    # Get token from request header
    provided_token = request.headers.get('X-Service-Token', '')

    if not provided_token:
        logger.warning(
            f"Internal service request without token from "
            f"{request.META.get('REMOTE_ADDR', 'unknown')}"
        )
        if required:
            raise ServiceAuthenticationFailed("Missing service token")
        return False

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_token, provided_token):
        logger.warning(
            f"Invalid internal service token from "
            f"{request.META.get('REMOTE_ADDR', 'unknown')}"
        )
        if required:
            raise ServiceAuthenticationFailed("Invalid service token")
        return False

    logger.debug("Internal service request authenticated")
    return True


def require_service_auth(view_func):
    """
    Decorator to require internal service authentication.

    Use this on views that should only be called by internal services
    (like the orchestrator).

    Example:
        @api_view(['POST'])
        @permission_classes([AllowAny])  # Skip user auth
        @require_service_auth
        def save_workspace(request):
            ...
    """
    from functools import wraps
    from rest_framework.response import Response
    from rest_framework import status

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            verify_service_token(request, required=True)
        except ServiceAuthenticationFailed as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return view_func(request, *args, **kwargs)

    return wrapper
