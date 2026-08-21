"""
Consigliere prompts module.

Contains system prompts and templates for the Consigliere AI.
"""

from .system_prompts import (
    CONSIGLIERE_SYSTEM_PROMPT,
    ANALYSIS_PROMPT_TEMPLATE,
    RECOMMENDATION_PROMPT_TEMPLATE,
    AI_COMPLETE_ANALYSIS_TEMPLATE,
)

__all__ = [
    "CONSIGLIERE_SYSTEM_PROMPT",
    "ANALYSIS_PROMPT_TEMPLATE",
    "RECOMMENDATION_PROMPT_TEMPLATE",
    "AI_COMPLETE_ANALYSIS_TEMPLATE",
]
