"""Custom exceptions for the Usage & Quota system."""

from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Optional


class QuotaException(Exception):
    """Base exception for quota-related errors."""

    def __init__(self, message: str, code: str = "quota_error"):
        self.message = message
        self.code = code
        super().__init__(message)


class QuotaExceededException(QuotaException):
    """Raised when a user exceeds their quota limit."""

    def __init__(
        self,
        message: str,
        limit_usd: Decimal,
        used_usd: Decimal,
        remaining_usd: Decimal,
        limit_type: str = "weekly",
        resets_in_seconds: Optional[int] = None,
        *,
        feature_name: Optional[str] = None,
        used_count: Optional[int] = None,
        limit_count: Optional[int] = None,
    ):
        super().__init__(message, code="quota_exceeded")
        self.limit_usd = limit_usd
        self.used_usd = used_usd
        self.remaining_usd = remaining_usd
        self.limit_type = limit_type
        self.resets_in_seconds = resets_in_seconds
        self.feature_name = feature_name
        self.used_count = used_count
        self.limit_count = limit_count

    @property
    def reset_at(self) -> Optional[datetime]:
        if self.resets_in_seconds is None:
            return None
        return datetime.now(dt_timezone.utc) + timedelta(
            seconds=self.resets_in_seconds
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response (legacy shape)."""
        result = {
            "error": self.code,
            "message": self.message,
            "details": {
                "limit_type": self.limit_type,
                "limit_usd": str(self.limit_usd),
                "used_usd": str(self.used_usd),
                "remaining_usd": str(self.remaining_usd),
            }
        }
        if self.resets_in_seconds is not None:
            result["details"]["resets_in_seconds"] = self.resets_in_seconds
            hours = self.resets_in_seconds // 3600
            result["details"]["resets_in_hours"] = hours
        if self.feature_name is not None:
            result["details"]["feature"] = self.feature_name
        return result

    def to_response_dict(self) -> dict:
        """402-shaped body for the DRF exception handler."""
        details: dict = {
            "limit_type": self.limit_type,
            "feature": self.feature_name,
            "upgrade_url": "/pricing",
        }
        if self.feature_name and self.limit_count is not None:
            details["used"] = self.used_count
            details["limit"] = self.limit_count
        else:
            details["limit_usd"] = str(self.limit_usd)
            details["used_usd"] = str(self.used_usd)
            details["remaining_usd"] = str(self.remaining_usd)
        if self.resets_in_seconds is not None:
            details["resets_in_seconds"] = self.resets_in_seconds
            reset_at = self.reset_at
            if reset_at is not None:
                details["reset_at"] = reset_at.isoformat()
        return {
            "error": self.code,
            "message": self.message,
            "details": details,
        }


class FeatureNotAvailableException(QuotaException):
    """Raised when a user tries to access a feature not in their plan."""

    def __init__(
        self,
        feature: str,
        plan_name: str,
        *,
        plan_slug: Optional[str] = None,
    ):
        message = f"Feature '{feature}' is not available in your {plan_name} plan"
        super().__init__(message, code="feature_not_available")
        self.feature = feature
        self.plan_name = plan_name
        self.plan_slug = plan_slug or (plan_name or "").lower()

    def to_dict(self) -> dict:
        """Convert to dictionary for API response (legacy shape)."""
        return {
            "error": self.code,
            "message": self.message,
            "details": {
                "feature": self.feature,
                "plan": self.plan_name,
                "plan_slug": self.plan_slug,
            }
        }

    def to_response_dict(self) -> dict:
        """402-shaped body for the DRF exception handler."""
        return {
            "error": self.code,
            "message": self.message,
            "details": {
                "feature": self.feature,
                "plan": self.plan_name,
                "plan_slug": self.plan_slug,
                "upgrade_url": "/pricing",
            },
        }


class SubscriptionNotFoundException(QuotaException):
    """Raised when a user doesn't have an active subscription."""

    def __init__(self, user_id: str):
        message = "No active subscription found for this user"
        super().__init__(message, code="no_subscription")
        self.user_id = user_id

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "error": self.code,
            "message": self.message,
        }


class ServicePricingNotFoundException(QuotaException):
    """Raised when pricing configuration is not found for a service/model."""

    def __init__(self, service: str, model_id: Optional[str] = None):
        model_str = f" (model: {model_id})" if model_id else ""
        message = f"Pricing not found for service '{service}'{model_str}"
        super().__init__(message, code="pricing_not_found")
        self.service = service
        self.model_id = model_id


class BillingMisconfiguration(QuotaException):
    """Raised when billing configuration is internally inconsistent
    (e.g. a tier-limit env var is set but the tier row is missing).

    Distinct from QuotaExceededException: this is an OPS bug, not a
    user issue, and should page the team. Referenced by the Sentry
    alert rule documented in docs/operations/sentry-alerts.md.
    """

    def __init__(self, message: str, *, hint: str = ""):
        super().__init__(message, code="billing_misconfigured")
        self.hint = hint

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": "Service temporarily unavailable",
            "details": {"hint": self.hint} if self.hint else {},
        }


# Brief-name aliases (task 10 brief uses these). Kept here so future
# callers can import either name; both refer to the same class.
QuotaExceeded = QuotaExceededException
FeatureNotAvailable = FeatureNotAvailableException
