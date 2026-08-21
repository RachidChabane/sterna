"""
OpenRouter provider for image generation.

Uses OpenRouter's unified API - same as normal chat messages.
No hardcoded models - just passes through the specified model.
"""

import base64
import logging
import re
from decimal import Decimal
from typing import Optional

import httpx
from django.conf import settings


from .base import (
    BaseImageProvider,
    ImageGenerationResult,
    ImageProviderError,
    RateLimitError,
    QuotaExhaustedError,
    ProviderUnavailableError,
)
from .constants import get_openrouter_model_id

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseImageProvider):
    """
    OpenRouter provider for image generation.

    Uses the user's provisioned OpenRouter API key, same as normal chat.
    No hardcoded model mappings - just passes through the model ID.
    """

    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        self.site_url = settings.OPENROUTER_SITE_URL
        self.app_name = "Sterna"

    def is_configured(self) -> bool:
        """Always available - uses user's key at call time."""
        return True

    def _get_api_key(self, api_key: Optional[str] = None) -> str:
        key = api_key or self._api_key
        if not key:
            raise ImageProviderError(
                "No OpenRouter API key provided. User may not have a provisioned key."
            )
        return key

    async def generate(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        api_key: Optional[str] = None,
    ) -> ImageGenerationResult:
        """
        Generate an image using OpenRouter.

        Args:
            prompt: Text description
            model: Canonical model ID (e.g., "google/gemini-2.5-flash-image")
            aspect_ratio: Desired aspect ratio
            resolution: Output resolution (passed to model if supported)
            api_key: User's OpenRouter API key
        """
        key = self._get_api_key(api_key)
        start_time = self._start_timer()

        # Convert canonical model ID to OpenRouter format
        openrouter_model = get_openrouter_model_id(model)

        payload = {
            "model": openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image: {prompt}"
                }
            ],
            # Required for OpenRouter image generation
            "modalities": ["image", "text"],
        }

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 429:
                    raise RateLimitError("OpenRouter rate limit exceeded")
                if response.status_code == 402:
                    raise QuotaExhaustedError("OpenRouter credits exhausted")
                if response.status_code == 403:
                    raise ImageProviderError(f"OpenRouter access denied: {response.text}")
                if response.status_code >= 500:
                    raise ProviderUnavailableError(f"OpenRouter server error: {response.status_code}")

                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            raise ProviderUnavailableError("OpenRouter request timeout")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"OpenRouter connection error: {e}")

        # Extract image from response
        image_data, mime_type = self._extract_image_from_response(data)
        width, height = self._get_dimensions_from_aspect_ratio(aspect_ratio)

        # Get cost from response if available
        cost_usd = self._extract_cost_from_response(data)

        return ImageGenerationResult(
            image_data=image_data,
            mime_type=mime_type,
            provider=self.name,
            model=model,
            width=width,
            height=height,
            generation_time_ms=self._get_elapsed_ms(start_time),
            cost_usd=cost_usd,
        )

    def _extract_image_from_response(self, data: dict) -> tuple[bytes, str]:
        """Extract image data from OpenRouter response."""
        choices = data.get("choices", [])
        if not choices:
            error = data.get("error", {})
            if error:
                error_msg = error.get("message", str(error))
                if "rate" in error_msg.lower() or "limit" in error_msg.lower():
                    raise RateLimitError(f"OpenRouter: {error_msg}")
                raise ImageProviderError(f"OpenRouter error: {error_msg}")
            raise ImageProviderError("No choices in OpenRouter response")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        # Check for images array (OpenRouter format)
        if "images" in message:
            images = message["images"]
            if images and len(images) > 0:
                image_item = images[0]
                # Handle dict format: {"type": "image_url", "image_url": {"url": "data:..."}}
                if isinstance(image_item, dict):
                    image_url = image_item.get("image_url", {}).get("url", "")
                else:
                    image_url = image_item
                if image_url and image_url.startswith("data:"):
                    return self._parse_data_url(image_url)

        # Try to find base64 image in content
        if content:
            # Look for data URL pattern
            match = re.search(
                r'data:(image/[a-zA-Z]+);base64,([A-Za-z0-9+/=]+)',
                content
            )
            if match:
                mime_type = match.group(1)
                image_data = base64.b64decode(match.group(2))
                return image_data, mime_type

            # Look for markdown image
            md_match = re.search(r'!\[.*?\]\((data:image/[^)]+)\)', content)
            if md_match:
                return self._parse_data_url(md_match.group(1))

        logger.error(f"[OpenRouter] Could not extract image from response: {content[:500]}")
        raise ImageProviderError("No image data found in OpenRouter response")

    def _extract_cost_from_response(self, data: dict) -> Optional[Decimal]:
        """Extract cost from OpenRouter response if available."""
        try:
            usage = data.get("usage", {})
            # OpenRouter may include cost info in various formats
            if "total_cost" in usage:
                return Decimal(str(usage["total_cost"]))
            # Fallback: calculate from tokens if pricing available
            return None
        except Exception:
            return None

    def _parse_data_url(self, data_url: str) -> tuple[bytes, str]:
        """Parse a data URL and return (bytes, mime_type)."""
        match = re.match(r'data:(image/[a-zA-Z]+);base64,(.+)', data_url)
        if match:
            return base64.b64decode(match.group(2)), match.group(1)
        raise ImageProviderError("Invalid data URL format")

    async def edit(
        self,
        image_data: bytes,
        prompt: str,
        model: str,
        mask_data: Optional[bytes] = None,
        api_key: Optional[str] = None,
    ) -> ImageGenerationResult:
        """Edit an image using OpenRouter."""
        key = self._get_api_key(api_key)
        start_time = self._start_timer()

        # Convert canonical model ID to OpenRouter format
        openrouter_model = get_openrouter_model_id(model)

        # Encode image as base64 data URL
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        image_url = f"data:image/png;base64,{image_base64}"

        payload = {
            "model": openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": f"Edit this image: {prompt}"}
                    ]
                }
            ],
            # Required for OpenRouter image generation
            "modalities": ["image", "text"],
        }

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 429:
                    raise RateLimitError("OpenRouter rate limit exceeded")
                if response.status_code == 402:
                    raise QuotaExhaustedError("OpenRouter credits exhausted")
                if response.status_code >= 500:
                    raise ProviderUnavailableError(f"OpenRouter server error: {response.status_code}")

                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            raise ProviderUnavailableError("OpenRouter request timeout")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"OpenRouter connection error: {e}")

        image_data, mime_type = self._extract_image_from_response(data)
        cost_usd = self._extract_cost_from_response(data)

        return ImageGenerationResult(
            image_data=image_data,
            mime_type=mime_type,
            provider=self.name,
            model=model,
            width=1024,
            height=1024,
            generation_time_ms=self._get_elapsed_ms(start_time),
            cost_usd=cost_usd,
        )
