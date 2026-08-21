"""
URL configuration for audit logging.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogViewSet,
    AuditLogRetentionPolicyViewSet,
    AuditLogArchiveViewSet,
)

router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="auditlog")
router.register(
    r"retention-policies", AuditLogRetentionPolicyViewSet, basename="auditlog-retention"
)
router.register(r"archives", AuditLogArchiveViewSet, basename="auditlog-archive")

app_name = "audit_logging"

urlpatterns = [
    path("", include(router.urls)),
]
