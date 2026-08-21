"""
Image Provider Chain - Fallback logic for image generation.

Tries providers in order:
1. Google AI Studio (Free tier) - uses system API key
2. OpenRouter (Fallback) - uses user's API key (like normal chat messages)
"""

import logging
from typing import List, Optional

from .base import (
    BaseImageProvider,
    ImageGenerationResult,
    ImageProviderError,
    RateLimitError,
    QuotaExhaustedError,
    ProviderUnavailableError,
    AllProvidersFailedError,
)
from .google_ai_studio import GoogleAIStudioProvider
from .openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


class ImageProviderChain:
    """
    Manages a chain of image generation providers with automatic fallback.

    Order of providers:
    1. Google AI Studio - Free tier (5 RPM, 25 RPD) - uses system API key
    2. OpenRouter - Fallback, uses user's OpenRouter API key (same as chat)
    """

    def __init__(
        self,
        providers: Optional[List[BaseImageProvider]] = None,
        user_api_key: Optional[str] = None,
    ):
        """
        Initialize the provider chain.

        Args:
            providers: Optional list of providers. If not provided,
                      uses default chain (Google → OpenRouter).
            user_api_key: User's OpenRouter API key for the fallback provider.
        """
        self._user_api_key = user_api_key

        if providers is not None:
            self._providers = providers
        else:
            # Default provider chain - only include configured providers
            self._providers = []

            google_provider = GoogleAIStudioProvider()
            if google_provider.is_configured():
                self._providers.append(google_provider)
                logger.info("[ImageProviderChain] Google AI Studio provider enabled")

            # OpenRouter is always available (uses user's key at call time)
            openrouter_provider = OpenRouterProvider(api_key=user_api_key)
            self._providers.append(openrouter_provider)
            logger.info("[ImageProviderChain] OpenRouter provider enabled (uses user's API key)")

            if not self._providers:
                logger.warning("[ImageProviderChain] No providers configured!")

    @property
    def providers(self) -> List[BaseImageProvider]:
        """Get the list of providers in the chain."""
        return self._providers

    async def generate(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        user_api_key: Optional[str] = None,
    ) -> ImageGenerationResult:
        """
        Generate an image, trying providers in order until one succeeds.

        Args:
            prompt: Text description of the image to generate
            model: Model ID (e.g., "google/gemini-2.5-flash-image")
            aspect_ratio: Desired aspect ratio
            resolution: Output resolution - "1K", "2K", or "4K"
            user_api_key: User's OpenRouter API key (for fallback provider)

        Returns:
            ImageGenerationResult with the generated image

        Raises:
            AllProvidersFailedError: If all providers fail
        """
        if not self._providers:
            raise AllProvidersFailedError("No image generation providers configured")

        last_error: Optional[Exception] = None
        api_key = user_api_key or self._user_api_key

        for provider in self._providers:
            try:
                logger.info(f"[ImageProviderChain] Trying {provider.name} for generation")

                # Pass api_key for OpenRouter (it ignores it for Google AI Studio)
                if isinstance(provider, OpenRouterProvider):
                    result = await provider.generate(
                        prompt=prompt,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        api_key=api_key,
                    )
                else:
                    result = await provider.generate(
                        prompt=prompt,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                    )

                logger.info(
                    f"[ImageProviderChain] {provider.name} succeeded "
                    f"({result.generation_time_ms}ms)"
                )
                return result

            except (RateLimitError, QuotaExhaustedError) as e:
                logger.warning(
                    f"[ImageProviderChain] {provider.name} rate limited/quota exhausted, "
                    f"trying next provider: {e}"
                )
                last_error = e
                continue

            except ProviderUnavailableError as e:
                logger.warning(
                    f"[ImageProviderChain] {provider.name} unavailable, "
                    f"trying next provider: {e}"
                )
                last_error = e
                continue

            except ImageProviderError as e:
                logger.error(
                    f"[ImageProviderChain] {provider.name} failed with error: {e}"
                )
                last_error = e
                continue

            except Exception as e:
                logger.error(
                    f"[ImageProviderChain] {provider.name} unexpected error: {e}"
                )
                last_error = e
                continue

        # All providers failed
        error_msg = f"All {len(self._providers)} providers failed"
        if last_error:
            error_msg += f". Last error: {last_error}"

        logger.error(f"[ImageProviderChain] {error_msg}")
        raise AllProvidersFailedError(error_msg)

    async def edit(
        self,
        image_data: bytes,
        prompt: str,
        model: str,
        mask_data: Optional[bytes] = None,
        user_api_key: Optional[str] = None,
    ) -> ImageGenerationResult:
        """
        Edit an image, trying providers in order until one succeeds.

        Args:
            image_data: Original image bytes
            prompt: Description of the edit
            model: User-facing model name
            mask_data: Optional mask for targeted editing
            user_api_key: User's OpenRouter API key (for fallback provider)

        Returns:
            ImageGenerationResult with the edited image

        Raises:
            AllProvidersFailedError: If all providers fail
        """
        if not self._providers:
            raise AllProvidersFailedError("No image generation providers configured")

        last_error: Optional[Exception] = None
        api_key = user_api_key or self._user_api_key

        for provider in self._providers:
            try:
                logger.info(f"[ImageProviderChain] Trying {provider.name} for editing")

                # Pass api_key for OpenRouter
                if isinstance(provider, OpenRouterProvider):
                    result = await provider.edit(
                        image_data=image_data,
                        prompt=prompt,
                        model=model,
                        mask_data=mask_data,
                        api_key=api_key,
                    )
                else:
                    result = await provider.edit(
                        image_data=image_data,
                        prompt=prompt,
                        model=model,
                        mask_data=mask_data,
                    )

                logger.info(
                    f"[ImageProviderChain] {provider.name} edit succeeded "
                    f"({result.generation_time_ms}ms)"
                )
                return result

            except (RateLimitError, QuotaExhaustedError) as e:
                logger.warning(
                    f"[ImageProviderChain] {provider.name} rate limited, trying next: {e}"
                )
                last_error = e
                continue

            except ProviderUnavailableError as e:
                logger.warning(
                    f"[ImageProviderChain] {provider.name} unavailable, trying next: {e}"
                )
                last_error = e
                continue

            except ImageProviderError as e:
                logger.error(f"[ImageProviderChain] {provider.name} edit failed: {e}")
                last_error = e
                continue

            except Exception as e:
                logger.error(f"[ImageProviderChain] {provider.name} unexpected error: {e}")
                last_error = e
                continue

        error_msg = f"All {len(self._providers)} providers failed to edit image"
        if last_error:
            error_msg += f". Last error: {last_error}"

        raise AllProvidersFailedError(error_msg)

    def get_available_providers(self) -> List[str]:
        """Get list of configured provider names."""
        return [p.name for p in self._providers]

    def is_available(self) -> bool:
        """Check if at least one provider is configured."""
        return len(self._providers) > 0
