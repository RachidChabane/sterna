"""
URL configuration for Consigliere module.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ConsiglierViewSet

router = DefaultRouter()
router.register(r"", ConsiglierViewSet, basename="consigliere")

app_name = "consigliere"

urlpatterns = [
    path("", include(router.urls)),
]
