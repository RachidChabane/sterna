"""Handlers for the Stripe webhook events that change billing state.

Each handler is idempotent at the row level: re-running on the same
event (or a Stripe SDK Retrieve of the same object) converges to the
same DB state. The ``StripeWebhookEvent`` dedup row is the safety net
for whole-event replays; per-row idempotency is the safety net for
out-of-order deliveries within a single subscription's lifecycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_tz
from typing import Any, Callable, Optional

import stripe
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from notifications.services import (
    send_plan_change_email,
    send_subscription_canceled,
    send_subscription_payment_failed,
    send_subscription_receipt,
    send_subscription_trial_ending,
)
from usage_quota.billing.service import get_billing_service
from usage_quota.models import SubscriptionPlan, UserSubscription
from usage_quota.services.stripe_helpers import (
    subscription_cancel_at_period_end,
    subscription_current_period_end,
    subscription_customer_id,
    subscription_id,
    subscription_metadata_plan_slug,
    subscription_metadata_user_id,
    subscription_price_id,
    subscription_status,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class _IgnorableEvent(Exception):
    """Raised internally when the event references a customer/sub we
    don't know about. Bubbles up to the dispatcher as a 'skipped'
    status, not an error — Stripe should NOT retry these."""


# ---------------------------------------------------------------------
# User + plan resolution
# ---------------------------------------------------------------------

def _resolve_user(*, customer_id: Optional[str],
                  meta_user_id: Optional[str]):
    """Find a user by stripe_customer_id, falling back to metadata user_id.

    Returns None if neither identifier resolves. The handler decides
    whether that's an error (raise) or a skip (log + skipped status).
    """
    if customer_id:
        user = User.objects.filter(stripe_customer_id=customer_id).first()
        if user is not None:
            return user
    if meta_user_id:
        user = User.objects.filter(id=meta_user_id).first()
        if user is not None:
            return user
    return None


def _resolve_plan(*, plan_slug: Optional[str],
                  price_id: Optional[str]) -> Optional[SubscriptionPlan]:
    """Resolve a SubscriptionPlan by metadata.plan_slug or price id.

    We resolve via BOTH sources when both are present and cross-check.
    On mismatch (drift between Checkout metadata and the Stripe price)
    we log a warning and prefer the price-id-based plan as authoritative
    (immutable Stripe state).
    """
    plan_via_slug: Optional[SubscriptionPlan] = None
    plan_via_price: Optional[SubscriptionPlan] = None

    if plan_slug:
        plan_via_slug = SubscriptionPlan.objects.filter(
            name=plan_slug, is_active=True,
        ).first()

    if price_id:
        plan_via_price = SubscriptionPlan.objects.filter(
            is_active=True,
        ).filter(
            Q(stripe_price_id_monthly=price_id)
            | Q(stripe_price_id_yearly=price_id),
        ).first()

    if (plan_via_slug and plan_via_price
            and plan_via_slug.id != plan_via_price.id):
        logger.warning(
            'stripe.webhook.plan_resolution_mismatch',
            extra={
                'plan_slug': plan_slug,
                'price_id': price_id,
                'slug_plan_id': str(plan_via_slug.id),
                'price_plan_id': str(plan_via_price.id),
            },
        )
        return plan_via_price

    return plan_via_slug or plan_via_price


def _format_period_end(unix_seconds: Optional[int]) -> Optional[str]:
    if unix_seconds is None:
        return None
    return datetime.fromtimestamp(unix_seconds, tz=dt_tz.utc).strftime('%Y-%m-%d')


def _format_amount(amount_minor_units, currency: str) -> str:
    """Render a Stripe minor-unit amount as a 2-decimal display string.

    Assumes a 2-decimal currency (USD/EUR/GBP). JPY (0 decimals) and
    KWD (3 decimals) would render wrong; Sterna is USD-only today.
    """
    if amount_minor_units is None:
        return ''
    return f"${amount_minor_units / 100:.2f} {currency.upper()}"


def _format_minor_units(amount, currency: str) -> str:
    """Render a Stripe minor-unit amount as a 2-decimal display string.

    Returns '' for None or 0 so the template can use
    ``{% if invoice.tax_display %}`` as the gate (no-VAT case).
    """
    if not amount:
        return ''
    return f"${amount / 100:.2f} {currency.upper()}"


def _format_unix_date(unix_seconds) -> str:
    if unix_seconds is None:
        return ''
    return datetime.fromtimestamp(unix_seconds, tz=dt_tz.utc).strftime(
        '%Y-%m-%d'
    )


def _resolve_tax_rate_display(invoice: Any) -> str:
    """Extract a 'VAT 19%' style label from invoice.total_tax_amounts.

    Stripe attaches one entry per rate; for a single-rate B2C invoice
    we read [0]. Returns '' if no tax was applied.

    API-version note: ``total_tax_amounts`` is the pre-API-2024 shape.
    Stripe API 2024-09+ renames this to ``total_taxes``. Both ship
    today depending on the account's pinned API version. We assume
    the older shape; on a newer-API account the field is absent and
    we return '', causing the template to fall back to the literal
    "VAT" label via ``tax_rate_display|default:"VAT"``.
    """
    tta_root = (invoice.get('total_tax_amounts')
                if isinstance(invoice, dict)
                else getattr(invoice, 'total_tax_amounts', None))
    if not tta_root:
        return ''
    first = tta_root[0]
    tax_rate = (first.get('tax_rate') if isinstance(first, dict)
                else getattr(first, 'tax_rate', None))
    if tax_rate is None:
        return ''
    if isinstance(tax_rate, str):
        return ''
    pct = (tax_rate.get('percentage') if isinstance(tax_rate, dict)
           else getattr(tax_rate, 'percentage', None))
    display_name = (tax_rate.get('display_name') if isinstance(tax_rate, dict)
                    else getattr(tax_rate, 'display_name', None))
    if pct is None:
        return ''
    label = display_name or 'VAT'
    return f"{label} {pct:g}%"


# ---------------------------------------------------------------------
# Email helpers (best-effort; never raise from a handler)
# ---------------------------------------------------------------------

def _safe_email(name: str, fn: Callable, *args, **kwargs) -> None:
    """Call an email-sender, swallow exceptions, log them.

    Webhooks must not 500 because Resend is degraded — the subscription
    mutation already happened and is the source of truth.
    """
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.warning(
            "stripe.webhook.email_failed",
            extra={"sender": name},
            exc_info=True,
        )


# ---------------------------------------------------------------------
# Event payload accessors (event-level: object + previous_attributes)
# ---------------------------------------------------------------------

def _event_object(event: Any) -> Any:
    if isinstance(event, dict):
        return event['data']['object']
    return event.data.object


def _event_previous_attributes(event: Any) -> dict:
    if isinstance(event, dict):
        return event.get('data', {}).get('previous_attributes', {}) or {}
    data = getattr(event, 'data', None)
    if data is None:
        return {}
    prev = getattr(data, 'previous_attributes', None)
    return prev or {}


def _event_created(event: Any) -> Optional[int]:
    """Top-level ``created`` unix seconds of a Stripe event (or None)."""
    if isinstance(event, dict):
        return event.get('created')
    return getattr(event, 'created', None)


def _is_stale_event(marker: Optional[int],
                    event_created: Optional[int]) -> bool:
    """True iff this event is strictly older than the row's marker.

    Guards UserSubscription writes against out-of-order webhook
    delivery (e.g. a late ``customer.subscription.created`` after a
    newer plan change was already applied). Events without a
    ``created`` timestamp — and rows without a marker — always apply
    (backwards compatible).
    """
    return (
        event_created is not None
        and marker is not None
        and event_created < marker
    )


def _invoice_field(invoice: Any, key: str, default: Any = None) -> Any:
    if isinstance(invoice, dict):
        return invoice.get(key, default)
    return getattr(invoice, key, default)


def _resolve_plan_name_from_invoice(invoice: Any, user) -> str:
    lines_root = (invoice.get('lines') if isinstance(invoice, dict)
                  else getattr(invoice, 'lines', None))
    if lines_root:
        data = (lines_root.get('data') if isinstance(lines_root, dict)
                else getattr(lines_root, 'data', None))
        if data:
            first = data[0]
            price = (first.get('price') if isinstance(first, dict)
                     else getattr(first, 'price', None))
            if price:
                price_id = (price.get('id') if isinstance(price, dict)
                            else getattr(price, 'id', None))
                plan = _resolve_plan(plan_slug=None, price_id=price_id)
                if plan is not None:
                    return plan.display_name
    return get_billing_service().get_user_plan(user).display_name


def _cancel_superseded_subscription(*, user, old_sub_id: str,
                                    new_sub_id: Optional[str]) -> None:
    """Cancel a Stripe subscription that a newer one has replaced.

    Belt-and-braces for the double-subscription defect: if a second
    Checkout slipped through (race, stale client), the user now has TWO
    live Stripe subscriptions and would be double-charged. The new one
    just became the row's source of truth, so the old one is canceled
    in Stripe. Idempotent: an already-canceled old subscription is a
    no-op. Never raises — the row mutation already happened and a
    Stripe retry of this event would re-run the whole handler.
    """
    log_extra = {
        'user_id': str(user.id),
        'old_subscription_id': old_sub_id,
        'new_subscription_id': new_sub_id,
    }
    try:
        old_sub = stripe.Subscription.retrieve(old_sub_id)
        old_status = subscription_status(old_sub)
        if old_status in ('canceled', 'incomplete_expired'):
            logger.info(
                'stripe.webhook.superseded_subscription_already_inactive',
                extra={**log_extra, 'old_status': old_status},
            )
            return
        # stripe-python's DeletableAPIResource.delete is a dual-dispatch
        # method (@class_method_variant): called on the class with a raw
        # id, as here, it correctly routes to the classmethod variant at
        # runtime, but its stub only types the instance-call overload.
        stripe.Subscription.delete(old_sub_id)  # type: ignore[arg-type]
        logger.warning(
            'stripe.webhook.superseded_subscription_canceled',
            extra={**log_extra, 'old_status': old_status},
        )
    except stripe.StripeError:
        logger.exception(
            'stripe.webhook.superseded_subscription_cancel_failed',
            extra=log_extra,
        )
        return
    try:
        from audit_logging.services import AuditService
        AuditService.log_action(
            action='stripe_superseded_subscription_canceled',
            user=user,
            old_subscription_id=old_sub_id,
            new_subscription_id=new_sub_id,
        )
    except Exception:
        logger.warning(
            'stripe.webhook.superseded_subscription_audit_failed',
            extra=log_extra, exc_info=True,
        )


def _downgrade_to_free(user, *, period_end: Optional[int],
                       event_created: Optional[int] = None) -> None:
    """Shared downgrade path: reset the row to the free plan.

    Used by ``customer.subscription.deleted`` and by the dunning
    terminal statuses (``unpaid`` / ``incomplete_expired``) on
    ``customer.subscription.updated``. Sends the cancel email iff the
    user was on a paid plan.
    """
    free_plan = SubscriptionPlan.objects.filter(
        name='free', is_active=True,
    ).first()
    if free_plan is None:
        raise RuntimeError("No active 'free' plan — server misconfigured")

    with transaction.atomic():
        row, _ = UserSubscription.objects.select_for_update().get_or_create(
            user=user, defaults={'plan': free_plan, 'is_active': True},
        )
        was_paid = row.plan.name != 'free'
        row.plan = free_plan
        row.stripe_subscription_id = None
        row.current_period_end = None
        row.cancel_at_period_end = False
        row.session_window_start = None
        if event_created is not None:
            row.stripe_event_created = event_created
        row.save()

    get_billing_service().invalidate_for_user(user)
    if was_paid:
        _safe_email(
            'send_subscription_canceled',
            send_subscription_canceled, user,
            period_end=_format_period_end(period_end),
        )


# ---------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------

def _handle_subscription_created(event: Any) -> None:
    """customer.subscription.created → set UserSubscription to the new plan.

    Plan resolution: ``_resolve_plan(plan_slug, price_id)`` — both
    cross-checked; price_id wins on mismatch. Sends
    ``send_plan_change_email(user, from_plan, plan)`` for welcome /
    plan-change messaging. Receipt is sent by
    ``_handle_invoice_payment_succeeded`` when the invoice arrives.
    """
    sub = _event_object(event)
    customer_id = subscription_customer_id(sub)
    meta_user_id = subscription_metadata_user_id(sub)
    user = _resolve_user(customer_id=customer_id, meta_user_id=meta_user_id)
    if user is None:
        logger.warning(
            "stripe.webhook.unknown_user",
            extra={"event_type": "customer.subscription.created",
                   "stripe_customer_id": customer_id},
        )
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )

    plan_slug = subscription_metadata_plan_slug(sub)
    price_id = subscription_price_id(sub)
    plan = _resolve_plan(plan_slug=plan_slug, price_id=price_id)
    if plan is None:
        logger.error(
            "stripe.webhook.unknown_plan",
            extra={"plan_slug": plan_slug, "price_id": price_id},
        )
        raise RuntimeError(
            f"No SubscriptionPlan for plan_slug={plan_slug!r} "
            f"price_id={price_id!r}"
        )

    sub_id = subscription_id(sub)
    period_end = subscription_current_period_end(sub)
    cancel_at_end = subscription_cancel_at_period_end(sub)
    event_created = _event_created(event)

    superseded_sub_id = None
    with transaction.atomic():
        existing = UserSubscription.objects.select_for_update().filter(
            user=user,
        ).first()
        if existing is not None and _is_stale_event(
            existing.stripe_event_created, event_created,
        ):
            logger.info(
                'stripe.webhook.stale_event_skipped',
                extra={
                    'event_type': 'customer.subscription.created',
                    'user_id': str(user.id),
                    'event_created_ts': event_created,
                    'row_marker_ts': existing.stripe_event_created,
                },
            )
            return
        was_first = existing is None or existing.plan.name == 'free'
        from_plan = existing.plan if existing is not None else None
        if (existing is not None and sub_id
                and existing.stripe_subscription_id
                and existing.stripe_subscription_id != sub_id):
            superseded_sub_id = existing.stripe_subscription_id
        defaults = {
            'plan': plan,
            'stripe_subscription_id': sub_id,
            'is_active': True,
            'current_period_end': period_end,
            'cancel_at_period_end': cancel_at_end,
        }
        if event_created is not None:
            defaults['stripe_event_created'] = event_created
        UserSubscription.objects.update_or_create(
            user=user,
            defaults=defaults,
        )

    get_billing_service().invalidate_for_user(user)
    if superseded_sub_id:
        # Belt-and-braces against the double-subscription defect: the
        # checkout view refuses paid→paid Checkout (409 USE_PORTAL),
        # but if a second subscription slipped through anyway, cancel
        # the old one so the user isn't double-charged.
        _cancel_superseded_subscription(
            user=user, old_sub_id=superseded_sub_id, new_sub_id=sub_id,
        )
    _safe_email(
        'send_plan_change_email',
        send_plan_change_email,
        user,
        None if was_first else from_plan,
        plan,
    )


def _handle_subscription_updated(event: Any) -> None:
    """customer.subscription.updated — diff the relevant fields.

    Fields we react to:
      * status                   → 'unpaid'/'incomplete_expired' is the
                                   dunning terminal state: downgrade to
                                   free. 'past_due' stays a grace period
                                   (log only, no downgrade).
      * items.data[0].price.id   → plan change (+ session_window_start
                                   reset on downgrade)
      * cancel_at_period_end     → flip + send cancel email
                                   (or quiet revert)
    Dunning *emails* are intentionally NOT sent here; they are owned by
    ``_handle_invoice_payment_failed`` (sole trigger).
    """
    sub = _event_object(event)
    previous = _event_previous_attributes(event)

    customer_id = subscription_customer_id(sub)
    meta_user_id = subscription_metadata_user_id(sub)
    user = _resolve_user(customer_id=customer_id, meta_user_id=meta_user_id)
    if user is None:
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )

    sub_id = subscription_id(sub)
    period_end = subscription_current_period_end(sub)
    cancel_at_end = subscription_cancel_at_period_end(sub)
    price_id = subscription_price_id(sub)
    new_plan = _resolve_plan(plan_slug=None, price_id=price_id)
    sub_status = subscription_status(sub)
    event_created = _event_created(event)

    marker = (
        UserSubscription.objects
        .filter(user=user)
        .values_list('stripe_event_created', flat=True)
        .first()
    )
    if _is_stale_event(marker, event_created):
        logger.info(
            'stripe.webhook.stale_event_skipped',
            extra={
                'event_type': 'customer.subscription.updated',
                'user_id': str(user.id),
                'event_created_ts': event_created,
                'row_marker_ts': marker,
            },
        )
        return

    # Dunning terminal states: Stripe gave up collecting (Smart Retries
    # exhausted with 'cancel subscription' disabled, or the incomplete
    # window expired). Without this, the user keeps paid limits forever
    # while never paying. 'past_due' remains a grace period.
    if sub_status in ('unpaid', 'incomplete_expired'):
        logger.warning(
            'stripe.webhook.dunning_downgrade',
            extra={
                'user_id': str(user.id),
                'stripe_subscription_id': sub_id,
                'subscription_status': sub_status,
            },
        )
        _downgrade_to_free(
            user, period_end=period_end, event_created=event_created,
        )
        return
    if sub_status == 'past_due':
        logger.info(
            'stripe.webhook.dunning_grace',
            extra={
                'user_id': str(user.id),
                'stripe_subscription_id': sub_id,
                'subscription_status': sub_status,
            },
        )

    plan_changed = False
    is_downgrade = False
    cancel_just_set = False
    from_plan = None

    with transaction.atomic():
        row = UserSubscription.objects.select_for_update().filter(
            user=user,
        ).first()
        if row is None:
            if new_plan is None:
                raise RuntimeError(
                    f"No SubscriptionPlan for price_id={price_id!r}"
                )
            defaults = {
                'plan': new_plan,
                'stripe_subscription_id': sub_id,
                'is_active': True,
                'current_period_end': period_end,
                'cancel_at_period_end': cancel_at_end,
            }
            if event_created is not None:
                defaults['stripe_event_created'] = event_created
            UserSubscription.objects.update_or_create(
                user=user,
                defaults=defaults,
            )
            get_billing_service().invalidate_for_user(user)
            return

        if price_id is not None and new_plan is None:
            logger.warning(
                'stripe.webhook.updated_unknown_price',
                extra={
                    'price_id': price_id,
                    'user_id': str(user.id),
                    'stripe_subscription_id': sub_id,
                },
            )

        plan_changed = (
            new_plan is not None and new_plan.id != row.plan_id
        )
        is_downgrade = (
            new_plan is not None
            and plan_changed
            and new_plan.weekly_limit_usd < row.plan.weekly_limit_usd
        )
        prev_cancel = bool(previous.get('cancel_at_period_end',
                                        row.cancel_at_period_end))
        cancel_just_set = (cancel_at_end and not prev_cancel)

        if plan_changed and new_plan is not None:
            from_plan = row.plan
            row.plan = new_plan
        if sub_id:
            row.stripe_subscription_id = sub_id
        row.current_period_end = period_end
        row.cancel_at_period_end = cancel_at_end
        if is_downgrade:
            row.session_window_start = None
        update_fields = [
            'plan', 'stripe_subscription_id', 'current_period_end',
            'cancel_at_period_end', 'updated_at',
        ]
        if is_downgrade:
            update_fields.append('session_window_start')
        if event_created is not None:
            row.stripe_event_created = event_created
            update_fields.append('stripe_event_created')
        row.save(update_fields=update_fields)

    get_billing_service().invalidate_for_user(user)

    if plan_changed:
        _safe_email('send_plan_change_email',
                    send_plan_change_email, user, from_plan, new_plan)
    if cancel_just_set:
        _safe_email('send_subscription_canceled',
                    send_subscription_canceled, user,
                    period_end=_format_period_end(period_end))


def _handle_subscription_deleted(event: Any) -> None:
    """customer.subscription.deleted → downgrade to free + final cancel email."""
    sub = _event_object(event)
    customer_id = subscription_customer_id(sub)
    meta_user_id = subscription_metadata_user_id(sub)
    user = _resolve_user(customer_id=customer_id, meta_user_id=meta_user_id)
    if user is None:
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )

    period_end = subscription_current_period_end(sub)
    event_created = _event_created(event)

    marker = (
        UserSubscription.objects
        .filter(user=user)
        .values_list('stripe_event_created', flat=True)
        .first()
    )
    if _is_stale_event(marker, event_created):
        # A .deleted for an OLD subscription delivered after the user
        # already re-subscribed (newer .created applied) must not
        # downgrade the new subscription.
        logger.info(
            'stripe.webhook.stale_event_skipped',
            extra={
                'event_type': 'customer.subscription.deleted',
                'user_id': str(user.id),
                'event_created_ts': event_created,
                'row_marker_ts': marker,
            },
        )
        return

    _downgrade_to_free(
        user, period_end=period_end, event_created=event_created,
    )


def _handle_invoice_payment_succeeded(event: Any) -> None:
    """invoice.payment_succeeded → send receipt with VAT breakdown.

    Builds the rich invoice_data dict (task 14) consumed by
    notifications.send_subscription_receipt. Flat keys, no nested
    object — the receipt template gates the VAT row on a truthy
    ``tax_display`` so reverse-charge B2B invoices render cleanly.
    """
    invoice = _event_object(event)
    customer_id = _invoice_field(invoice, 'customer')
    user = _resolve_user(customer_id=customer_id, meta_user_id=None)
    if user is None:
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )

    currency = _invoice_field(invoice, 'currency', 'usd')
    amount_paid = _invoice_field(invoice, 'amount_paid')
    subtotal = _invoice_field(invoice, 'subtotal')
    tax = _invoice_field(invoice, 'tax') or 0
    period_start = _invoice_field(invoice, 'period_start')
    period_end = _invoice_field(invoice, 'period_end')

    status_transitions = _invoice_field(invoice, 'status_transitions') or {}
    if isinstance(status_transitions, dict):
        paid_at = status_transitions.get('paid_at')
    else:
        paid_at = getattr(status_transitions, 'paid_at', None)

    invoice_data = {
        'plan_name': _resolve_plan_name_from_invoice(invoice, user),
        'amount_display': _format_amount(amount_paid, currency),
        'subtotal_display': _format_minor_units(subtotal, currency),
        'tax_display': _format_minor_units(tax, currency),
        'tax_rate_display': _resolve_tax_rate_display(invoice),
        'period_start': _format_period_end(period_start) or '',
        'period_end': _format_period_end(period_end) or '',
        'date_paid_display': _format_unix_date(paid_at),
        'next_renewal_display': _format_period_end(period_end) or '',
        'invoice_number': (
            _invoice_field(invoice, 'number', '')
            or _invoice_field(invoice, 'id', '')
        ),
        'hosted_invoice_url':
            _invoice_field(invoice, 'hosted_invoice_url') or '',
        'invoice_pdf': _invoice_field(invoice, 'invoice_pdf') or '',
    }
    _safe_email('send_subscription_receipt',
                send_subscription_receipt, user, invoice_data)


def _handle_invoice_payment_failed(event: Any) -> None:
    """invoice.payment_failed → dunning email only (no row mutation).

    UserSubscription has no ``status`` field today, so the downgrade is
    deferred to the eventual ``customer.subscription.deleted`` after
    Stripe's Smart Retries window exhausts.
    """
    invoice = _event_object(event)
    customer_id = _invoice_field(invoice, 'customer')
    user = _resolve_user(customer_id=customer_id, meta_user_id=None)
    if user is None:
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )
    _safe_email('send_subscription_payment_failed',
                send_subscription_payment_failed, user)


def _handle_subscription_trial_will_end(event: Any) -> None:
    """customer.subscription.trial_will_end → 3-day reminder email."""
    sub = _event_object(event)
    customer_id = subscription_customer_id(sub)
    meta_user_id = subscription_metadata_user_id(sub)
    user = _resolve_user(customer_id=customer_id, meta_user_id=meta_user_id)
    if user is None:
        raise _IgnorableEvent(
            f"No user for stripe_customer_id={customer_id!r}"
        )
    trial_end = (sub.get('trial_end') if isinstance(sub, dict)
                 else getattr(sub, 'trial_end', None))
    _safe_email(
        'send_subscription_trial_ending',
        send_subscription_trial_ending, user,
        trial_end=_format_period_end(trial_end),
    )


EVENT_HANDLERS: dict[str, Callable[[Any], None]] = {
    'customer.subscription.created': _handle_subscription_created,
    'customer.subscription.updated': _handle_subscription_updated,
    'customer.subscription.deleted': _handle_subscription_deleted,
    'customer.subscription.trial_will_end': _handle_subscription_trial_will_end,
    'invoice.payment_succeeded': _handle_invoice_payment_succeeded,
    'invoice.payment_failed': _handle_invoice_payment_failed,
}


def dispatch(event: Any) -> str:
    """Dispatch a verified Stripe event to its handler.

    Returns ``'ok'`` on handler success, ``'skipped'`` if we don't
    handle this event type. Raises on handler exceptions (the view
    converts these to 500 → Stripe retries).
    """
    event_type = event['type'] if isinstance(event, dict) else event.type
    handler = EVENT_HANDLERS.get(event_type)
    if handler is None:
        logger.info(
            "stripe.webhook.event_type_skipped",
            extra={"event_type": event_type},
        )
        return 'skipped'
    handler(event)
    return 'ok'
