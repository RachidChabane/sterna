"""WebSocket authentication middleware for voice rooms."""

import logging
from urllib.parse import parse_qs

import jwt
from channels.db import database_sync_to_async  # type: ignore[import-untyped]
from channels.middleware import BaseMiddleware  # type: ignore[import-untyped]
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT.

    Token is expected in query string: ws://...?token=<jwt_token>
    """

    async def __call__(self, scope, receive, send):
        # Get token from query string
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        if token:
            scope["user"] = await self.get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user_from_token(self, token: str):
        """Validate JWT token and return user."""
        try:
            # Use same secret key as JWTManager
            secret_key = getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY)
            algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")

            # Decode token
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[algorithm],
            )

            # Get user ID from token
            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id:
                logger.warning("No user_id in JWT payload")
                return AnonymousUser()

            # Get user from database
            try:
                user = User.objects.get(id=user_id)
                return user
            except User.DoesNotExist:
                logger.warning(f"User {user_id} not found")
                return AnonymousUser()

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return AnonymousUser()
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return AnonymousUser()
        except Exception as e:
            logger.error(f"Error validating JWT: {e}")
            return AnonymousUser()
