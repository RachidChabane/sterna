"""Post-deploy smoke checks (task 28). Run after `kubectl rollout
status` succeeds. Each check is independent and times out fast.

No data-export check: the endpoint (/api/auth/account/data-export/)
requires an authenticated user - see core/smoke/README.md
"Why no data-export check".
"""
import hashlib
import hmac
import json
import os
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.smoke


# --- Module-scoped wall-time tracker for the budget check below ---
_SESSION_START = time.monotonic()


def _unauthed_client(base_url: str, timeout: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout)


def test_livez_returns_200(base_url, http_timeout):
    with _unauthed_client(base_url, http_timeout) as c:
        r = c.head("/livez")
    assert r.status_code == 200, f"{base_url}/livez → {r.status_code}"


def test_readyz_returns_200(base_url, http_timeout):
    """503 here means the deployment is not ready — that's a smoke
    failure, not a skip."""
    with _unauthed_client(base_url, http_timeout) as c:
        r = c.head("/readyz")
    assert r.status_code == 200, f"{base_url}/readyz → {r.status_code}"


def test_api_health_returns_200(base_url, http_timeout):
    with _unauthed_client(base_url, http_timeout) as c:
        r = c.get("/api/health/")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "healthy", body


def test_authed_user_can_send_chat_message(authed_client):
    """Storage write contract: create conversation + chat + 1 user
    message. No LLM round-trip; we test that the message persists."""
    name = f"smoke-{uuid.uuid4().hex[:8]}"
    r = authed_client.post(
        "/api/conversations/",
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.text
    conv_id = r.json()["id"]

    try:
        r = authed_client.post(
            f"/api/conversations/{conv_id}/chats/",
            json={},
        )
        assert r.status_code in (200, 201), r.text
        chat_id = r.json()["id"]

        r = authed_client.post(
            f"/api/conversations/{conv_id}/chats/{chat_id}/messages/",
            json={"role": "user", "content": "smoke test ping"},
        )
        assert r.status_code in (200, 201), r.text
        assert r.json().get("id")
    finally:
        # Best-effort teardown — if it fails the smoke user accumulates
        # rows, which is acceptable.
        try:
            authed_client.delete(f"/api/conversations/{conv_id}/")
        except Exception:
            pass


def test_stripe_webhook_accepts_signed_event(base_url, http_timeout):
    """Gated on SMOKE_STRIPE_WEBHOOK_SECRET. Signs a webhook event
    Stripe-style and POSTs it. The dispatcher logs+200s for an
    unknown customer ID — no prod billing state is mutated."""
    secret = os.environ.get("SMOKE_STRIPE_WEBHOOK_SECRET")
    if not secret:
        pytest.skip("SMOKE_STRIPE_WEBHOOK_SECRET not set")

    payload = {
        "id": f"evt_smoke_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": f"sub_smoke_{uuid.uuid4().hex[:12]}",
                "customer": f"cus_smoke_{uuid.uuid4().hex[:12]}",
                "status": "active",
            }
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    header = f"t={timestamp},v1={signature}"

    with _unauthed_client(base_url, http_timeout) as c:
        r = c.post(
            "/api/billing/webhook/",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": header,
            },
        )
    # 200 = dispatcher logged unknown customer and no-op'd. 400 would
    # indicate a signature mismatch (bad secret). 5xx = server bug.
    assert r.status_code == 200, f"webhook → {r.status_code}: {r.text}"


def test_smoke_suite_within_overall_budget():
    """Run-last sanity check: the suite must finish within
    SMOKE_OVERALL_TIMEOUT_S. If it does not, a future change has
    slowed smoke down dangerously."""
    budget = float(os.environ.get("SMOKE_OVERALL_TIMEOUT_S", "120"))
    elapsed = time.monotonic() - _SESSION_START
    assert elapsed < budget, (
        f"Smoke suite took {elapsed:.1f}s, over budget {budget}s"
    )
