"""Subscription state transitions — model-side only (no Stripe).

Stripe wiring lands in task 12; this service is the in-process write
surface that task 12 will wrap.
"""
import logging

from django.db import transaction

from usage_quota.exceptions import SubscriptionNotFoundException
from usage_quota.models import SubscriptionPlan, UserSubscription
from usage_quota.services import get_quota_service

logger = logging.getLogger(__name__)


class SubscriptionService:
    """In-process subscription state writer (no Stripe — task 12 wraps)."""

    def __init__(self):
        self._quota = get_quota_service()

    @transaction.atomic
    def change_plan(
        self,
        user,
        target_plan_slug: str,
        *,
        initiated_by: str = 'admin',
        reason: str = '',
    ) -> dict:
        """Reassign the user's plan.

        Semantics:
          * Upgrade / lateral move: reassign plan; preserve
            ``weekly_window_start`` and ``session_window_start``.
          * Downgrade (lower ``weekly_limit_usd``): reassign; preserve
            ``weekly_window_start``; reset ``session_window_start = None``
            so the user can't finish a Pro-sized burst on a Free budget.
          * Same plan: no-op (return early; no email).
          * Inactive / unknown target: raise
            ``SubscriptionNotFoundException``.

        Returns a dict describing the change (for audit + admin UI).
        """
        try:
            target = SubscriptionPlan.objects.get(
                name=target_plan_slug, is_active=True,
            )
        except SubscriptionPlan.DoesNotExist:
            raise SubscriptionNotFoundException(target_plan_slug)

        sub = UserSubscription.objects.select_for_update().filter(
            user=user, is_active=True,
        ).first()

        if sub is None:
            # First-time subscription. Use get_or_create to be safe under
            # concurrent admin calls.
            sub, created = UserSubscription.objects.get_or_create(
                user=user,
                is_active=True,
                defaults={'plan': target},
            )
            if not created and sub.plan_id != target.id:
                from_plan = sub.plan
                is_downgrade = (
                    target.weekly_limit_usd < from_plan.weekly_limit_usd
                )
                sub.plan = target
                if is_downgrade:
                    sub.session_window_start = None
                sub.save()
                self._notify(user, from_plan, target, initiated_by, reason)
                self._quota._invalidate_user_cache(str(user.id))
                self._audit(user, from_plan, target, initiated_by, reason)
                return {
                    'from': from_plan.name,
                    'to': target.name,
                    'is_downgrade': is_downgrade,
                    'session_window_reset': is_downgrade,
                }
            self._notify(user, None, target, initiated_by, reason)
            self._quota._invalidate_user_cache(str(user.id))
            self._audit(user, None, target, initiated_by, reason)
            return {
                'from': None,
                'to': target.name,
                'is_downgrade': False,
                'session_window_reset': False,
            }

        from_plan = sub.plan
        if from_plan.id == target.id:
            return {
                'from': from_plan.name,
                'to': target.name,
                'is_downgrade': False,
                'session_window_reset': False,
            }

        is_downgrade = target.weekly_limit_usd < from_plan.weekly_limit_usd
        sub.plan = target
        if is_downgrade:
            sub.session_window_start = None
        sub.save()
        self._notify(user, from_plan, target, initiated_by, reason)
        self._quota._invalidate_user_cache(str(user.id))
        self._audit(user, from_plan, target, initiated_by, reason)

        logger.info(
            "subscription.change_plan",
            extra={
                "user_id": str(user.id),
                "from": from_plan.name,
                "to": target.name,
                "is_downgrade": is_downgrade,
                "initiated_by": initiated_by,
            },
        )
        return {
            'from': from_plan.name,
            'to': target.name,
            'is_downgrade': is_downgrade,
            'session_window_reset': is_downgrade,
        }

    def _notify(self, user, from_plan, to_plan, initiated_by, reason):
        try:
            from notifications.services import send_plan_change_email
            send_plan_change_email(user, from_plan, to_plan)
        except Exception:
            logger.warning("plan_change_email_failed", exc_info=True)

    def _audit(self, user, from_plan, to_plan, initiated_by, reason):
        try:
            from audit_logging.services import AuditService
            AuditService.log_action(
                action='subscription_plan_change',
                user=user,
                from_plan=(from_plan.name if from_plan else None),
                to_plan=to_plan.name,
                initiated_by=initiated_by,
                reason=reason,
            )
        except Exception:
            logger.warning("plan_change_audit_failed", exc_info=True)
