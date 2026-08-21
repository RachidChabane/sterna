"""Tests for ConversationAnalyzer — pure conversation analysis logic.

No LLM calls, no database access: this service only inspects the
ChatGroup dict handed in from the frontend, so these are plain unit
tests (deterministic inputs -> asserted analysis structure). Related
branches of the same method are grouped into one test function with
multiple sub-checks to keep the suite tight.
"""

from decimal import Decimal

import pytest

from consigliere.services.analyzer import ConversationAnalyzer
from consigliere.tests.conftest import make_chat_group

pytestmark = pytest.mark.django_db


@pytest.fixture
def analyzer():
    return ConversationAnalyzer()


def test_empty_chat_group_returns_empty_analysis(analyzer):
    result = analyzer.analyze_chat_group({"chats": []})

    assert result["conversation_type"] == "unknown"
    assert result["total_messages"] == 0
    assert result["insights"] == ["No conversation data available"]
    assert result["total_cost"] == Decimal("0")


def test_detects_conversation_type_from_keywords(analyzer):
    technical = analyzer.analyze_chat_group(
        make_chat_group(
            messages=[
                {"role": "user", "content": "I have a bug in this function, can you debug the algorithm?"},
                {"role": "assistant", "content": "Sure, let's look at the code."},
            ]
        )
    )
    creative = analyzer.analyze_chat_group(
        make_chat_group(
            messages=[
                {"role": "user", "content": "Write a creative short story about a character on a narrative quest"},
                {"role": "assistant", "content": "Once upon a time..."},
            ]
        )
    )
    unmatched = analyzer.analyze_chat_group(
        make_chat_group(
            messages=[
                {"role": "user", "content": "xyzzy plugh"},
                {"role": "assistant", "content": "..."},
            ]
        )
    )

    assert technical["conversation_type"] == "technical_discussion"
    assert creative["conversation_type"] == "creative_writing"
    assert unmatched["conversation_type"] == "general_assistance"


def test_calculates_metrics_from_costs_tokens_and_latency(analyzer):
    with_data = analyzer.analyze_chat_group(
        make_chat_group(
            messages=[
                {
                    "role": "assistant",
                    "content": "Answer one",
                    "tokens": {"prompt": 100, "completion": 50},
                    "cost": 0.01,
                    "latency": 2000,  # ms
                },
                {
                    "role": "assistant",
                    "content": "Answer two",
                    "tokens": {"prompt": 200, "completion": 100},
                    "cost": 0.02,
                    "latency": 4000,  # ms
                },
            ]
        )
    )
    assert with_data["total_messages"] == 2
    assert with_data["total_tokens"] == 450
    assert with_data["total_cost"] == Decimal("0.03")
    assert with_data["avg_cost_per_message"] == Decimal("0.015")
    # Latency is stored in ms upstream and converted to seconds.
    assert with_data["avg_latency"] == pytest.approx(3.0)

    # Messages with no cost/latency/tokens data must not raise or skew averages.
    without_data = analyzer._calculate_metrics(
        [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    )
    assert without_data["total_messages"] == 2
    assert without_data["total_cost"] == Decimal("0")
    assert without_data["avg_cost_per_message"] == Decimal("0")
    assert without_data["avg_latency"] == 0.0


def test_detects_needs_from_keywords_and_spending(analyzer):
    precise = analyzer.analyze_chat_group(
        make_chat_group(
            messages=[
                {"role": "user", "content": "I need an accurate and precise, exact and specific answer"},
                {"role": "assistant", "content": "Here you go."},
            ]
        )
    )
    expensive = analyzer.analyze_chat_group(
        make_chat_group(messages=[{"role": "assistant", "content": "Expensive answer", "cost": 0.05}])
    )
    cheap = analyzer.analyze_chat_group(
        make_chat_group(messages=[{"role": "assistant", "content": "Cheap answer", "cost": 0.0001}])
    )

    assert precise["detected_needs"]["precision"] == "high"
    assert expensive["detected_needs"]["cost_efficiency"] == "high"
    assert cheap["detected_needs"]["cost_efficiency"] == "low"


def test_get_models_used_and_insights_overview_and_cap(analyzer):
    chat_group = make_chat_group(
        model_id="anthropic/claude-3-haiku",
        messages=[
            {
                "role": "assistant",
                "content": "One",
                "model_id": "anthropic/claude-3-haiku",
                "tokens": {"prompt": 100, "completion": 50},
                "cost": 0.01,
            },
            {
                "role": "assistant",
                "content": "Two",
                "model_id": "anthropic/claude-3-haiku",
                "tokens": {"prompt": 50, "completion": 25},
                "cost": 0.005,
            },
        ],
    )

    result = analyzer.analyze_chat_group(chat_group)

    # models_used aggregates per-model usage stats.
    models_used = result["models_used"]
    assert len(models_used) == 1
    entry = models_used[0]
    assert entry["model_id"] == "anthropic/claude-3-haiku"
    assert entry["message_count"] == 2
    assert entry["total_prompt_tokens"] == 150
    assert entry["total_completion_tokens"] == 75
    assert entry["total_cost"] == Decimal("0.015")

    # Insights always open with an overview and the detected type.
    assert any("Analyzed" in insight for insight in result["insights"])
    assert any("Conversation type" in insight for insight in result["insights"])

    # A conversation that trips every insight branch is still capped at 8.
    long_user_msg = "x" * 600
    messages = [
        {"role": "user", "content": long_user_msg + " creative innovative unique original imagine design"},
        {"role": "assistant", "content": "ok", "cost": 0.02, "latency": 8000},
    ]
    many_insights_group = {
        "id": "cg-many",
        "chats": [
            {"id": "c1", "model": {"model_id": "m1", "name": "Model One"}, "messages": messages},
            {"id": "c2", "model": {"model_id": "m2", "name": "Model Two"}, "messages": messages},
        ],
    }
    capped = analyzer.analyze_chat_group(many_insights_group)
    assert len(capped["insights"]) <= 8
