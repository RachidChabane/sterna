"""
Cost Calculator for External Services.

Calculates costs in USD for all billable external services.
Uses ServicePricing configuration from database with fallback defaults.
"""

import logging
from decimal import Decimal
from typing import Optional

from django.core.cache import cache
from django.db import models
from django.utils import timezone

from usage_quota.models import ServicePricing, ServiceType

logger = logging.getLogger(__name__)

# Fallback pricing when database config is not available
# These are approximate prices based on provider documentation as of 2024
FALLBACK_PRICING = {
    # ElevenLabs TTS - per 1K characters
    ServiceType.ELEVENLABS_TTS: {
        'default': Decimal('0.30'),  # ~$0.30/1K chars (Flash model)
        'eleven_flash_v2_5': Decimal('0.11'),
        'eleven_flash_v2': Decimal('0.11'),
        'eleven_turbo_v2_5': Decimal('0.18'),
        'eleven_turbo_v2': Decimal('0.18'),
        'eleven_multilingual_v2': Decimal('0.30'),
        'eleven_monolingual_v1': Decimal('0.30'),
    },
    # OpenAI TTS - per 1K characters
    ServiceType.OPENAI_TTS: {
        'default': Decimal('0.015'),  # $0.015/1K chars (tts-1)
        'tts-1': Decimal('0.015'),
        'tts-1-hd': Decimal('0.030'),
    },
    # Deepgram STT - per minute
    ServiceType.DEEPGRAM_STT: {
        'default': Decimal('0.0043'),  # ~$0.0043/min (nova-2)
        'nova-2': Decimal('0.0043'),
        'nova': Decimal('0.0043'),
        'enhanced': Decimal('0.0145'),
        'base': Decimal('0.0125'),
    },
    # Brave Search - per request
    ServiceType.BRAVE_SEARCH: {
        'default': Decimal('0.005'),  # ~$0.005/request (Pro plan)
    },
    # Image Generation - per image
    # Default fallback pricing - actual cost should come from API response
    ServiceType.IMAGE_GENERATION: {
        'default': Decimal('0.00'),  # Default - most image models are free or low cost
    },
    # MCP tool invocation - flat per-call placeholder
    ServiceType.MCP_TOOL_INVOCATION: {
        'default': Decimal('0.001'),
    },
    # Google Maps - per-endpoint pricing (keyed by endpoint name = model_id)
    ServiceType.GOOGLE_MAPS: {
        'default': Decimal('0.005'),
        'geocoding': Decimal('0.005'),
        'directions': Decimal('0.005'),
        'places_nearby': Decimal('0.032'),
        'places_details': Decimal('0.017'),
        'air_quality': Decimal('0.005'),
        'street_view': Decimal('0.007'),
        # Frontend photo-enrichment proxy (llm.views.google_maps_place_photo):
        # one Places Text Search (~$0.032) + one photo fetch (~$0.007).
        'places_photo': Decimal('0.039'),
    },
}

# Cache TTL for pricing lookups
PRICING_CACHE_TTL = 300  # 5 minutes


class CostCalculator:
    """
    Calculates costs for all external services in USD.

    Uses ServicePricing from database when available, falls back to
    hardcoded defaults when not configured.
    """

    def calculate_cost(
        self,
        service: str,
        model_id: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        character_count: int = 0,
        audio_seconds: float = 0,
        request_count: int = 1,
    ) -> Decimal:
        """
        Calculate cost for any service type.

        Args:
            service: Service type (from ServiceType choices)
            model_id: Optional model identifier for per-model pricing
            prompt_tokens: Input tokens (for LLM)
            completion_tokens: Output tokens (for LLM)
            character_count: Character count (for TTS)
            audio_seconds: Audio duration in seconds (for STT)
            request_count: Number of requests (for search)

        Returns:
            Cost in USD as Decimal
        """
        if service == ServiceType.OPENROUTER:
            return self.calculate_openrouter_cost(
                model_id=model_id or 'unknown',
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        elif service == ServiceType.ELEVENLABS_TTS:
            return self.calculate_elevenlabs_cost(
                character_count=character_count,
                model_id=model_id,
            )
        elif service == ServiceType.OPENAI_TTS:
            return self.calculate_openai_tts_cost(
                character_count=character_count,
                model_id=model_id,
            )
        elif service == ServiceType.DEEPGRAM_STT:
            return self.calculate_deepgram_cost(
                audio_seconds=audio_seconds,
                model_id=model_id,
            )
        elif service == ServiceType.BRAVE_SEARCH:
            return self.calculate_brave_search_cost(
                request_count=request_count,
            )
        elif service == ServiceType.IMAGE_GENERATION:
            return self.calculate_image_generation_cost(
                model_id=model_id,
                request_count=request_count,
            )
        elif service == ServiceType.MCP_TOOL_INVOCATION:
            return self.calculate_mcp_invocation_cost(
                request_count=request_count,
            )
        elif service == ServiceType.GOOGLE_MAPS:
            return self.calculate_google_maps_cost(
                endpoint=model_id,
                request_count=request_count,
            )
        elif service == ServiceType.CODE_SESSION:
            # Real cost comes from Claude CLI's total_cost_usd reported
            # by the runner; the calculator returns 0 if the caller did
            # not pre-supply a cost.
            return Decimal('0')
        else:
            logger.warning(f"Unknown service type: {service}")
            return Decimal('0')

    def calculate_openrouter_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal:
        """
        Calculate OpenRouter LLM cost using existing CatalogService pricing.

        Leverages the existing pricing infrastructure in llm.catalog_service.
        """
        try:
            from llm.catalog_service import CatalogService
            catalog_service = CatalogService()
            cost_details = catalog_service.estimate_cost_detailed(
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            return cost_details.get('total_cost', Decimal('0'))
        except Exception as e:
            logger.warning(f"Failed to get OpenRouter pricing for {model_id}: {e}")
            # Fallback: rough estimate at $0.01/1K prompt, $0.02/1K completion
            prompt_cost = Decimal(str(prompt_tokens)) / 1000 * Decimal('0.01')
            completion_cost = Decimal(str(completion_tokens)) / 1000 * Decimal('0.02')
            return prompt_cost + completion_cost

    def calculate_elevenlabs_cost(
        self,
        character_count: int,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """
        Calculate ElevenLabs TTS cost.

        Pricing is per character, stored as price per 1K chars.
        """
        price_per_1k = self._get_tts_price(
            service=ServiceType.ELEVENLABS_TTS,
            model_id=model_id,
        )
        return Decimal(str(character_count)) / 1000 * price_per_1k

    def calculate_openai_tts_cost(
        self,
        character_count: int,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """
        Calculate OpenAI TTS cost.

        Pricing is per character, stored as price per 1K chars.
        """
        price_per_1k = self._get_tts_price(
            service=ServiceType.OPENAI_TTS,
            model_id=model_id,
        )
        return Decimal(str(character_count)) / 1000 * price_per_1k

    def calculate_deepgram_cost(
        self,
        audio_seconds: float,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """
        Calculate Deepgram STT cost.

        Pricing is per audio minute.
        """
        price_per_minute = self._get_stt_price(
            service=ServiceType.DEEPGRAM_STT,
            model_id=model_id,
        )
        audio_minutes = Decimal(str(audio_seconds)) / 60
        return audio_minutes * price_per_minute

    def calculate_brave_search_cost(
        self,
        request_count: int = 1,
    ) -> Decimal:
        """
        Calculate Brave Search API cost.

        Pricing is per search request.
        """
        price_per_request = self._get_search_price(
            service=ServiceType.BRAVE_SEARCH,
        )
        return Decimal(str(request_count)) * price_per_request

    def calculate_image_generation_cost(
        self,
        model_id: Optional[str] = None,
        request_count: int = 1,
    ) -> Decimal:
        """
        Calculate image generation cost.

        Pricing is per image generated, varies by provider and model.
        model_id format: provider/model (e.g., "google/gemini-2.0-flash-exp")
        """
        price_per_image = self._get_image_generation_price(model_id)
        return Decimal(str(request_count)) * price_per_image

    def calculate_mcp_invocation_cost(
        self,
        request_count: int = 1,
    ) -> Decimal:
        """MCP tool invocation: flat per-call rate from DB, fallback hardcoded."""
        pricing = self._get_pricing_from_db(
            ServiceType.MCP_TOOL_INVOCATION,
            None,
        )
        if pricing and pricing.price_per_request is not None:
            return Decimal(str(request_count)) * pricing.price_per_request
        fallback = FALLBACK_PRICING.get(ServiceType.MCP_TOOL_INVOCATION, {})
        return Decimal(str(request_count)) * fallback.get(
            'default', Decimal('0.001')
        )

    def calculate_google_maps_cost(
        self,
        endpoint: Optional[str] = None,
        request_count: int = 1,
    ) -> Decimal:
        """Google Maps: per-endpoint pricing (model_id = endpoint name)."""
        pricing = self._get_pricing_from_db(
            ServiceType.GOOGLE_MAPS,
            endpoint,
        )
        if pricing and pricing.price_per_request is not None:
            return Decimal(str(request_count)) * pricing.price_per_request
        fallback = FALLBACK_PRICING.get(ServiceType.GOOGLE_MAPS, {})
        rate = fallback.get(endpoint, fallback.get('default', Decimal('0.005')))
        return Decimal(str(request_count)) * rate

    def _get_image_generation_price(
        self,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """Get image generation price per image from DB or fallback."""
        # Try database first
        pricing = self._get_pricing_from_db(ServiceType.IMAGE_GENERATION, model_id)
        if pricing and pricing.price_per_request:
            return pricing.price_per_request

        # Fallback to hardcoded prices
        fallback = FALLBACK_PRICING.get(ServiceType.IMAGE_GENERATION, {})
        if model_id and model_id in fallback:
            return fallback[model_id]
        return fallback.get('default', Decimal('0.02'))

    def estimate_openrouter_cost(
        self,
        model_id: str,
        estimated_tokens: int,
    ) -> Decimal:
        """
        Estimate OpenRouter cost for quota pre-check.

        Uses a 50/50 split between input/output tokens for estimation.
        """
        prompt_tokens = estimated_tokens // 2
        completion_tokens = estimated_tokens - prompt_tokens
        return self.calculate_openrouter_cost(
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _get_tts_price(
        self,
        service: str,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """Get TTS price per 1K characters from DB or fallback."""
        # Try database first
        pricing = self._get_pricing_from_db(service, model_id)
        if pricing and pricing.price_per_1k_chars:
            return pricing.price_per_1k_chars

        # Fallback to hardcoded prices
        fallback = FALLBACK_PRICING.get(service, {})
        if model_id and model_id in fallback:
            return fallback[model_id]
        return fallback.get('default', Decimal('0.01'))

    def _get_stt_price(
        self,
        service: str,
        model_id: Optional[str] = None,
    ) -> Decimal:
        """Get STT price per minute from DB or fallback."""
        pricing = self._get_pricing_from_db(service, model_id)
        if pricing and pricing.price_per_minute:
            return pricing.price_per_minute

        fallback = FALLBACK_PRICING.get(service, {})
        if model_id and model_id in fallback:
            return fallback[model_id]
        return fallback.get('default', Decimal('0.01'))

    def _get_search_price(
        self,
        service: str,
    ) -> Decimal:
        """Get search price per request from DB or fallback."""
        pricing = self._get_pricing_from_db(service, None)
        if pricing and pricing.price_per_request:
            return pricing.price_per_request

        fallback = FALLBACK_PRICING.get(service, {})
        return fallback.get('default', Decimal('0.005'))

    def _get_pricing_from_db(
        self,
        service: str,
        model_id: Optional[str] = None,
    ) -> Optional[ServicePricing]:
        """
        Get active pricing from database with caching.

        Looks for model-specific pricing first, then service-wide default.
        """
        cache_key = f"service_pricing:{service}:{model_id or 'default'}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached if cached != 'none' else None

        now = timezone.now()

        # Try model-specific pricing first
        if model_id:
            pricing = ServicePricing.objects.filter(
                service=service,
                model_id=model_id,
                is_active=True,
                effective_from__lte=now,
            ).filter(
                models.Q(effective_until__isnull=True) |
                models.Q(effective_until__gte=now)
            ).order_by('-effective_from').first()

            if pricing:
                cache.set(cache_key, pricing, PRICING_CACHE_TTL)
                return pricing

        # Try service-wide default
        pricing = ServicePricing.objects.filter(
            service=service,
            model_id='',
            is_active=True,
            effective_from__lte=now,
        ).filter(
            models.Q(effective_until__isnull=True) |
            models.Q(effective_until__gte=now)
        ).order_by('-effective_from').first()

        if pricing:
            cache.set(cache_key, pricing, PRICING_CACHE_TTL)
        else:
            cache.set(cache_key, 'none', PRICING_CACHE_TTL)

        return pricing



# Singleton instance
_cost_calculator: Optional[CostCalculator] = None


def get_cost_calculator() -> CostCalculator:
    """Get the singleton CostCalculator instance."""
    global _cost_calculator
    if _cost_calculator is None:
        _cost_calculator = CostCalculator()
    return _cost_calculator
