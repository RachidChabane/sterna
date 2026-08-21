"""Shared Sentry SDK initializer.

All services call init_sentry(service=...) at startup. Init is a
no-op if SENTRY_DSN is unset, so dev/test never connect.
"""

import os
from typing import Iterable, Optional

import sentry_sdk
from sentry_sdk.integrations import Integration


def init_sentry(
    service: str,
    *,
    extra_integrations: Optional[Iterable[Integration]] = None,
    traces_sample_rate: Optional[float] = None,
) -> None:
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return

    env = os.environ.get("ENVIRONMENT", "development")
    sample = traces_sample_rate
    if sample is None:
        sample = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        integrations=list(extra_integrations or []),
        traces_sample_rate=sample,
        send_default_pii=False,
        release=os.environ.get("RELEASE_SHA") or None,
    )
    sentry_sdk.set_tag("service", service)
