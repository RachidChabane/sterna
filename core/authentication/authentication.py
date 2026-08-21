from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from sterna.middleware.request_id import current_user_id
from .jwt_utils import JWTManager

User = get_user_model()


class JWTAuthentication(BaseAuthentication):
    """
    JWT token-based authentication for Django REST Framework.
    """

    def authenticate(self, request):
        """
        Authenticate the request using JWT token from Authorization header.
        """
        # Get Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Bearer "):
            return None

        # Extract token
        token = auth_header[7:]

        if not token:
            return None

        # Verify token
        payload = JWTManager.verify_token(token, token_type="access")

        if not payload:
            raise AuthenticationFailed("Invalid or expired token")

        try:
            # Get user from payload
            user = User.objects.get(id=payload["user_id"])

            if not user.is_active:
                raise AuthenticationFailed("User account is disabled")

            # Store JWT payload in request for potential use
            request.jwt_payload = payload

            try:
                request._user_id_token = current_user_id.set(str(user.id))
            except (AttributeError, TypeError):
                pass

            return (user, None)

        except User.DoesNotExist:
            raise AuthenticationFailed("User not found")

    def authenticate_header(self, request):
        """
        Return the authentication header required.
        """
        return "Bearer"


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """
    Tells drf-spectacular how to represent JWTAuthentication in the
    generated OpenAPI schema (as a standard HTTP bearer scheme).
    """

    target_class = "authentication.authentication.JWTAuthentication"
    name = "Bearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
