"""
Video generation constants and API configuration.

IMPORTANT: Model configuration (pricing, capabilities, etc.) is now stored in the
database (VideoModelCatalog). Use llm.models.VideoModelCatalog for model lookups.

This file contains:
- API configuration for video providers (endpoints, timeouts)
- Resolution mappings for different aspect ratios
- Default values for video generation parameters
- Quota configuration (to be moved to database in future)

DEPRECATED: VideoModelConfig, VIDEO_MODELS, and related functions are deprecated.
Use VideoModelCatalog.get_by_model_id() or VideoModelCatalog.get_by_canonical_id() instead.
"""

import warnings
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


# =============================================================================
# API Configuration (Still in use - not deprecated)
# =============================================================================


@dataclass(frozen=True)
class APIConfig:
    """API-related configuration for video providers."""

    base_url: str = "https://api.openai.com/v1"
    videos_endpoint: str = "/videos"
    connect_timeout_seconds: float = 30.0
    read_timeout_seconds: float = 300.0  # Long timeout for video downloads
    poll_interval_seconds: int = 5
    max_poll_timeout_seconds: int = 600  # 10 minutes max wait


# OpenAI API configuration
OPENAI_API_CONFIG = APIConfig()

# Runway API configuration
# API docs: https://docs.dev.runwayml.com/
RUNWAY_API_CONFIG = APIConfig(
    base_url="https://api.dev.runwayml.com/v1",
    videos_endpoint="/text_to_video",  # Base endpoint (varies by model)
    connect_timeout_seconds=30.0,
    read_timeout_seconds=300.0,
    poll_interval_seconds=5,
    max_poll_timeout_seconds=600,
)


# =============================================================================
# Resolution Configuration (Still in use)
# =============================================================================


@dataclass(frozen=True)
class ResolutionConfig:
    """Resolution configuration with dimensions."""

    name: str
    width: int
    height: int


# Resolution mappings for different aspect ratios
ASPECT_RATIO_RESOLUTIONS: Dict[str, Dict[str, ResolutionConfig]] = {
    "16:9": {
        "720p": ResolutionConfig("720p", 1280, 720),
        "1080p": ResolutionConfig("1080p", 1920, 1080),
        "4K": ResolutionConfig("4K", 3840, 2160),
    },
    "9:16": {
        "720p": ResolutionConfig("720p", 720, 1280),
        "1080p": ResolutionConfig("1080p", 1080, 1920),
        "4K": ResolutionConfig("4K", 2160, 3840),
    },
    "1:1": {
        "720p": ResolutionConfig("720p", 720, 720),
        "1080p": ResolutionConfig("1080p", 1080, 1080),
        "4K": ResolutionConfig("4K", 2160, 2160),
    },
    "4:3": {
        "720p": ResolutionConfig("720p", 960, 720),
        "1080p": ResolutionConfig("1080p", 1440, 1080),
        "4K": ResolutionConfig("4K", 2880, 2160),
    },
    "3:4": {
        "720p": ResolutionConfig("720p", 720, 960),
        "1080p": ResolutionConfig("1080p", 1080, 1440),
        "4K": ResolutionConfig("4K", 2160, 2880),
    },
}

SUPPORTED_ASPECT_RATIOS: Tuple[str, ...] = ("16:9", "9:16", "1:1", "4:3", "3:4")


# =============================================================================
# Default Values (Still in use)
# =============================================================================

DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_RESOLUTION = "720p"
DEFAULT_DURATION_SECONDS = 4
DEFAULT_FPS = 24
VALID_DURATIONS_SECONDS = (4, 5, 6, 8, 10, 12)  # Varies by provider


# =============================================================================
# Quota Configuration (To be moved to database in future)
# =============================================================================


@dataclass
class QuotaLimitConfig:
    """Quota limits for a subscription tier."""

    daily_videos: Optional[int]  # None = unlimited
    daily_seconds: Optional[int]  # Total seconds per day
    daily_cost_usd: Optional[Decimal]  # Max daily spend
    max_duration_per_video: int  # Per-video limit
    allowed_models: List[str]  # Which models can be used


QUOTA_LIMITS: Dict[str, QuotaLimitConfig] = {
    "free": QuotaLimitConfig(
        daily_videos=2,
        daily_seconds=20,
        daily_cost_usd=Decimal("2.50"),
        max_duration_per_video=8,
        allowed_models=["sora-2", "veo3.1_fast"],
    ),
    "pro": QuotaLimitConfig(
        daily_videos=20,
        daily_seconds=300,
        daily_cost_usd=Decimal("50.00"),
        max_duration_per_video=12,
        allowed_models=["sora-2", "sora-2-pro", "veo3.1_fast", "veo3.1"],
    ),
    "enterprise": QuotaLimitConfig(
        daily_videos=None,
        daily_seconds=None,
        daily_cost_usd=None,
        max_duration_per_video=12,
        allowed_models=["sora-2", "sora-2-pro", "veo3.1_fast", "veo3.1"],
    ),
}

# Default cost estimate for pre-flight quota checks
DEFAULT_ESTIMATED_COST_USD = Decimal("0.12") * DEFAULT_DURATION_SECONDS


# =============================================================================
# DEPRECATED: Model Configuration
# Use VideoModelCatalog from llm.models instead
# =============================================================================


@dataclass(frozen=True)
class VideoModelConfig:
    """
    DEPRECATED: Use VideoModelCatalog from llm.models instead.

    This class is kept for backward compatibility but should not be used
    for new code. Model configuration is now stored in the database.
    """

    model_id: str
    canonical_id: str
    display_name: str
    price_per_second_usd: Decimal
    max_duration_seconds: int
    max_resolution: str
    supported_fps: Tuple[int, ...]
    supported_resolutions: Tuple[str, ...]
    description: str
    best_for: str
    is_default: bool = False
    is_pro: bool = False


# DEPRECATED model constants - kept for backward compatibility
# Use VideoModelCatalog.get_by_model_id() instead
SORA_2 = VideoModelConfig(
    model_id="sora-2",
    canonical_id="openai/sora-2",
    display_name="Sora 2 (Standard)",
    price_per_second_usd=Decimal("0.12"),
    max_duration_seconds=12,
    max_resolution="720p",
    supported_fps=(24, 30),
    supported_resolutions=("720p",),
    description="Fast video generation",
    best_for="Quick iterations, drafts",
    is_default=True,
)

SORA_2_PRO = VideoModelConfig(
    model_id="sora-2-pro",
    canonical_id="openai/sora-2-pro",
    display_name="Sora 2 Pro",
    price_per_second_usd=Decimal("0.50"),
    max_duration_seconds=12,
    max_resolution="4K",
    supported_fps=(24, 30, 60),
    supported_resolutions=("720p", "4K"),
    description="Highest quality output",
    best_for="Marketing, production content",
    is_pro=True,
)

RUNWAY_VEO31_FAST = VideoModelConfig(
    model_id="veo3.1_fast",
    canonical_id="runway/veo3.1-fast",
    display_name="Veo 3.1 Fast",
    price_per_second_usd=Decimal("0.15"),
    max_duration_seconds=8,
    max_resolution="1080p",
    supported_fps=(24,),
    supported_resolutions=("720p", "1080p"),
    description="Fast text-to-video",
    best_for="Quick iterations",
)

RUNWAY_VEO31 = VideoModelConfig(
    model_id="veo3.1",
    canonical_id="runway/veo3.1",
    display_name="Veo 3.1",
    price_per_second_usd=Decimal("0.20"),
    max_duration_seconds=8,
    max_resolution="1080p",
    supported_fps=(24,),
    supported_resolutions=("720p", "1080p"),
    description="High quality text-to-video",
    best_for="Professional videos",
    is_pro=True,
)

# DEPRECATED registries - use VideoModelCatalog instead
VIDEO_MODELS: Dict[str, VideoModelConfig] = {
    SORA_2.model_id: SORA_2,
    SORA_2_PRO.model_id: SORA_2_PRO,
    RUNWAY_VEO31_FAST.model_id: RUNWAY_VEO31_FAST,
    RUNWAY_VEO31.model_id: RUNWAY_VEO31,
}

VIDEO_MODELS_BY_CANONICAL: Dict[str, VideoModelConfig] = {
    SORA_2.canonical_id: SORA_2,
    SORA_2_PRO.canonical_id: SORA_2_PRO,
    RUNWAY_VEO31_FAST.canonical_id: RUNWAY_VEO31_FAST,
    RUNWAY_VEO31.canonical_id: RUNWAY_VEO31,
}

DEFAULT_VIDEO_MODEL = SORA_2


# =============================================================================
# Helper Functions (Non-deprecated)
# =============================================================================


def get_resolution(aspect_ratio: str, quality: str) -> ResolutionConfig:
    """Get resolution config for aspect ratio and quality level."""
    aspect_resolutions = ASPECT_RATIO_RESOLUTIONS.get(
        aspect_ratio, ASPECT_RATIO_RESOLUTIONS[DEFAULT_ASPECT_RATIO]
    )
    return aspect_resolutions.get(quality, aspect_resolutions[DEFAULT_RESOLUTION])


def get_resolution_string(aspect_ratio: str, quality: str) -> str:
    """Get resolution as WIDTHxHEIGHT string."""
    res = get_resolution(aspect_ratio, quality)
    return f"{res.width}x{res.height}"


# =============================================================================
# DEPRECATED Helper Functions
# Use VideoModelCatalog methods instead
# =============================================================================


def get_model_config(model_id: str) -> VideoModelConfig:
    """
    DEPRECATED: Use VideoModelCatalog.get_by_model_id() instead.
    """
    warnings.warn(
        "get_model_config is deprecated. Use VideoModelCatalog.get_by_model_id() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return VIDEO_MODELS.get(model_id, DEFAULT_VIDEO_MODEL)


def get_model_by_canonical(canonical_id: str) -> VideoModelConfig:
    """
    DEPRECATED: Use VideoModelCatalog.get_by_canonical_id() instead.
    """
    warnings.warn(
        "get_model_by_canonical is deprecated. Use VideoModelCatalog.get_by_canonical_id() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return VIDEO_MODELS_BY_CANONICAL.get(canonical_id, DEFAULT_VIDEO_MODEL)


def calculate_cost(model_id: str, duration_seconds: float) -> Decimal:
    """
    DEPRECATED: Use VideoModelCatalog.calculate_cost() instead.
    """
    warnings.warn(
        "calculate_cost is deprecated. Use model_instance.calculate_cost() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = VIDEO_MODELS.get(model_id, DEFAULT_VIDEO_MODEL)
    return config.price_per_second_usd * Decimal(str(duration_seconds))


def get_available_models() -> List[VideoModelConfig]:
    """
    DEPRECATED: Use VideoModelCatalog.objects.filter(is_active=True) instead.
    """
    warnings.warn(
        "get_available_models is deprecated. Use VideoModelCatalog.objects.filter(is_active=True) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return list(VIDEO_MODELS.values())


def is_valid_model(model_id: str) -> bool:
    """
    DEPRECATED: Use VideoModelCatalog.get_by_model_id() and check for None instead.
    """
    warnings.warn(
        "is_valid_model is deprecated. Use VideoModelCatalog.get_by_model_id() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return model_id in VIDEO_MODELS


def get_max_duration(model_id: str) -> int:
    """
    DEPRECATED: Use VideoModelCatalog capabilities instead.
    """
    warnings.warn(
        "get_max_duration is deprecated. Use model.capabilities.get('max_duration') instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = VIDEO_MODELS.get(model_id, DEFAULT_VIDEO_MODEL)
    return config.max_duration_seconds
