"""
URL configuration for Sparks API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SparkViewSet, AppViewSet

router = DefaultRouter()
router.register(r'sparks', SparkViewSet, basename='spark')
router.register(r'apps', AppViewSet, basename='app')

urlpatterns = [
    path('', include(router.urls)),
]
