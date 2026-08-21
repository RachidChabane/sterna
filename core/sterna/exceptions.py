"""Project-wide DRF exception handler.

Registered via ``REST_FRAMEWORK['EXCEPTION_HANDLER']``. Maps billing
exceptions to 402; passes everything else to DRF's default handler.
"""
import logging

from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from usage_quota.exceptions import (
    BillingMisconfiguration,
    FeatureNotAvailableException,
    QuotaExceededException,
    SubscriptionNotFoundException,
)

logger = logging.getLogger(__name__)

PAYMENT_REQUIRED = 402  # DRF doesn't expose a constant for this


def _audit_quota_exceeded(exc, context) -> None:
    """Leave an AuditLog trail when a request is rejected for quota.

    Best-effort: an audit failure must never break the 402 response.
    Lives in the exception-handler layer (not quota_service) so the
    audit fires exactly once per rejected request, wherever the
    QuotaExceededException was raised.
    """
    try:
        from audit_logging.models import AuditLog

        request = (context or {}).get("request")
        user = getattr(request, "user", None)
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        request_id = getattr(request, "request_id", None)
        if not request_id:
            from sterna.middleware.request_id import current_request_id

            request_id = current_request_id.get()
        AuditLog.objects.log(
            action="BILLING_QUOTA_EXCEEDED",
            user=user,
            request_id=request_id,
            success=False,
            extra_data={
                "feature": exc.feature_name,
                "limit_type": exc.limit_type,
            },
        )
    except Exception:
        logger.warning("billing.quota_exceeded_audit_failed", exc_info=True)


def billing_exception_handler(exc, context):
    if isinstance(exc, FeatureNotAvailableException):
        logger.info(
            "billing.feature_not_available",
            extra={"feature": exc.feature, "plan_slug": exc.plan_slug},
        )
        return Response(exc.to_response_dict(), status=PAYMENT_REQUIRED)
    if isinstance(exc, QuotaExceededException):
        logger.info(
            "billing.quota_exceeded",
            extra={
                "feature": exc.feature_name,
                "limit_type": exc.limit_type,
            },
        )
        _audit_quota_exceeded(exc, context)
        return Response(exc.to_response_dict(), status=PAYMENT_REQUIRED)
    if isinstance(exc, SubscriptionNotFoundException):
        logger.error("billing.no_subscription", extra={"user_id": exc.user_id})
        return Response(
            exc.to_dict(),
            status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(exc, BillingMisconfiguration):
        logger.error("billing.misconfiguration", extra={"hint": exc.hint})
        return Response(
            exc.to_dict(),
            status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return drf_default_handler(exc, context)
