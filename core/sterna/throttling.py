"""CF-aware DRF throttle subclasses.

Task-29 H1: DRF's stock ``AnonRateThrottle`` / ``UserRateThrottle``
call ``self.get_ident(request)`` which reads ``request.META['REMOTE_ADDR']``
directly. In our topology that means the per-IP throttle key is
``REMOTE_ADDR`` (the gateway pod IP), not the true client IP.

These subclasses override ``get_ident`` to use
``sterna.client_ip.get_client_ip`` so the throttle key is CF-aware
when CF-Connecting-IP is present.

The ``DEFAULT_THROTTLE_CLASSES`` setting wires the subclasses into the
default throttle stack so app code does not need to opt in per-view.
"""
from __future__ import annotations

from rest_framework.throttling import (
    AnonRateThrottle as DRFAnonRateThrottle,
    UserRateThrottle as DRFUserRateThrottle,
)

from sterna.client_ip import get_client_ip


class AnonRateThrottle(DRFAnonRateThrottle):
    def get_ident(self, request):
        return get_client_ip(request) or super().get_ident(request)


class UserRateThrottle(DRFUserRateThrottle):
    def get_ident(self, request):
        return get_client_ip(request) or super().get_ident(request)
