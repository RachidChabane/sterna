# Sterna smoke suite

## What this is

A small, deterministic pytest module that asserts the deployed product
serves traffic. It runs against any URL — staging, production, a
local dev server, an in-cluster service. It is invoked by the deploy
workflows immediately after `kubectl rollout status` succeeds, and is
the gate that flips `deploy-production.yml` into rollback mode if it
fails.

Smoke checks are NOT a substitute for unit/integration tests; they
just confirm the rollout is alive. Each check is independent, gets
its own `httpx.Client`, and times out fast (default 10s per request,
120s total).

## How to run locally

```bash
cd core
pip install pytest==8.3.4 httpx==0.28.1
export SMOKE_BASE_URL=http://localhost:8000
export SMOKE_TEST_USER_PASSWORD=...   # 16+ chars
pytest -c /dev/null smoke/ -v --tb=short
```

`-c /dev/null` bypasses `core/pytest.ini`'s `--reuse-db` (a
pytest-django option). If you are running inside the production web
container, pytest-django is present, so a vanilla `pytest smoke/ -v`
works.

## How to run in CI

The deploy workflows invoke this twice per deploy:

1. **In-cluster** — `kubectl exec` into the web pod, hits the
   in-cluster service URL. Catches deployment-internal regressions.
2. **Public URL** — runner-side, hits the Cloudflare-Tunnel-exposed
   URL. Catches DNS / tunnel issues.

Both pick up `SMOKE_TEST_USER_PASSWORD` + `SMOKE_STRIPE_WEBHOOK_SECRET`
from secrets (the pod inherits them via the `smoke-secrets`
ExternalSecret; the runner picks them up from GitHub Actions secrets).

## Env contract

| Var | Required? | Purpose |
|---|---|---|
| `SMOKE_BASE_URL` | required | e.g. `https://staging.example.com` |
| `SMOKE_TEST_USER_EMAIL` | optional (default `smoke@sterna-internal.test`) | login email |
| `SMOKE_TEST_USER_PASSWORD` | required | login password (16+ chars) |
| `SMOKE_STRIPE_WEBHOOK_SECRET` | optional | enables Stripe webhook check |
| `SMOKE_HTTP_TIMEOUT_S` | optional (default `10`) | per-request timeout |
| `SMOKE_OVERALL_TIMEOUT_S` | optional (default `120`) | suite wall-time cap |

Missing **required** env → module-level skip. Missing **optional**
env → only the gated check skips. So an early-bringup smoke against
a cluster without Stripe-webhook secrets still runs the basics.

## What checks run

- `test_livez_returns_200` — `HEAD /livez` returns 200.
- `test_readyz_returns_200` — `HEAD /readyz` returns 200 (503 is a
  fail; the deploy is not ready).
- `test_api_health_returns_200` — `GET /api/health/` JSON body has
  `status: healthy`.
- `test_authed_user_can_send_chat_message` — login as the smoke user,
  POST a conversation + chat + text message. Asserts the storage
  write path works end-to-end (no LLM round-trip).
- `test_stripe_webhook_accepts_signed_event` — gated by
  `SMOKE_STRIPE_WEBHOOK_SECRET`. Signs a `customer.subscription.updated`
  event for a non-existent customer; the dispatcher 200s on unknown
  customer.
- `test_smoke_suite_within_overall_budget` — asserts wall-time
  under `SMOKE_OVERALL_TIMEOUT_S`.

## Why no data-export check

The GDPR export endpoint now ships at `/api/auth/account/data-export/`
(`core/authentication/urls.py`), but it requires an authenticated
user and produces an async export job — not a good fit for an
unauthenticated fast smoke probe. Covered by unit tests
(`core/authentication/tests/test_gdpr_export.py`) instead.

## Used by

Run this harness as an automated pre-deploy gate against the
production URL before any manual end-to-end verification.
