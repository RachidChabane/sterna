"""Get-or-create a Stripe Customer object for a Sterna user (task 11).

This module is the only place stripe.api_key is set at import time;
other Stripe-touching modules (sync_stripe_prices, future webhook
handler) import this module first to ensure the SDK is configured.

Behavior contract:
  * If user.stripe_customer_id already set: return it (no API call).
  * If STRIPE_API_KEY unset (dev/test without explicit override):
    log and return None — no exception, no API call.
  * Else: stripe.Customer.create(email=..., metadata={'user_id': ...}),
    save id back to user, return it.
  * On stripe.RateLimitError: re-raise so the caller (Celery
    task) can retry with backoff.
  * On stripe.StripeError other subclasses: log + re-raise —
    Celery's autoretry handles transient API errors; permanent ones
    (auth failures) should page via Sentry, not silently succeed.
"""

from __future__ import annotations

import logging
from typing import Optional

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

# Configure the SDK once at import. settings.STRIPE_API_KEY may be ""
# in dev/test — that's fine, no API call is ever made when it's empty
# because of the _stripe_configured() guard below.
stripe.api_key = settings.STRIPE_API_KEY or None


def _stripe_configured() -> bool:
    """True iff the Stripe SDK has been given a real key."""
    return bool(settings.STRIPE_API_KEY)


def get_or_create_stripe_customer(user) -> Optional[str]:
    """Return the user's Stripe customer ID, creating it if needed.

    Args:
        user: A persisted authentication.User instance.

    Returns:
        The cus_… string, or None if Stripe is not configured for this
        environment (dev without keys; tests that don't patch).
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id

    if not _stripe_configured():
        logger.info(
            "stripe.customer.skipped_no_key",
            extra={"user_id": str(user.id)},
        )
        return None

    try:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
    except stripe.RateLimitError:
        logger.warning(
            "stripe.customer.rate_limited",
            extra={"user_id": str(user.id)},
        )
        raise
    except stripe.StripeError:
        logger.exception(
            "stripe.customer.create_failed",
            extra={"user_id": str(user.id)},
        )
        raise

    user.stripe_customer_id = customer.id
    user.save(update_fields=["stripe_customer_id", "updated_at"])
    logger.info(
        "stripe.customer.created",
        extra={"user_id": str(user.id), "stripe_customer_id": customer.id},
    )
    return customer.id
