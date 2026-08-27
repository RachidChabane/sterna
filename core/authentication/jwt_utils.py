import jwt
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from typing import Dict, Optional, Tuple, TypedDict
import secrets

_logger = logging.getLogger("authentication.jwt")


class TokenPairPayload(TypedDict):
    """Response shape shared by ``create_token_pair`` and ``refresh_access_token``."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class JWTManager:
    """Manage JWT token creation and validation."""

    @staticmethod
    def get_secret_key():
        """Get the JWT secret key from settings."""
        return getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY)

    @staticmethod
    def get_algorithm():
        """Get the JWT algorithm from settings."""
        return getattr(settings, "JWT_ALGORITHM", "HS256")

    @staticmethod
    def get_access_token_lifetime():
        """Get access token lifetime from settings."""
        return getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME", timedelta(minutes=15))

    @staticmethod
    def get_refresh_token_lifetime():
        """Get refresh token lifetime from settings."""
        return getattr(settings, "JWT_REFRESH_TOKEN_LIFETIME", timedelta(days=7))

    @classmethod
    def create_access_token(cls, user) -> str:
        """Create an access token for a user."""
        now = timezone.now()
        payload = {
            "user_id": str(user.id),
            "email": user.email,
            "type": "access",
            "iat": now,
            "exp": now + cls.get_access_token_lifetime(),
            "jti": secrets.token_urlsafe(16),
        }

        return jwt.encode(payload, cls.get_secret_key(), algorithm=cls.get_algorithm())

    @classmethod
    def create_refresh_token(cls, user) -> Tuple[str, datetime]:
        """Create a refresh token for a user and return token with expiry."""
        now = timezone.now()
        expires_at = now + cls.get_refresh_token_lifetime()

        payload = {
            "user_id": str(user.id),
            "email": user.email,
            "type": "refresh",
            "iat": now,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(32),
        }

        token = jwt.encode(payload, cls.get_secret_key(), algorithm=cls.get_algorithm())

        return token, expires_at

    @classmethod
    def verify_token(cls, token: str, token_type: str = "access") -> Optional[Dict]:
        """
        Verify and decode a JWT token.

        task-29 H4: dev-token bypass is now opt-in (``DEV_TOKEN_BYPASS=True``)
        and explicitly disabled when ``DJANGO_ENV=prod``. Previously, a
        misconfigured prod environment with ``DEBUG=True`` would have
        accepted dev tokens. Now both conditions must hold.

        In production (``DJANGO_ENV=prod``) the bypass is unreachable
        regardless of other settings.
        """
        # Dev-token bypass — explicit opt-in only.
        bypass_enabled = getattr(settings, "DEV_TOKEN_BYPASS", False)
        env = getattr(settings, "DJANGO_ENV", "dev")
        if (
            bypass_enabled
            and env != "prod"
            and token.startswith("dev-")
        ):
            _logger.warning(
                "jwt.dev_token_accepted prefix=%s env=%s",
                token[:20],
                env,
            )
            return {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "email": "dev@example.com",
                "type": token_type,
            }

        try:
            payload = jwt.decode(
                token, cls.get_secret_key(), algorithms=[cls.get_algorithm()]
            )

            if payload.get("type") != token_type:
                return None

            return payload

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @classmethod
    def create_token_pair(cls, user) -> TokenPairPayload:
        """Create both access and refresh tokens for a user.

        Only the SHA-256 digest of the refresh token is persisted —
        a database leak must not yield usable refresh tokens.
        """
        from .models import RefreshToken

        access_token = cls.create_access_token(user)
        refresh_token, expires_at = cls.create_refresh_token(user)

        # Store the refresh token hash in the database (starts a new
        # rotation family via the field default).
        RefreshToken.objects.create(
            user=user,
            token=RefreshToken.hash_token(refresh_token),
            expires_at=expires_at,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": int(cls.get_access_token_lifetime().total_seconds()),
        }

    @staticmethod
    def get_rotation_grace():
        """Reuse-grace window for concurrent refreshes (timedelta).

        The frontend interceptors have no single-flight mutex: on
        access-token expiry, parallel 401s each retry with the same
        refresh token. Within this window a just-rotated token may
        rotate again (Auth0-style "reuse interval") instead of being
        treated as theft.
        """
        return getattr(
            settings, "JWT_REFRESH_ROTATION_GRACE", timedelta(seconds=60)
        )

    @classmethod
    def refresh_access_token(cls, refresh_token: str) -> Optional[TokenPairPayload]:
        """Rotate the refresh token and mint a new access token.

        Standard refresh-token rotation with reuse detection:

        * the presented token is revoked and a successor is issued in
          the same ``family`` (session metadata carries over);
        * presenting an already-revoked token is treated as theft —
          the whole family is revoked and a structured warning logged
          — unless the token was rotated less than
          ``JWT_REFRESH_ROTATION_GRACE`` ago (concurrent-request race,
          see :meth:`get_rotation_grace`), in which case another
          successor is issued in the same family.

        Returns the same fields as :meth:`create_token_pair`
        (``access_token``, ``refresh_token``, ``token_type``,
        ``expires_in``) so the response is a superset of the
        pre-rotation shape.
        """
        from .models import RefreshToken, User

        # Verify the refresh token signature/expiry/type
        payload = cls.verify_token(refresh_token, token_type="refresh")
        if not payload:
            return None

        token_hash = RefreshToken.hash_token(refresh_token)
        try:
            db_token = RefreshToken.objects.get(token=token_hash)
        except RefreshToken.DoesNotExist:
            return None

        now = timezone.now()

        if db_token.is_revoked:
            # ``last_used`` is stamped at rotation time; tokens revoked
            # any other way (logout, family kill, revoke-all) don't
            # get it refreshed, so only a genuine just-rotated token
            # can land in the grace window. The window is anchored to
            # the original rotation and never slides — replaying the
            # same token cannot keep it open.
            within_grace = (
                db_token.last_used is not None
                and now - db_token.last_used <= cls.get_rotation_grace()
            )
            if not within_grace:
                # Reuse of a rotated/revoked token — assume the family
                # is compromised and revoke every member still active.
                revoked_count = RefreshToken.objects.filter(
                    family=db_token.family, is_revoked=False
                ).update(is_revoked=True)
                _logger.warning(
                    "jwt.refresh_token_reuse_detected user_id=%s family=%s "
                    "revoked_count=%d",
                    db_token.user_id,
                    db_token.family,
                    revoked_count,
                )
                return None
            _logger.info(
                "jwt.refresh_token_reuse_within_grace user_id=%s family=%s",
                db_token.user_id,
                db_token.family,
            )
        elif db_token.expires_at <= now:
            return None

        try:
            user = User.objects.get(id=payload["user_id"])
        except User.DoesNotExist:
            return None

        if not db_token.is_revoked:
            # Rotate: revoke the presented token (grace-window reuse
            # skips this — the token is already revoked and its
            # ``last_used`` anchor must not move)…
            db_token.is_revoked = True
            db_token.last_used = now
            db_token.save(update_fields=["is_revoked", "last_used"])

        # …and issue its successor in the same family, carrying the
        # session metadata forward so SessionListView stays coherent.
        new_refresh_token, expires_at = cls.create_refresh_token(user)
        RefreshToken.objects.create(
            user=user,
            token=RefreshToken.hash_token(new_refresh_token),
            expires_at=expires_at,
            family=db_token.family,
            user_agent=db_token.user_agent,
            ip_address=db_token.ip_address,
            metadata=db_token.metadata,
        )

        access_token = cls.create_access_token(user)

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": int(cls.get_access_token_lifetime().total_seconds()),
        }

    @classmethod
    def revoke_refresh_token(cls, refresh_token: str) -> bool:
        """Revoke a refresh token (accepts the raw token from the client)."""
        from .models import RefreshToken

        try:
            db_token = RefreshToken.objects.get(
                token=RefreshToken.hash_token(refresh_token)
            )
            db_token.is_revoked = True
            db_token.save()
            return True
        except RefreshToken.DoesNotExist:
            return False

    @classmethod
    def revoke_all_user_tokens(cls, user) -> int:
        """Revoke all refresh tokens for a user."""
        from .models import RefreshToken

        return RefreshToken.objects.filter(user=user, is_revoked=False).update(
            is_revoked=True
        )
