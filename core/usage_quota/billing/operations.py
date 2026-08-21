"""
Billable Operation Data Classes.

Provides standard interfaces for all billable operations across services.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any

from usage_quota.models import ServiceType, FeatureType


@dataclass
class BillableOperation:
    """
    Represents a single billable operation.

    This is the standard interface for ALL billable operations.
    Services fill in relevant fields; others remain at default values.

    Examples:
        # LLM completion
        op = BillableOperation(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            model_id='anthropic/claude-3-5-sonnet',
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal('0.015'),
        )

        # TTS synthesis
        op = BillableOperation(
            service=ServiceType.ELEVENLABS_TTS,
            feature=FeatureType.VOICE_ROOM,
            model_id='eleven_flash_v2_5',
            character_count=500,
        )

        # Search request
        op = BillableOperation(
            service=ServiceType.BRAVE_SEARCH,
            feature=FeatureType.CHAT,
            request_count=1,
        )
    """
    # Required: Service and feature identification
    service: ServiceType
    feature: FeatureType = FeatureType.CHAT

    # Model identification (for LLM, TTS, STT)
    model_id: str = ""

    # LLM-specific metrics
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # TTS-specific metrics
    character_count: int = 0

    # STT-specific metrics
    audio_seconds: float = 0.0

    # Search-specific metrics
    request_count: int = 0

    # Computed cost (filled by BillingService if not provided)
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    # Tracking metadata
    request_id: str = ""
    session_id: str = ""
    extra_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Who pays for this op: 'platform' (default) or 'byok'. The BillingService
    # is the sole enforcement point — it rejects 'byok' for PLATFORM_ONLY_SERVICES.
    billing_origin: str = "platform"

    @property
    def total_tokens(self) -> int:
        """Total tokens for LLM operations."""
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'service': self.service.value if hasattr(self.service, 'value') else str(self.service),
            'feature': self.feature.value if hasattr(self.feature, 'value') else str(self.feature),
            'model_id': self.model_id,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
            'character_count': self.character_count,
            'audio_seconds': self.audio_seconds,
            'request_count': self.request_count,
            'cost_usd': str(self.cost_usd),
            'request_id': self.request_id,
            'session_id': self.session_id,
            'extra_data': self.extra_data,
            'timestamp': self.timestamp.isoformat(),
            'billing_origin': self.billing_origin,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BillableOperation':
        """Create from dictionary."""
        return cls(
            service=ServiceType(data['service']),
            feature=FeatureType(data.get('feature', 'chat')),
            model_id=data.get('model_id', ''),
            prompt_tokens=data.get('prompt_tokens', 0),
            completion_tokens=data.get('completion_tokens', 0),
            character_count=data.get('character_count', 0),
            audio_seconds=data.get('audio_seconds', 0.0),
            request_count=data.get('request_count', 0),
            cost_usd=Decimal(data.get('cost_usd', '0')),
            request_id=data.get('request_id', ''),
            session_id=data.get('session_id', ''),
            extra_data=data.get('extra_data', {}),
            timestamp=datetime.fromisoformat(data['timestamp']) if 'timestamp' in data else datetime.utcnow(),
            billing_origin=data.get('billing_origin', 'platform'),
        )


@dataclass
class QuotaStatus:
    """
    User's current quota status.

    Returned by BillingService.check_quota() and get_quota_status().
    """
    allowed: bool
    weekly_limit_usd: Decimal
    weekly_used_usd: Decimal
    weekly_remaining_usd: Decimal
    session_limit_usd: Decimal
    session_used_usd: Decimal
    session_remaining_usd: Decimal
    weekly_resets_in_seconds: int
    session_resets_in_seconds: int
    denial_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'allowed': self.allowed,
            'weekly_limit_usd': float(self.weekly_limit_usd),
            'weekly_used_usd': float(self.weekly_used_usd),
            'weekly_remaining_usd': float(self.weekly_remaining_usd),
            'session_limit_usd': float(self.session_limit_usd),
            'session_used_usd': float(self.session_used_usd),
            'session_remaining_usd': float(self.session_remaining_usd),
            'weekly_resets_in_seconds': self.weekly_resets_in_seconds,
            'session_resets_in_seconds': self.session_resets_in_seconds,
            'denial_reason': self.denial_reason,
        }
