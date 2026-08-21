"""
Root URL configuration for Consigliere microservice.

This is the main URL routing for when Consigliere runs as a standalone service.
"""

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include

urlpatterns = [
    # Admin interface (optional, for debugging)
    path("admin/", admin.site.urls),

    # Consigliere API endpoints at /api/consigliere/
    path("api/consigliere/", include("consigliere.urls")),

    # Conversations API endpoints at /api/conversations/
    path("api/", include("conversations.urls")),

    # Health check endpoint
    path("health/", lambda request: HttpResponse("OK")),
]
