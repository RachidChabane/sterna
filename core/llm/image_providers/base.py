"""
Base classes and types for image generation providers.
"""

import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ImageProviderError(Exception):
    """Base exception for image provider errors."""
    pass


class RateLimitError(ImageProviderError):
    """Raised when provider rate limit is exceeded."""
    pass


class QuotaExhaustedError(ImageProviderError):
    """Raised when provider quota is exhausted."""
    pass


class ProviderUnavailableError(ImageProviderError):
    """Raised when provider is temporarily unavailable."""
    pass


class AllProvidersFailedError(ImageProviderError):
    """Raised when all providers in the chain have failed."""
    pass


@dataclass
class ImageGenerationResult:
    """Result from image generation."""
    image_data: bytes
    mime_type: str
    provider: str
    model: str
    width: int = 1024
    height: int = 1024
    generation_time_ms: int = 0
    cost_usd: Optional[Decimal] = None
    revised_prompt: Optional[str] = None

    def generate_asset_id(self) -> str:
        """Generate a unique asset ID based on content hash."""
        content_hash = hashlib.sha256(self.image_data).hexdigest()[:16]
        return f"img_{content_hash}_{uuid.uuid4().hex[:8]}"

    def get_sha256(self) -> str:
        """Get SHA256 hash of the image data."""
        return hashlib.sha256(self.image_data).hexdigest()


class BaseImageProvider(ABC):
    """Abstract base class for image generation providers."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
    ) -> ImageGenerationResult:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            model: Model ID to use (e.g., "gemini-2.0-flash-exp")
            aspect_ratio: Desired aspect ratio (e.g., "1:1", "16:9")
            resolution: Output resolution - "1K", "2K", or "4K" (model dependent)

        Returns:
            ImageGenerationResult with the generated image data

        Raises:
            RateLimitError: If rate limit is exceeded
            QuotaExhaustedError: If quota is exhausted
            ProviderUnavailableError: If provider is temporarily unavailable
            ImageProviderError: For other errors
        """
        pass

    @abstractmethod
    async def edit(
        self,
        image_data: bytes,
        prompt: str,
        model: str,
        mask_data: Optional[bytes] = None,
    ) -> ImageGenerationResult:
        """
        Edit an existing image based on a text prompt.

        Args:
            image_data: Original image bytes
            prompt: Description of the edit to make
            model: Model ID to use
            mask_data: Optional mask indicating areas to edit

        Returns:
            ImageGenerationResult with the edited image data

        Raises:
            ImageProviderError: If editing fails or is not supported
        """
        pass

    def _get_dimensions_from_aspect_ratio(self, aspect_ratio: str) -> tuple[int, int]:
        """Convert aspect ratio string to width/height dimensions."""
        ratios = {
            "1:1": (1024, 1024),
            "16:9": (1792, 1024),
            "9:16": (1024, 1792),
            "4:3": (1365, 1024),
            "3:4": (1024, 1365),
            "3:2": (1536, 1024),
            "2:3": (1024, 1536),
        }
        return ratios.get(aspect_ratio, (1024, 1024))

    def _start_timer(self) -> float:
        """Start a timer for measuring generation time."""
        return time.time()

    def _get_elapsed_ms(self, start_time: float) -> int:
        """Get elapsed time in milliseconds since start_time."""
        return int((time.time() - start_time) * 1000)
