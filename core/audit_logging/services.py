"""
Service layer for audit logging operations.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
from django.db.models import Q, Count, Avg, Max, Min
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from .models import AuditLog, AuditLogRetentionPolicy, AuditLogArchive


class AuditService:
    """
    Service for audit logging operations.

    Provides high-level methods for:
    - Creating audit logs
    - Querying audit logs
    - Managing retention policies
    - Archiving old logs
    - Generating audit reports
    """

    @staticmethod
    def log_action(
        action: str,
        user=None,
        resource=None,
        success=True,
        error_message=None,
        **extra_data,
    ) -> AuditLog:
        """
        Log a single action to the audit log.

        Args:
            action: Action identifier (e.g., 'AUTH_LOGIN', 'DATASET_CREATE')
            user: User performing the action
            resource: Resource being acted upon
            success: Whether the action succeeded
            error_message: Error message if action failed
            **extra_data: Additional context data

        Returns:
            Created AuditLog instance
        """
        audit_log = AuditLog.objects.create(
            action=action,
            user=user,
            resource_object=resource,
            success=success,
            error_message=error_message,
            extra_data=extra_data,
        )
        return audit_log

    @staticmethod
    def get_logs_for_resource(resource, limit=100) -> List[AuditLog]:
        """
        Get audit logs for a specific resource.

        Args:
            resource: Resource instance
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog instances
        """
        content_type = ContentType.objects.get_for_model(resource)
        return list(
            AuditLog.objects.filter(
                resource_type=content_type, resource_id=str(resource.pk)
            ).order_by("-timestamp")[:limit]
        )

    @staticmethod
    def get_user_activity(
        user, start_date=None, end_date=None, limit=100
    ) -> List[AuditLog]:
        """
        Get activity logs for a specific user.

        Args:
            user: User instance
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog instances
        """
        queryset = AuditLog.objects.filter(user=user)

        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        return list(queryset.order_by("-timestamp")[:limit])

    @staticmethod
    def get_failed_actions(
        start_date=None, end_date=None, action_category=None, limit=100
    ) -> List[AuditLog]:
        """
        Get failed action logs.

        Args:
            start_date: Start of date range
            end_date: End of date range
            action_category: Category to filter by
            limit: Maximum number of logs to return

        Returns:
            List of failed AuditLog instances
        """
        queryset = AuditLog.objects.filter(success=False)

        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        if action_category:
            queryset = queryset.filter(action_category=action_category)

        return list(queryset.order_by("-timestamp")[:limit])

    @staticmethod
    def get_action_statistics(
        start_date=None, end_date=None
    ) -> Dict[str, Any]:
        """
        Get statistics about actions.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dictionary with action statistics
        """
        queryset = AuditLog.objects.all()

        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        # Get action counts
        action_counts = (
            queryset.values("action").annotate(count=Count("id")).order_by("-count")
        )

        # Get category counts
        category_counts = (
            queryset.values("action_category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Get success/failure rates
        total_count = queryset.count()
        success_count = queryset.filter(success=True).count()
        failure_count = queryset.filter(success=False).count()

        # Get performance metrics
        performance = queryset.filter(duration_ms__isnull=False).aggregate(
            avg_duration=Avg("duration_ms"),
            max_duration=Max("duration_ms"),
            min_duration=Min("duration_ms"),
        )

        return {
            "total_actions": total_count,
            "successful_actions": success_count,
            "failed_actions": failure_count,
            "success_rate": (success_count / total_count * 100)
            if total_count > 0
            else 0,
            "action_counts": list(action_counts[:10]),
            "category_counts": list(category_counts),
            "performance": performance,
        }

    @staticmethod
    def search_logs(
        query: str, start_date=None, end_date=None, limit=100
    ) -> List[AuditLog]:
        """
        Search audit logs.

        Args:
            query: Search query
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of logs to return

        Returns:
            List of matching AuditLog instances
        """
        # Build search query
        search_q = (
            Q(action__icontains=query)
            | Q(user_email__icontains=query)
            | Q(resource_str__icontains=query)
            | Q(error_message__icontains=query)
        )

        queryset = AuditLog.objects.filter(search_q)

        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        return list(queryset.order_by("-timestamp")[:limit])

    @staticmethod
    def apply_retention_policies():
        """
        Apply retention policies to audit logs.

        Archives or deletes old logs based on active retention policies.
        """
        policies = AuditLogRetentionPolicy.objects.filter(is_active=True)

        for policy in policies:
            # Calculate cutoff date
            cutoff_date = timezone.now() - timedelta(days=policy.get_retention_days())

            # Find logs to process
            queryset = AuditLog.objects.filter(timestamp__lt=cutoff_date)

            if policy.action_category:
                queryset = queryset.filter(action_category=policy.action_category)

            # Process logs
            for audit_log in queryset.iterator(chunk_size=100):
                if policy.archive_before_deletion:
                    # Archive the log
                    AuditService.archive_log(audit_log, policy)

                # Delete the log
                audit_log.delete()

    @staticmethod
    def archive_log(audit_log: AuditLog, policy: AuditLogRetentionPolicy):
        """
        Archive an audit log.

        Args:
            audit_log: Log to archive
            policy: Retention policy being applied
        """
        # Prepare archived data
        archived_data = {
            "id": str(audit_log.id),
            "timestamp": audit_log.timestamp.isoformat(),
            "user_id": str(audit_log.user_id) if audit_log.user_id else None,
            "user_email": audit_log.user_email,
            "user_ip": audit_log.user_ip,
            "user_agent": audit_log.user_agent,
            "action": audit_log.action,
            "action_category": audit_log.action_category,
            "resource_type": audit_log.resource_type.model
            if audit_log.resource_type
            else None,
            "resource_id": audit_log.resource_id,
            "resource_str": audit_log.resource_str,
            "extra_data": audit_log.extra_data,
            "request_id": audit_log.request_id,
            "session_id": audit_log.session_id,
            "success": audit_log.success,
            "error_message": audit_log.error_message,
            "duration_ms": audit_log.duration_ms,
        }

        # Create archive entry
        AuditLogArchive.objects.create(
            original_id=audit_log.id,
            archived_data=archived_data,
            archived_by_policy=policy,
        )

    @staticmethod
    def generate_audit_report(
        start_date: datetime, end_date: datetime, format="json"
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive audit report.

        Args:
            start_date: Start of report period
            end_date: End of report period
            format: Report format ('json', 'csv', 'pdf')

        Returns:
            Report data in requested format
        """
        # Get all logs for period
        queryset = AuditLog.objects.filter(
            timestamp__gte=start_date, timestamp__lte=end_date
        )

        # Get statistics
        stats = AuditService.get_action_statistics(start_date, end_date)

        # Get top users
        top_users = (
            queryset.values("user__email")
            .annotate(action_count=Count("id"))
            .order_by("-action_count")[:10]
        )

        # Get failed actions
        failed_actions = (
            queryset.filter(success=False)
            .values("action", "error_message")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        )

        # Build report
        report = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "statistics": stats,
            "top_users": list(top_users),
            "failed_actions": list(failed_actions),
            "generated_at": timezone.now().isoformat(),
        }

        # Format conversion would happen here for CSV/PDF
        # For now, just return JSON format
        return report

    @staticmethod
    def get_session_logs(session_id: str) -> List[AuditLog]:
        """
        Get all logs for a specific session.

        Args:
            session_id: Session ID to filter by

        Returns:
            List of AuditLog instances for the session
        """
        return list(
            AuditLog.objects.filter(session_id=session_id).order_by("timestamp")
        )
