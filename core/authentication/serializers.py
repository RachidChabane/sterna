from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import secrets
import logging

from .consent_constants import VALID_CATEGORIES
from .models import User, EmailVerificationToken, PasswordResetToken, SocialAccount
from .validators import DisposableEmailValidator

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    # Read: extract from full_name. Write: combine into full_name.
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "avatar_url",
            "is_verified",
            "is_active",
            "date_joined",
            "last_login",
        )
        # task-29 C2 fix: email, is_active, and avatar_url are read-only
        # via this serializer. Email changes flow through a dedicated
        # re-verification endpoint (M8 tracked issue). Avatar uploads
        # flow through AvatarUploadView (magic-byte validated). OAuth
        # flows assign avatar_url via direct attribute write.
        read_only_fields = (
            "id",
            "email",
            "is_active",
            "avatar_url",
            "is_verified",
            "date_joined",
            "last_login",
        )

    def to_representation(self, instance):
        """Extract first_name and last_name from full_name for reading."""
        data = super().to_representation(instance)
        if instance.full_name:
            parts = instance.full_name.split(' ', 1)
            data['first_name'] = parts[0] if parts else ''
            data['last_name'] = parts[1] if len(parts) > 1 else ''
        else:
            data['first_name'] = ''
            data['last_name'] = ''

        # Resolve r2:// avatar URLs to backend-served URLs
        if data.get('avatar_url') and data['avatar_url'].startswith('r2://'):
            data['avatar_url'] = self._resolve_avatar_url(data['avatar_url'], instance)

        return data

    def _resolve_avatar_url(self, r2_url: str, user_instance) -> str:
        """
        Resolve r2://{bucket}/{key} URL to a backend-served URL.

        Instead of returning a presigned R2 URL (which has CORS issues),
        we return a URL to our backend avatar endpoint that proxies the image.

        Args:
            r2_url: URL in format r2://{bucket}/{key}
            user_instance: The User model instance

        Returns:
            Backend URL: /api/auth/avatar/{user_id}/
        """
        try:
            # Parse r2://bucket/key format to validate it
            if not r2_url.startswith('r2://'):
                return r2_url

            path = r2_url[5:]  # Remove 'r2://'
            parts = path.split('/', 1)
            if len(parts) != 2:
                return r2_url

            # Return URL to backend avatar endpoint
            # The endpoint will fetch from R2 and return the image
            # This avoids CORS issues with presigned R2 URLs
            if user_instance and hasattr(user_instance, 'id'):
                return f"/api/auth/avatar/{user_instance.id}/"

            return ""

        except Exception as e:
            logger.warning(f"Failed to resolve avatar URL {r2_url}: {e}")
            return ""

    def update(self, instance, validated_data):
        """Combine first_name and last_name into full_name when updating."""
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)

        # If either name field was provided, update full_name
        if first_name is not None or last_name is not None:
            # Get current values if not provided
            if first_name is None:
                if instance.full_name:
                    parts = instance.full_name.split(' ', 1)
                    first_name = parts[0] if parts else ''
                else:
                    first_name = ''
            if last_name is None:
                if instance.full_name:
                    parts = instance.full_name.split(' ', 1)
                    last_name = parts[1] if len(parts) > 1 else ''
                else:
                    last_name = ''

            # Combine into full_name
            validated_data['full_name'] = f"{first_name} {last_name}".strip()

        return super().update(instance, validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(
        write_only=True, required=True, min_length=8, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    turnstile_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = (
            "email",
            "full_name",
            "password",
            "password_confirm",
            "turnstile_token",
        )
        extra_kwargs = {
            "email": {"validators": [DisposableEmailValidator()]},
        }

    def validate_email(self, value):
        """Validate email is unique."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email address already registered.")
        return value.lower()

    def validate_password(self, value):
        """Validate password strength."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        """Validate passwords match."""
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        """Create new user and send verification email."""
        validated_data.pop("password_confirm")
        validated_data.pop("turnstile_token", None)
        password = validated_data.pop("password")

        user = User.objects.create_user(password=password, **validated_data)

        # Create email verification token
        token = secrets.token_urlsafe(32)
        EmailVerificationToken.objects.create(
            user=user, token=token, expires_at=timezone.now() + timedelta(hours=24)
        )

        # TODO: Send verification email asynchronously
        # send_verification_email.delay(user.id, token)

        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True, write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        """Validate credentials and authenticate user."""
        email = attrs.get("email", "").lower()
        password = attrs.get("password", "")

        if email and password:
            user = authenticate(
                request=self.context.get("request"), username=email, password=password
            )

            if not user:
                raise serializers.ValidationError("Invalid email or password.")

            if not user.is_active:
                raise serializers.ValidationError("Account is disabled.")

            attrs["user"] = user
            return attrs

        raise serializers.ValidationError('Must include "email" and "password".')


class RefreshTokenSerializer(serializers.Serializer):
    """Serializer for refreshing access token."""

    refresh_token = serializers.CharField(required=True)


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification."""

    token = serializers.CharField(required=True)

    def validate_token(self, value):
        """Validate the verification token."""
        try:
            token_obj = EmailVerificationToken.objects.get(token=value, is_used=False)

            if not token_obj.is_valid():
                raise serializers.ValidationError("Verification token has expired.")

            self.token_obj = token_obj
            return value

        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Invalid verification token.")


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for resending verification email."""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Validate email exists and is not verified."""
        try:
            user = User.objects.get(email__iexact=value)

            if user.is_verified:
                raise serializers.ValidationError("Email already verified.")

            self.user = user
            return value.lower()

        except User.DoesNotExist:
            raise serializers.ValidationError("Email not found.")


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting password reset."""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Validate email exists."""
        try:
            self.user = User.objects.get(email__iexact=value)
            return value.lower()
        except User.DoesNotExist:
            # Don't reveal if email exists or not
            return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset."""

    token = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True, required=True, min_length=8, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    def validate_token(self, value):
        """Validate the reset token."""
        try:
            token_obj = PasswordResetToken.objects.get(token=value, is_used=False)

            if not token_obj.is_valid():
                raise serializers.ValidationError("Reset token has expired.")

            self.token_obj = token_obj
            return value

        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token.")

    def validate_password(self, value):
        """Validate password strength."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        """Validate passwords match."""
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password."""

    old_password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        write_only=True, required=True, min_length=8, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    def validate_old_password(self, value):
        """Validate old password is correct."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        """Validate new password strength."""
        try:
            validate_password(value, user=self.context["request"].user)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        """Validate new passwords match."""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs


class SocialAccountSerializer(serializers.ModelSerializer):
    """Serializer for SocialAccount model."""

    provider_display = serializers.CharField(source="get_provider_display", read_only=True)
    can_disconnect = serializers.SerializerMethodField()

    class Meta:
        model = SocialAccount
        fields = [
            "id",
            "provider",
            "provider_display",
            "provider_user_id",
            "email",
            "username",
            "avatar_url",
            "created_at",
            "updated_at",
            "last_login",
            "can_disconnect",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_login"]

    def get_can_disconnect(self, obj):
        """Check if user can disconnect this account."""
        # User can disconnect if they have:
        # 1. A password (can login without OAuth), OR
        # 2. Multiple social accounts
        user = obj.user
        has_password = user.has_usable_password()
        social_accounts_count = user.social_accounts.count()

        # Can disconnect if has password OR has other social accounts
        return has_password or social_accounts_count > 1


class ConsentSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=255, required=True)
    categories = serializers.JSONField(required=True)
    version = serializers.CharField(max_length=32, required=True)

    def validate_categories(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("`categories` must be an object.")
        unknown = set(value.keys()) - set(VALID_CATEGORIES)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown categories: {sorted(unknown)}. "
                f"Allowed: {list(VALID_CATEGORIES)}."
            )
        missing = set(VALID_CATEGORIES) - set(value.keys())
        if missing:
            raise serializers.ValidationError(
                f"Missing categories: {sorted(missing)}."
            )
        for key, val in value.items():
            if not isinstance(val, bool):
                raise serializers.ValidationError(
                    f"Category `{key}` must be a boolean, got {type(val).__name__}."
                )
        if value.get("essential") is not True:
            raise serializers.ValidationError(
                "`essential` cookies cannot be disabled."
            )
        return value


class ConsentAttachSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=255, required=True)
