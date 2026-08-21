from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib.auth import update_session_auth_hash
from datetime import timedelta
import ipaddress
import secrets
import logging

from .consent_constants import EU_REGION_SET
from .models import (
    AccountDeletionRequest,
    ConsentRecord,
    DataExportRequest,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    SocialAccount,
    User,
)
from .permissions import IsVerifiedUser
from .services.signup_guard import check_ip_velocity
from .services.turnstile import verify_turnstile

# Import security utilities from centralized module
from security import (
    validate_image_magic_bytes,
    sanitize_image,
    get_image_format_from_mime,
)

# Centralized abuse / rate-limit helpers (see core/exceptions.py — task 18
# surface bootstrapped by task 19; see plan §0.3).
from exceptions import (
    apply_ratelimit,
    client_ip,
    emit_suspicious_activity,
    json_body_field_key,
)
from sterna.client_ip import get_client_ip
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    RefreshTokenSerializer,
    EmailVerificationSerializer,
    ResendVerificationSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
    SocialAccountSerializer,
    ConsentSerializer,
    ConsentAttachSerializer,
)
from .jwt_utils import JWTManager

logger = logging.getLogger(__name__)


@method_decorator(
    apply_ratelimit(key="ip", rate="5/h", group="register-ip", method="POST"),
    name="post",
)
@method_decorator(
    apply_ratelimit(
        key=json_body_field_key("email"),
        rate="10/h",
        group="register-email",
        method="POST",
    ),
    name="post",
)
class RegisterView(APIView):
    """User registration endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        ip = client_ip(request)

        block = check_ip_velocity(ip, request=request)
        if block is not None:
            return Response(
                {
                    "code": "SIGNUP_THROTTLED",
                    "reason": block.reason.value,
                    "message": (
                        "Too many signup attempts from your network. "
                        "Please try again later."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        token = request.data.get("turnstile_token", "") or ""
        if not verify_turnstile(token, ip):
            missing = not token
            emit_suspicious_activity(
                category="signup_abuse",
                reason="turnstile_missing" if missing else "turnstile_failed",
                request=request,
            )
            return Response(
                {
                    "code": "CAPTCHA_REQUIRED" if missing else "CAPTCHA_FAILED",
                    "message": "Please complete the security check and try again.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "message": "Registration successful. Please check your email to verify your account.",
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )

        email_errors = serializer.errors.get("email", [])
        for err in email_errors:
            if getattr(err, "code", "") == "disposable_email":
                raw_email = request.data.get("email") or ""
                if isinstance(raw_email, str) and "@" in raw_email:
                    email_domain = raw_email.rsplit("@", 1)[-1].lower()
                else:
                    email_domain = ""
                emit_suspicious_activity(
                    category="signup_abuse",
                    reason="disposable_email",
                    request=request,
                    email_domain=email_domain,
                )
                break
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(
    apply_ratelimit(
        key="ip",
        rate="30/m",
        method="POST",
        group="oauth",
        scope="auth.oauth.state",
    ),
    name="post",
)
class OAuthStateView(APIView):
    """Mint a one-time OAuth state nonce (task 19).

    The frontend calls this BEFORE redirecting the user to the OAuth
    provider. The minted nonce is stored in Redis with a 5-minute TTL
    and is consumed (deleted) by the OAuth callback handler.
    """

    permission_classes = [AllowAny]

    OAUTH_STATE_TTL_SECONDS = 300
    OAUTH_STATE_BYTES = 16

    def post(self, request):
        nonce = secrets.token_hex(self.OAUTH_STATE_BYTES)
        cache.set(
            f"oauth_state:{nonce}",
            True,
            timeout=self.OAUTH_STATE_TTL_SECONDS,
        )
        return Response({"state": nonce})


@method_decorator(
    apply_ratelimit(key="ip", rate="10/m", group="login-ip", method="POST"),
    name="post",
)
@method_decorator(
    apply_ratelimit(
        key=json_body_field_key("email"),
        rate="20/m",
        group="login-email",
        method="POST",
    ),
    name="post",
)
class LoginView(APIView):
    """User login endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            user = serializer.validated_data["user"]

            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            # Create JWT tokens
            tokens = JWTManager.create_token_pair(user)

            # Store request metadata in refresh token (DB stores the
            # SHA-256 hash of the raw token, so look up by hash)
            refresh_token = RefreshToken.objects.filter(
                token=RefreshToken.hash_token(tokens["refresh_token"])
            ).first()
            if refresh_token:
                refresh_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
                refresh_token.ip_address = get_client_ip(request)
                refresh_token.save()

            return Response({**tokens, "user": UserSerializer(user).data})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """User logout endpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Get refresh token from request
        refresh_token = request.data.get("refresh_token")

        if refresh_token:
            # Revoke the refresh token
            JWTManager.revoke_refresh_token(refresh_token)
            message = "Logout successful."
        else:
            # Revoke all user's refresh tokens
            count = JWTManager.revoke_all_user_tokens(request.user)
            message = f"Logout successful. Revoked {count} session(s)."

        return Response({"message": message})


class RefreshTokenView(APIView):
    """Refresh access token endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)

        if serializer.is_valid():
            refresh_token = serializer.validated_data["refresh_token"]
            new_tokens = JWTManager.refresh_access_token(refresh_token)

            if new_tokens:
                return Response(new_tokens)

            return Response(
                {"error": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmailVerificationView(APIView):
    """Email verification endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)

        if serializer.is_valid():
            token_obj = serializer.token_obj
            user = token_obj.user

            # Mark user as verified
            user.is_verified = True
            user.save(update_fields=["is_verified"])

            # Mark token as used
            token_obj.is_used = True
            token_obj.save()

            return Response(
                {
                    "message": "Email verified successfully.",
                    "user": UserSerializer(user).data,
                }
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(
    apply_ratelimit(
        key="user_or_ip",
        rate="5/d",
        group="resend-verification",
        method="POST",
    ),
    name="post",
)
class ResendVerificationView(APIView):
    """Resend email verification endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.user

            # Invalidate old tokens
            EmailVerificationToken.objects.filter(user=user, is_used=False).update(
                is_used=True
            )

            # Create new token
            token = secrets.token_urlsafe(32)
            EmailVerificationToken.objects.create(
                user=user, token=token, expires_at=timezone.now() + timedelta(hours=24)
            )

            # TODO: Send verification email asynchronously
            # send_verification_email.delay(user.id, token)

            return Response(
                {"message": "Verification email sent. Please check your inbox."}
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(
    apply_ratelimit(key="ip", rate="5/h", group="reset-ip", method="POST"),
    name="post",
)
@method_decorator(
    apply_ratelimit(
        key=json_body_field_key("email"),
        rate="3/h",
        group="reset-email",
        method="POST",
    ),
    name="post",
)
class PasswordResetRequestView(APIView):
    """Request password reset endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)

        if serializer.is_valid():
            serializer.validated_data["email"]

            # Always return success to avoid email enumeration
            response_message = "If an account exists with this email, a password reset link has been sent."

            if hasattr(serializer, "user"):
                user = serializer.user

                # Invalidate old tokens
                PasswordResetToken.objects.filter(user=user, is_used=False).update(
                    is_used=True
                )

                # Create new token
                token = secrets.token_urlsafe(32)
                PasswordResetToken.objects.create(
                    user=user,
                    token=token,
                    expires_at=timezone.now() + timedelta(hours=1),
                )

                # TODO: Send password reset email asynchronously
                # send_password_reset_email.delay(user.id, token)

            return Response({"message": response_message})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """Confirm password reset endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)

        if serializer.is_valid():
            token_obj = serializer.token_obj
            user = token_obj.user

            # Set new password
            user.set_password(serializer.validated_data["password"])
            user.save()

            # Mark token as used
            token_obj.is_used = True
            token_obj.save()

            # Revoke all refresh tokens for security
            JWTManager.revoke_all_user_tokens(user)

            return Response(
                {
                    "message": "Password reset successful. Please login with your new password."
                }
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """Change password endpoint for authenticated users."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data["new_password"])
            user.save()

            # Update session to prevent logout
            update_session_auth_hash(request, user)

            # Optionally revoke all refresh tokens except current
            # This is a security measure to logout from other devices
            if request.data.get("logout_other_sessions", False):
                current_token = request.data.get("current_refresh_token")
                if current_token:
                    RefreshToken.objects.filter(user=user, is_revoked=False).exclude(
                        token=RefreshToken.hash_token(current_token)
                    ).update(is_revoked=True)

            return Response({"message": "Password changed successfully."})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    """User profile endpoint."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user profile."""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        """Update current user profile."""
        serializer = UserSerializer(request.user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SessionListView(APIView):
    """List user's active sessions (refresh tokens)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get all active sessions."""
        sessions = RefreshToken.objects.filter(
            user=request.user, is_revoked=False, expires_at__gt=timezone.now()
        ).values("id", "created_at", "last_used", "user_agent", "ip_address")

        return Response({"sessions": list(sessions), "count": sessions.count()})

    def delete(self, request, session_id=None):
        """Revoke a specific session or all sessions."""
        if session_id:
            # Revoke specific session
            try:
                token = RefreshToken.objects.get(
                    id=session_id, user=request.user, is_revoked=False
                )
                token.is_revoked = True
                token.save()
                return Response({"message": "Session revoked successfully."})
            except RefreshToken.DoesNotExist:
                return Response(
                    {"error": "Session not found."}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Revoke all sessions
            count = JWTManager.revoke_all_user_tokens(request.user)
            return Response(
                {"message": f"All {count} session(s) revoked successfully."}
            )


class SocialAccountListView(APIView):
    """List all social accounts linked to the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get list of all social accounts for authenticated user."""
        accounts = request.user.social_accounts.all()
        serializer = SocialAccountSerializer(accounts, many=True)
        return Response(serializer.data)


class SocialAccountDisconnectView(APIView):
    """Disconnect a social account from the user."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, account_id):
        """Disconnect a social account."""
        try:
            account = request.user.social_accounts.get(id=account_id)
        except SocialAccount.DoesNotExist:
            return Response(
                {"error": "Social account not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user can disconnect
        has_password = request.user.has_usable_password()
        social_accounts_count = request.user.social_accounts.count()

        if not has_password and social_accounts_count <= 1:
            return Response(
                {
                    "error": "Cannot disconnect last social account. "
                    "Please set a password first or link another account."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider = account.get_provider_display()
        account.delete()

        return Response({"message": f"{provider} account disconnected successfully"})


class AvatarUploadView(APIView):
    """
    Upload and update user avatar.

    Security measures:
    1. Magic byte validation - verifies actual file content, not just Content-Type header
    2. Image re-encoding via PIL - strips EXIF metadata and prevents polyglot attacks
    3. Size limits - both file size and image dimensions
    4. Authenticated users only
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    # Allowed image MIME types
    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    # Max file size: 5MB
    MAX_SIZE = 5 * 1024 * 1024

    def post(self, request):
        """Upload a new avatar image."""
        if "file" not in request.FILES:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES["file"]

        # Validate file size first (before reading content)
        if file.size > self.MAX_SIZE:
            return Response(
                {"error": f"File too large. Maximum size: {self.MAX_SIZE // (1024 * 1024)}MB"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Read file content
            content = file.read()

            # Security: Validate magic bytes (don't trust Content-Type header)
            detected_type = validate_image_magic_bytes(content)
            if not detected_type or detected_type not in self.ALLOWED_TYPES:
                return Response(
                    {"error": "Invalid image file. Please upload a valid JPEG, PNG, GIF, or WebP image."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Security: Re-encode image to strip metadata and prevent polyglot attacks
            # This also validates the image is actually renderable
            target_format = get_image_format_from_mime(detected_type)
            try:
                sanitized_content, final_mime_type = sanitize_image(content, target_format)
            except ValueError as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Import storage service
            from workspaces.services.workspace_storage import (
                R2PathBuilder,
                get_storage_service,
            )

            user_id = str(request.user.id)

            # Generate R2 key with file extension
            extension = self._get_extension(final_mime_type)
            r2_key = f"{R2PathBuilder.user_avatar(user_id)}.{extension}"

            # Upload sanitized image to R2
            storage = get_storage_service()
            success = storage._upload_to_r2(r2_key, sanitized_content, final_mime_type)

            if not success:
                return Response(
                    {"error": "Failed to upload avatar. Please try again."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Store the R2 key as a special URL format
            # Format: r2://{bucket}/{key} - will be resolved to presigned URL when needed
            avatar_storage_url = f"r2://{storage.config.bucket_name}/{r2_key}"

            # Update user's avatar_url with storage reference
            request.user.avatar_url = avatar_storage_url
            request.user.save(update_fields=["avatar_url"])

            logger.info(
                "auth.avatar_uploaded",
                extra={"user_id": str(user_id), "r2_key": r2_key},
            )

            # Return a fresh presigned URL for immediate use
            avatar_url = self._generate_avatar_url(storage, r2_key, final_mime_type)

            return Response({
                "avatar_url": avatar_url,
                "message": "Avatar uploaded successfully",
            })

        except Exception:
            logger.error(
                "auth.avatar_upload_failed",
                extra={"user_id": str(request.user.id)},
                exc_info=True,
            )
            return Response(
                {"error": "Failed to upload avatar. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request):
        """Remove user's avatar (reset to default)."""
        try:
            avatar_url = request.user.avatar_url

            # Only delete from R2 if the avatar is stored there
            if avatar_url and avatar_url.startswith("r2://"):
                from workspaces.services.workspace_storage import get_storage_service

                storage = get_storage_service()

                # Parse r2://bucket/key format
                path = avatar_url[5:]  # Remove 'r2://'
                parts = path.split('/', 1)
                if len(parts) == 2:
                    _, r2_key = parts
                    storage._delete_from_r2(r2_key)

            # Clear the avatar URL
            request.user.avatar_url = ""
            request.user.save(update_fields=["avatar_url"])

            return Response({"message": "Avatar removed successfully"})

        except Exception:
            logger.error(
                "auth.avatar_delete_failed",
                extra={"user_id": str(request.user.id)},
                exc_info=True,
            )
            return Response(
                {"error": "Failed to remove avatar. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_extension(self, content_type: str) -> str:
        """Get file extension from MIME type."""
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        return extensions.get(content_type, "png")

    def _generate_avatar_url(self, storage, r2_key: str, content_type: str) -> str:
        """Generate a presigned URL for the avatar."""
        try:
            client = storage._get_r2_client()
            if client:
                # Generate presigned URL valid for 7 days
                url = client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': storage.config.bucket_name,
                        'Key': r2_key,
                        'ResponseContentType': content_type,
                    },
                    ExpiresIn=7 * 24 * 60 * 60,  # 7 days
                )
                return url
        except Exception:
            logger.warning("auth.avatar_presigned_url_failed", exc_info=True)

        # Fallback: construct direct URL (requires public bucket or CDN)
        return f"{storage.config.effective_endpoint_url}/{storage.config.bucket_name}/{r2_key}"



@api_view(['GET'])
@authentication_classes([])  # No authentication required - public endpoint
@permission_classes([AllowAny])
def serve_user_avatar(request, user_id: str):
    """
    Serve user avatar image.

    This endpoint bypasses CORS issues with presigned R2 URLs by proxying
    the image through the backend. The image is fetched from R2 and returned
    with proper cache headers.

    Args:
        user_id: UUID of the user

    Returns:
        Image binary with appropriate Content-Type header
    """
    from django.http import HttpResponse
    from uuid import UUID

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return Response(
            {'error': 'Invalid user ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get user
    try:
        user = User.objects.get(id=user_uuid)
    except User.DoesNotExist:
        return HttpResponse(status=404)

    avatar_url = user.avatar_url

    if not avatar_url:
        return HttpResponse(status=404)

    # task-29 C3 fix: only redirect to OAuth-provider CDNs. C2's fix
    # blocks self-set avatar_url via PATCH, but OAuth login flows
    # write the provider's URL straight onto the user. We require a
    # configured allowlist (suffix match) and 404 otherwise — defense
    # in depth against a hostile OAuth profile.
    if not avatar_url.startswith('r2://'):
        from django.conf import settings
        from django.http import HttpResponseRedirect
        from urllib.parse import urlparse

        allowlist = tuple(
            d.lower() for d in getattr(
                settings,
                "AVATAR_REDIRECT_ALLOWLIST",
                ("googleusercontent.com", "avatars.githubusercontent.com"),
            )
        )
        try:
            host = (urlparse(avatar_url).hostname or "").lower()
        except (ValueError, TypeError):
            return HttpResponse(status=404)
        if not any(host == d or host.endswith(f".{d}") for d in allowlist):
            logger.warning(
                "auth.avatar_redirect_blocked",
                extra={"user_id": str(user_id), "host": host},
            )
            return HttpResponse(status=404)
        return HttpResponseRedirect(avatar_url)

    # Parse r2://bucket/key format
    path = avatar_url[5:]  # Remove 'r2://'
    parts = path.split('/', 1)
    if len(parts) != 2:
        return HttpResponse(status=404)

    bucket, key = parts

    try:
        from workspaces.services.workspace_storage import get_storage_service

        storage = get_storage_service()
        client = storage._get_r2_client()

        if not client:
            logger.warning(
                "auth.r2_client_unavailable",
                extra={"context": "serve_user_avatar"},
            )
            return HttpResponse(status=503)

        # Fetch the image from R2
        response = client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read()
        content_type = response.get('ContentType', 'image/png')

        # Determine content type from key extension if not set
        if content_type == 'application/octet-stream':
            if key.endswith('.jpg') or key.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif key.endswith('.gif'):
                content_type = 'image/gif'
            elif key.endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = 'image/png'

        # Return image with cache headers
        http_response = HttpResponse(content, content_type=content_type)
        http_response['Cache-Control'] = 'public, max-age=86400'  # 24 hours
        http_response['Content-Length'] = len(content)

        return http_response

    except Exception:
        logger.error(
            "auth.serve_avatar_failed",
            extra={"user_id": str(user_id)},
            exc_info=True,
        )
        return HttpResponse(status=500)


def _anonymize_ip(ip: str) -> str:
    """Zero the last octet of an IPv4 or the last 80 bits of an IPv6."""
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if isinstance(addr, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        return str(network.network_address)
    network = ipaddress.ip_network(f"{ip}/48", strict=False)
    return str(network.network_address)


def _detect_region(request) -> str:
    country = request.META.get("HTTP_CF_IPCOUNTRY", "").upper()
    if not country or country == "XX":
        return "unknown"
    return "EU" if country in EU_REGION_SET else "non-EU"


def _region_default_for_client(request) -> str:
    region = _detect_region(request)
    return "EU" if region == "unknown" else region


class ConsentView(APIView):
    """Anonymous-or-authenticated consent record CRUD."""

    permission_classes = [AllowAny]

    def get(self, request):
        session_id = request.query_params.get("session_id", "").strip()
        record_payload = None
        if session_id:
            record = ConsentRecord.objects.filter(session_id=session_id).first()
            if record:
                record_payload = {
                    "session_id": record.session_id,
                    "categories": record.categories,
                    "version": record.version,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                }
        return Response(
            {
                "consent": record_payload,
                "region_default": _region_default_for_client(request),
            }
        )

    def post(self, request):
        serializer = ConsentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        ip = _anonymize_ip(get_client_ip(request))
        user = request.user if request.user.is_authenticated else None

        # Do NOT use update_or_create with `user` in defaults — that would
        # silently reassign the FK on every POST and destroy the audit
        # trail. Bind the FK only on create, or on update of an unbound row.
        record = ConsentRecord.objects.filter(
            session_id=data["session_id"]
        ).first()
        if record:
            record.categories = data["categories"]
            record.version = data["version"]
            record.ip_anonymized = ip
            if user is not None and record.user_id is None:
                record.user = user
            record.save()
            created = False
        else:
            record = ConsentRecord.objects.create(
                session_id=data["session_id"],
                categories=data["categories"],
                version=data["version"],
                ip_anonymized=ip,
                user=user,
            )
            created = True

        return Response(
            {
                "consent": {
                    "session_id": record.session_id,
                    "categories": record.categories,
                    "version": record.version,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                },
                "region_default": _region_default_for_client(request),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConsentAttachView(APIView):
    """Bind anonymous ConsentRecord rows to the now-authenticated user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConsentAttachSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        session_id = serializer.validated_data["session_id"]
        updated = ConsentRecord.objects.filter(
            session_id=session_id, user__isnull=True
        ).update(user=request.user)
        return Response({"attached": updated})
class DataExportRequestView(APIView):
    """POST /api/auth/account/data-export — request a data export zip."""

    permission_classes = [IsAuthenticated, IsVerifiedUser]

    def post(self, request):
        user = request.user
        now = timezone.now()

        if DataExportRequest.objects.filter(
            user=user,
            status__in=[
                DataExportRequest.Status.PENDING,
                DataExportRequest.Status.PROCESSING,
            ],
        ).exists():
            return Response(
                {"error": "An export is already in progress."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        recent = DataExportRequest.objects.filter(
            user=user,
            status=DataExportRequest.Status.READY,
            ready_at__gt=now - timedelta(hours=24),
        ).exists()
        if recent:
            return Response(
                {"error": "Please wait 24 hours between data exports."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        req = DataExportRequest.objects.create(user=user)

        from .tasks import export_user_data
        export_user_data.delay(str(user.id), str(req.id))

        return Response(
            {"request_id": str(req.id), "status": req.status},
            status=status.HTTP_202_ACCEPTED,
        )


class DataExportStatusView(APIView):
    """GET /api/auth/account/data-export/<uuid:request_id>"""

    permission_classes = [IsAuthenticated, IsVerifiedUser]

    def get(self, request, request_id):
        try:
            req = DataExportRequest.objects.get(
                id=request_id, user=request.user
            )
        except DataExportRequest.DoesNotExist:
            return Response(
                {"error": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        body = {
            "request_id": str(req.id),
            "status": req.status,
            "requested_at": req.requested_at.isoformat(),
        }
        if req.status == DataExportRequest.Status.READY:
            body.update({
                "download_url": req.download_url,
                "expires_at": (
                    req.download_url_expires_at.isoformat()
                    if req.download_url_expires_at else None
                ),
                "ready_at": (
                    req.ready_at.isoformat() if req.ready_at else None
                ),
            })
        elif req.status == DataExportRequest.Status.FAILED:
            body["error"] = req.failed_reason or "Export failed."
        return Response(body)


class AccountDeletionRequestView(APIView):
    """POST /api/auth/account/delete-request"""

    permission_classes = [IsAuthenticated, IsVerifiedUser]

    def post(self, request):
        user = request.user
        password = request.data.get("password") or ""
        confirm_email = (
            request.data.get("confirm_email") or ""
        ).strip().lower()

        if confirm_email != user.email.lower():
            return Response(
                {"error": "Email confirmation does not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.has_usable_password():
            if not user.check_password(password):
                return Response(
                    {"error": "Invalid password."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        existing = AccountDeletionRequest.objects.filter(
            user=user, status=AccountDeletionRequest.Status.PENDING
        ).first()
        if existing:
            return Response(
                {
                    "request_id": str(existing.id),
                    "scheduled_for": existing.scheduled_for.isoformat(),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        scheduled_for = timezone.now() + timedelta(days=7)
        jti = secrets.token_urlsafe(32)
        req = AccountDeletionRequest.objects.create(
            user=user,
            user_email_snapshot=user.email,
            scheduled_for=scheduled_for,
            cancel_token_jti=jti,
        )

        user.is_active = False
        user.save(update_fields=["is_active"])
        JWTManager.revoke_all_user_tokens(user)

        from .tokens import create_cancel_deletion_token
        from notifications.services import send_account_deletion_confirmation
        cancel_token = create_cancel_deletion_token(req)
        try:
            send_account_deletion_confirmation(
                user,
                cancel_token=cancel_token,
                grace_days=7,
                request_id=str(req.id),
            )
        except Exception:
            logger.exception("Failed to send deletion confirmation email")

        return Response(
            {
                "request_id": str(req.id),
                "scheduled_for": req.scheduled_for.isoformat(),
                "status": req.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AccountDeletionCancelView(APIView):
    """POST /api/auth/account/delete-request/cancel

    body: { "token": "<one-shot JWT>" }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        from .tokens import verify_cancel_deletion_token

        token = (request.data.get("token") or "").strip()
        if not token:
            return Response(
                {"error": "Missing token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = verify_cancel_deletion_token(token)
        if not result:
            return Response(
                {"error": "Invalid or expired cancellation link."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        req_id, jti = result

        try:
            req = AccountDeletionRequest.objects.get(
                id=req_id, cancel_token_jti=jti
            )
        except AccountDeletionRequest.DoesNotExist:
            return Response(
                {"error": "Cancellation request not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # One-shot semantics: once the request is CANCELED / COMPLETED
        # / FAILED the token is spent (see tokens.py docstring).
        if req.status != AccountDeletionRequest.Status.PENDING:
            return Response(
                {"error": "This deletion request is no longer pending."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = req.user
        with transaction.atomic():
            req.status = AccountDeletionRequest.Status.CANCELED
            req.canceled_at = timezone.now()
            req.save(update_fields=["status", "canceled_at"])
            if user is not None and not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])

        logger.info(
            "account_deletion.canceled",
            extra={
                "deletion_request_id": str(req.id),
                "user_id": str(user.id) if user else None,
            },
        )
        try:
            from audit_logging.services import AuditService

            AuditService.log_action(
                action="AUTH_ACCOUNT_DELETION_CANCELED",
                user=user,
                deletion_request_id=str(req.id),
            )
        except Exception:
            logger.exception(
                "Failed to write deletion-cancel audit entry"
            )

        return Response(
            {
                "request_id": str(req.id),
                "status": req.status,
                "canceled_at": req.canceled_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
