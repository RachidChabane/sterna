# Sterna API Gateway

FastAPI reverse proxy that sits in front of Sterna's backend microservices
(`web`, `orchestrator`, `user-preferences`, `brave-search`, `google-maps`,
...). It is the single entry point the frontend talks to: everything under
`/api/*` and `/api/v1/*` is authenticated, rate-limited, and routed to the
right backend by this service.

## What it does

- **JWT-authenticated routing** — `gateway/middleware/auth.py` validates the
  bearer token on every HTTP request except the explicit `public_paths`
  allow-list in `gateway/config.py` (login/register/OAuth callbacks, health
  checks, etc.), then `gateway/routing/proxy.py` forwards the request to the
  backend service mapped in `Settings.routes`, rewriting the path prefix per
  `Settings.route_rewrites`. The sandbox WebSocket route
  (`/api/v1/sandbox/ws/{path}` in `gateway/main.py`) is routed but *not*
  authenticated at the gateway layer — it accepts the upgrade and forwards
  the raw query string to the orchestrator, which validates the JWT passed
  as a query param itself (browsers can't set headers on a WS handshake).
- **Rate limiting** — `gateway/rate_limiting/redis_limiter.py`, backed by
  Redis. The middleware is only mounted (on the app's startup hook) if the
  Redis connection succeeds; if Redis is unavailable at startup, it is never
  mounted, so the gateway fails open (requests pass through unlimited)
  rather than refusing to serve traffic.
- **Fail-closed startup** — `gateway/config.py`'s `Settings` validators run at
  boot, before the app accepts traffic, and raise if either check fails:
  - `jwt_secret_key` must not be empty, the placeholder
    `"change-me-in-production"`, or a `django-insecure*` dev key, unless
    `GATEWAY_ALLOW_INSECURE_JWT_SECRET=true` **and**
    `GATEWAY_ENVIRONMENT=development` — the bypass is inert everywhere else,
    so a stray flag left in a staging/production config can't reopen the
    hole.
  - if `cors_allow_credentials` is true (the default), `cors_origins` must be
    a non-empty, non-wildcard list — credentialed requests can never be
    paired with `*`, so an environment that forgets to set
    `GATEWAY_CORS_ORIGINS` fails loud at boot instead of silently allowing
    (or silently rejecting) every origin.
- **CORS policy** — origins come only from `GATEWAY_CORS_ORIGINS` (a JSON
  array, e.g. `'["https://app.example.com"]'`); there is no built-in default
  origin list, by design (see fail-closed startup above).

## Configuration

All settings are environment variables prefixed `GATEWAY_` (see
`gateway/config.py` for the full list and defaults), e.g.:

```bash
GATEWAY_JWT_SECRET_KEY=<real-secret>
GATEWAY_CORS_ORIGINS='["https://app.example.com"]'
GATEWAY_REDIS_URL=redis://redis:6379/0
GATEWAY_ENVIRONMENT=production
```

## Running the tests

`Settings` validates at import time (see fail-closed startup above), so a
placeholder-free `GATEWAY_JWT_SECRET_KEY` and an explicit
`GATEWAY_CORS_ORIGINS` must be set before the test suite can even import
`gateway.main` — most individual tests then override `Settings` via the
`settings` fixture in `tests/conftest.py`, but these two still have to be
valid at collection time:

```bash
cd core/api-gateway
pip install -r requirements.txt
GATEWAY_JWT_SECRET_KEY=ci-test-secret-key-not-for-prod \
GATEWAY_CORS_ORIGINS='["http://localhost:5173"]' \
pytest
```

(Same values CI uses in `.github/workflows/ci.yml`.) `pyproject.toml` also
declares a `[project.optional-dependencies] dev` extra (`pip install -e
".[dev]"`) with the same test/lint/type-check tooling.
