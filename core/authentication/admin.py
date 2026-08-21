from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, EmailVerificationToken, PasswordResetToken, RefreshToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model."""

    list_display = (
        "email",
        "full_name",
        "is_active",
        "is_verified",
        "is_staff",
        "date_joined",
    )
    list_filter = (
        "is_active",
        "is_verified",
        "is_staff",
        "is_superuser",
        "date_joined",
    )
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("full_name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Admin interface for EmailVerificationToken model."""

    list_display = ("user", "token", "is_used", "created_at", "expires_at")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    readonly_fields = ("token", "created_at")
    ordering = ("-created_at",)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin interface for PasswordResetToken model."""

    list_display = ("user", "token", "is_used", "created_at", "expires_at")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    readonly_fields = ("token", "created_at")
    ordering = ("-created_at",)


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    """Admin interface for RefreshToken model."""

    list_display = (
        "user",
        "is_revoked",
        "created_at",
        "expires_at",
        "last_used",
        "ip_address",
    )
    list_filter = ("is_revoked", "created_at", "expires_at", "last_used")
    search_fields = ("user__email", "ip_address")
    readonly_fields = ("token", "created_at")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {"fields": ("user", "token", "is_revoked")}),
        (_("Timestamps"), {"fields": ("created_at", "expires_at", "last_used")}),
        (_("Metadata"), {"fields": ("user_agent", "ip_address")}),
    )
