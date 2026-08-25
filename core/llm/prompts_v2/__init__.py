"""
Prompts V2 Module

Optimized prompt building with caching support and modular layers.
Based on Anthropic's Advanced Tool Use patterns.
"""

from .modular_prompts import (
    PromptLayer,
    PromptSection,
    STATIC_CORE_PROMPTS,
    CONDITIONAL_PROMPTS,
)
from .optimized_builder import (
    OptimizedPromptBuilder,
    get_prompt_builder,
    estimate_system_prompt,
)

__all__ = [
    "PromptLayer",
    "PromptSection",
    "STATIC_CORE_PROMPTS",
    "CONDITIONAL_PROMPTS",
    "OptimizedPromptBuilder",
    "get_prompt_builder",
    "estimate_system_prompt",
]
