"""Stripe Checkout + Customer Portal session helpers (task 12).

Thin wrappers around the three Stripe entry points the views need,
with consistent logging and a single import surface for patching in
tests (``stripe.checkout.Session.create`` is patched at
``usage_quota.billing.stripe_checkout.stripe.checkout.Session.create``).

Importing ``services.stripe_customer`` ensures ``stripe.api_key`` is
configured at module load — that module is the canonical place where
the SDK is initialised.
"""

from __future__ import annotations

import logging

import stripe
from django.utils import timezone

# Side-effect: configures stripe.api_key from settings.STRIPE_API_KEY.
from usage_quota.services.stripe_customer import _stripe_configured  # noqa: F401

logger = logging.getLogger(__name__)


def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    user_id: str,
    plan_slug: str,
    billing_cycle: str,
) -> stripe.checkout.Session:
    """Create a Stripe Checkout Session in subscription mode.

    Idempotency: a per-second key prevents duplicate charges on a network
    retry of the same POST. A user double-clicking is two separate POSTs
    (each with their own key) — Stripe permits two open sessions; the
    first auto-expires in 24h. ``billing_cycle`` is in the key so a user
    toggling Monthly↔Yearly within the same wall-second on the same plan
    gets two distinct sessions instead of being collapsed.
    """
    return stripe.checkout.Session.create(
        mode='subscription',
        customer=customer_id,
        line_items=[{'price': price_id, 'quantity': 1}],
        automatic_tax={'enabled': True},
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
        subscription_data={
            'metadata': {
                'user_id': user_id,
                'plan_slug': plan_slug,
                'billing_cycle': billing_cycle,
            },
        },
        idempotency_key=(
            f"checkout:{user_id}:{plan_slug}:{billing_cycle}:"
            f"{int(timezone.now().timestamp())}"
        ),
    )


def create_portal_session(
    *, customer_id: str, return_url: str,
) -> stripe.billing_portal.Session:
    """Create a Stripe Customer Portal session for an existing customer."""
    return stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )


def retrieve_checkout_session(session_id: str) -> stripe.checkout.Session:
    """Retrieve a Checkout Session with the subscription + price expanded.

    The expand list lets one call return both the subscription id and
    the price id (needed for plan-from-price lookup in
    ``sync_from_session``) without a second roundtrip.
    """
    return stripe.checkout.Session.retrieve(
        session_id,
        expand=['subscription', 'subscription.items.data.price'],
    )
