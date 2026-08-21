"""
Image Generation Providers.

Provides a fallback chain of image generation providers:
1. Google AI Studio (Free tier)
2. OpenRouter (Reliable fallback)

Model constants are centralized in constants.py.
"""

from .base import (
    ImageGenerationResult,
    ImageProviderError,
    RateLimitError,
    QuotaExhaustedError,
    ProviderUnavailableError,
    AllProvidersFailedError,
    BaseImageProvider,
)
from .google_ai_studio import GoogleAIStudioProvider
from .openrouter import OpenRouterProvider
from .chain import ImageProviderChain
from .constants import (
    ImageModelConfig,
    GEMINI_FLASH_IMAGE,
    GEMINI_PRO_IMAGE,
    IMAGE_MODELS,
    DEFAULT_IMAGE_MODEL,
    SUPPORTED_ASPECT_RATIOS,
    get_model_config,
    get_google_ai_studio_model_id,
    get_openrouter_model_id,
    get_default_model_id,
    is_valid_model,
    get_available_models,
)

__all__ = [
    # Base classes and types
    "ImageGenerationResult",
    "ImageProviderError",
    "RateLimitError",
    "QuotaExhaustedError",
    "ProviderUnavailableError",
    "AllProvidersFailedError",
    "BaseImageProvider",
    # Providers
    "GoogleAIStudioProvider",
    "OpenRouterProvider",
    # Chain
    "ImageProviderChain",
    # Constants
    "ImageModelConfig",
    "GEMINI_FLASH_IMAGE",
    "GEMINI_PRO_IMAGE",
    "IMAGE_MODELS",
    "DEFAULT_IMAGE_MODEL",
    "SUPPORTED_ASPECT_RATIOS",
    "get_model_config",
    "get_google_ai_studio_model_id",
    "get_openrouter_model_id",
    "get_default_model_id",
    "is_valid_model",
    "get_available_models",
]
