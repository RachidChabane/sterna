"""Shared fixtures for consigliere test modules.

Mirrors the ``auth_as`` pattern from ``usage_quota/tests/conftest.py``
and ``authentication/tests/conftest.py``: the project uses a custom
``JWTManager`` whose payload carries ``type: access`` —
``rest_framework_simplejwt`` tokens would be rejected by
``authentication.authentication.JWTAuthentication``.
"""

from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from authentication.jwt_utils import JWTManager
from authentication.models import User
from llm.models import ModelCatalog


@pytest.fixture(autouse=True)
def _clear_pricing_cache():
    """CatalogService caches model pricing by model_id (LocMemCache is
    process-global). Without this, a price cached by an unrelated test
    module using the same model_id (e.g. "anthropic/claude-3-haiku")
    would leak into these tests and make cost assertions flaky
    depending on test run order.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_as():
    """Factory: attach a JWT for ``user`` to ``client``."""

    def _auth(client, user):
        access_token = JWTManager.create_access_token(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client

    return _auth


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="consigliere-user@example.com",
        password="Sup3r-secret!",
        is_verified=True,
    )


@pytest.fixture
def other_verified_user(db):
    return User.objects.create_user(
        email="consigliere-other@example.com",
        password="0ther-secret!",
        is_verified=True,
    )


@pytest.fixture
def haiku_model(db):
    """A cheap, fast model — used as the "current" model in most fixtures."""
    return ModelCatalog.objects.create(
        model_id="anthropic/claude-3-haiku",
        name="Claude 3 Haiku",
        provider="anthropic",
        prompt_price=Decimal("0.00025"),
        completion_price=Decimal("0.00125"),
        max_tokens=200000,
        is_available=True,
    )


@pytest.fixture
def opus_model(db):
    """A premium, expensive model."""
    return ModelCatalog.objects.create(
        model_id="anthropic/claude-3-opus",
        name="Claude 3 Opus",
        provider="anthropic",
        prompt_price=Decimal("0.015"),
        completion_price=Decimal("0.075"),
        max_tokens=200000,
        is_available=True,
    )


@pytest.fixture
def budget_model(db):
    """A cheap, budget-tier model."""
    return ModelCatalog.objects.create(
        model_id="mistralai/mistral-7b",
        name="Mistral 7B",
        provider="mistralai",
        prompt_price=Decimal("0.00007"),
        completion_price=Decimal("0.00007"),
        max_tokens=32000,
        is_available=True,
    )


@pytest.fixture
def unavailable_model(db):
    """A catalog entry that must never be recommended."""
    return ModelCatalog.objects.create(
        model_id="vendor/unlisted-model",
        name="Unlisted Model",
        provider="vendor",
        prompt_price=Decimal("0.001"),
        completion_price=Decimal("0.002"),
        max_tokens=8000,
        is_available=False,
    )


def make_chat_group(
    model_id="anthropic/claude-3-haiku",
    model_name="Claude 3 Haiku",
    chat_id="chat-1",
    group_id="cg-1",
    messages=None,
):
    """Build a minimal ChatGroup payload, matching the frontend's shape."""
    if messages is None:
        messages = [
            {"role": "user", "content": "Help me debug this Python function, it raises a TypeError"},
            {
                "role": "assistant",
                "content": "Let's look at the traceback and the function signature.",
                "model_id": model_id,
                "tokens": {"prompt": 120, "completion": 80},
                "cost": 0.004,
                "latency": 1500,
            },
        ]
    return {
        "id": group_id,
        "chats": [
            {
                "id": chat_id,
                "model": {"model_id": model_id, "name": model_name},
                "messages": messages,
            }
        ],
    }


@pytest.fixture
def chat_group_data():
    return make_chat_group()


def valid_ai_analysis_payload(model_id="anthropic/claude-3-haiku", model_name="Claude 3 Haiku", provider="anthropic"):
    """A well-formed AI response payload matching ``_parse_ai_response``'s contract."""
    return {
        "conversation_type": "technical_discussion",
        "detected_needs": {
            "creativity": "low",
            "precision": "high",
            "speed": "medium",
            "cost_efficiency": "medium",
        },
        "insights": [
            "User focused on technical problem-solving with code examples",
            "Precision was prioritized over creative solutions",
        ],
        "recommended_from_conversation": {
            "model_id": model_id,
            "model_name": model_name,
            "provider": provider,
            "reasoning": "This model gave accurate, concise answers throughout.",
            "score": 0.92,
            "metrics": {
                "total_messages": 1,
                "avg_cost": 0.004,
                "avg_latency": 1.5,
            },
        },
        "alternative_models": [
            {
                "model_id": "openai/gpt-4o",
                "model_name": "GPT-4o",
                "provider": "openai",
                "rank": 1,
                "score": 0.88,
                "reasoning": "Similar precision with faster responses.",
                "tradeoffs": {
                    "cost_savings": "+15%",
                    "quality_delta": "-5%",
                    "speed_delta": "+35%",
                },
                "estimated_cost_per_message": 0.0025,
            }
        ],
    }
