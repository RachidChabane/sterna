"""
URL configuration for API app.
"""

from django.urls import path

from .views import (
    HealthCheckView,
    LivenessProbeView,
    ReadinessProbeView,
    DetailedHealthView,
)
from . import sandbox_views
from . import document_views

app_name = "api"

urlpatterns = [
    # Health check endpoints
    path("health/", HealthCheckView.as_view(), name="health"),
    path("health/live/", LivenessProbeView.as_view(), name="liveness"),
    path("health/ready/", ReadinessProbeView.as_view(), name="readiness"),
    path("health/detailed/", DetailedHealthView.as_view(), name="health_detailed"),

    # Document processing
    path("documents/extract/", document_views.extract_document, name="extract_document"),

    # Sandbox - Artifacts API
    path("sandbox/artifacts/<str:user_id>/<str:project_id>/", sandbox_views.list_artifacts, name="sandbox_list_artifacts"),
    path("sandbox/artifacts/<str:user_id>/<str:project_id>/<str:artifact_name>/", sandbox_views.get_artifact_download_url, name="sandbox_get_artifact"),
]
