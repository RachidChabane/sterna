"""Tests for ModelRecommender — scoring and recommendation-building logic.

Backed by real ``ModelCatalog`` rows (the only DB dependency) so
``recommend_models`` runs deterministically end to end. Closely related
checks on the same call are grouped into one test function to keep the
suite tight.
"""

from decimal import Decimal

import pytest

from consigliere.services.recommender import ModelRecommender

pytestmark = pytest.mark.django_db


@pytest.fixture
def recommender():
    return ModelRecommender()


def test_recommend_models_excludes_current_and_unavailable_ranks_and_respects_limit(
    recommender, haiku_model, opus_model, budget_model, unavailable_model
):
    analysis = {
        "detected_needs": {"cost_efficiency": "high", "precision": "medium", "speed": "medium"},
        "conversation_type": "technical_discussion",
    }

    recommendations = recommender.recommend_models(
        analysis=analysis, current_model_id=haiku_model.model_id, limit=5
    )

    recommended_ids = {rec["model_id"] for rec in recommendations}
    assert recommended_ids == {opus_model.model_id, budget_model.model_id}  # excludes current + unavailable
    ranks = [rec["rank"] for rec in recommendations]
    assert ranks == list(range(1, len(recommendations) + 1))

    limited = recommender.recommend_models(
        analysis=analysis, current_model_id=haiku_model.model_id, limit=1
    )
    assert len(limited) == 1


def test_recommend_models_returns_empty_list_when_catalog_empty(recommender):
    analysis = {"detected_needs": {}, "conversation_type": "general_assistance"}

    recommendations = recommender.recommend_models(
        analysis=analysis, current_model_id="anthropic/claude-3-haiku", limit=5
    )

    assert recommendations == []


def test_high_cost_sensitivity_prefers_cheaper_model(recommender, opus_model, budget_model):
    """With high cost sensitivity, the budget model should outscore the premium one."""
    analysis = {
        "detected_needs": {"cost_efficiency": "high"},
        "conversation_type": "general_assistance",
    }

    recommendations = recommender.recommend_models(
        analysis=analysis, current_model_id="anthropic/claude-3-haiku", limit=5
    )

    scores = {rec["model_id"]: rec["score"] for rec in recommendations}
    assert scores[budget_model.model_id] > scores[opus_model.model_id]


def test_quality_and_speed_tier_detection(recommender):
    assert recommender._get_quality_tier("anthropic/claude-3-opus") == "premium"
    assert recommender._get_quality_tier("anthropic/claude-3-haiku") == "high"
    assert recommender._get_quality_tier("mistralai/mistral-7b") == "budget"
    assert recommender._get_quality_tier("totally/unknown-model") == "medium"

    assert recommender._get_speed_tier("anthropic/claude-3-haiku") == "very_fast"
    assert recommender._get_speed_tier("anthropic/claude-3-opus") == "slow"
    assert recommender._get_speed_tier("totally/unknown-model") == "moderate"


def test_cost_calculation_and_score_bounds(recommender, haiku_model):
    cost = recommender._calculate_model_cost(
        prompt_price=1.0,  # $1 per 1K prompt tokens
        completion_price=2.0,  # $2 per 1K completion tokens
        prompt_tokens=1000,
        completion_tokens=500,
    )
    # 1000 prompt tokens @ $1/1K = $1.00; 500 completion @ $2/1K = $1.00
    assert cost == pytest.approx(2.0)

    analysis = {
        "detected_needs": {"cost_efficiency": "high", "precision": "high", "speed": "high"}
    }
    model = {
        "model_id": haiku_model.model_id,
        "prompt_price": haiku_model.prompt_price,
        "completion_price": haiku_model.completion_price,
        "max_tokens": haiku_model.max_tokens,
    }
    # A budget preference multiplier must never push the score above 1.0.
    score = recommender._score_model(model, analysis, user_preferences={"budget_preference": "premium"})
    assert 0.0 <= score <= 1.0


def test_build_recommendation_includes_reasoning_and_tradeoffs(recommender, haiku_model, opus_model):
    analysis = {
        "detected_needs": {"precision": "high"},
        "conversation_type": "technical_discussion",
        "models_used": [
            {
                "model_id": haiku_model.model_id,
                "total_prompt_tokens": 100,
                "total_completion_tokens": 50,
                "total_cost": Decimal("0.01"),
                "message_count": 1,
            }
        ],
    }
    available_models = [
        {
            "model_id": haiku_model.model_id,
            "name": haiku_model.name,
            "provider": haiku_model.provider,
            "prompt_price": haiku_model.prompt_price,
            "completion_price": haiku_model.completion_price,
            "max_tokens": haiku_model.max_tokens,
        },
        {
            "model_id": opus_model.model_id,
            "name": opus_model.name,
            "provider": opus_model.provider,
            "prompt_price": opus_model.prompt_price,
            "completion_price": opus_model.completion_price,
            "max_tokens": opus_model.max_tokens,
        },
    ]

    recommendation = recommender._build_recommendation(
        model=available_models[1],
        rank=1,
        score=0.9,
        analysis=analysis,
        current_model=available_models[0],
        user_preferences={},
        available_models=available_models,
    )

    assert recommendation["model_id"] == opus_model.model_id
    assert recommendation["rank"] == 1
    assert recommendation["score"] == 0.9
    assert recommendation["reasoning"]
    assert "cost_savings" in recommendation["tradeoffs"]
    assert "quality_delta" in recommendation["tradeoffs"]
    assert "speed_delta" in recommendation["tradeoffs"]
    # Opus is strictly more expensive than Haiku -> negative savings.
    assert recommendation["tradeoffs"]["cost_savings"].startswith("-")
