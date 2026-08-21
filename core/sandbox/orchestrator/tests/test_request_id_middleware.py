"""Tests for the shared RequestIDMiddleware in _observability.py.

Requires fastapi/starlette (installed in the orchestrator CI job and
in the service image); skipped in environments without them.
"""

import os
import sys

import pytest

fastapi = pytest.importorskip("fastapi")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _observability import RequestIDMiddleware, current_request_id  # noqa: E402


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/probe")
    async def probe():
        # What the log filters see mid-request.
        return {"contextvar": current_request_id.get()}

    return TestClient(app)


class TestRequestIDMiddleware:
    def test_inbound_header_preserved_and_echoed(self, client):
        rid = "cafef00d-cafe-cafe-cafe-cafef00dcafe"
        resp = client.get("/probe", headers={"X-Request-ID": rid})
        assert resp.status_code == 200
        # ContextVar visible to log filters during the request:
        assert resp.json()["contextvar"] == rid
        # Mirrored on the response for the caller:
        assert resp.headers["X-Request-ID"] == rid

    def test_request_id_minted_when_absent(self, client):
        import uuid

        resp = client.get("/probe")
        assert resp.status_code == 200
        minted = resp.headers["X-Request-ID"]
        uuid.UUID(minted)  # valid UUIDv4
        assert resp.json()["contextvar"] == minted

    def test_contextvar_reset_after_request(self, client):
        client.get("/probe", headers={"X-Request-ID": "rid-leak-check"})
        assert current_request_id.get() is None
