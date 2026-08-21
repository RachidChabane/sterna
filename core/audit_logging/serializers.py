"""
Serializers for audit logging API.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import AuditLog, AuditLogRetentionPolicy, AuditLogArchive

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Minimal user serializer for audit logs."""

    class Meta:
        model = User
        fields = ["id", "email", "full_name"]


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for AuditLog model.
    """

    user = UserSummarySerializer(read_only=True)
    action_display = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()
    resource_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "user",
            "user_email",
            "user_ip",
            "action",
            "action_display",
            "action_category",
            "category_display",
            "resource_type",
            "resource_id",
            "resource_str",
            "resource_display",
            "extra_data",
            "request_id",
            "session_id",
            "success",
            "error_message",
            "duration_ms",
        ]
        read_only_fields = fields

    def get_action_display(self, obj):
        """Get human-readable action display."""
        return AuditLog.ACTION_TYPES.get(obj.action, obj.action)

    def get_category_display(self, obj):
        """Get human-readable category display."""
        if obj.action_category:
            return AuditLog.ACTION_CATEGORIES.get(
                obj.action_category, obj.action_category
            )
        return None

    def get_resource_display(self, obj):
        """Get resource display string."""
        if obj.resource_str:
            return obj.resource_str
        elif obj.resource_type and obj.resource_id:
            return f"{obj.resource_type.model}:{obj.resource_id}"
        return None


class AuditLogListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for listing audit logs.
    """

    user_display = serializers.SerializerMethodField()
    action_display = serializers.SerializerMethodField()
    resource_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "user_display",
            "action",
            "action_display",
            "action_category",
            "resource_display",
            "success",
            "duration_ms",
        ]

    def get_user_display(self, obj):
        """Get user display string."""
        return obj.user_email or (obj.user.email if obj.user else "Anonymous")

    def get_action_display(self, obj):
        """Get human-readable action display."""
        return AuditLog.ACTION_TYPES.get(obj.action, obj.action)

    def get_resource_display(self, obj):
        """Get resource display string."""
        if obj.resource_str:
            return obj.resource_str
        elif obj.resource_type and obj.resource_id:
            return f"{obj.resource_type.model}:{obj.resource_id}"
        return None


class AuditLogRetentionPolicySerializer(serializers.ModelSerializer):
    """
    Serializer for AuditLogRetentionPolicy model.
    """

    retention_days = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLogRetentionPolicy
        fields = [
            "id",
            "name",
            "description",
            "retention_value",
            "retention_unit",
            "retention_days",
            "action_category",
            "category_display",
            "archive_before_deletion",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_retention_days(self, obj):
        """Get retention period in days."""
        return obj.get_retention_days()

    def get_category_display(self, obj):
        """Get human-readable category display."""
        if obj.action_category:
            return AuditLog.ACTION_CATEGORIES.get(
                obj.action_category, obj.action_category
            )
        return "All Categories"


class AuditLogArchiveSerializer(serializers.ModelSerializer):
    """
    Serializer for AuditLogArchive model.
    """

    policy_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLogArchive
        fields = [
            "id",
            "original_id",
            "archived_data",
            "archived_at",
            "archived_by_policy",
            "policy_name",
            "storage_location",
        ]
        read_only_fields = fields

    def get_policy_name(self, obj):
        """Get policy name."""
        return obj.archived_by_policy.name if obj.archived_by_policy else None


class AuditLogStatisticsSerializer(serializers.Serializer):
    """
    Serializer for audit log statistics.
    """

    total_actions = serializers.IntegerField()
    successful_actions = serializers.IntegerField()
    failed_actions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    action_counts = serializers.ListField(child=serializers.DictField())
    category_counts = serializers.ListField(child=serializers.DictField())
    performance = serializers.DictField()


class AuditReportSerializer(serializers.Serializer):
    """
    Serializer for audit reports.
    """

    period = serializers.DictField()
    statistics = AuditLogStatisticsSerializer()
    top_users = serializers.ListField(child=serializers.DictField())
    failed_actions = serializers.ListField(child=serializers.DictField())
    generated_at = serializers.DateTimeField()


class AuditLogQuerySerializer(serializers.Serializer):
    """
    Serializer for audit log query parameters.
    """

    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    action_category = serializers.ChoiceField(
        choices=[(k, v) for k, v in AuditLog.ACTION_CATEGORIES.items()],
        required=False,
        allow_null=True,
    )
    user_id = serializers.UUIDField(required=False, allow_null=True)
    success = serializers.BooleanField(required=False, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True)
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=50, min_value=1, max_value=200)
