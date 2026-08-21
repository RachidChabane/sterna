"""Tests for /livez and /readyz root-level URL aliases (task 28)."""
import json

import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def client():
    return Client()


def test_livez_head_returns_200(client):
    response = client.head("/livez")
    assert response.status_code == 200


def test_readyz_head_returns_200_or_503(client):
    """Readiness depends on DB+cache+redis fixtures; accept either —
    we're asserting the URL exists, not that deps are up at unit-test time."""
    response = client.head("/readyz")
    assert response.status_code in (200, 503)


def test_livez_get_returns_alive_json(client):
    response = client.get("/livez")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload.get("status") == "alive"


def test_livez_reverse_resolves_to_root_path():
    """Guard against accidentally moving the alias under /api/."""
    assert reverse("livez") == "/livez"
    assert reverse("readyz") == "/readyz"
