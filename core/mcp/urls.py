"""URL configuration for MCP app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MCPDynamicOAuthCallbackView,
    MCPServerViewSet,
    MCPToolApprovalViewSet,
    MCPToolExecutionViewSet,
    MCPToolViewSet,
)

app_name = "mcp"

router = DefaultRouter()
router.register(r"servers", MCPServerViewSet, basename="server")
router.register(r"tools", MCPToolViewSet, basename="tool")
router.register(r"approvals", MCPToolApprovalViewSet, basename="approval")
router.register(r"executions", MCPToolExecutionViewSet, basename="execution")

urlpatterns = [
    # Dynamic OAuth callback for arbitrary MCP servers
    path("oauth/callback/", MCPDynamicOAuthCallbackView.as_view(), name="oauth-callback"),
    # Router URLs
    path("", include(router.urls)),
]
