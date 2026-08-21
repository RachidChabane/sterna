"""
Google AI Studio provider for image generation.

Uses Gemini models via Google's Generative Language API.
Free tier: 5 RPM, 25 RPD, 250K TPM
"""

import base64
import logging
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
from .constants import get_google_ai_studio_model_id

logger = logging.getLogger(__name__)


class GoogleAIStudioProvider(BaseImageProvider):
    """
    Google AI Studio provider using Gemini models.

    Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    Auth: x-goog-api-key header
    """

    name = "google_ai_studio"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        self.api_key = getattr(settings, "GOOGLE_AI_STUDIO_API_KEY", "")

    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        return bool(self.api_key)

    def _normalize_model_id(self, model: str) -> str:
        """
        Convert canonical model ID to Google AI Studio format.

        Uses the centralized constants to map model IDs.
        Example: "google/gemini-2.5-flash-image" -> "gemini-2.5-flash-image"
        """
        return get_google_ai_studio_model_id(model)

    async def generate(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
    ) -> ImageGenerationResult:
        """Generate an image using Google AI Studio.

        Args:
            prompt: Text description of the image to generate
            model: Model ID (will be normalized to remove google/ prefix)
            aspect_ratio: Image aspect ratio (1:1, 16:9, etc.)
            resolution: Output resolution - "1K", "2K", or "4K" (Gemini 3 Pro only)
        """
        if not self.is_configured():
            raise ImageProviderError("Google AI Studio API key not configured")

        start_time = self._start_timer()
        normalized_model = self._normalize_model_id(model)
        url = f"{self.BASE_URL}/models/{normalized_model}:generateContent"

        # Build generation config
        generation_config: dict = {
            "responseModalities": ["TEXT", "IMAGE"],
        }

        # Add resolution for Gemini 3 Pro Image (supports 1K, 2K, 4K)
        # Must use uppercase 'K'
        if resolution and resolution.upper() in ("1K", "2K", "4K"):
            generation_config["imageSize"] = resolution.upper()

        # Build the request payload
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": generation_config,
        }

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                # Handle rate limiting
                if response.status_code == 429:
                    logger.warning("[GoogleAIStudio] Rate limit exceeded")
                    raise RateLimitError("Google AI Studio rate limit exceeded")

                # Handle quota exhausted
                if response.status_code == 403:
                    error_text = response.text
                    if "quota" in error_text.lower():
                        logger.warning("[GoogleAIStudio] Quota exhausted")
                        raise QuotaExhaustedError("Google AI Studio quota exhausted")
                    raise ImageProviderError(f"Access denied: {error_text}")

                # Handle server errors
                if response.status_code >= 500:
                    logger.error(f"[GoogleAIStudio] Server error: {response.status_code}")
                    raise ProviderUnavailableError(f"Google AI Studio server error: {response.status_code}")

                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            logger.error("[GoogleAIStudio] Request timeout")
            raise ProviderUnavailableError("Google AI Studio request timeout")
        except httpx.RequestError as e:
            logger.error(f"[GoogleAIStudio] Request error: {e}")
            raise ProviderUnavailableError(f"Google AI Studio connection error: {e}")

        # Parse response and extract image
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise ImageProviderError("No candidates in response")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            image_data = None
            mime_type = "image/png"
            revised_prompt = None

            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    image_data = base64.b64decode(inline_data["data"])
                    mime_type = inline_data.get("mimeType", "image/png")
                elif "text" in part:
                    # Sometimes the model returns a revised/enhanced prompt
                    revised_prompt = part["text"]

            if image_data is None:
                raise ImageProviderError("No image data in response")

            width, height = self._get_dimensions_from_aspect_ratio(aspect_ratio)

            return ImageGenerationResult(
                image_data=image_data,
                mime_type=mime_type,
                provider=self.name,
                model=model,
                width=width,
                height=height,
                generation_time_ms=self._get_elapsed_ms(start_time),
                cost_usd=Decimal("0"),  # Free tier
                revised_prompt=revised_prompt,
            )

        except KeyError as e:
            logger.error(f"[GoogleAIStudio] Failed to parse response: {e}")
            raise ImageProviderError(f"Failed to parse Google AI Studio response: {e}")

    async def edit(
        self,
        image_data: bytes,
        prompt: str,
        model: str,
        mask_data: Optional[bytes] = None,
    ) -> ImageGenerationResult:
        """
        Edit an image using Google AI Studio.

        Gemini supports image editing by providing the source image
        along with the edit prompt.
        """
        if not self.is_configured():
            raise ImageProviderError("Google AI Studio API key not configured")

        start_time = self._start_timer()
        normalized_model = self._normalize_model_id(model)
        url = f"{self.BASE_URL}/models/{normalized_model}:generateContent"

        # Encode the source image
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # Build payload with image and edit prompt
        parts = [
            {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": image_base64,
                }
            },
            {"text": prompt}
        ]

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            }
        }

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 429:
                    raise RateLimitError("Google AI Studio rate limit exceeded")

                if response.status_code == 403:
                    error_text = response.text
                    if "quota" in error_text.lower():
                        raise QuotaExhaustedError("Google AI Studio quota exhausted")
                    raise ImageProviderError(f"Access denied: {error_text}")

                if response.status_code >= 500:
                    raise ProviderUnavailableError(f"Google AI Studio server error: {response.status_code}")

                response.raise_for_status()
                data = response.json()

        except httpx.TimeoutException:
            raise ProviderUnavailableError("Google AI Studio request timeout")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Google AI Studio connection error: {e}")

        # Parse response
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise ImageProviderError("No candidates in response")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            result_image_data = None
            mime_type = "image/png"

            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    result_image_data = base64.b64decode(inline_data["data"])
                    mime_type = inline_data.get("mimeType", "image/png")

            if result_image_data is None:
                raise ImageProviderError("No image data in edit response")

            return ImageGenerationResult(
                image_data=result_image_data,
                mime_type=mime_type,
                provider=self.name,
                model=model,
                width=1024,
                height=1024,
                generation_time_ms=self._get_elapsed_ms(start_time),
                cost_usd=Decimal("0"),
            )

        except KeyError as e:
            raise ImageProviderError(f"Failed to parse edit response: {e}")
