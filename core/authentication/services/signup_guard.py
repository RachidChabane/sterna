"""Per-IP signup velocity guard (task 19).

Uses fixed-window counters with rolling TTL (each window's start is
anchored to the first request that opens it; the counter resets to
zero once the TTL elapses) via Django's cache framework. This is NOT a
true sliding window — see `_bump` below for why the looser semantics
are intentional.

Coexistence with task 18 rate limiting (see plan §0.2):

- Task 18's ``@apply_ratelimit(key='ip', rate='5/h')`` fires on the
  decorator chain. The 6th attempt within 1h is blocked with
  ``429 RATE_LIMITED`` before the view body ever runs.
- Task 19's ``check_ip_velocity`` ALSO checks 5/h (same window) plus
  20/24h (the additional ceiling task 18 doesn't enforce). It runs at
  the top of ``RegisterView.post``, after the decorator chain has
  allowed the request through. Result:

  * 1h breach: caught by task 18 → 429.
  * 24h breach (under the 1h ceiling): caught by task 19 → 403.

Counters are bumped on every POST to ``/api/auth/register/``,
regardless of whether the underlying signup succeeds, so an attacker
cannot cycle through validation failures without ever filling the
budget. Key namespace ``signup_guard:ip:*`` is disjoint from task 18's
``sterna:rl:*`` — the buckets do not share state.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

from exceptions import emit_suspicious_activity

logger = logging.getLogger("sterna.signup_guard")


SIGNUP_IP_LIMIT_1H = 5
SIGNUP_IP_LIMIT_24H = 20
SIGNUP_IP_TTL_1H = 3600
SIGNUP_IP_TTL_24H = 86_400


class BlockReason(enum.Enum):
    IP_VELOCITY = "ip_velocity"


@dataclass(frozen=True)
class Block:
    """Returned by ``check_ip_velocity`` when the IP is over budget."""

    reason: BlockReason
    count_1h: int
    count_24h: int


def _key(ip: str, window: str) -> str:
    return f"signup_guard:ip:{ip}:{window}"


def _bump(ip: str, window: str, ttl: int) -> int:
    """Increment-with-TTL. Returns the new count. Fail-open on cache error.

    ``cache.add`` is idempotent on first write (returns True, sets the
    TTL). On subsequent calls within the TTL it returns False and does
    NOT touch the TTL. ``cache.incr`` then bumps the value without
    resetting the window — that's the rolling-TTL property documented
    in the module docstring.
    """
    key = _key(ip, window)
    try:
        if cache.add(key, 1, timeout=ttl):
            return 1
        return cache.incr(key)
    except Exception as exc:  # noqa: BLE001 — fail-open on Redis blip
        logger.warning(
            "signup_guard.cache_error",
            extra={"ip": ip, "window": window, "error": str(exc)},
        )
        return 0


def record_signup_attempt(ip: str) -> tuple[int, int]:
    """Bump both windows. Returns ``(count_1h, count_24h)``."""
    if not ip:
        return (0, 0)
    return (
        _bump(ip, "1h", SIGNUP_IP_TTL_1H),
        _bump(ip, "24h", SIGNUP_IP_TTL_24H),
    )


def check_ip_velocity(ip: str, *, request=None) -> Optional[Block]:
    """Inspect-and-bump the IP velocity counters.

    Call ONCE per ``/api/auth/register/`` POST at the top of the view,
    BEFORE serializer validation. The bump is part of this call — do
    not bump separately.

    Returns ``Block(...)`` when the IP is over budget; the caller
    translates that into a 403 response.
    """
    if not ip:
        return None
    count_1h, count_24h = record_signup_attempt(ip)

    over_1h = count_1h > SIGNUP_IP_LIMIT_1H
    over_24h = count_24h > SIGNUP_IP_LIMIT_24H

    if over_1h or over_24h:
        emit_suspicious_activity(
            category="signup_abuse",
            reason=BlockReason.IP_VELOCITY.value,
            request=request,
            actor=f"ip:{ip}",
            count_1h=count_1h,
            count_24h=count_24h,
        )
        return Block(
            reason=BlockReason.IP_VELOCITY,
            count_1h=count_1h,
            count_24h=count_24h,
        )
    return None
