"""
Video generation providers package.

This package provides video generation capabilities using various AI providers.
Currently supports OpenAI Sora and Runway Gen-4 models.

Usage:
    from llm.video_providers import OpenAISoraProvider, RunwayProvider, VideoGenerationResult

    # OpenAI Sora
    provider = OpenAISoraProvider()
    result = await provider.generate(
        prompt="A beautiful sunset over the ocean",
        duration=10,
    )

    # Runway Gen-4
    provider = RunwayProvider()
    result = await provider.generate(
        prompt="A beautiful sunset over the ocean",
        duration=10,
        model="gen4_turbo",
    )
"""

from .base import (
    BaseVideoProvider,
    ContentPolicyError,
    GenerationTimeoutError,
    InvalidInputError,
    InvalidPromptError,
    QuotaExhaustedError,
    RateLimitError,
    VideoGenerationInput,
    VideoGenerationResult,
    VideoInputType,
    VideoProviderError,
    VideoStatus,
)
from .constants import (
    DEFAULT_ASPECT_RATIO,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_ESTIMATED_COST_USD,
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    DEFAULT_VIDEO_MODEL,
    OPENAI_API_CONFIG,
    QUOTA_LIMITS,
    RUNWAY_API_CONFIG,
    RUNWAY_VEO31,
    RUNWAY_VEO31_FAST,
    SORA_2,
    SORA_2_PRO,
    SUPPORTED_ASPECT_RATIOS,
    VIDEO_MODELS,
    VIDEO_MODELS_BY_CANONICAL,
    APIConfig,
    QuotaLimitConfig,
    ResolutionConfig,
    VideoModelConfig,
    calculate_cost,
    get_available_models,
    get_max_duration,
    get_model_by_canonical,
    get_model_config,
    get_resolution,
    get_resolution_string,
    is_valid_model,
)
from .openai_sora import OpenAISoraProvider
from .runway import RunwayProvider

__all__ = [
    # Providers
    "OpenAISoraProvider",
    "RunwayProvider",
    "BaseVideoProvider",
    # Input/Output types
    "VideoGenerationInput",
    "VideoGenerationResult",
    "VideoInputType",
    "VideoStatus",
    # Exceptions
    "VideoProviderError",
    "RateLimitError",
    "QuotaExhaustedError",
    "GenerationTimeoutError",
    "InvalidPromptError",
    "InvalidInputError",
    "ContentPolicyError",
    # Configuration classes
    "VideoModelConfig",
    "ResolutionConfig",
    "QuotaLimitConfig",
    "APIConfig",
    # Model constants - OpenAI Sora
    "SORA_2",
    "SORA_2_PRO",
    # Model constants - Runway Veo
    "RUNWAY_VEO31_FAST",
    "RUNWAY_VEO31",
    # Model registries
    "VIDEO_MODELS",
    "VIDEO_MODELS_BY_CANONICAL",
    "DEFAULT_VIDEO_MODEL",
    # Resolution constants
    "SUPPORTED_ASPECT_RATIOS",
    "DEFAULT_ASPECT_RATIO",
    "DEFAULT_RESOLUTION",
    "DEFAULT_DURATION_SECONDS",
    "DEFAULT_FPS",
    "DEFAULT_ESTIMATED_COST_USD",
    # Config
    "OPENAI_API_CONFIG",
    "RUNWAY_API_CONFIG",
    "QUOTA_LIMITS",
    # Helper functions
    "get_model_config",
    "get_model_by_canonical",
    "get_resolution",
    "get_resolution_string",
    "calculate_cost",
    "get_available_models",
    "is_valid_model",
    "get_max_duration",
]
