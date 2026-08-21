"""Anonymize user_id -> repeatable token for BillingSummary.

CRITICAL: The pepper must NEVER rotate after the first BillingSummary
row is written. Rotation produces orphan rows under the old token and
new rows under a new token for the same user — breaks tax aggregation
and violates the 7-year retention contract. Treat the pepper as a
permanent constant in the secrets store.
"""

import hashlib
import hmac
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def anonymize_user_id(user_id) -> str:
    """HMAC-SHA256(user_id) with BILLING_ANONYMIZATION_PEPPER.

    Same user_id always yields same token; recovery requires the pepper.
    Raises ImproperlyConfigured if pepper is empty — refuses to silently
    fall back to a default that would corrupt the tax-aggregation
    invariant.
    """
    pepper = getattr(settings, "BILLING_ANONYMIZATION_PEPPER", None)
    if not pepper:
        raise ImproperlyConfigured(
            "BILLING_ANONYMIZATION_PEPPER must be set; it is a permanent "
            "secret and rotating it breaks tax-data aggregation."
        )
    if isinstance(user_id, uuid.UUID):
        user_id = str(user_id)
    return hmac.new(
        pepper.encode("utf-8"),
        str(user_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
