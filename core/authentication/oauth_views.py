"""
OAuth authentication views for social login providers.
"""
import hashlib
import time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from google.auth.transport import requests
from google.oauth2 import id_token
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import logging

from exceptions import apply_ratelimit

from .jwt_utils import JWTManager
from .serializers import UserSerializer
from .models import RefreshToken, SocialAccount

from exceptions import emit_suspicious_activity
from sterna.client_ip import get_client_ip

logger = logging.getLogger(__name__)
User = get_user_model()


def _google_token_auth(request):
    """Shared implementation for ``google_auth`` / ``google_one_tap_auth``.

    Expected request body:
    {
        "credential": "Google ID token from frontend"
    }
    """
    credential = request.data.get('credential')

    if not credential:
        return Response(
            {'error': 'Google credential is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Verify the Google ID token with clock skew tolerance
        idinfo = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
            clock_skew_in_seconds=300  # Allow 5 minutes clock skew
        )

        # Google's OAuth2 audience check
        if idinfo['aud'] != settings.GOOGLE_OAUTH_CLIENT_ID:
            raise ValueError('Invalid audience.')

        # Extract user info from Google token
        email = idinfo.get('email')
        email_verified = idinfo.get('email_verified', False)
        first_name = idinfo.get('given_name', '')
        last_name = idinfo.get('family_name', '')
        picture = idinfo.get('picture', '')
        google_id = idinfo.get('sub')  # Google's unique user ID
        issued_at = idinfo.get('iat')

        # Defense-in-depth: reject ID tokens issued more than 10 minutes
        # ago. The library already checks `exp` with 300s skew; this
        # adds a wider absolute upper bound (task 19, plan §9.2).
        if issued_at and (time.time() - issued_at) > 600:
            logger.warning(
                "google_oauth.token_too_old",
                extra={"sub": google_id, "iat": issued_at},
            )
            emit_suspicious_activity(
                category="oauth_replay",
                reason="google_token_too_old",
                request=request,
            )
            return Response(
                {"error": "Authentication token expired. Please sign in again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Replay guard: SHA-256(sub|iat). 10-minute Redis TTL — a fresh
        # legitimate token gets a new iat each call (task 19, §9.2).
        if google_id and issued_at is not None:
            replay_key = "oauth_replay:google:" + hashlib.sha256(
                f"{google_id}:{issued_at}".encode("utf-8")
            ).hexdigest()
            if not cache.add(replay_key, True, timeout=600):
                emit_suspicious_activity(
                    category="oauth_replay",
                    reason="google_credential_reused",
                    request=request,
                )
                return Response(
                    {"error": "Authentication token already used."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if not email:
            return Response(
                {'error': 'Email not provided by Google'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # task-29 C4: safe resolution avoids the email-only get_or_create
        # that would auto-merge an attacker-controlled Google identity
        # with a pre-existing local-password account.
        full_name = f"{first_name} {last_name}".strip()
        from .services.oauth_account import resolve_or_create_oauth_user

        resolution = resolve_or_create_oauth_user(
            provider="google",
            provider_user_id=google_id,
            email=email,
            email_verified=bool(email_verified),
            full_name=full_name,
            avatar_url=picture,
        )
        if resolution.conflict:
            emit_suspicious_activity(
                category="oauth_account_takeover",
                reason="email_collides_with_password_account",
                request=request,
                provider="google",
            )
            return Response(
                {
                    "error": "account_link_required",
                    "message": (
                        "An account with this email already exists. "
                        "Please log in with your password, then link "
                        "Google from Settings → Linked Accounts."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        if resolution.unverified_block:
            return Response(
                {
                    "error": "email_not_verified",
                    "message": "Google did not verify this email. Cannot create account.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = resolution.user
        created = resolution.created

        if created:
            logger.info(f"New user created via Google OAuth: {email}")
        else:
            # Existing user (already linked via SocialAccount, or
            # OAuth-only at this email). Refresh secondary fields.
            updated = False
            if not user.full_name and full_name:
                user.full_name = full_name
                updated = True
            if not user.is_verified and email_verified:
                user.is_verified = True
                updated = True
            # Only update avatar if user doesn't have a custom-uploaded avatar (R2)
            # Custom avatars are stored with r2:// prefix and should be preserved
            has_custom_avatar = user.avatar_url and user.avatar_url.startswith('r2://')
            if picture and not has_custom_avatar and user.avatar_url != picture:
                user.avatar_url = picture
                updated = True

            if updated:
                user.save()

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        # Create or update SocialAccount (always stores provider avatar for reference)
        social_account, sa_created = SocialAccount.objects.update_or_create(
            user=user,
            provider='google',
            defaults={
                'provider_user_id': google_id,
                'email': email,
                'avatar_url': picture,
                'last_login': timezone.now(),
                'extra_data': {
                    'email_verified': email_verified,
                    'picture': picture,
                }
            }
        )

        # Generate JWT tokens
        tokens = JWTManager.create_token_pair(user)

        # Store request metadata in refresh token (DB stores the
        # SHA-256 hash of the raw token, so look up by hash)
        refresh_token = RefreshToken.objects.filter(
            token=RefreshToken.hash_token(tokens["refresh_token"])
        ).first()
        if refresh_token:
            refresh_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
            refresh_token.ip_address = get_client_ip(request)
            refresh_token.metadata = {
                'provider': 'google',
                'google_id': google_id,
                'picture': picture,
            }
            refresh_token.save()

        return Response({
            'access': tokens['access_token'],
            'refresh': tokens['refresh_token'],
            'user': UserSerializer(user).data,
            'created': created,
            'message': 'Successfully authenticated with Google'
        })

    except ValueError as e:
        # Invalid token
        logger.error(f"Google OAuth token validation failed: {str(e)}")
        return Response(
            {'error': 'Invalid Google credential'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        # Other errors
        logger.error(f"Google OAuth error: {str(e)}")
        return Response(
            {'error': 'Authentication failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@apply_ratelimit(key="ip", rate="30/m", group="oauth-callback", method="POST")
def google_auth(request):
    """Authenticate user with a Google OAuth ID token."""
    return _google_token_auth(request)


@api_view(['POST'])
@permission_classes([AllowAny])
@apply_ratelimit(key="ip", rate="30/m", group="oauth-callback", method="POST")
def google_one_tap_auth(request):
    """
    Handle Google One Tap authentication.
    This is similar to google_auth but specifically for One Tap flow.

    Calls the shared implementation directly (NOT the decorated
    ``google_auth`` view — passing a DRF ``Request`` back through
    ``@api_view`` raises an AssertionError) and shares the same
    ``oauth-callback`` rate-limit bucket as the other two callbacks.
    """
    return _google_token_auth(request)


@api_view(['POST'])
@permission_classes([AllowAny])
@apply_ratelimit(key="ip", rate="30/m", group="oauth-callback", method="POST")
def github_auth(request):
    """
    Authenticate user with GitHub OAuth code.

    Expected request body:
    {
        "code": "Authorization code from GitHub"
    }
    """
    import requests as http_requests
    import time
    from datetime import datetime

    request_start_time = time.time()
    timestamp = datetime.utcnow().isoformat()
    logger.info("=== GitHub OAuth Request Received ===")
    logger.info(f"Timestamp: {timestamp}")

    code = request.data.get('code')

    if not code:
        logger.warning("No code provided in request")
        return Response(
            {'error': 'GitHub authorization code is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    logger.info(f"Code received (length: {len(code)})")

    # State nonce validation (task 19, §9.3). The frontend mints the
    # state via /api/auth/oauth/state/, sessionStorage-checks it on
    # callback, and threads it through to us here.
    state = request.data.get("state", "") or ""
    if not state:
        emit_suspicious_activity(
            category="oauth_replay",
            reason="github_state_missing",
            request=request,
        )
        return Response(
            {"error": "Missing OAuth state parameter."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    state_key = f"oauth_state:{state}"
    if not cache.get(state_key):
        emit_suspicious_activity(
            category="oauth_replay",
            reason="github_state_invalid",
            request=request,
        )
        return Response(
            {"error": "OAuth state expired or invalid. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    cache.delete(state_key)  # single-use

    # Code reuse guard (task 19, §9.3). cache.add returns False if the
    # SHA-256(code) key already exists → reject as replay.
    code_key = "oauth_replay:github:" + hashlib.sha256(
        code.encode("utf-8")
    ).hexdigest()
    if not cache.add(code_key, True, timeout=600):
        emit_suspicious_activity(
            category="oauth_replay",
            reason="github_code_reused",
            request=request,
        )
        return Response(
            {"error": "Authorization code already used."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Exchange code for access token
        logger.info("Attempting to exchange code with GitHub...")
        token_url = 'https://github.com/login/oauth/access_token'
        token_data = {
            'client_id': settings.GITHUB_OAUTH_CLIENT_ID,
            'client_secret': settings.GITHUB_OAUTH_CLIENT_SECRET,
            'code': code,
        }
        token_headers = {'Accept': 'application/json'}

        github_call_start = time.time()
        token_response = http_requests.post(
            token_url,
            data=token_data,
            headers=token_headers,
            timeout=10
        )
        github_call_duration = time.time() - github_call_start
        logger.info(f"GitHub token exchange response received in {github_call_duration:.3f}s")
        logger.info(f"GitHub response status: {token_response.status_code}")

        token_response.raise_for_status()
        token_json = token_response.json()
        logger.info(f"GitHub response JSON keys: {list(token_json.keys())}")

        access_token = token_json.get('access_token')
        if not access_token:
            error_description = token_json.get('error_description', 'Failed to get access token')
            error_message = token_json.get('error', 'unknown_error')
            elapsed = time.time() - request_start_time
            logger.error(f"GitHub OAuth token exchange failed after {elapsed:.3f}s: {error_message} - {error_description}")
            logger.error(f"Full GitHub error response: {token_json}")
            return Response(
                {'error': 'Failed to authenticate with GitHub'},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info("Successfully obtained GitHub access token")

        # Get user info from GitHub
        logger.info("Fetching GitHub user info...")
        user_url = 'https://api.github.com/user'
        user_headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        }

        user_response = http_requests.get(
            user_url,
            headers=user_headers,
            timeout=10
        )
        user_response.raise_for_status()
        github_user = user_response.json()
        logger.info(f"GitHub user info fetched: {github_user.get('login')}")

        # Get user emails
        logger.info("Fetching GitHub user emails...")
        emails_url = 'https://api.github.com/user/emails'
        emails_response = http_requests.get(
            emails_url,
            headers=user_headers,
            timeout=10
        )
        emails_response.raise_for_status()
        github_emails = emails_response.json()

        # Find primary verified email
        email = None
        email_verified = False
        for email_obj in github_emails:
            if email_obj.get('primary') and email_obj.get('verified'):
                email = email_obj.get('email')
                email_verified = True
                break

        # Fallback to first verified email
        if not email:
            for email_obj in github_emails:
                if email_obj.get('verified'):
                    email = email_obj.get('email')
                    email_verified = True
                    break

        # Fallback to public email from profile
        if not email:
            email = github_user.get('email')
            email_verified = False

        if not email:
            return Response(
                {'error': 'No email associated with this GitHub account'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract user info
        github_id = str(github_user.get('id'))
        full_name = github_user.get('name', '')
        username = github_user.get('login', '')
        avatar_url = github_user.get('avatar_url', '')

        # task-29 C4: safe resolution. See google_auth for rationale.
        if not full_name:
            full_name = username  # Use GitHub username as fallback

        from .services.oauth_account import resolve_or_create_oauth_user

        resolution = resolve_or_create_oauth_user(
            provider="github",
            provider_user_id=github_id,
            email=email,
            email_verified=bool(email_verified),
            full_name=full_name,
            avatar_url=avatar_url,
        )
        if resolution.conflict:
            emit_suspicious_activity(
                category="oauth_account_takeover",
                reason="email_collides_with_password_account",
                request=request,
                provider="github",
            )
            return Response(
                {
                    "error": "account_link_required",
                    "message": (
                        "An account with this email already exists. "
                        "Please log in with your password, then link "
                        "GitHub from Settings → Linked Accounts."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        if resolution.unverified_block:
            return Response(
                {
                    "error": "email_not_verified",
                    "message": "GitHub did not verify this email. Cannot create account.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = resolution.user
        created = resolution.created

        if created:
            logger.info(f"New user created via GitHub OAuth: {email}")
        else:
            # Existing user, update their info if needed
            updated = False
            if not user.full_name and full_name:
                user.full_name = full_name
                updated = True
            if not user.is_verified and email_verified:
                user.is_verified = True
                updated = True
            # Only update avatar if user doesn't have a custom-uploaded avatar (R2)
            # Custom avatars are stored with r2:// prefix and should be preserved
            has_custom_avatar = user.avatar_url and user.avatar_url.startswith('r2://')
            if avatar_url and not has_custom_avatar and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
                updated = True

            if updated:
                user.save()

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        # Create or update SocialAccount (always stores provider avatar for reference)
        social_account, sa_created = SocialAccount.objects.update_or_create(
            user=user,
            provider='github',
            defaults={
                'provider_user_id': github_id,
                'email': email,
                'username': username,
                'avatar_url': avatar_url,
                'last_login': timezone.now(),
                'extra_data': {
                    'email_verified': email_verified,
                }
            }
        )

        # Generate JWT tokens
        logger.info(f"Generating JWT tokens for user: {user.email}")
        tokens = JWTManager.create_token_pair(user)

        # Store request metadata in refresh token (DB stores the
        # SHA-256 hash of the raw token, so look up by hash)
        refresh_token = RefreshToken.objects.filter(
            token=RefreshToken.hash_token(tokens["refresh_token"])
        ).first()
        if refresh_token:
            refresh_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
            refresh_token.ip_address = get_client_ip(request)
            refresh_token.metadata = {
                'provider': 'github',
                'github_id': github_id,
                'username': username,
                'avatar_url': avatar_url,
            }
            refresh_token.save()

        total_duration = time.time() - request_start_time
        logger.info(f"=== GitHub OAuth completed successfully in {total_duration:.3f}s ===")
        logger.info(f"User: {user.email} (created: {created})")

        return Response({
            'access': tokens['access_token'],
            'refresh': tokens['refresh_token'],
            'user': UserSerializer(user).data,
            'created': created,
            'message': 'Successfully authenticated with GitHub'
        })

    except http_requests.exceptions.RequestException as e:
        logger.error(f"GitHub API request failed: {str(e)}")
        return Response(
            {'error': 'Failed to communicate with GitHub'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e:
        logger.error(f"GitHub OAuth error: {str(e)}")
        return Response(
            {'error': 'Authentication failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


