"""
Service for comparing model catalog entries given user-selected priorities and constraints.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from .models import ModelCatalog
from .comparison_config import (
    WEIGHT_LEVELS,
    NORMALIZATION_EPSILON,
    CONTEXT_THRESHOLD_MINIMUM_MULTIMODAL,
    ComparisonPreset,
    ComparisonConstraints,
    ComparisonPriorities,
    CapabilityWeights,
    get_preset,
)


# Typical request scenario for cost calculation
COMPARISON_PROMPT_TOKENS = 500
COMPARISON_COMPLETION_TOKENS = 1500
COMPARISON_REQUEST_COUNT = 1000

# Context display thresholds (tokens)
CONTEXT_DISPLAY_MILLION = 1_000_000
CONTEXT_DISPLAY_THOUSAND = 1_000


def _normalize(values: List[float], invert: bool = False) -> List[float]:
    """Normalize values to [0, 1] range. Optionally invert (for metrics where lower is better)."""
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    rng = max(vmax - vmin, NORMALIZATION_EPSILON)
    out = [((v - vmin) / rng) for v in values]
    return [1.0 - n if invert else n for n in out]


def calculate_cost_per_1m_tokens(model: ModelCatalog) -> float:
    """Compute average cost per 1M tokens (average of prompt and completion prices)."""
    from .pricing_config import PRICE_CONVERSION_FACTOR

    prompt_price = float(model.prompt_price or 0)
    completion_price = float(model.completion_price or 0)

    # Convert from per-1K (storage) to per-1M (display) and average
    prompt_per_1m = prompt_price * PRICE_CONVERSION_FACTOR
    completion_per_1m = completion_price * PRICE_CONVERSION_FACTOR

    return (prompt_per_1m + completion_per_1m) / 2


def format_context_length(tokens: int) -> str:
    """Format context length for display (e.g., '128K', '1M')."""
    if tokens >= CONTEXT_DISPLAY_MILLION:
        return f"{tokens // CONTEXT_DISPLAY_MILLION}M"
    elif tokens >= CONTEXT_DISPLAY_THOUSAND:
        return f"{tokens // CONTEXT_DISPLAY_THOUSAND}K"
    return str(tokens)


@dataclass
class ModelScore:
    """Score result for a single model."""
    model_id: str
    id: str
    name: str
    provider: str
    score: float
    score_percentage: float
    breakdown: Dict[str, float]
    cost_per_1m_tokens: float
    context_length: int
    context_display: str
    capabilities: List[str]
    is_best: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.model_id,
            "name": self.name,
            "provider": self.provider,
            "score": round(self.score, 3),
            "score_pct": round(self.score_percentage, 1),
            "breakdown": {k: round(v, 3) for k, v in self.breakdown.items()},
            "cost_per_1k": round(self.cost_per_1m_tokens, 2),
            "context_length": self.context_length,
            "context_str": self.context_display,
            "capabilities": self.capabilities,
            "is_best": self.is_best,
        }


@dataclass
class ComparisonResult:
    """Result of a model comparison."""
    scores: List[ModelScore]
    best_model: Optional[ModelScore]
    total_compared: int
    preset_id: str
    preset_label: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_compared": self.total_compared,
            "preset": self.preset_id,
            "preset_label": self.preset_label,
            "models": [s.to_dict() for s in self.scores],
            "best_model": self.best_model.to_dict() if self.best_model else None,
        }


class ModelComparisonService:
    """Service for comparing models using weighted scoring algorithm."""

    def compare_with_preset(
        self,
        models: List[ModelCatalog],
        preset_id: str = "balanced",
        additional_constraints: Optional[ComparisonConstraints] = None,
        limit: int = 10,
    ) -> ComparisonResult:
        """Compare models using a preset configuration."""
        preset = get_preset(preset_id)
        return self._compare(
            models=models,
            preset=preset,
            additional_constraints=additional_constraints,
            limit=limit,
        )

    def compare_with_options(
        self,
        models: List[ModelCatalog],
        priorities: ComparisonPriorities,
        constraints: ComparisonConstraints,
        capability_weights: Optional[CapabilityWeights] = None,
        cost_direction: str = "lower",
        limit: int = 10,
    ) -> ComparisonResult:
        """Compare models with custom options (for API endpoint)."""
        if not models:
            return ComparisonResult(
                scores=[],
                best_model=None,
                total_compared=0,
                preset_id="custom",
                preset_label="Custom",
            )

        # Apply constraints to filter models
        filtered = self._apply_constraints(models, constraints)
        if not filtered:
            return ComparisonResult(
                scores=[],
                best_model=None,
                total_compared=0,
                preset_id="custom",
                preset_label="Custom",
            )

        # Calculate scores
        scores = self._calculate_scores(
            filtered,
            priorities,
            capability_weights or CapabilityWeights(),
            cost_direction,
        )

        # Sort by score descending and limit
        scores.sort(key=lambda s: s.score, reverse=True)
        scores = scores[:limit]

        # Mark best model
        if scores:
            scores[0].is_best = True

        return ComparisonResult(
            scores=scores,
            best_model=scores[0] if scores else None,
            total_compared=len(scores),
            preset_id="custom",
            preset_label="Custom",
        )

    def _compare(
        self,
        models: List[ModelCatalog],
        preset: ComparisonPreset,
        additional_constraints: Optional[ComparisonConstraints] = None,
        limit: int = 10,
    ) -> ComparisonResult:
        """Internal comparison implementation."""
        if not models:
            return ComparisonResult(
                scores=[],
                best_model=None,
                total_compared=0,
                preset_id=preset.id,
                preset_label=preset.label,
            )

        # Merge preset constraints with additional constraints
        effective_constraints = self._merge_constraints(
            preset.constraints, additional_constraints
        )

        # Apply constraints to filter models
        filtered = self._apply_constraints(models, effective_constraints)
        if not filtered:
            return ComparisonResult(
                scores=[],
                best_model=None,
                total_compared=0,
                preset_id=preset.id,
                preset_label=preset.label,
            )

        # Calculate scores
        scores = self._calculate_scores(
            filtered,
            preset.priorities,
            preset.capability_weights,
            preset.cost_direction,
        )

        # Sort by score descending and limit
        scores.sort(key=lambda s: s.score, reverse=True)
        scores = scores[:limit]

        # Mark best model
        if scores:
            scores[0].is_best = True

        return ComparisonResult(
            scores=scores,
            best_model=scores[0] if scores else None,
            total_compared=len(scores),
            preset_id=preset.id,
            preset_label=preset.label,
        )

    def _merge_constraints(
        self,
        preset_constraints: ComparisonConstraints,
        additional: Optional[ComparisonConstraints],
    ) -> ComparisonConstraints:
        """Merge preset constraints with additional user constraints."""
        if not additional:
            return preset_constraints

        # Additional constraints override preset where specified
        return ComparisonConstraints(
            must_support_functions=additional.must_support_functions or preset_constraints.must_support_functions,
            must_support_structured_outputs=additional.must_support_structured_outputs or preset_constraints.must_support_structured_outputs,
            must_support_reasoning=additional.must_support_reasoning or preset_constraints.must_support_reasoning,
            must_support_prompt_caching=additional.must_support_prompt_caching or preset_constraints.must_support_prompt_caching,
            must_support_stream_cancellation=additional.must_support_stream_cancellation or preset_constraints.must_support_stream_cancellation,
            must_be_available=additional.must_be_available or preset_constraints.must_be_available,
            must_be_multimodal=additional.must_be_multimodal or preset_constraints.must_be_multimodal,
            must_support_vision=additional.must_support_vision or preset_constraints.must_support_vision,
            min_context_tokens=additional.min_context_tokens or preset_constraints.min_context_tokens,
            max_cost_per_1m_tokens=additional.max_cost_per_1m_tokens or preset_constraints.max_cost_per_1m_tokens,
        )

    def _apply_constraints(
        self, models: List[ModelCatalog], constraints: ComparisonConstraints
    ) -> List[ModelCatalog]:
        """Filter models based on constraints."""
        result = []
        for m in models:
            if constraints.must_be_available and not m.is_available:
                continue
            if constraints.must_support_functions and not m.supports_functions:
                continue
            if constraints.must_support_structured_outputs and not m.supports_structured_outputs:
                continue
            if constraints.must_support_reasoning and not m.supports_reasoning:
                continue
            if constraints.must_support_prompt_caching and not m.supports_prompt_caching:
                continue
            if constraints.must_support_stream_cancellation and not m.supports_stream_cancellation:
                continue
            if constraints.must_support_vision:
                if "image" not in (m.input_modalities or []):
                    continue
            if constraints.must_be_multimodal:
                modality_count = len(m.input_modalities or []) + len(m.output_modalities or [])
                if modality_count < CONTEXT_THRESHOLD_MINIMUM_MULTIMODAL:
                    continue
            if constraints.min_context_tokens and m.max_tokens:
                if m.max_tokens < constraints.min_context_tokens:
                    continue
            if constraints.max_cost_per_1m_tokens is not None:
                cost = calculate_cost_per_1m_tokens(m)
                if cost > constraints.max_cost_per_1m_tokens:
                    continue
            result.append(m)
        return result

    def _calculate_scores(
        self,
        models: List[ModelCatalog],
        priorities: ComparisonPriorities,
        capability_weights: CapabilityWeights,
        cost_direction: str,
    ) -> List[ModelScore]:
        """Calculate weighted scores for all models."""
        # Convert priorities to numeric weights
        weights = {
            "cost": WEIGHT_LEVELS.get(priorities.cost, 0),
            "context": WEIGHT_LEVELS.get(priorities.context, 0),
            "capabilities": WEIGHT_LEVELS.get(priorities.capabilities, 0),
            "multimodality": WEIGHT_LEVELS.get(priorities.multimodality, 0),
            "availability": WEIGHT_LEVELS.get(priorities.availability, 0),
        }

        # Calculate raw metrics
        costs = [calculate_cost_per_1m_tokens(m) for m in models]
        contexts = [float(m.max_tokens or 0) for m in models]

        # Capability scores with custom weights
        cap_scores = []
        for m in models:
            score = 0.0
            score += capability_weights.functions if m.supports_functions else 0.0
            score += capability_weights.structured_outputs if m.supports_structured_outputs else 0.0
            score += capability_weights.reasoning if m.supports_reasoning else 0.0
            score += capability_weights.prompt_caching if m.supports_prompt_caching else 0.0
            score += capability_weights.stream_cancellation if m.supports_stream_cancellation else 0.0
            cap_scores.append(score)

        # Multimodality scores
        mod_scores = [
            float(len(m.input_modalities or []) + len(m.output_modalities or []))
            for m in models
        ]

        # Availability (1 if available, 0 otherwise)
        avail_scores = [1.0 if m.is_available else 0.0 for m in models]

        # Normalize all metrics to [0, 1]
        cost_normalized = _normalize(costs, invert=(cost_direction != "higher"))
        context_normalized = _normalize(contexts)
        cap_normalized = _normalize(cap_scores)
        mod_normalized = _normalize(mod_scores)

        # Calculate final scores
        results = []
        for i, m in enumerate(models):
            breakdown = {
                "cost": cost_normalized[i] * weights["cost"],
                "context": context_normalized[i] * weights["context"],
                "capabilities": cap_normalized[i] * weights["capabilities"],
                "multimodality": mod_normalized[i] * weights["multimodality"],
                "availability": avail_scores[i] * weights["availability"],
            }
            total_score = sum(breakdown.values())

            # Calculate max possible score for percentage
            max_score = sum(weights.values())
            score_pct = (total_score / max_score * 100) if max_score > 0 else 0

            # Build capabilities list
            capabilities = []
            if m.supports_functions:
                capabilities.append("tools")
            if m.supports_structured_outputs:
                capabilities.append("json")
            if m.supports_reasoning:
                capabilities.append("reasoning")
            if "image" in (m.input_modalities or []):
                capabilities.append("vision")

            results.append(ModelScore(
                model_id=m.model_id,
                id=str(m.id),
                name=m.name,
                provider=m.provider,
                score=total_score,
                score_percentage=score_pct,
                breakdown=breakdown,
                cost_per_1m_tokens=costs[i],
                context_length=m.max_tokens or 0,
                context_display=format_context_length(m.max_tokens or 0),
                capabilities=capabilities,
            ))

        return results


# Singleton instance for convenience
comparison_service = ModelComparisonService()
