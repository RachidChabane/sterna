"""Admin-only endpoints for usage_quota (staff-gated)."""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from usage_quota.services.subscription_service import SubscriptionService

User = get_user_model()


@api_view(['PUT', 'POST'])
@permission_classes([IsAdminUser])
def change_user_plan(request, user_id):
    """Reassign a user's subscription plan.

    Idempotent: the same input twice → second call no-ops.
    """
    target_slug = request.data.get('target_plan_slug')
    if not target_slug:
        return Response(
            {"error": "target_plan_slug required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reason = request.data.get('reason', '')
    user = get_object_or_404(User, id=user_id)
    result = SubscriptionService().change_plan(
        user,
        target_slug,
        initiated_by=f'admin:{request.user.email}',
        reason=reason,
    )
    return Response(result, status=status.HTTP_200_OK)
