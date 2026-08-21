"""
Embedding service for generating vector embeddings.
"""

import logging
from typing import List, Optional, TYPE_CHECKING

from django.conf import settings

from ..config import config

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Handles embedding generation via configurable API.

    Note: Cost calculation is handled by KnowledgePricingService
    to maintain single responsibility and use dynamic pricing.
    """

    def __init__(self, user: Optional['User'] = None):
        from usage_quota.constants import BILLING_ORIGIN_PLATFORM

        self.model = config.embedding_model
        self.dimensions = config.embedding_dimensions
        self._api_url = config.embedding_api_url
        self._user = user
        # Resolved lazily on first API call so constructing an instance
        # without a user (Celery startup) doesn't touch the DB.
        self._billing_origin: Optional[str] = (
            None if user is not None else BILLING_ORIGIN_PLATFORM
        )

    @property
    def billing_origin(self) -> str:
        """Return the cached billing_origin (resolves on first read)."""
        from usage_quota.constants import BILLING_ORIGIN_PLATFORM
        if self._billing_origin is None:
            self._billing_origin = self._resolve_origin()
        return self._billing_origin or BILLING_ORIGIN_PLATFORM

    def _resolve_origin(self) -> str:
        from usage_quota.constants import BILLING_ORIGIN_PLATFORM
        if not self._user:
            return BILLING_ORIGIN_PLATFORM
        try:
            from llm.services.api_key_resolver import resolve_with_origin
            _, origin = resolve_with_origin(user=self._user)
            return origin
        except Exception:
            return BILLING_ORIGIN_PLATFORM

    def _resolve_api_key(self) -> str:
        if not self._user:
            return settings.OPENROUTER_API_KEY
        try:
            from llm.services.api_key_resolver import resolve_with_origin
            api_key, origin = resolve_with_origin(user=self._user)
            self._billing_origin = origin
            return api_key
        except Exception:
            return settings.OPENROUTER_API_KEY

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for single text."""
        return self._call_api([text])[0]

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            all_embeddings.extend(self._call_api(batch))
        return all_embeddings

    def _call_api(self, inputs: List[str]) -> List[List[float]]:
        """
        Call embedding API with retry logic.

        DRY - single implementation for all embedding requests.
        """
        import httpx
        from tenacity import (
            retry,
            stop_after_attempt,
            wait_exponential,
            retry_if_exception_type,
        )

        api_key = self._resolve_api_key()

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        )
        def _request():
            response = httpx.post(
                self._api_url,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': self.model,
                    'input': inputs,
                    'dimensions': self.dimensions,  # text-embedding-3-large supports dimension reduction
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()

        data = _request()
        return [item['embedding'] for item in data['data']]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return int(len(text.split()) * config.tokens_per_word_estimate)
