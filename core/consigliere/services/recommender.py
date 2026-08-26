"""
Model recommender for Consigliere AI.

Recommends optimal LLM models based on conversation analysis and user preferences.
"""

import logging
from typing import Dict, List, Any, Optional

from llm.models import ModelCatalog
from ..config import ScoringConfig

logger = logging.getLogger(__name__)


class ModelRecommender:
    """
    Recommends optimal models based on conversation analysis and user needs.
    """

    # Model quality tiers (subjective, based on common knowledge)
    QUALITY_TIERS = {
        "premium": [
            "gpt-4",
            "claude-3-opus",
            "claude-3.5-sonnet",
            "gemini-pro",
            "gemini-1.5-pro",
        ],
        "high": [
            "gpt-3.5-turbo",
            "claude-3-sonnet",
            "claude-3-haiku",
            "gemini-flash",
            "mistral-large",
        ],
        "medium": [
            "llama-3",
            "mixtral",
            "mistral-medium",
            "qwen",
            "deepseek",
        ],
        "budget": [
            "llama-2",
            "mistral-7b",
            "phi",
        ],
    }

    # Speed tiers (based on typical latency)
    SPEED_TIERS = {
        "very_fast": ["claude-3-haiku", "gemini-flash", "gpt-3.5-turbo"],
        "fast": ["mistral-medium", "llama-3", "deepseek"],
        "moderate": ["claude-3-sonnet", "gpt-4", "gemini-pro"],
        "slow": ["claude-3-opus", "claude-3.5-sonnet"],
    }

    def recommend_models(
        self,
        analysis: Dict[str, Any],
        current_model_id: str,
        user_preferences: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recommend optimal models based on analysis.

        Args:
            analysis: Conversation analysis results
            current_model_id: Currently selected model
            user_preferences: Optional user preferences
            limit: Maximum number of recommendations

        Returns:
            List of recommendation dictionaries
        """
        user_preferences = user_preferences or {}

        # Get available models from catalog
        available_models = self._get_available_models()

        if not available_models:
            logger.warning("No models available in catalog")
            return []

        # Get current model info
        current_model = self._get_model_info(current_model_id, available_models)

        # Score all models
        scored_models: List[Dict[str, Any]] = []
        for model in available_models:
            if model["model_id"] == current_model_id:
                continue  # Skip current model

            score = self._score_model(
                model,
                analysis,
                user_preferences,
            )

            scored_models.append({
                "model": model,
                "score": score,
            })

        # Sort by score (highest first)
        scored_models.sort(key=lambda x: x["score"], reverse=True)

        # Generate recommendations
        recommendations = []
        for rank, item in enumerate(scored_models[:limit], start=1):
            model = item["model"]
            score = item["score"]

            recommendation = self._build_recommendation(
                model=model,
                rank=rank,
                score=score,
                analysis=analysis,
                current_model=current_model,
                user_preferences=user_preferences,
                available_models=available_models,
            )

            recommendations.append(recommendation)

        return recommendations

    def _get_available_models(self) -> List[Dict[str, Any]]:
        """
        Get available models from catalog.

        Returns:
            List of model dictionaries
        """
        models = ModelCatalog.objects.filter(
            is_available=True,
            prompt_price__isnull=False,
            completion_price__isnull=False,
        ).values(
            "model_id",
            "name",
            "provider",
            "prompt_price",
            "completion_price",
            "max_tokens",
            "supports_streaming",
            "supports_functions",
        )

        return list(models)

    def _get_model_info(
        self, model_id: str, available_models: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Get model info from catalog."""
        for model in available_models:
            if model["model_id"] == model_id:
                return model
        return None

    def _score_model(
        self,
        model: Dict[str, Any],
        analysis: Dict[str, Any],
        user_preferences: Dict[str, Any],
    ) -> float:
        """
        Score a model based on how well it fits the conversation needs.

        Args:
            model: Model info
            analysis: Conversation analysis
            user_preferences: User preferences

        Returns:
            Score between 0 and 1
        """
        score = 0.0
        weights_sum = 0.0

        # 1. Cost scoring
        cost_weight = ScoringConfig.COST_WEIGHT
        detected_needs = analysis.get("detected_needs", {})
        cost_sensitivity = detected_needs.get("cost_efficiency", "medium")

        if cost_sensitivity == "high":
            # Prefer cheaper models
            avg_price = (
                float(model.get("prompt_price", 0))
                + float(model.get("completion_price", 0))
            ) / 2
            cost_score = max(0, 1 - (avg_price / 0.05))  # Normalize to 0-1
            score += cost_score * cost_weight
            weights_sum += cost_weight

        # 2. Quality scoring
        quality_weight = ScoringConfig.QUALITY_WEIGHT
        quality_tier = self._get_quality_tier(model["model_id"])
        quality_score = ScoringConfig.QUALITY_SCORES.get(quality_tier, 0.5)

        precision_need = detected_needs.get("precision", "medium")
        if precision_need == "high":
            score += quality_score * quality_weight
            weights_sum += quality_weight

        # 3. Speed scoring
        speed_weight = ScoringConfig.SPEED_WEIGHT
        speed_tier = self._get_speed_tier(model["model_id"])
        speed_score = ScoringConfig.SPEED_SCORES.get(speed_tier, 0.5)

        speed_need = detected_needs.get("speed", "medium")
        if speed_need == "high":
            score += speed_score * speed_weight
            weights_sum += speed_weight

        # 4. Context length scoring
        context_weight = ScoringConfig.CONTEXT_WEIGHT
        max_tokens = model.get("max_tokens", 0)
        if max_tokens:
            context_score = min(1.0, max_tokens / ScoringConfig.CONTEXT_NORMALIZATION_THRESHOLD)
            score += context_score * context_weight
            weights_sum += context_weight

        # Normalize final score
        if weights_sum > 0:
            score = score / weights_sum

        # Apply user preference multipliers
        budget_pref = user_preferences.get("budget_preference", "balanced")
        if budget_pref == "budget" and quality_tier in ["budget", "medium"]:
            score *= ScoringConfig.BUDGET_PREFERENCE_MULTIPLIER
        elif budget_pref == "premium" and quality_tier in ["premium", "high"]:
            score *= ScoringConfig.BUDGET_PREFERENCE_MULTIPLIER

        return min(1.0, score)  # Cap at 1.0

    def _get_quality_tier(self, model_id: str) -> str:
        """Determine quality tier for a model."""
        model_id_lower = model_id.lower()

        for tier, patterns in self.QUALITY_TIERS.items():
            for pattern in patterns:
                if pattern.lower() in model_id_lower:
                    return tier

        return "medium"  # Default

    def _get_speed_tier(self, model_id: str) -> str:
        """Determine speed tier for a model."""
        model_id_lower = model_id.lower()

        for tier, patterns in self.SPEED_TIERS.items():
            for pattern in patterns:
                if pattern.lower() in model_id_lower:
                    return tier

        return "moderate"  # Default

    def _calculate_model_cost(
        self,
        prompt_price: float,
        completion_price: float,
        prompt_tokens: float,
        completion_tokens: float,
    ) -> float:
        """
        Calculate cost based on actual token counts.

        Args:
            prompt_price: Price per 1K prompt tokens
            completion_price: Price per 1K completion tokens
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Total cost in USD
        """
        prompt_cost = (prompt_tokens * prompt_price) / ScoringConfig.TOKEN_PRICE_DIVISOR
        completion_cost = (completion_tokens * completion_price) / ScoringConfig.TOKEN_PRICE_DIVISOR
        return prompt_cost + completion_cost

    def _get_baseline_model(
        self, analysis: Dict[str, Any], available_models: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Get the cheapest model actually used in the conversation.

        Args:
            analysis: Conversation analysis with models_used data
            available_models: List of available models from catalog

        Returns:
            Baseline model dict with usage stats, or None if no models used
        """
        models_used = analysis.get("models_used", [])
        if not models_used:
            return None

        # Find the model with lowest total cost from those used
        cheapest = min(models_used, key=lambda m: float(m.get("total_cost", 0)))

        # Get its pricing from catalog and add usage stats
        for model in available_models:
            if model["model_id"] == cheapest["model_id"]:
                return {
                    **model,
                    "avg_prompt_tokens": cheapest["total_prompt_tokens"]
                    / max(cheapest["message_count"], 1),
                    "avg_completion_tokens": cheapest["total_completion_tokens"]
                    / max(cheapest["message_count"], 1),
                }

        return None

    def _build_recommendation(
        self,
        model: Dict[str, Any],
        rank: int,
        score: float,
        analysis: Dict[str, Any],
        current_model: Optional[Dict[str, Any]],
        user_preferences: Dict[str, Any],
        available_models: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build a recommendation dictionary with reasoning and trade-offs.

        Args:
            model: Recommended model
            rank: Rank in recommendation list
            score: Calculated score
            analysis: Conversation analysis
            current_model: Current model info
            user_preferences: User preferences
            available_models: List of available models

        Returns:
            Recommendation dictionary
        """
        # Calculate trade-offs vs baseline (cheapest model used in conversation)
        tradeoffs = {}
        baseline_model = self._get_baseline_model(analysis, available_models)

        if baseline_model:
            # Add baseline info to tradeoffs for transparency
            tradeoffs["baseline_model_name"] = baseline_model.get("name", "Unknown")
            tradeoffs["baseline_model_id"] = baseline_model.get("model_id", "")

            # Cost comparison using actual token usage from conversation
            baseline_cost = self._calculate_model_cost(
                float(baseline_model.get("prompt_price", 0)),
                float(baseline_model.get("completion_price", 0)),
                baseline_model.get("avg_prompt_tokens", 0),
                baseline_model.get("avg_completion_tokens", 0),
            )

            new_model_cost = self._calculate_model_cost(
                float(model.get("prompt_price", 0)),
                float(model.get("completion_price", 0)),
                baseline_model.get("avg_prompt_tokens", 0),
                baseline_model.get("avg_completion_tokens", 0),
            )

            if baseline_cost > 0:
                cost_delta = ((baseline_cost - new_model_cost) / baseline_cost) * 100
                tradeoffs["cost_savings"] = f"{cost_delta:+.0f}%"

            # Quality comparison (vs baseline)
            baseline_quality = self._get_quality_tier(baseline_model["model_id"])
            new_quality = self._get_quality_tier(model["model_id"])
            quality_delta = (
                ScoringConfig.QUALITY_TIER_SCORES.get(new_quality, 2)
                - ScoringConfig.QUALITY_TIER_SCORES.get(baseline_quality, 2)
            ) * ScoringConfig.TIER_DELTA_MULTIPLIER
            tradeoffs["quality_delta"] = f"{quality_delta:+.0f}%"

            # Speed comparison (vs baseline)
            baseline_speed = self._get_speed_tier(baseline_model["model_id"])
            new_speed = self._get_speed_tier(model["model_id"])
            speed_delta = (
                ScoringConfig.SPEED_TIER_SCORES.get(new_speed, 2)
                - ScoringConfig.SPEED_TIER_SCORES.get(baseline_speed, 2)
            ) * ScoringConfig.TIER_DELTA_MULTIPLIER
            tradeoffs["speed_delta"] = f"{speed_delta:+.0f}%"

        # Generate reasoning
        reasoning = self._generate_reasoning(
            model, analysis, tradeoffs, user_preferences
        )

        # Estimate cost per message using actual conversation token distribution
        if baseline_model:
            # Use actual token distribution from conversation
            estimated_cost = self._calculate_model_cost(
                float(model.get("prompt_price", 0)),
                float(model.get("completion_price", 0)),
                baseline_model.get("avg_prompt_tokens", 0),
                baseline_model.get("avg_completion_tokens", 0),
            )
        else:
            # Fallback: estimate based on total tokens (less accurate)
            avg_tokens = analysis.get("total_tokens", ScoringConfig.DEFAULT_FALLBACK_TOKENS) / max(
                analysis.get("total_messages", 1), 1
            )
            # Assume 2:1 prompt to completion ratio
            avg_prompt_tokens = avg_tokens * ScoringConfig.PROMPT_TOKEN_RATIO
            avg_completion_tokens = avg_tokens * ScoringConfig.COMPLETION_TOKEN_RATIO
            estimated_cost = self._calculate_model_cost(
                float(model.get("prompt_price", 0)),
                float(model.get("completion_price", 0)),
                avg_prompt_tokens,
                avg_completion_tokens,
            )

        return {
            "model_id": model["model_id"],
            "model_name": model["name"],
            "provider": model["provider"],
            "score": round(score, 2),
            "rank": rank,
            "reasoning": reasoning,
            "tradeoffs": tradeoffs,
            "estimated_cost_per_message": estimated_cost,  # Return as float, not Decimal
            "estimated_quality_score": score,  # Use overall score as quality proxy
        }

    def _generate_reasoning(
        self,
        model: Dict[str, Any],
        analysis: Dict[str, Any],
        tradeoffs: Dict[str, str],
        user_preferences: Dict[str, Any],
    ) -> str:
        """Generate human-readable reasoning for recommendation."""
        reasons = []

        # Quality tier reason
        quality_tier = self._get_quality_tier(model["model_id"])
        conversation_type = analysis.get("conversation_type", "general_assistance")

        if quality_tier == "premium":
            reasons.append(
                f"Excellent quality for {conversation_type.replace('_', ' ')}"
            )
        elif quality_tier == "high":
            reasons.append("Good balance of quality and efficiency")
        elif quality_tier == "budget":
            reasons.append(f"Cost-effective option for {conversation_type.replace('_', ' ')}")

        # Cost reason
        if tradeoffs.get("cost_savings"):
            savings = tradeoffs["cost_savings"]
            if savings.startswith("+"):
                reasons.append(f"Saves {savings.replace('+', '')} on costs")
            elif savings.startswith("-"):
                reasons.append(
                    f"Higher cost ({savings.replace('-', '+')}), but better quality"
                )

        # Speed reason
        speed_tier = self._get_speed_tier(model["model_id"])
        detected_needs = analysis.get("detected_needs", {})
        if (
            speed_tier in ["very_fast", "fast"]
            and detected_needs.get("speed") == "high"
        ):
            reasons.append("Fast response times")

        # Context length reason
        max_tokens = model.get("max_tokens", 0)
        if max_tokens and max_tokens > ScoringConfig.LARGE_CONTEXT_THRESHOLD:
            reasons.append(f"Large context window ({max_tokens:,} tokens)")

        # Fallback
        if not reasons:
            reasons.append("Well-suited for your conversation pattern")

        return ". ".join(reasons) + "."
