from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from .jwt_utils import JWTManager

User = get_user_model()


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to authenticate users using JWT tokens from Authorization header.
    """

    def process_request(self, request):
        """
        Extract and verify JWT token from Authorization header.
        """
        # Skip if user is already authenticated
        if hasattr(request, "user") and request.user.is_authenticated:
            return

        # Get Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if auth_header.startswith("Bearer "):
            # Extract token
            token = auth_header[7:]

            # Verify token
            payload = JWTManager.verify_token(token, token_type="access")

            if payload:
                try:
                    # Get user from payload
                    user = User.objects.get(id=payload["user_id"])
                    request.user = user
                    request.jwt_payload = payload
                except User.DoesNotExist:
                    request.user = AnonymousUser()
            else:
                request.user = AnonymousUser()
        else:
            request.user = AnonymousUser()
