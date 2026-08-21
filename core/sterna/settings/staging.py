"""Staging settings. Inherits from prod.

Kept as a thin alias so that staging can diverge from prod in the
future (e.g. tighter rate limits, different sandbox quotas) without
a settings-module rename. Staging Kustomize overlay currently points
at `sterna.settings.prod`; switching it to `sterna.settings.staging`
is a separate task.
"""

from django.core.exceptions import ImproperlyConfigured

from .prod import *  # noqa: F401, F403

# Preventive guard: staging must run on Stripe TEST keys. A live key
# here would bill real cards from a non-prod environment. prod.py has
# already required STRIPE_API_KEY from env at this point.
if STRIPE_API_KEY.startswith("sk_live_"):
    raise ImproperlyConfigured(
        "STRIPE_API_KEY is a LIVE key (sk_live_…) but settings.staging "
        "is loaded. Use a test key (sk_test_…) in staging."
    )
