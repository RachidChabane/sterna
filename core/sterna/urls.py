"""
URL configuration for sterna project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

from workspaces.api import views as workspace_views
from api.views import LivenessProbeView, ReadinessProbeView

# Custom error handlers
handler404 = "sterna.views.custom_404"

urlpatterns = [
    # Public share pages (no auth required) - must be BEFORE api/ routes
    path("share/<str:token>/", workspace_views.public_share_view, name="public-share"),
    path("share/<str:token>/raw/", workspace_views.public_share_raw, name="public-share-raw"),

    # Admin — restrict access to staff via IP allowlist or Cloudflare Access in production
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/llm/", include("llm.urls")),
    path("api/settings/", include("llm.settings_urls")),
    path("api/mcp/", include("mcp.urls")),
    path("api/consigliere/", include("consigliere.urls")),
    path("api/voice-rooms/", include("voice_rooms.urls")),
    path("api/code-sessions/", include("code_sessions.urls")),  # Coding agent features
    path("api/audit/", include("audit_logging.urls")),
    path("api/", include("usage_quota.urls")),
    path("api/admin/", include("usage_quota.admin_urls")),
    path("api/workspaces/", include("workspaces.urls")),  # Workspace persistence
    path("api/", include("conversations.urls")),  # Conversation storage
    path("api/", include("sparks.urls")),  # Interactive React components
    path("api/knowledge/", include("knowledge_base.urls")),  # Knowledge Base with RAG
    path("api/support/", include("support.urls")),
    # API Documentation
    path("api/docs/", include("documentation.urls")),
    # Health check endpoints
    path("health/", lambda request: JsonResponse({"status": "healthy"})),
    path(
        "api/health/", lambda request: JsonResponse({"status": "healthy", "api": "v1"})
    ),
    # k8s-convention probe aliases (audit middleware exempts these paths,
    # see core/audit_logging/middleware.py SKIP_PATHS).
    path("livez", LivenessProbeView.as_view(), name="livez"),
    path("readyz", ReadinessProbeView.as_view(), name="readyz"),
]
