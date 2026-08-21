"""Tests for ConsiglierChatHandler — Consigliere chat responses.

The OpenRouter network call is always mocked; cost estimation is
exercised against a real ``ModelCatalog`` row so the numbers are
deterministic.
"""

from unittest.mock import MagicMock, patch

import pytest

from consigliere.services.chat_handler import ConsiglierChatHandler

pytestmark = pytest.mark.django_db


@pytest.fixture
def mocked_client():
    with patch("consigliere.services.chat_handler.OpenRouterClient") as client_cls:
        instance = MagicMock()
        client_cls.return_value = instance
        yield instance


def test_chat_returns_content_usage_and_cost_matching_catalog_pricing(mocked_client, haiku_model):
    mocked_client.complete.return_value = {
        "content": "Use Claude 3 Haiku for cheap, fast responses.",
        "model": haiku_model.model_id,
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
    }

    handler = ConsiglierChatHandler(current_model=haiku_model.model_id)
    response = handler.chat(
        messages=[{"role": "user", "content": "What model should I use?"}],
        context="Some analysis context",
    )

    assert response["content"] == "Use Claude 3 Haiku for cheap, fast responses."
    assert response["model_used"] == haiku_model.model_id
    assert response["tokens_used"] == 2000
    assert response["prompt_tokens"] == 1000
    assert response["completion_tokens"] == 1000
    assert response["prompt_cost"] + response["completion_cost"] == response["cost"]
    assert response["latency"] >= 0
    # 1000 prompt tokens @ $0.00025/1K + 1000 completion @ $0.00125/1K (haiku_model pricing).
    assert float(response["prompt_cost"]) == pytest.approx(0.00025, abs=1e-8)
    assert float(response["completion_cost"]) == pytest.approx(0.00125, abs=1e-8)


def test_chat_injects_system_prompt_with_context(mocked_client, haiku_model):
    mocked_client.complete.return_value = {
        "content": "ok",
        "model": haiku_model.model_id,
        "usage": {},
    }

    handler = ConsiglierChatHandler(current_model=haiku_model.model_id)
    handler.chat(
        messages=[{"role": "user", "content": "Hi"}],
        context="UNIQUE_MARKER_CONTEXT",
    )

    call_kwargs = mocked_client.complete.call_args.kwargs
    system_message = call_kwargs["messages"][0]
    assert system_message["role"] == "system"
    assert "UNIQUE_MARKER_CONTEXT" in system_message["content"]
    # User message is forwarded after the system prompt.
    assert call_kwargs["messages"][1] == {"role": "user", "content": "Hi"}


def test_chat_falls_back_to_estimate_when_model_unpriced(mocked_client):
    """Model absent from the catalog must not raise — cost falls back to a rough estimate."""
    mocked_client.complete.return_value = {
        "content": "answer",
        "model": "vendor/unknown-model",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
    }

    handler = ConsiglierChatHandler(current_model="vendor/unknown-model")
    response = handler.chat(
        messages=[{"role": "user", "content": "Hi"}], context="ctx"
    )

    assert response["cost"] > 0


def test_chat_stream_accumulates_content_and_yields_done_event(mocked_client, haiku_model):
    mocked_client.complete_stream.return_value = iter(
        [
            {"event": "content", "data": {"content": "Hel"}},
            {"event": "content", "data": {"content": "lo"}},
            {
                "event": "done",
                "data": {
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model": haiku_model.model_id,
                },
            },
        ]
    )

    handler = ConsiglierChatHandler(current_model=haiku_model.model_id)
    events = list(
        handler.chat_stream(messages=[{"role": "user", "content": "Hi"}], context="ctx")
    )

    content_events = [e for e in events if e["event"] == "content"]
    done_events = [e for e in events if e["event"] == "done"]

    assert [e["data"]["content"] for e in content_events] == ["Hel", "lo"]
    assert len(done_events) == 1
    assert done_events[0]["data"]["content"] == "Hello"
    assert done_events[0]["data"]["cost"] >= 0
    assert "latency" in done_events[0]["data"]


def test_chat_propagates_openrouter_exception(mocked_client, haiku_model):
    from llm.exceptions import OpenRouterException

    mocked_client.complete.side_effect = OpenRouterException("provider is down")

    handler = ConsiglierChatHandler(current_model=haiku_model.model_id)

    with pytest.raises(OpenRouterException):
        handler.chat(messages=[{"role": "user", "content": "Hi"}], context="ctx")
