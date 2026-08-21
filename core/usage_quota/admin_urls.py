"""Admin (staff-gated) URLs for usage_quota."""

from django.urls import path

from . import admin_views

urlpatterns = [
    path(
        'users/<uuid:user_id>/plan/',
        admin_views.change_user_plan,
        name='admin-change-user-plan',
    ),
]
