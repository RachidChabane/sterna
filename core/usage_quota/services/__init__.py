"""
Usage Quota Services.

Provides centralized usage tracking and quota enforcement.

Pricing Configuration:
    All external service pricing is centralized in FALLBACK_PRICING dict
    in cost_calculator.py. Modify there to update costs for:
    - Brave Search: $0.005/request ($5/1000)
    - ElevenLabs TTS: varies by model
    - OpenAI TTS: $0.015-0.030/1K chars
    - Deepgram STT: ~$0.0043/min
"""

from .quota_service import (
    QuotaService,
    QuotaCheckResult,
    UsageDeductResult,
    QuotaInfo,
    get_quota_service,
    WEEKLY_WINDOW_DAYS,
    SESSION_WINDOW_HOURS,
)
from .cost_calculator import (
    CostCalculator,
    get_cost_calculator,
    FALLBACK_PRICING,
)

__all__ = [
    # Quota Service
    'QuotaService',
    'QuotaCheckResult',
    'UsageDeductResult',
    'QuotaInfo',
    'get_quota_service',
    'WEEKLY_WINDOW_DAYS',
    'SESSION_WINDOW_HOURS',
    # Cost Calculator
    'CostCalculator',
    'get_cost_calculator',
    'FALLBACK_PRICING',
]
