"""Smoke-suite conftest (task 28).

Self-contained: the `smoke` marker is registered here via
`pytest_configure` so the file works whether `core/pytest.ini` is
loaded (in-pod) or skipped via `pytest -c /dev/null` (runner-side,
where pytest-django is not installed and `--reuse-db` would crash
pytest at startup).
"""
import os

import pytest

SMOKE_BASE_URL = os.environ.get("SMOKE_BASE_URL")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "smoke: deploy-time smoke tests (require SMOKE_BASE_URL)",
    )


if not SMOKE_BASE_URL:
    pytest.skip(
        "SMOKE_BASE_URL not set; smoke tests are deploy-time only.",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def base_url():
    return SMOKE_BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def http_timeout():
    return float(os.environ.get("SMOKE_HTTP_TIMEOUT_S", "10"))


@pytest.fixture(scope="session")
def smoke_user_credentials():
    email = os.environ.get(
        "SMOKE_TEST_USER_EMAIL", "smoke@sterna-internal.test"
    )
    pw = os.environ.get("SMOKE_TEST_USER_PASSWORD")
    if not pw:
        pytest.skip("SMOKE_TEST_USER_PASSWORD not set")
    return email, pw


@pytest.fixture(scope="session")
def authed_client(base_url, smoke_user_credentials, http_timeout):
    import httpx

    email, pw = smoke_user_credentials
    with httpx.Client(base_url=base_url, timeout=http_timeout) as c:
        r = c.post(
            "/api/auth/login/",
            json={"email": email, "password": pw},
        )
        r.raise_for_status()
        # LoginView returns {access_token, refresh_token, token_type,
        # expires_in, user}; see core/authentication/jwt_utils.py.
        access = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {access}"
        yield c
