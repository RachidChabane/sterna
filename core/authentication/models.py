from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import hashlib
import uuid

from mcp.fields import EncryptedTextField


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError(_("Email address is required"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True"))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True"))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email-based authentication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"), unique=True, db_index=True)
    full_name = models.CharField(_("full name"), max_length=255, blank=True)
    avatar_url = models.URLField(
        _("avatar URL"),
        max_length=500,
        blank=True,
        null=True,
        help_text=_("Profile picture URL from OAuth provider"),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this user should be treated as active."),
    )
    is_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Designates whether the user has verified their email address."),
    )

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    last_login = models.DateTimeField(_("last login"), blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # OpenRouter API key (encrypted at rest for security)
    openrouter_api_key = EncryptedTextField(
        blank=True,
        null=True,
        help_text=_("User's personal OpenRouter API key (encrypted at rest)"),
    )
    # Key hash for OpenRouter API management lookups (not the actual key)
    openrouter_key_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Hash identifier from OpenRouter for key management API"),
    )
    # Track when key was provisioned
    openrouter_key_provisioned_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_("When the OpenRouter key was provisioned"),
    )

    # Provider-scoped BYOK keys (encrypted at rest). JSON object mapping
    # provider slug (see llm.provider_registry.BYOK_PROVIDERS) -> API key.
    # Chat requests to a matching first-party model are routed directly
    # to the provider's OpenAI-compatible endpoint with this key.
    provider_api_keys = EncryptedTextField(
        blank=True,
        null=True,
        help_text=_(
            "JSON object mapping provider slug to the user's API key for "
            "that provider (encrypted at rest)"
        ),
    )

    # Stripe linkage (task 11). Filled async by ensure_stripe_customer
    # task after signup. Indexed because the webhook handler (task 13)
    # looks up users by this column to apply subscription updates.
    stripe_customer_id = models.CharField(
        _("Stripe customer ID"),
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Stripe Customer object ID (cus_…). Set asynchronously after signup."),
    )

    # Image generation settings
    # OpenRouter model IDs (Google AI Studio uses same IDs without 'google/' prefix)
    IMAGE_MODEL_CHOICES = [
        ("google/gemini-2.5-flash-image", "Nano Banana (Fast)"),
        ("google/gemini-3-pro-image-preview", "Nano Banana Pro (Quality)"),
    ]
    preferred_image_model = models.CharField(
        max_length=255,
        choices=IMAGE_MODEL_CHOICES,
        default="google/gemini-2.5-flash-image",
        help_text=_("Preferred model for image generation"),
    )

    # Video generation settings
    # Using canonical model IDs: provider/model-name
    # Valid models are fetched from VideoModelCatalog database table
    # Validation happens in VideoSettingsView.patch()
    preferred_video_model = models.CharField(
        max_length=255,
        blank=True,
        default="runway/veo3.1-fast",  # Fast and cost-effective text-to-video
        help_text=_("Preferred model for video generation (validated against VideoModelCatalog)"),
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        db_table = "auth_user"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return the full name of the user."""
        return self.full_name or self.email

    def get_short_name(self):
        """Return the short name of the user."""
        return self.full_name.split()[0] if self.full_name else self.email.split("@")[0]

    # --- Provider-scoped BYOK key helpers -------------------------------
    # provider_api_keys stores a JSON object {provider_slug: api_key}.
    # These helpers parse/serialize that JSON safely; they mutate the
    # in-memory field only — callers are responsible for .save().

    def _load_provider_keys(self) -> dict:
        """Parse provider_api_keys into a dict, tolerating bad/empty data."""
        import json

        raw = self.provider_api_keys
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_provider_key(self, provider: str):
        """Return the user's API key for ``provider``, or None."""
        key = self._load_provider_keys().get(provider)
        return key if isinstance(key, str) and key else None

    def set_provider_key(self, provider: str, key: str) -> None:
        """Set the API key for ``provider`` (in memory; call .save() after)."""
        import json

        keys = self._load_provider_keys()
        keys[provider] = key
        self.provider_api_keys = json.dumps(keys)

    def delete_provider_key(self, provider: str) -> None:
        """Remove the API key for ``provider`` (in memory; call .save() after)."""
        import json

        keys = self._load_provider_keys()
        keys.pop(provider, None)
        self.provider_api_keys = json.dumps(keys) if keys else None


class PasswordResetToken(models.Model):
    """Model for password reset tokens."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reset_tokens"
    )
    token = models.CharField(max_length=255, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "auth_password_reset_token"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def is_valid(self):
        """Check if the token is still valid."""
        return not self.is_used and self.expires_at > timezone.now()


class EmailVerificationToken(models.Model):
    """Model for email verification tokens."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(max_length=255, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "auth_email_verification_token"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def is_valid(self):
        """Check if the token is still valid."""
        return not self.is_used and self.expires_at > timezone.now()


class RefreshToken(models.Model):
    """Model for tracking refresh tokens.

    ``token`` stores the SHA-256 hex digest of the raw JWT, never the
    plaintext — a DB leak must not hand out usable refresh tokens.
    ``family`` groups a rotation chain: each refresh revokes the
    presented token and issues a successor in the same family, and
    reuse of an already-revoked member revokes the whole family
    (standard rotation reuse detection). See ``JWTManager``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    token = models.TextField(
        unique=True, help_text=_("SHA-256 hex digest of the raw refresh JWT")
    )
    family = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text=_("Rotation-chain id; reuse detection revokes the whole family"),
    )
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used = models.DateTimeField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional metadata (provider info, etc.)"),
    )

    class Meta:
        db_table = "auth_refresh_token"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "is_revoked"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["user", "is_revoked"]),
        ]

    def is_valid(self):
        """Check if the refresh token is still valid."""
        return not self.is_revoked and self.expires_at > timezone.now()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """SHA-256 hex digest used as the stored form of a raw refresh JWT."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SocialAccount(models.Model):
    """Model for tracking social OAuth accounts linked to a user."""

    PROVIDER_CHOICES = [
        ("google", "Google"),
        ("github", "GitHub"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="social_accounts"
    )
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(
        max_length=255, help_text=_("Unique ID from the OAuth provider (google_id, github_id)")
    )
    email = models.EmailField(help_text=_("Email used with this provider"))
    username = models.CharField(
        max_length=255, blank=True, help_text=_("Username from provider (GitHub, etc.)")
    )
    avatar_url = models.URLField(max_length=500, blank=True)
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional provider-specific data"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Last time this provider was used to login"),
    )

    class Meta:
        db_table = "auth_social_account"
        unique_together = [("provider", "provider_user_id")]
        indexes = [
            models.Index(fields=["user", "provider"]),
            models.Index(fields=["provider", "provider_user_id"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("social account")
        verbose_name_plural = _("social accounts")

    def __str__(self):
        return f"{self.user.email} - {self.provider}"


class ConsentRecord(models.Model):
    """Audit row for ePrivacy + GDPR consent decisions.

    Keyed on a browser-minted UUIDv4 ``session_id`` so visitors
    without an account can record a decision; bound to a ``User`` via
    a separate ``POST /api/auth/consent/attach/`` call after signup
    or login.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text=_("Client-minted UUIDv4 identifying the browser session"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="consent_records",
        null=True,
        blank=True,
        help_text=_("Set when the visitor signs up or logs in; NULL for anonymous visitors"),
    )
    categories = models.JSONField(
        default=dict,
        help_text=_(
            'Map of category → enabled. e.g. '
            '{"essential": true, "analytics": false, "marketing": false}'
        ),
    )
    version = models.CharField(
        max_length=32,
        help_text=_("Cookie policy version the consent was given against"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_anonymized = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("IPv4 with last octet zeroed, or IPv6 with last 80 bits zeroed"),
    )

    class Meta:
        db_table = "auth_consent_record"
        constraints = [
            models.UniqueConstraint(
                fields=["session_id"],
                name="auth_consent_record_session_id_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("consent record")
        verbose_name_plural = _("consent records")

    def __str__(self):
        return f"ConsentRecord(session={self.session_id[:8]}…, version={self.version})"
class DataExportRequest(models.Model):
    """GDPR Art. 15 — user-initiated data export request."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="data_export_requests"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_at = models.DateTimeField(default=timezone.now)
    ready_at = models.DateTimeField(null=True, blank=True)
    failed_reason = models.TextField(blank=True)
    download_url = models.TextField(blank=True)
    download_url_expires_at = models.DateTimeField(null=True, blank=True)
    r2_key = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "auth_data_export_request"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user", "-requested_at"]),
            models.Index(fields=["status", "ready_at"]),
        ]

    def __str__(self):
        return f"DataExport {self.id} ({self.status}) for {self.user_id}"


class AccountDeletionRequest(models.Model):
    """GDPR Art. 17 — user-initiated account deletion request.

    user is SET_NULL so the row survives the hard-delete for audit.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        CANCELED = "canceled", _("Canceled")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_deletion_requests",
    )
    user_email_snapshot = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_at = models.DateTimeField(default=timezone.now)
    scheduled_for = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancel_token_jti = models.CharField(max_length=64, unique=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        db_table = "auth_account_deletion_request"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["user", "-requested_at"]),
        ]

    def __str__(self):
        return (
            f"AccountDeletion {self.id} ({self.status}) — "
            f"{self.user_email_snapshot}"
        )


class BillingSummary(models.Model):
    """Anonymized billing aggregate retained for tax compliance (7y).

    Survives user hard-delete. anonymized_user_token = HMAC-SHA256 of
    user_id with the BILLING_ANONYMIZATION_PEPPER setting — so the same
    user yields the same token across rows but the original UUID cannot
    be recovered without the pepper.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anonymized_user_token = models.CharField(max_length=64, db_index=True)
    month = models.DateField(db_index=True)
    total_charged_usd = models.DecimalField(
        max_digits=12, decimal_places=4, default=0
    )
    tax_collected_usd = models.DecimalField(
        max_digits=12, decimal_places=4, default=0
    )
    country_code = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_summary"
        unique_together = [("anonymized_user_token", "month", "country_code")]
        indexes = [
            models.Index(fields=["month"]),
            models.Index(fields=["anonymized_user_token"]),
        ]
        ordering = ["-month"]

    def __str__(self):
        return (
            f"BillingSummary {self.month} {self.anonymized_user_token[:8]}…"
        )
