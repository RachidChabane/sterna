"""
Documentation-only serializers for the auth OpenAPI schema.

Every class here exists purely to give drf-spectacular a precise shape
to describe a request or response body. None of them are instantiated
by the views to build a response or validate input — the views keep
constructing plain dicts exactly as before; wire format is unchanged.
See authentication/openapi_schema.py for where these get attached to
the view methods.
"""
from rest_framework import serializers

from .serializers import ConsentCategoriesSerializer, UserSerializer


class MessageResponseSerializer(serializers.Serializer):
    """A bare `{"message": "..."}` acknowledgement body."""
    message = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """Shape of `JWTManager.create_token_pair` / `refresh_access_token`."""
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()


class RegisterResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserSerializer()


class LoginResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    user = UserSerializer()


class LogoutRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=False, allow_blank=True)


class OAuthStateResponseSerializer(serializers.Serializer):
    state = serializers.CharField()


class EmailVerificationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = UserSerializer()


class ChangePasswordRequestSerializer(serializers.Serializer):
    """Documents the full request body — the view also reads
    `logout_other_sessions` / `current_refresh_token` directly off
    `request.data`, alongside the fields `ChangePasswordSerializer`
    validates.
    """
    old_password = serializers.CharField()
    new_password = serializers.CharField()
    new_password_confirm = serializers.CharField()
    logout_other_sessions = serializers.BooleanField(required=False)
    current_refresh_token = serializers.CharField(required=False, allow_blank=True)


class SessionSerializer(serializers.Serializer):
    """One entry of `SessionListView`'s `sessions` list."""
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    last_used = serializers.DateTimeField(allow_null=True)
    user_agent = serializers.CharField(allow_blank=True)
    ip_address = serializers.CharField(allow_null=True)


class SessionListResponseSerializer(serializers.Serializer):
    sessions = SessionSerializer(many=True)
    count = serializers.IntegerField()


class AvatarUploadRequestSerializer(serializers.Serializer):
    file = serializers.FileField()


class AvatarUploadResponseSerializer(serializers.Serializer):
    avatar_url = serializers.CharField()
    message = serializers.CharField()


class ConsentRecordSerializer(serializers.Serializer):
    """Shape of the `consent` object nested in consent GET/POST responses."""
    session_id = serializers.CharField()
    categories = ConsentCategoriesSerializer()
    version = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ConsentResponseSerializer(serializers.Serializer):
    consent = ConsentRecordSerializer(allow_null=True)
    region_default = serializers.ChoiceField(choices=["EU", "non-EU"])


class ConsentAttachResponseSerializer(serializers.Serializer):
    attached = serializers.IntegerField()


class GoogleAuthRequestSerializer(serializers.Serializer):
    credential = serializers.CharField()


class GithubAuthRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()


class OAuthLoginResponseSerializer(serializers.Serializer):
    """Shape returned by the Google / GitHub OAuth callback views.

    A distinct shape from `LoginResponseSerializer` — OAuth callbacks
    key the tokens as `access`/`refresh` and add `created`, while
    password login uses `access_token`/`refresh_token`.
    """
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
    created = serializers.BooleanField()
    message = serializers.CharField()


class DataExportCreateResponseSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    status = serializers.CharField()


class DataExportStatusResponseSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    status = serializers.CharField()
    requested_at = serializers.DateTimeField()
    download_url = serializers.CharField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    ready_at = serializers.DateTimeField(required=False, allow_null=True)
    error = serializers.CharField(required=False)


class AccountDeletionRequestSerializer(serializers.Serializer):
    password = serializers.CharField(required=False, allow_blank=True)
    confirm_email = serializers.CharField()


class AccountDeletionCreateResponseSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    scheduled_for = serializers.DateTimeField()
    status = serializers.CharField(required=False)


class CancelDeletionRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class AccountDeletionCancelResponseSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    status = serializers.CharField()
    canceled_at = serializers.DateTimeField()
