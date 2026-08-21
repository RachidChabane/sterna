"""
Configuration and constants for model comparison scoring.
Avoid magic numbers by centralizing thresholds and mappings here.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

PriorityLevel = Literal["off", "nice", "important", "critical"]
CostDirection = Literal["lower", "higher"]
PresetId = Literal["balanced", "budget", "long_context", "tool_use", "multimodal", "coding"]


# Discrete weight levels - maps priority labels to numeric weights
WEIGHT_LEVELS: Dict[PriorityLevel, int] = {
    "off": 0,
    "nice": 1,
    "important": 2,
    "critical": 3,
}


# Normalization safeguard to avoid division by zero
NORMALIZATION_EPSILON = 1e-9


# Context length thresholds (tokens)
CONTEXT_THRESHOLD_LONG = 32_000
CONTEXT_THRESHOLD_MINIMUM_MULTIMODAL = 2  # input + output modalities combined


# Cost threshold for budget preset (USD per 1M tokens)
COST_THRESHOLD_BUDGET = 10.0


@dataclass(frozen=True)
class CapabilityWeights:
    """Weights for individual capability scoring."""
    functions: float = 1.0
    structured_outputs: float = 1.0
    reasoning: float = 1.0
    prompt_caching: float = 1.0
    stream_cancellation: float = 1.0


@dataclass(frozen=True)
class ComparisonConstraints:
    """Hard constraints that filter out models."""
    must_support_functions: bool = False
    must_support_structured_outputs: bool = False
    must_support_reasoning: bool = False
    must_support_prompt_caching: bool = False
    must_support_stream_cancellation: bool = False
    must_be_available: bool = False
    must_be_multimodal: bool = False
    must_support_vision: bool = False
    min_context_tokens: Optional[int] = None
    max_cost_per_1m_tokens: Optional[float] = None


@dataclass(frozen=True)
class ComparisonPriorities:
    """Priority levels for each scoring dimension."""
    cost: PriorityLevel = "important"
    context: PriorityLevel = "important"
    capabilities: PriorityLevel = "important"
    multimodality: PriorityLevel = "nice"
    availability: PriorityLevel = "nice"


@dataclass(frozen=True)
class ComparisonPreset:
    """Complete preset configuration."""
    id: PresetId
    label: str
    description: str
    priorities: ComparisonPriorities
    constraints: ComparisonConstraints = field(default_factory=ComparisonConstraints)
    capability_weights: CapabilityWeights = field(default_factory=CapabilityWeights)
    cost_direction: CostDirection = "lower"


# Default priorities (balanced)
DEFAULT_PRIORITIES = ComparisonPriorities()

# Default constraints (all disabled)
DEFAULT_CONSTRAINTS = ComparisonConstraints()


# All available presets
COMPARISON_PRESETS: Dict[PresetId, ComparisonPreset] = {
    "balanced": ComparisonPreset(
        id="balanced",
        label="Balanced",
        description="Even trade-off of cost, capacity, and capabilities",
        priorities=ComparisonPriorities(),
    ),
    "budget": ComparisonPreset(
        id="budget",
        label="Budget",
        description="Minimize cost for typical workloads",
        priorities=ComparisonPriorities(
            cost="critical",
            context="nice",
            capabilities="nice",
            multimodality="off",
            availability="important",
        ),
        constraints=ComparisonConstraints(
            max_cost_per_1m_tokens=COST_THRESHOLD_BUDGET,
        ),
    ),
    "long_context": ComparisonPreset(
        id="long_context",
        label="Long Context",
        description="Prioritize very large context windows",
        priorities=ComparisonPriorities(
            cost="nice",
            context="critical",
            capabilities="important",
            multimodality="off",
            availability="important",
        ),
        constraints=ComparisonConstraints(
            min_context_tokens=CONTEXT_THRESHOLD_LONG,
        ),
    ),
    "tool_use": ComparisonPreset(
        id="tool_use",
        label="Tool Use",
        description="Prefer models that excel at tool use and JSON outputs",
        priorities=ComparisonPriorities(
            cost="important",
            context="nice",
            capabilities="critical",
            multimodality="off",
            availability="important",
        ),
        constraints=ComparisonConstraints(
            must_support_functions=True,
            must_support_structured_outputs=True,
        ),
    ),
    "multimodal": ComparisonPreset(
        id="multimodal",
        label="Multimodal",
        description="Favor models supporting multiple input/output modalities",
        priorities=ComparisonPriorities(
            cost="nice",
            context="nice",
            capabilities="important",
            multimodality="critical",
            availability="important",
        ),
        constraints=ComparisonConstraints(
            must_be_multimodal=True,
        ),
    ),
    "coding": ComparisonPreset(
        id="coding",
        label="Coding",
        description="Optimize for coding workloads with reasoning emphasis",
        priorities=ComparisonPriorities(
            cost="nice",
            context="critical",
            capabilities="critical",
            multimodality="off",
            availability="important",
        ),
        capability_weights=CapabilityWeights(
            reasoning=3.0,
            functions=2.0,
            structured_outputs=1.0,
            prompt_caching=0.0,
            stream_cancellation=0.0,
        ),
        cost_direction="higher",  # Higher cost often correlates with quality for coding
    ),
}


def get_preset(preset_id: str) -> ComparisonPreset:
    """Get a preset by ID, defaulting to balanced."""
    return COMPARISON_PRESETS.get(preset_id, COMPARISON_PRESETS["balanced"])


def get_all_preset_ids() -> List[PresetId]:
    """Get list of all available preset IDs."""
    return list(COMPARISON_PRESETS.keys())
