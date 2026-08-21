"""
API views for audit logging.
"""

from datetime import datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import AuditLog, AuditLogRetentionPolicy, AuditLogArchive
from .serializers import (
    AuditLogSerializer,
    AuditLogListSerializer,
    AuditLogRetentionPolicySerializer,
    AuditLogArchiveSerializer,
    AuditLogStatisticsSerializer,
    AuditReportSerializer,
)
from .services import AuditService


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing audit logs.

    Provides endpoints for:
    - Listing audit logs with filtering
    - Viewing individual audit log entries
    - Getting statistics
    - Searching logs
    - Generating reports
    """

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get filtered queryset based on permissions and parameters."""
        queryset = AuditLog.objects.all()

        # Non-superusers only see their own activity.
        if not self.request.user.is_superuser:
            queryset = queryset.filter(user=self.request.user)

        # Apply filters from query params
        params = self.request.query_params

        # Date range filter
        start_date = params.get("start_date")
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
                queryset = queryset.filter(timestamp__gte=start_date)
            except (ValueError, TypeError):
                pass

        end_date = params.get("end_date")
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
                queryset = queryset.filter(timestamp__lte=end_date)
            except (ValueError, TypeError):
                pass

        # Category filter
        action_category = params.get("action_category")
        if action_category:
            queryset = queryset.filter(action_category=action_category)

        # User filter
        user_id = params.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Success filter
        success = params.get("success")
        if success is not None:
            queryset = queryset.filter(success=success.lower() == "true")

        # Search filter
        search = params.get("search")
        if search:
            from django.db.models import Q

            search_q = (
                Q(action__icontains=search)
                | Q(user_email__icontains=search)
                | Q(resource_str__icontains=search)
                | Q(error_message__icontains=search)
            )
            queryset = queryset.filter(search_q)

        return queryset.order_by("-timestamp")

    def get_serializer_class(self):
        """Use different serializers for list vs detail views."""
        if self.action == "list":
            return AuditLogListSerializer
        return AuditLogSerializer

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """
        Get audit log statistics.

        Query parameters:
        - start_date: Start of date range (ISO format)
        - end_date: End of date range (ISO format)
        """
        # Parse parameters
        start_date = request.query_params.get("start_date")
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
            except (ValueError, TypeError):
                start_date = None

        end_date = request.query_params.get("end_date")
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
            except (ValueError, TypeError):
                end_date = None

        # Get statistics
        stats = AuditService.get_action_statistics(
            start_date=start_date, end_date=end_date
        )

        serializer = AuditLogStatisticsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_activity(self, request):
        """
        Get current user's activity logs.

        Query parameters:
        - start_date: Start of date range (ISO format)
        - end_date: End of date range (ISO format)
        - limit: Maximum number of logs to return (default 100)
        """
        # Parse parameters
        start_date = request.query_params.get("start_date")
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
            except (ValueError, TypeError):
                start_date = None

        end_date = request.query_params.get("end_date")
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
            except (ValueError, TypeError):
                end_date = None

        limit = int(request.query_params.get("limit", 100))

        # Get user activity
        logs = AuditService.get_user_activity(
            user=request.user, start_date=start_date, end_date=end_date, limit=limit
        )

        serializer = AuditLogListSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def failed_actions(self, request):
        """
        Get failed action logs.

        Query parameters:
        - start_date: Start of date range (ISO format)
        - end_date: End of date range (ISO format)
        - action_category: Category to filter by
        - limit: Maximum number of logs to return (default 100)
        """
        # Check permissions - only admins can view all failed actions
        if not request.user.is_superuser and not request.has_permission(
            "audit.view_failed"
        ):
            return Response(
                {"error": "You do not have permission to view failed actions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Parse parameters
        start_date = request.query_params.get("start_date")
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
            except (ValueError, TypeError):
                start_date = None

        end_date = request.query_params.get("end_date")
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
            except (ValueError, TypeError):
                end_date = None

        action_category = request.query_params.get("action_category")
        limit = int(request.query_params.get("limit", 100))

        # Get failed actions
        logs = AuditService.get_failed_actions(
            start_date=start_date,
            end_date=end_date,
            action_category=action_category,
            limit=limit,
        )

        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def generate_report(self, request):
        """
        Generate an audit report.

        Request body:
        {
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z",
            "format": "json"
        }
        """
        # Check permissions
        if not request.user.is_superuser and not request.has_permission(
            "audit.generate_report"
        ):
            return Response(
                {"error": "You do not have permission to generate reports"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Parse request data
        data = request.data

        try:
            start_date = datetime.fromisoformat(data["start_date"])
            end_date = datetime.fromisoformat(data["end_date"])
        except (KeyError, ValueError, TypeError):
            return Response(
                {"error": "Invalid date format. Use ISO format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report_format = data.get("format", "json")

        # Generate report
        report = AuditService.generate_audit_report(
            start_date=start_date,
            end_date=end_date,
            format=report_format,
        )

        serializer = AuditReportSerializer(report)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def resource_logs(self, request, pk=None):
        """
        Get all audit logs for a specific resource.

        The pk should be in the format: {content_type_id}:{resource_id}
        """
        try:
            content_type_id, resource_id = pk.split(":")

            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get(id=content_type_id)

            # Get the resource
            model_class = content_type.model_class()
            resource = get_object_or_404(model_class, pk=resource_id)

            # Check permissions to view this resource
            if not request.user.is_superuser:
                # Custom permission check based on resource type
                if hasattr(resource, "project"):
                    # Check if user has access to the project
                    if not resource.project.memberships.filter(
                        user=request.user, is_active=True
                    ).exists():
                        return Response(
                            {"error": "You do not have access to this resource"},
                            status=status.HTTP_403_FORBIDDEN,
                        )

            # Get audit logs for resource
            logs = AuditService.get_logs_for_resource(resource, limit=100)

            serializer = AuditLogSerializer(logs, many=True)
            return Response(serializer.data)

        except (ValueError, ContentType.DoesNotExist):
            return Response(
                {"error": "Invalid resource identifier"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AuditLogRetentionPolicyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing audit log retention policies.
    """

    queryset = AuditLogRetentionPolicy.objects.all()
    serializer_class = AuditLogRetentionPolicySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Only superusers can manage retention policies."""
        if not self.request.user.is_superuser:
            return AuditLogRetentionPolicy.objects.none()
        return super().get_queryset()

    @action(detail=True, methods=["post"])
    def apply_policy(self, request, pk=None):
        """
        Manually apply a retention policy.
        """
        if not request.user.is_superuser:
            return Response(
                {"error": "Only superusers can apply retention policies"},
                status=status.HTTP_403_FORBIDDEN,
            )

        policy = self.get_object()

        # Apply the policy
        AuditService.apply_retention_policies()

        return Response({"message": f"Policy {policy.name} applied successfully"})


class AuditLogArchiveViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing archived audit logs.
    """

    queryset = AuditLogArchive.objects.all()
    serializer_class = AuditLogArchiveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Only superusers can view archives."""
        if not self.request.user.is_superuser:
            return AuditLogArchive.objects.none()
        return super().get_queryset().order_by("-archived_at")
