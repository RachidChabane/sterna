"""
Pricing service for Knowledge Base operations.
Fetches dynamic pricing from OpenRouter catalog.
"""

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# Default pricing for common embedding models (price per 1M tokens in USD)
# Source: OpenAI pricing as of 2024
DEFAULT_EMBEDDING_PRICING = {
    'openai/text-embedding-3-large': Decimal('0.13'),    # $0.13 per 1M tokens
    'openai/text-embedding-3-small': Decimal('0.02'),    # $0.02 per 1M tokens
    'openai/text-embedding-ada-002': Decimal('0.10'),    # $0.10 per 1M tokens
}


class KnowledgePricingService:
    """
    Fetches embedding model pricing from OpenRouter catalog.
    Falls back to ServicePricing table, then to hardcoded defaults.
    """

    def __init__(self):
        self._pricing_cache: dict = {}
        self._cache_ttl = 300  # 5 minutes

    def get_embedding_cost(self, model_id: str, token_count: int) -> Decimal:
        """
        Calculate embedding cost based on model pricing from catalog.
        Embedding models typically only charge for input tokens.

        Args:
            model_id: The embedding model identifier
            token_count: Number of tokens to embed

        Returns:
            Cost in USD as Decimal
        """
        pricing = self._get_model_pricing(model_id)
        if pricing:
            # Embedding = input tokens only
            cost_per_token = pricing.get('prompt_price', Decimal('0'))
            return (Decimal(token_count) / Decimal(1_000_000)) * cost_per_token

        # Fallback to ServicePricing table
        return self._get_fallback_pricing(model_id, token_count)

    def _get_model_pricing(self, model_id: str) -> Optional[dict]:
        """Fetch pricing from OpenRouter model catalog."""
        try:
            from llm.models import ModelCatalog
            model = ModelCatalog.objects.filter(model_id=model_id).first()
            if model:
                return {
                    'prompt_price': model.prompt_price or Decimal('0'),
                    'completion_price': model.completion_price or Decimal('0'),
                }
        except Exception as e:
            logger.warning(f"Failed to fetch model pricing: {e}")
        return None

    def _get_fallback_pricing(self, model_id: str, token_count: int) -> Decimal:
        """Fallback to ServicePricing table, then to hardcoded defaults."""
        # Try ServicePricing table first
        try:
            from usage_quota.models import ServicePricing, ServiceType

            pricing = ServicePricing.objects.filter(
                service=ServiceType.KNOWLEDGE_BASE_EMBEDDING,
                model_id=model_id,
                is_active=True,
            ).first()

            if pricing and pricing.price_per_1m_input_tokens:
                return (
                    Decimal(token_count) / Decimal(1_000_000)
                ) * pricing.price_per_1m_input_tokens

        except Exception as e:
            logger.warning(f"Failed to get ServicePricing: {e}")

        # Fall back to hardcoded defaults for known models
        if model_id in DEFAULT_EMBEDDING_PRICING:
            price_per_1m = DEFAULT_EMBEDDING_PRICING[model_id]
            return (Decimal(token_count) / Decimal(1_000_000)) * price_per_1m

        # If no pricing found, log warning and return 0 (don't block the operation)
        logger.warning(f"No pricing found for embedding model: {model_id}")
        return Decimal('0')
