"""
Centralized constants for image generation models.

This file is the single source of truth for all image generation model IDs
and their mappings across different providers.

Provider chain:
1. Google AI Studio (Free tier) - uses system API key
2. OpenRouter (Fallback) - uses user's API key

Model documentation:
- Gemini 2.5 Flash Image: https://ai.google.dev/gemini-api/docs/image-generation
- OpenRouter models: https://openrouter.ai/models?q=gemini+image
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ImageModelConfig:
    """Configuration for an image generation model."""

    # Canonical model ID (used in tool catalog and user preferences)
    canonical_id: str

    # User-facing display name
    display_name: str

    # Google AI Studio model ID (without google/ prefix)
    google_ai_studio_id: str

    # OpenRouter model ID (with google/ prefix)
    openrouter_id: str

    # Description for UI
    description: str

    # Whether this is the default model
    is_default: bool = False

    # Supported resolutions
    supported_resolutions: tuple = ("1K", "2K")

    # Estimated cost per image (for quota estimation)
    estimated_cost_usd: float = 0.02


# =============================================================================
# Model Definitions
# =============================================================================

# Gemini 2.5 Flash Image - Fast, good quality, production-ready
GEMINI_FLASH_IMAGE = ImageModelConfig(
    canonical_id="google/gemini-2.5-flash-image",
    display_name="Nano Banana",
    google_ai_studio_id="gemini-2.5-flash-image",
    openrouter_id="google/gemini-2.5-flash-image",  # Same as canonical (no -preview suffix)
    description="Fast, good quality image generation",
    is_default=True,
    supported_resolutions=("1K", "2K"),
    estimated_cost_usd=0.00,  # Free via Google AI Studio
)

# Gemini 3 Pro Image Preview - Best quality, slower
GEMINI_PRO_IMAGE = ImageModelConfig(
    canonical_id="google/gemini-3-pro-image-preview",
    display_name="Nano Banana Pro",
    google_ai_studio_id="gemini-3-pro-image-preview",
    openrouter_id="google/gemini-3-pro-image-preview",
    description="Best quality, supports 4K resolution",
    is_default=False,
    supported_resolutions=("1K", "2K", "4K"),
    estimated_cost_usd=0.04,
)


# =============================================================================
# Model Registry
# =============================================================================

# All available image models
IMAGE_MODELS: Dict[str, ImageModelConfig] = {
    GEMINI_FLASH_IMAGE.canonical_id: GEMINI_FLASH_IMAGE,
    GEMINI_PRO_IMAGE.canonical_id: GEMINI_PRO_IMAGE,
}

# Default model for image generation
DEFAULT_IMAGE_MODEL = GEMINI_FLASH_IMAGE

# Supported aspect ratios (common to all models)
SUPPORTED_ASPECT_RATIOS = (
    "1:1",    # Square
    "16:9",   # Landscape (widescreen)
    "9:16",   # Portrait (mobile)
    "4:3",    # Landscape (standard)
    "3:4",    # Portrait (standard)
    "3:2",    # Landscape (photo)
    "2:3",    # Portrait (photo)
    "21:9",   # Ultra-wide
)


# =============================================================================
# Helper Functions
# =============================================================================

def get_model_config(model_id: str) -> ImageModelConfig:
    """
    Get the model configuration for a given model ID.

    Args:
        model_id: Canonical model ID (e.g., "google/gemini-2.5-flash-image")

    Returns:
        ImageModelConfig for the model, or default if not found.
    """
    return IMAGE_MODELS.get(model_id, DEFAULT_IMAGE_MODEL)


def get_google_ai_studio_model_id(model_id: str) -> str:
    """
    Convert a canonical model ID to Google AI Studio format.

    Args:
        model_id: Canonical model ID (e.g., "google/gemini-2.5-flash-image")

    Returns:
        Google AI Studio model ID (e.g., "gemini-2.5-flash-image")
    """
    config = get_model_config(model_id)
    return config.google_ai_studio_id


def get_openrouter_model_id(model_id: str) -> str:
    """
    Convert a canonical model ID to OpenRouter format.

    Args:
        model_id: Canonical model ID (e.g., "google/gemini-2.5-flash-image")

    Returns:
        OpenRouter model ID (e.g., "google/gemini-2.5-flash-image-preview")
    """
    config = get_model_config(model_id)
    return config.openrouter_id


def get_default_model_id() -> str:
    """Get the default model ID for image generation."""
    return DEFAULT_IMAGE_MODEL.canonical_id


def is_valid_model(model_id: str) -> bool:
    """Check if a model ID is valid."""
    return model_id in IMAGE_MODELS


def get_available_models() -> list:
    """Get list of all available model configurations."""
    return list(IMAGE_MODELS.values())
