"""REST API views for Usage & Quota management."""

import json
import logging

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from authentication.permissions import IsVerifiedUser

from .billing.stripe_checkout import (
    create_checkout_session as _stripe_create_checkout,
    create_portal_session as _stripe_create_portal,
    retrieve_checkout_session as _stripe_retrieve_session,
)
from .exceptions import (
    FeatureNotAvailableException,
    SubscriptionNotFoundException,
)
from .models import (
    StripeWebhookEvent,
    SubscriptionPlan,
    UsageLog,
    UserSubscription,
)
from .serializers import (
    BillingStatusSerializer,
    CheckoutSessionRequestSerializer,
    CheckoutSessionResponseSerializer,
    PortalSessionResponseSerializer,
    QuotaCheckRequestSerializer,
    QuotaCheckResponseSerializer,
    QuotaInfoSerializer,
    SubscriptionPlanDetailSerializer,
    SyncFromSessionResponseSerializer,
    UsageDeductRequestSerializer,
    UsageDeductResponseSerializer,
    UsageLogSerializer,
    UsageSummarySerializer,
    UsageWithLimitsSerializer,
)
from .services import get_quota_service
from .services.stripe_customer import get_or_create_stripe_customer
from .services.stripe_helpers import (
    session_field,
    subscription_metadata_user_id,
    subscription_price_id,
)

logger = logging.getLogger(__name__)


class UsageHistoryPagination(PageNumberPagination):
    """Pagination for usage history."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


# =============================================================================
# User-facing endpoints
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quota(request):
    """
    Get current quota information for the authenticated user.

    Returns remaining weekly and session limits, usage breakdown by service
    and feature, and plan details.

    Response:
    {
        "plan": "pro",
        "plan_display_name": "Pro Plan",
        "weekly": {
            "limit_usd": "20.00",
            "used_usd": "8.45",
            "remaining_usd": "11.55",
            "window_start": "2025-12-18T00:00:00Z"
        },
        "session": {
            "limit_usd": "5.00"
        },
        "features": {"voice_rooms": true, "code_sessions": true},
        "by_service": {...},
        "by_feature": {...}
    }
    """
    quota_service = get_quota_service()

    try:
        quota_info = quota_service.get_user_quota_info(request.user)
        serializer = QuotaInfoSerializer(quota_info)
        return Response(serializer.data)
    except SubscriptionNotFoundException:
        return Response(
            {"error": "subscription_not_found", "message": "No subscription found for user"},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_usage_summary(request):
    """
    Get usage summary for the authenticated user.

    Query params:
    - days: Number of days to include (default: 7, max: 30)

    Response:
    {
        "period_start": "2025-12-18T00:00:00Z",
        "period_end": "2025-12-25T23:59:59Z",
        "total_cost_usd": "12.45",
        "total_requests": 245,
        "by_service": {...},
        "by_feature": {...},
        "by_day": [...]
    }
    """
    days = min(int(request.query_params.get('days', 7)), 30)

    now = timezone.now()
    period_start = now - timedelta(days=days)

    # Get usage logs for the period
    logs = UsageLog.objects.filter(
        user=request.user,
        timestamp__gte=period_start,
    )

    # Calculate totals
    from django.db.models import Sum, Count
    totals = logs.aggregate(
        total_cost=Sum('cost_usd'),
        total_requests=Count('id'),
    )

    # By service
    by_service_data = logs.values('service').annotate(
        total_cost=Sum('cost_usd'),
        total_requests=Count('id'),
    )
    by_service = {
        row['service']: {
            'used_usd': str(row['total_cost'] or 0),
            'requests': row['total_requests'],
        }
        for row in by_service_data
    }

    # By feature
    by_feature_data = logs.values('feature').annotate(
        total_cost=Sum('cost_usd'),
        total_requests=Count('id'),
    )
    by_feature = {
        row['feature']: {
            'used_usd': str(row['total_cost'] or 0),
            'requests': row['total_requests'],
        }
        for row in by_feature_data
    }

    # By day
    from django.db.models.functions import TruncDate
    by_day_data = logs.annotate(
        date=TruncDate('timestamp')
    ).values('date').annotate(
        total_cost=Sum('cost_usd'),
        total_requests=Count('id'),
    ).order_by('date')

    by_day = [
        {
            'date': row['date'].isoformat() if row['date'] else None,
            'cost_usd': str(row['total_cost'] or 0),
            'requests': row['total_requests'],
        }
        for row in by_day_data
    ]

    summary_data = {
        'period_start': period_start,
        'period_end': now,
        'total_cost_usd': totals['total_cost'] or 0,
        'total_requests': totals['total_requests'] or 0,
        'by_service': by_service,
        'by_feature': by_feature,
        'by_day': by_day,
    }

    serializer = UsageSummarySerializer(summary_data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_usage_history(request):
    """
    Get paginated usage history for the authenticated user.

    Query params:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - service: Filter by service type
    - feature: Filter by feature type
    - session_id: Filter by session ID

    Response:
    {
        "count": 245,
        "next": "http://...?page=2",
        "previous": null,
        "results": [...]
    }
    """
    queryset = UsageLog.objects.filter(user=request.user)

    # Apply filters
    service = request.query_params.get('service')
    if service:
        queryset = queryset.filter(service=service)

    feature = request.query_params.get('feature')
    if feature:
        queryset = queryset.filter(feature=feature)

    session_id = request.query_params.get('session_id')
    if session_id:
        queryset = queryset.filter(session_id=session_id)

    # Paginate
    paginator = UsageHistoryPagination()
    page = paginator.paginate_queryset(queryset, request)

    serializer = UsageLogSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# =============================================================================
# Internal endpoints (for service-to-service communication)
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_quota(request):
    """
    Pre-flight quota check before a billable operation.

    Used by services (e.g., Brave Search) to verify quota before proceeding.
    Cost can be provided directly via estimated_cost_usd, or calculated from request_count.

    Request:
    {
        "service": "brave_search",
        "estimated_cost_usd": "0.005",  // Optional - calculated if not provided
        "request_count": 1,              // Used to calculate cost if estimated_cost_usd not provided
        "feature": "search",
        "session_id": "optional"
    }

    Response:
    {
        "allowed": true,
        "reason": null,
        "remaining_weekly_usd": "11.55",
        "remaining_session_usd": "5.00",
        "weekly_limit_usd": "20.00",
        "session_limit_usd": "5.00"
    }
    """
    serializer = QuotaCheckRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    quota_service = get_quota_service()

    # Target user is always the JWT-authenticated caller. Any user_id
    # in the body is ignored (DRF drops unknown fields).
    user = request.user

    # Calculate cost if not provided (centralized pricing)
    estimated_cost_usd = data.get('estimated_cost_usd')
    if estimated_cost_usd is None:
        from .services import get_cost_calculator
        cost_calculator = get_cost_calculator()
        estimated_cost_usd = cost_calculator.calculate_cost(
            service=data['service'],
            request_count=data.get('request_count', 1),
        )

    try:
        result = quota_service.check_quota(
            user=user,
            service=data['service'],
            estimated_cost_usd=estimated_cost_usd,
            feature=data.get('feature', 'other'),
            session_id=data.get('session_id'),
        )

        response_serializer = QuotaCheckResponseSerializer({
            'allowed': result.allowed,
            'reason': result.reason,
            'remaining_weekly_usd': result.remaining_weekly_usd,
            'remaining_session_usd': result.remaining_session_usd,
            'weekly_limit_usd': result.weekly_limit_usd,
            'session_limit_usd': result.session_limit_usd,
        })

        return Response(response_serializer.data)

    except SubscriptionNotFoundException as e:
        return Response(
            {"error": "subscription_not_found", "message": str(e)},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deduct_usage(request):
    """
    Record usage after a successful billable operation.

    Used by services to deduct from user's quota after successful API calls.
    Cost can be provided directly via cost_usd, or calculated from request_count/character_count/audio_seconds.

    Request:
    {
        "service": "brave_search",
        "cost_usd": "0.005",      // Optional - calculated if not provided
        "request_count": 1,       // Used to calculate cost for request-based services
        "character_count": 0,     // Used to calculate cost for TTS services
        "audio_seconds": 0,       // Used to calculate cost for STT services
        "feature": "search",
        "session_id": "optional",
        "extra_data": {}
    }

    Response:
    {
        "success": true,
        "usage_log_id": "uuid",
        "cost_usd": "0.005",
        "new_weekly_used_usd": "8.50",
        "new_remaining_weekly_usd": "11.50"
    }
    """
    serializer = UsageDeductRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    quota_service = get_quota_service()

    # Target user is always the JWT-authenticated caller. Any user_id
    # in the body is ignored (DRF drops unknown fields).
    user = request.user

    # Calculate cost if not provided (centralized pricing)
    cost_usd = data.get('cost_usd')
    if cost_usd is None:
        from .services import get_cost_calculator
        cost_calculator = get_cost_calculator()
        cost_usd = cost_calculator.calculate_cost(
            service=data['service'],
            model_id=data.get('model_id', ''),
            request_count=data.get('request_count', 1),
            character_count=data.get('character_count', 0),
            audio_seconds=data.get('audio_seconds', 0),
            prompt_tokens=data.get('prompt_tokens', 0),
            completion_tokens=data.get('completion_tokens', 0),
        )

    try:
        result = quota_service.deduct_usage(
            user=user,
            service=data['service'],
            cost_usd=cost_usd,
            feature=data.get('feature', 'other'),
            session_id=data.get('session_id', ''),
            model_id=data.get('model_id', ''),
            prompt_tokens=data.get('prompt_tokens', 0),
            completion_tokens=data.get('completion_tokens', 0),
            character_count=data.get('character_count', 0),
            audio_seconds=data.get('audio_seconds', 0),
            request_count=data.get('request_count', 1),
            request_id=data.get('request_id', ''),
            extra_data=data.get('extra_data', {}),
        )

        response_serializer = UsageDeductResponseSerializer({
            'success': result.success,
            'usage_log_id': result.usage_log_id,
            'cost_usd': cost_usd,
            'new_weekly_used_usd': result.new_weekly_used_usd,
            'new_remaining_weekly_usd': result.new_remaining_weekly_usd,
        })

        return Response(response_serializer.data)

    except SubscriptionNotFoundException as e:
        return Response(
            {"error": "subscription_not_found", "message": str(e)},
            status=status.HTTP_404_NOT_FOUND
        )


# =============================================================================
# Feature access check
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_feature_access(request, feature_name):
    """
    Check if the authenticated user has access to a specific feature.

    Response:
    {
        "has_access": true,
        "feature": "voice_rooms"
    }
    """
    quota_service = get_quota_service()

    try:
        has_access = quota_service.check_feature_access(request.user, feature_name)
        return Response({
            "has_access": has_access,
            "feature": feature_name,
        })
    except FeatureNotAvailableException as e:
        return Response({
            "has_access": False,
            "feature": feature_name,
            "message": str(e),
        })
    except SubscriptionNotFoundException:
        return Response({
            "has_access": False,
            "feature": feature_name,
            "message": "No subscription found",
        })


from .feature_flags import get_release_stages  # noqa: E402


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_feature_flags(request):
    """
    Return feature release stages.
    Admin users see 'hidden' features; regular users see only beta/experimental.
    """
    stages = get_release_stages(is_admin=request.user.is_staff)
    return Response({'features': stages})


# =============================================================================
# Subscription endpoints (task 9: tier-aware plan + per-feature usage)
# =============================================================================

# Keys for which per-feature attribution in UsageLog is already correct.
# For any other key the backend returns `used: null` so the frontend does
# not render misleading numbers (e.g. counting LLM turns as voice-room
# sessions). Task 10 will fix attribution feature-by-feature and grow
# this set toward the full set of per-feature keys.
ATTRIBUTABLE_USAGE_KEYS: set = set()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscription_plan(request):
    """Return the authenticated user's active SubscriptionPlan.

    Includes per-feature count limits and Stripe price-id placeholders
    (Stripe wiring lands in task 11).
    """
    from .billing.service import get_billing_service
    try:
        plan = get_billing_service().get_user_plan(request.user)
    except SubscriptionNotFoundException:
        return Response(
            {"error": "subscription_not_found", "message": "No default plan configured"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(SubscriptionPlanDetailSerializer(plan).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscription_usage(request):
    """Return weekly/session totals + per-feature usage zipped with plan limits.

    Each ``per_feature[key]`` is ``{used, used_usd, limit}``. ``used`` is
    ``None`` (JSON ``null``) when the backend cannot reliably attribute
    usage to that feature yet; the frontend renders "—" in that case.
    """
    from .billing.service import get_billing_service
    billing = get_billing_service()
    try:
        plan = billing.get_user_plan(request.user)
    except SubscriptionNotFoundException:
        return Response(
            {"error": "subscription_not_found", "message": "No default plan configured"},
            status=status.HTTP_404_NOT_FOUND,
        )

    quota_info = billing._quota_service.get_user_quota_info(request.user)
    per_feature_limits = plan.get_per_feature_limits()
    by_feature = quota_info.by_feature  # {feature_name: {used_usd, requests}}
    per_feature = {}
    for key, limit in per_feature_limits.items():
        used_entry = by_feature.get(key, {})
        used_count = (
            used_entry.get("requests", 0)
            if key in ATTRIBUTABLE_USAGE_KEYS
            else None
        )
        per_feature[key] = {
            "used": used_count,
            "used_usd": used_entry.get("used_usd", "0"),
            "limit": limit,
        }

    response = {
        "weekly_used_usd": quota_info.weekly_used_usd,
        "weekly_limit_usd": quota_info.weekly_limit_usd,
        "weekly_window_end": quota_info.window_end,
        "session_used_usd": quota_info.session_used_usd,
        "session_limit_usd": quota_info.session_limit_usd,
        "session_window_end": quota_info.session_window_end,
        "per_feature": per_feature,
    }
    return Response(UsageWithLimitsSerializer(response).data)


# =============================================================================
# Stripe Checkout + Customer Portal (task 12)
# =============================================================================


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerifiedUser])
def create_checkout_session(request):
    """Start a Stripe Checkout Session for the authenticated user.

    Validates plan + cycle, resolves stripe_customer_id (creating one
    if the post-signup Celery task lost the race), and creates a
    subscription-mode Checkout Session with automatic tax + promotion
    codes enabled.
    """
    serializer = CheckoutSessionRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    plan_slug = serializer.validated_data['plan_slug']
    billing_cycle = serializer.validated_data['billing_cycle']

    try:
        target_plan = SubscriptionPlan.objects.get(name=plan_slug, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return Response(
            {'error': 'plan_not_found',
             'message': f'Unknown plan {plan_slug!r}'},
            status=status.HTTP_404_NOT_FOUND,
        )

    price_id = (
        target_plan.stripe_price_id_yearly if billing_cycle == 'yearly'
        else target_plan.stripe_price_id_monthly
    )
    if not price_id:
        logger.error(
            'checkout.no_price_id',
            extra={'plan_slug': plan_slug, 'billing_cycle': billing_cycle},
        )
        return Response(
            {'error': 'plan_not_billable',
             'message': 'Stripe price not configured for this plan.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Already-on-plan guard via BillingService so the lazy-default path
    # (no UserSubscription row yet) is handled. Cycle-only changes
    # (monthly↔yearly on the same plan) intentionally route through the
    # Customer Portal, not Checkout.
    from .billing.service import get_billing_service
    billing = get_billing_service()
    current_plan = billing.get_user_plan(request.user)
    if current_plan.name == plan_slug:
        return Response(
            {'error': 'already_on_plan',
             'message': f'You are already on the {current_plan.display_name} plan.'},
            status=status.HTTP_409_CONFLICT,
        )

    # Paid→paid plan changes must go through the Customer Portal
    # (subscription update), NOT a new Checkout Session — a second
    # Checkout creates a SECOND Stripe subscription and double-charges
    # the user. The webhook layer cancels a superseded subscription as
    # belt-and-braces, but the portal is the only correct flow here.
    has_active_stripe_sub = (
        UserSubscription.objects
        .filter(user=request.user, is_active=True)
        .exclude(stripe_subscription_id__isnull=True)
        .exclude(stripe_subscription_id='')
        .exists()
    )
    if has_active_stripe_sub:
        logger.info(
            'checkout.use_portal_redirect',
            extra={
                'user_id': str(request.user.id),
                'current_plan': current_plan.name,
                'target_plan': plan_slug,
            },
        )
        return Response(
            {'error': 'use_portal',
             'code': 'USE_PORTAL',
             'message': ('You already have an active subscription. '
                         'Change plans via the billing portal.'),
             'portal_hint': '/api/billing/portal-session/'},
            status=status.HTTP_409_CONFLICT,
        )

    customer_id = get_or_create_stripe_customer(request.user)
    if customer_id is None:
        logger.error(
            'checkout.no_customer_id',
            extra={'user_id': str(request.user.id)},
        )
        return Response(
            {'error': 'billing_unavailable',
             'message': 'Billing is not configured in this environment.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    base = settings.FRONTEND_URL.rstrip('/')
    try:
        session = _stripe_create_checkout(
            customer_id=customer_id,
            price_id=price_id,
            success_url=f"{base}/billing/return?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/pricing",
            user_id=str(request.user.id),
            plan_slug=plan_slug,
            billing_cycle=billing_cycle,
        )
    except stripe.error.InvalidRequestError as exc:
        # Most common: customer belongs to a different account (test vs
        # live key drift). The runtime canary; sanity_check_stripe_mode
        # is the upstream guard.
        logger.error(
            'checkout.stripe_invalid_request',
            extra={
                'user_id': str(request.user.id),
                'stripe_customer_id': customer_id,
                'stripe_mode': (
                    'live' if getattr(settings, 'STRIPE_LIVE_MODE', False)
                    else 'test'
                ),
                'detail': str(exc),
            },
        )
        return Response(
            {'error': 'stripe_misconfigured',
             'message': 'Billing service is misconfigured. Contact support.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except stripe.error.StripeError:
        logger.exception(
            'checkout.stripe_error',
            extra={'user_id': str(request.user.id)},
        )
        return Response(
            {'error': 'stripe_error',
             'message': 'Could not start checkout. Try again shortly.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        CheckoutSessionResponseSerializer({'url': session.url}).data
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_portal_session(request):
    """Open a Stripe Customer Portal session for managing an existing sub.

    Intentionally NOT gated by ``IsVerifiedUser``: a paid user whose
    email-verification lapses (e.g. address rotation) must still be able
    to cancel or update their subscription. The verified-email gate is
    only applied at upgrade time (``create_checkout_session``).
    """
    sub = UserSubscription.objects.filter(
        user=request.user, is_active=True,
    ).first()
    # Brief: "refuses if user has no active Stripe subscription". A free-plan
    # user has a UserSubscription row but no ``stripe_subscription_id``; the
    # portal would 404 in Stripe for that case, so refuse here with 409.
    if sub is None or not sub.stripe_subscription_id:
        return Response(
            {'error': 'no_subscription',
             'message': 'You need an active paid plan to manage billing.'},
            status=status.HTTP_409_CONFLICT,
        )

    customer_id = get_or_create_stripe_customer(request.user)
    if customer_id is None:
        return Response(
            {'error': 'billing_unavailable',
             'message': 'Billing is not configured in this environment.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    base = settings.FRONTEND_URL.rstrip('/')
    try:
        session = _stripe_create_portal(
            customer_id=customer_id,
            return_url=f"{base}/settings/billing",
        )
    except stripe.error.StripeError:
        logger.exception(
            'portal.stripe_error',
            extra={'user_id': str(request.user.id)},
        )
        return Response(
            {'error': 'stripe_error',
             'message': 'Could not open portal. Try again shortly.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        PortalSessionResponseSerializer({'url': session.url}).data
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_from_session(request):
    """Pull a completed Checkout Session and reconcile UserSubscription.

    Called by ``/billing/return`` after Stripe redirects the user back.
    The task-13 webhook handler will run the same idempotent reconciliation;
    this endpoint exists only for the immediate-feedback window before the
    webhook arrives.
    """
    session_id = (
        request.query_params.get('session_id')
        or request.data.get('session_id')
    )
    if not session_id:
        return Response(
            {'error': 'missing_session_id'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = _stripe_retrieve_session(session_id)
    except stripe.error.InvalidRequestError:
        return Response(
            {'error': 'session_not_found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    except stripe.error.StripeError:
        logger.exception(
            'sync.stripe_error',
            extra={'user_id': str(request.user.id)},
        )
        return Response(
            {'error': 'stripe_error'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # OWNERSHIP CHECK — must precede any DB write. The truthiness gate on
    # request.user.stripe_customer_id prevents a None==None vacuous-truth
    # bypass during the post-signup Celery race window.
    user_customer = request.user.stripe_customer_id
    session_customer = session_field(session, 'customer')
    owner_match = bool(user_customer) and session_customer == user_customer

    subscription = session_field(session, 'subscription')
    meta_user = subscription_metadata_user_id(subscription) if subscription else None
    meta_match = bool(meta_user) and meta_user == str(request.user.id)

    if not (owner_match or meta_match):
        logger.warning(
            'sync.foreign_session_attempt',
            extra={
                'user_id': str(request.user.id),
                'session_customer': session_customer,
            },
        )
        return Response(
            {'error': 'forbidden'},
            status=status.HTTP_403_FORBIDDEN,
        )

    payment_status = session_field(session, 'payment_status')
    if payment_status not in ('paid', 'no_payment_required'):
        return Response(
            {'error': 'payment_incomplete',
             'message': f'Payment status: {payment_status}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if subscription is None:
        return Response(
            {'error': 'no_subscription_on_session'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    price_id = subscription_price_id(subscription)
    if not price_id:
        return Response(
            {'error': 'no_items_on_subscription'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target = SubscriptionPlan.objects.filter(
        is_active=True,
    ).filter(
        Q(stripe_price_id_monthly=price_id)
        | Q(stripe_price_id_yearly=price_id),
    ).first()
    if target is None:
        logger.error('sync.unknown_price_id', extra={'price_id': price_id})
        return Response(
            {'error': 'unknown_price_id'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    sub_id = session_field(subscription, 'id') if isinstance(subscription, dict) \
        else getattr(subscription, 'id', None)
    sub_status = session_field(subscription, 'status') if isinstance(subscription, dict) \
        else getattr(subscription, 'status', None)
    sub_period_end = (
        subscription.get('current_period_end') if isinstance(subscription, dict)
        else getattr(subscription, 'current_period_end', None)
    )
    sub_cancel_at_period_end = bool(
        subscription.get('cancel_at_period_end') if isinstance(subscription, dict)
        else getattr(subscription, 'cancel_at_period_end', False)
    )

    # REPLAY GUARD — a paid session_id stays retrievable forever, so an
    # old session whose subscription has since been canceled must NOT
    # re-grant the plan for free. Only live subscriptions reconcile.
    if sub_status not in ('active', 'trialing'):
        logger.warning(
            'sync.subscription_not_active',
            extra={
                'user_id': str(request.user.id),
                'stripe_subscription_id': sub_id,
                'subscription_status': sub_status,
            },
        )
        return Response(
            {'error': 'subscription_not_active',
             'message': f'Subscription status: {sub_status}'},
            status=status.HTTP_409_CONFLICT,
        )

    # Idempotent reconcile — converges with task-13 webhook. Preserves
    # weekly_window_start (not in defaults).
    UserSubscription.objects.update_or_create(
        user=request.user,
        defaults={
            'plan': target,
            'stripe_subscription_id': sub_id,
            'is_active': True,
            'current_period_end': sub_period_end,
            'cancel_at_period_end': sub_cancel_at_period_end,
        },
    )

    from .billing.service import get_billing_service
    get_billing_service().invalidate_for_user(request.user)

    return Response(SyncFromSessionResponseSerializer({
        'plan': target.name,
        'plan_display_name': target.display_name,
        'status': sub_status or '',
        'current_period_end': sub_period_end,
        'cancel_at_period_end': sub_cancel_at_period_end,
    }).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_billing_status(request):
    """Return the user's current plan + cached Stripe period/cancel state.

    Backs the /settings/billing page so the renewal date + cancellation
    banner render without a Stripe API call. Free-plan users see
    ``current_period_end=None`` and ``cancel_at_period_end=False``.
    """
    from .billing.service import get_billing_service
    try:
        plan = get_billing_service().get_user_plan(request.user)
    except SubscriptionNotFoundException:
        return Response(
            {'error': 'subscription_not_found',
             'message': 'No default plan configured'},
            status=status.HTTP_404_NOT_FOUND,
        )

    sub = UserSubscription.objects.filter(
        user=request.user, is_active=True,
    ).first()

    return Response(BillingStatusSerializer({
        'plan': plan.name,
        'plan_display_name': plan.display_name,
        'plan_description': plan.description or '',
        'is_paid': plan.name != 'free',
        'current_period_end': sub.current_period_end if sub else None,
        'cancel_at_period_end': bool(sub.cancel_at_period_end) if sub else False,
    }).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def invoices_list(request):
    """Return the user's last 24 Stripe invoices.

    Users with no stripe_customer_id (never upgraded) get an empty
    list, not a 404. Fields are explicitly whitelisted — no raw
    Stripe payload leaks.
    """
    customer_id = request.user.stripe_customer_id
    if not customer_id:
        return Response({'results': []})

    try:
        # expand=['data.lines.data.price'] is REQUIRED — without it,
        # invoice.lines.data[0].price is a string id and
        # _resolve_plan_name_from_invoice falls back to the user's
        # *current* plan, mis-labeling historical invoices after a
        # downgrade.
        invoices = stripe.Invoice.list(
            customer=customer_id, limit=24,
            expand=['data.lines.data.price'],
        )
    except stripe.error.StripeError:
        logger.exception(
            'invoices.stripe_error',
            extra={'user_id': str(request.user.id)},
        )
        return Response(
            {'error': 'stripe_error',
             'message': 'Could not load invoices. Try again shortly.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    from .services.stripe_webhooks import _resolve_plan_name_from_invoice

    # Read invoices.data (first page only). DO NOT call
    # invoices.auto_paging_iter() — limit=24 is Stripe's page-size
    # parameter; auto-paging would follow has_more=True to subsequent
    # pages, blowing past the documented 24-row cap.
    data = (invoices.data if not isinstance(invoices, dict)
            else invoices.get('data', []))
    results = []
    for inv in data:
        results.append({
            'id': session_field(inv, 'id'),
            'number': session_field(inv, 'number') or '',
            'created': session_field(inv, 'created'),
            'total': session_field(inv, 'total'),
            'subtotal_excl_tax': session_field(inv, 'subtotal'),
            'tax': session_field(inv, 'tax') or 0,
            'currency': (session_field(inv, 'currency') or 'usd').lower(),
            'status': session_field(inv, 'status') or '',
            'hosted_invoice_url': session_field(inv, 'hosted_invoice_url') or '',
            'invoice_pdf': session_field(inv, 'invoice_pdf') or '',
            'plan_name': _resolve_plan_name_from_invoice(inv, request.user),
        })

    return Response({'results': results})


# =============================================================================
# Stripe webhook (task 13)
# =============================================================================


def _serialize_event_payload(event) -> dict:
    """Coerce a stripe.Event (SDK object or dict) into a JSON-safe dict.

    ``StripeObject.to_dict()`` returns a dict but can include
    non-JSON-native values (e.g. Decimal on newer API versions). The
    ``json.dumps(..., default=str)`` round-trip ensures the final
    payload survives Django's JSONField encoder without raising.
    """
    raw = event if isinstance(event, dict) else event.to_dict()
    return json.loads(json.dumps(raw, default=str))


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """Receive + verify + dedup + dispatch a Stripe webhook delivery.

    Auth: Stripe signs the raw body with ``STRIPE_WEBHOOK_SECRET``;
    ``stripe.Webhook.construct_event`` verifies and raises on bad
    signature.

    Idempotency + race-safety: the dedup state machine is
    ``NULL → processing → ok | error | skipped``, claimed via an
    atomic CAS ``UPDATE ... WHERE processed_status NOT IN
    ('ok','processing')``. A parallel delivery that loses the CAS
    returns 200 ``in_flight``; the original worker wins.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error('stripe.webhook.no_secret')
        return Response(
            {'error': 'webhook_not_configured'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning(
            'stripe.webhook.bad_signature',
            extra={'detail': str(exc)},
        )
        return Response(
            {'error': 'invalid_signature'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    event_id = event['id']
    event_type = event['type']

    # Step A: idempotent INSERT (ignore conflict — another worker may
    # have inserted first; the CAS in Step C decides who dispatches).
    # Inner atomic() wraps the INSERT in a SAVEPOINT so a duplicate-PK
    # IntegrityError rolls back JUST this statement, not the outer
    # connection-level transaction (mandatory under pytest-django's
    # outer transaction wrapper; also good practice in production).
    try:
        with transaction.atomic():
            StripeWebhookEvent.objects.create(
                id=event_id,
                type=event_type,
                payload=_serialize_event_payload(event),
                processed_status=None,
            )
    except IntegrityError:
        pass

    # Step B: short-circuit if already processed.
    current_status = (
        StripeWebhookEvent.objects
        .filter(id=event_id)
        .values_list('processed_status', flat=True)
        .first()
    )
    if current_status == StripeWebhookEvent.PROCESSED_STATUS_OK:
        logger.info(
            'stripe.webhook.dedup_noop',
            extra={'event_id': event_id, 'event_type': event_type},
        )
        return Response({'received': True, 'dedup': True})

    # Step C: CAS claim — atomic UPDATE excluding ok + FRESH processing.
    # A 'processing' claim older than PROCESSING_CLAIM_TTL is treated as
    # abandoned (worker crashed between claim and terminal write) and is
    # claimable again — otherwise the event is permanently lost, since
    # Stripe's retries all short-circuit as in_flight. A NULL claimed_at
    # counts as fresh (the claim below always stamps it; NULL can only
    # be a row written mid-deploy).
    stale_cutoff = timezone.now() - StripeWebhookEvent.PROCESSING_CLAIM_TTL
    claimed = (
        StripeWebhookEvent.objects
        .filter(id=event_id)
        .exclude(processed_status=StripeWebhookEvent.PROCESSED_STATUS_OK)
        .exclude(
            Q(processed_status=StripeWebhookEvent.PROCESSED_STATUS_PROCESSING)
            & (Q(claimed_at__isnull=True) | Q(claimed_at__gt=stale_cutoff)),
        )
        .update(
            processed_status=StripeWebhookEvent.PROCESSED_STATUS_PROCESSING,
            claimed_at=timezone.now(),
            error_message=None,
            processed_at=None,
        )
    )
    if claimed == 0:
        logger.info(
            'stripe.webhook.in_flight',
            extra={'event_id': event_id, 'event_type': event_type},
        )
        return Response({'received': True, 'in_flight': True})

    # Step D: dispatch with terminal-state write.
    from .services.stripe_webhooks import _IgnorableEvent, dispatch
    try:
        result_status = dispatch(event)
    except _IgnorableEvent as exc:
        StripeWebhookEvent.objects.filter(id=event_id).update(
            processed_status=StripeWebhookEvent.PROCESSED_STATUS_SKIPPED,
            error_message=str(exc)[:5000],
            processed_at=timezone.now(),
        )
        return Response({'received': True, 'skipped': True})
    except Exception as exc:
        logger.exception(
            'stripe.webhook.handler_failed',
            extra={'event_id': event_id, 'event_type': event_type},
        )
        StripeWebhookEvent.objects.filter(id=event_id).update(
            processed_status=StripeWebhookEvent.PROCESSED_STATUS_ERROR,
            error_message=str(exc)[:5000],
            processed_at=timezone.now(),
        )
        # Return 500 explicitly (instead of re-raise) so the response
        # path is deterministic for Stripe — any 5xx triggers a retry.
        # Re-raising would trip the RequestIDMiddleware's exception path,
        # which then double-resets its ContextVar token.
        return Response(
            {'error': 'handler_failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    StripeWebhookEvent.objects.filter(id=event_id).update(
        processed_status=(
            StripeWebhookEvent.PROCESSED_STATUS_OK if result_status == 'ok'
            else StripeWebhookEvent.PROCESSED_STATUS_SKIPPED
        ),
        error_message=None,
        processed_at=timezone.now(),
    )
    return Response({'received': True})
