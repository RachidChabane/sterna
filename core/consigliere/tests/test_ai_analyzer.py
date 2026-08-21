"""Tests for AIAnalyzer — LLM-backed conversation analysis.

The OpenRouter network call is always mocked: these tests assert that,
given a deterministic mocked LLM response, the analyzer produces the
expected recommendation structure (and rejects malformed responses).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from consigliere.services.ai_analyzer import AIAnalyzer
from consigliere.tests.conftest import make_chat_group, valid_ai_analysis_payload

pytestmark = pytest.mark.django_db


def _mock_complete_response(payload: dict, model="anthropic/claude-3-haiku") -> dict:
    return {
        "content": json.dumps(payload),
        "model": model,
        "usage": {"total_tokens": 500, "prompt_tokens": 400, "completion_tokens": 100},
    }


@pytest.fixture
def mocked_client():
    """Patch OpenRouterClient so AIAnalyzer never touches the network."""
    with patch("consigliere.services.ai_analyzer.OpenRouterClient") as client_cls:
        instance = MagicMock()
        client_cls.return_value = instance
        yield instance


def test_analyze_with_ai_returns_expected_structure(mocked_client, haiku_model, chat_group_data):
    payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    mocked_client.complete.return_value = _mock_complete_response(payload)

    analyzer = AIAnalyzer(current_model=haiku_model.model_id)
    result = analyzer.analyze_with_ai(
        chat_group_data=chat_group_data,
        current_model_id=haiku_model.model_id,
        metrics={"total_messages": 2, "total_cost": 0.004, "avg_latency": 1.5, "total_tokens": 200},
    )

    assert result["conversation_type"] == "technical_discussion"
    assert result["detected_needs"]["precision"] == "high"
    assert result["recommended_from_conversation"]["model_id"] == haiku_model.model_id
    assert len(result["alternative_models"]) == 1
    assert result["ai_model_used"] == "anthropic/claude-3-haiku"
    assert result["ai_tokens_used"] == 500


def test_analyze_with_ai_streaming_yields_progress_then_result(mocked_client, haiku_model, chat_group_data):
    payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    mocked_client.complete.return_value = _mock_complete_response(payload)

    analyzer = AIAnalyzer(current_model=haiku_model.model_id)
    events = list(
        analyzer.analyze_with_ai_streaming(
            chat_group_data=chat_group_data,
            current_model_id=haiku_model.model_id,
            metrics={"total_messages": 2, "total_cost": 0.0, "avg_latency": 0.0, "total_tokens": 0},
        )
    )

    progress_events = [e for e in events if "_result" not in e]
    result_events = [e for e in events if "_result" in e]

    assert len(result_events) == 1
    assert result_events[0]["_result"]["conversation_type"] == "technical_discussion"
    # All intermediate progress events carry the expected shape.
    for event in progress_events:
        assert {"step", "status", "message", "timestamp"} <= set(event.keys())
    # The pipeline reports each step completing, in order.
    completed_steps = [e["step"] for e in progress_events if e["status"] == "completed"]
    assert completed_steps == [
        "preparing_context",
        "fetching_models",
        "calling_ai",
        "parsing_response",
        "calculating_costs",
        "saving",
    ]


def test_analyze_with_ai_rejects_recommendation_not_used_in_conversation(mocked_client, haiku_model, opus_model, chat_group_data):
    """The AI must not recommend a model that was never actually used."""
    payload = valid_ai_analysis_payload(model_id=opus_model.model_id)  # not used in chat_group_data
    mocked_client.complete.return_value = _mock_complete_response(payload)

    analyzer = AIAnalyzer(current_model=haiku_model.model_id)

    with pytest.raises(ValueError, match="must be one of the models"):
        analyzer.analyze_with_ai(
            chat_group_data=chat_group_data,
            current_model_id=haiku_model.model_id,
            metrics={"total_messages": 2, "total_cost": 0.0, "avg_latency": 0.0, "total_tokens": 0},
        )


def test_parse_ai_response_validates_required_fields_and_enum_values(mocked_client, haiku_model, chat_group_data):
    missing_field_payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    del missing_field_payload["insights"]
    mocked_client.complete.return_value = _mock_complete_response(missing_field_payload)

    analyzer = AIAnalyzer(current_model=haiku_model.model_id)
    with pytest.raises(ValueError, match="Missing required field: insights"):
        analyzer.analyze_with_ai(
            chat_group_data=chat_group_data, current_model_id=haiku_model.model_id, metrics={}
        )

    bad_enum_payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    bad_enum_payload["detected_needs"]["precision"] = "extreme"  # not high/medium/low
    mocked_client.complete.return_value = _mock_complete_response(bad_enum_payload)

    with pytest.raises(ValueError, match="Invalid value for precision"):
        analyzer.analyze_with_ai(
            chat_group_data=chat_group_data, current_model_id=haiku_model.model_id, metrics={}
        )


def test_parses_json_from_markdown_or_raises_on_invalid(mocked_client, haiku_model, chat_group_data):
    payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    mocked_client.complete.return_value = {
        "content": f"Here is the analysis:\n```json\n{json.dumps(payload)}\n```",
        "model": haiku_model.model_id,
        "usage": {"total_tokens": 42},
    }
    analyzer = AIAnalyzer(current_model=haiku_model.model_id)
    result = analyzer.analyze_with_ai(
        chat_group_data=chat_group_data, current_model_id=haiku_model.model_id, metrics={}
    )
    assert result["conversation_type"] == "technical_discussion"

    mocked_client.complete.return_value = {
        "content": "This is not JSON at all",
        "model": haiku_model.model_id,
        "usage": {},
    }
    with pytest.raises(ValueError, match="No JSON object found"):
        analyzer.analyze_with_ai(
            chat_group_data=chat_group_data, current_model_id=haiku_model.model_id, metrics={}
        )


def test_calculate_real_cost_tradeoffs_and_conversation_content_helpers(mocked_client, haiku_model, opus_model):
    analyzer = AIAnalyzer(current_model=haiku_model.model_id)

    analysis_data = {
        "recommended_from_conversation": {"model_id": opus_model.model_id},
        "alternative_models": [{"model_id": haiku_model.model_id, "tradeoffs": {}}],
    }
    result = analyzer._calculate_real_cost_tradeoffs(analysis_data, chat_group_data={}, metrics={})
    savings = result["alternative_models"][0]["tradeoffs"]["cost_savings"]
    # Haiku is much cheaper than Opus -> large positive savings.
    assert savings.startswith("+")

    chat_group = make_chat_group(
        messages=[
            {
                "role": "user",
                "content": "Look at this",
                "attachments_meta": [
                    {"type": "image", "filename": "diagram.png"},
                    {"type": "file", "is_pdf": True, "filename": "spec.pdf"},
                ],
            },
        ]
    )
    content = analyzer._build_conversation_content(chat_group)
    assert "1 image" in content
    assert "1 PDF" in content
    assert "diagram.png" in content
