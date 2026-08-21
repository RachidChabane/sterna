"""
URL configuration for settings endpoints.
"""

from django.urls import path
from .settings_views import (
    CodingAgentModelPreferencesView,
    ImageSettingsView,
    OpenRouterSettingsView,
    ProviderKeyDetailView,
    ProviderKeysView,
    VideoSettingsView,
)

app_name = "settings"

urlpatterns = [
    path("openrouter/", OpenRouterSettingsView.as_view(), name="openrouter"),
    path("provider-keys/", ProviderKeysView.as_view(), name="provider-keys"),
    path(
        "provider-keys/<str:provider>/",
        ProviderKeyDetailView.as_view(),
        name="provider-key-detail",
    ),
    path("images/", ImageSettingsView.as_view(), name="images"),
    path("videos/", VideoSettingsView.as_view(), name="videos"),
    path("coding-agent-models/", CodingAgentModelPreferencesView.as_view(), name="coding-agent-models"),
]