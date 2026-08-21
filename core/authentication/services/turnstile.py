"""Cloudflare Turnstile token verification (task 19).

``verify_turnstile(token, ip)`` POSTs to
https://challenges.cloudflare.com/turnstile/v0/siteverify with the
token plus a server-side secret, and returns a boolean.

Dev/test bypass: when ``settings.DEBUG`` is True OR
``settings.TURNSTILE_SECRET_KEY`` is empty, the function returns True
without any network call. That keeps existing tests
(``test_user_registration`` etc.) passing without a token, and lets
dev signup work without Turnstile keys configured.

Production: ``settings.TURNSTILE_SECRET_KEY`` must be set
(``prod.py`` fail-loud). The frontend renders the widget when
``VITE_TURNSTILE_SITE_KEY`` is set; when it isn't (dev without keys),
the widget is not rendered and submit goes through without a token.

Fail-mode posture: ``signup_guard`` is fail-OPEN (Redis outage →
request passes), ``turnstile`` is fail-CLOSED (network flake → request
fails). Asymmetry is deliberate: a Cloudflare outage is rare; an
attacker DoS'ing our path to siteverify is exactly the threat captcha
defends against.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger("sterna.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SITEVERIFY_TIMEOUT_SECONDS = 5


def _is_dev_or_unconfigured() -> bool:
    """Bypass guard for local dev and unconfigured tests."""
    if getattr(settings, "DEBUG", False):
        return True
    secret = getattr(settings, "TURNSTILE_SECRET_KEY", "") or ""
    return not secret


def verify_turnstile(token: str, ip: str) -> bool:
    """Verify a Turnstile token. Returns True on success."""
    if _is_dev_or_unconfigured():
        return True
    if not token:
        return False

    secret = settings.TURNSTILE_SECRET_KEY
    payload = {"secret": secret, "response": token}
    if ip:
        payload["remoteip"] = ip

    try:
        resp = requests.post(
            SITEVERIFY_URL,
            data=payload,
            timeout=SITEVERIFY_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("turnstile.network_error", extra={"error": str(exc)})
        return False

    if resp.status_code != 200:
        logger.warning(
            "turnstile.bad_status", extra={"status": resp.status_code}
        )
        return False

    try:
        body = resp.json()
    except ValueError:
        logger.warning("turnstile.bad_json")
        return False

    success = bool(body.get("success"))
    if not success:
        logger.info(
            "turnstile.failed",
            extra={"error_codes": body.get("error-codes", [])},
        )
    return success
