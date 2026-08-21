"""Shape-tolerant accessors for Stripe Session / Subscription objects.

Stripe SDK objects expose attributes via ``getattr``; dict-deserialized
events expose them via ``__getitem__``. These helpers paper over both
so handlers don't have to branch.
"""

from __future__ import annotations

from typing import Any, Optional


def session_field(session: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` off a Stripe ``Session`` (dict- or SDK-shaped)."""
    if isinstance(session, dict):
        return session.get(key, default)
    return getattr(session, key, default)


def subscription_metadata_user_id(subscription: Any) -> Optional[str]:
    """Pull ``metadata['user_id']`` off a stripe.Subscription."""
    if isinstance(subscription, dict):
        meta = subscription.get('metadata') or {}
    else:
        meta = getattr(subscription, 'metadata', None) or {}
    user_id = meta.get('user_id') if isinstance(meta, dict) else None
    return user_id or None


def subscription_metadata_plan_slug(subscription: Any) -> Optional[str]:
    """Pull ``metadata['plan_slug']`` off a stripe.Subscription.

    Set by Checkout (``subscription_data.metadata.plan_slug``); used by
    the ``customer.subscription.created`` handler as the primary plan
    lookup. Falls through to price-id lookup when missing.
    """
    if isinstance(subscription, dict):
        meta = subscription.get('metadata') or {}
    else:
        meta = getattr(subscription, 'metadata', None) or {}
    slug = meta.get('plan_slug') if isinstance(meta, dict) else None
    return slug or None


def subscription_price_id(subscription: Any) -> Optional[str]:
    """First line item's price id off a stripe.Subscription."""
    if isinstance(subscription, dict):
        items_root = subscription.get('items') or {}
        items = items_root.get('data') if isinstance(items_root, dict) else []
    else:
        items_root = getattr(subscription, 'items', None)
        items = getattr(items_root, 'data', None) if items_root is not None else None
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        price = first.get('price') or {}
        return price.get('id') if isinstance(price, dict) else None
    price = getattr(first, 'price', None)
    return getattr(price, 'id', None) if price is not None else None


def subscription_current_period_end(subscription: Any) -> Optional[int]:
    """``current_period_end`` unix seconds off a stripe.Subscription."""
    if isinstance(subscription, dict):
        return subscription.get('current_period_end')
    return getattr(subscription, 'current_period_end', None)


def subscription_cancel_at_period_end(subscription: Any) -> bool:
    """``cancel_at_period_end`` bool off a stripe.Subscription."""
    if isinstance(subscription, dict):
        return bool(subscription.get('cancel_at_period_end', False))
    return bool(getattr(subscription, 'cancel_at_period_end', False))


def subscription_id(subscription: Any) -> Optional[str]:
    """``id`` off a stripe.Subscription."""
    if isinstance(subscription, dict):
        return subscription.get('id')
    return getattr(subscription, 'id', None)


def subscription_status(subscription: Any) -> Optional[str]:
    """``status`` off a stripe.Subscription (active/past_due/canceled/etc)."""
    if isinstance(subscription, dict):
        return subscription.get('status')
    return getattr(subscription, 'status', None)


def subscription_customer_id(subscription: Any) -> Optional[str]:
    """``customer`` (string id) off a stripe.Subscription."""
    if isinstance(subscription, dict):
        return subscription.get('customer')
    return getattr(subscription, 'customer', None)
