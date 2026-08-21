"""
Utility functions for provider icon management.

This module provides smart, dynamic provider-to-icon mapping without hardcoding.
Performance optimized with LRU cache for frequently accessed providers.
"""

import logging
from functools import lru_cache
from typing import Optional

from .icon_config import (
    PROVIDER_ICON_MAPPINGS,
    KNOWN_LOBEHUB_ICONS,
    LOBEHUB_CDN_BASE,
    LOBEHUB_CDN_BASE_SVG,
    LOBEHUB_CDN_BASE_WEBP,
)

logger = logging.getLogger(__name__)


def normalize_provider_name(provider: str) -> str:
    """
    Normalize a provider name to a standard format.

    This function applies intelligent normalization rules:
    - Converts to lowercase
    - Removes common suffixes (-ai, -llm, etc.)
    - Handles special characters and hyphens

    Args:
        provider: Raw provider name from OpenRouter (e.g., "meta-llama", "mistralai")

    Returns:
        Normalized provider name (e.g., "meta", "mistral")

    Examples:
        >>> normalize_provider_name("meta-llama")
        'meta'
        >>> normalize_provider_name("mistralai")
        'mistral'
        >>> normalize_provider_name("OpenAI")
        'openai'
    """
    if not provider:
        return ""

    # Convert to lowercase
    normalized = provider.lower().strip()

    # Remove common AI-related suffixes (only if they make sense)
    # e.g., "mistralai" -> "mistral", but not "openai" -> "open"
    suffixes_to_remove = ["ai", "llm", "ml"]
    for suffix in suffixes_to_remove:
        # Only remove if there's a substantial prefix left
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            # Check if removing the suffix leaves a known provider
            potential = normalized[: -len(suffix)]
            if potential in KNOWN_LOBEHUB_ICONS or potential in PROVIDER_ICON_MAPPINGS:
                normalized = potential
                break

    # Handle compound names (take the first part if it's a known provider)
    # e.g., "meta-llama" -> "meta", "google-vertex" -> "google-vertex" (keep compound)
    if "-" in normalized:
        parts = normalized.split("-")
        first_part = parts[0]

        # Check if the first part alone is a known provider
        if first_part in KNOWN_LOBEHUB_ICONS:
            # But keep compound names if they're specifically mapped
            if normalized not in PROVIDER_ICON_MAPPINGS:
                normalized = first_part

    return normalized


@lru_cache(maxsize=128)
def get_provider_icon_slug(provider: str) -> Optional[str]:
    """
    Get the LobeHub icon slug for a given provider.

    This function uses intelligent mapping and normalization to find the best icon.
    It tries multiple strategies:
    1. Direct mapping from PROVIDER_ICON_MAPPINGS
    2. Normalized provider name if it's in KNOWN_LOBEHUB_ICONS
    3. Returns None if no match found (frontend will use simple fallback icons)

    Performance: Results are cached in memory (LRU cache) for repeated calls.

    Args:
        provider: Provider name from OpenRouter

    Returns:
        LobeHub icon slug (e.g., "openai", "anthropic", "meta") or None if not found

    Examples:
        >>> get_provider_icon_slug("openai")
        'openai'
        >>> get_provider_icon_slug("meta-llama")
        'meta'
        >>> get_provider_icon_slug("unknown-provider")
        None  # frontend will use Building2 icon
    """
    if not provider:
        logger.debug("Empty provider name, returning None")
        return None

    provider_lower = provider.lower().strip()

    # Strategy 1: Direct mapping from config
    if provider_lower in PROVIDER_ICON_MAPPINGS:
        slug = PROVIDER_ICON_MAPPINGS[provider_lower]
        logger.debug(f"Found direct mapping: {provider} -> {slug}")
        return slug

    # Strategy 2: Normalized provider name
    normalized = normalize_provider_name(provider)
    if normalized in KNOWN_LOBEHUB_ICONS:
        logger.debug(f"Using normalized provider name: {provider} -> {normalized}")
        return normalized

    # Strategy 3: Check if original lowercase is in known icons
    if provider_lower in KNOWN_LOBEHUB_ICONS:
        logger.debug(f"Using lowercase provider name: {provider} -> {provider_lower}")
        return provider_lower

    # Strategy 4: No match found, return None (frontend will use simple fallback icon)
    logger.debug(
        f"No icon mapping found for provider '{provider}', returning None (frontend will use fallback)"
    )
    return None


def get_provider_icon_url(
    provider: str, size: str = "dark", format: str = "png"
) -> Optional[str]:
    """
    Get the CDN URL for a provider's icon.

    Args:
        provider: Provider name from OpenRouter
        size: Icon variant - "light" or "dark" (default: "dark")
        format: Image format - "png", "svg", or "webp" (default: "png")

    Returns:
        Full CDN URL for the provider icon, or None if no icon found

    Examples:
        >>> get_provider_icon_url("openai")
        'https://unpkg.com/@lobehub/icons-static-png@1.95.0/dark/openai.png'
        >>> get_provider_icon_url("anthropic", size="light")
        'https://unpkg.com/@lobehub/icons-static-png@1.95.0/light/anthropic.png'
        >>> get_provider_icon_url("unknown-provider")
        None
    """
    slug = get_provider_icon_slug(provider)

    # If no slug found, return None (frontend will use simple fallback icon)
    if not slug:
        return None

    # Adjust CDN base URL based on format. Versions are pinned in icon_config
    # (not @latest) — this is an optional, MIT-licensed CDN asset and the
    # frontend falls back to a generic icon if it fails to load.
    cdn_base = LOBEHUB_CDN_BASE
    if format == "svg":
        cdn_base = LOBEHUB_CDN_BASE_SVG
    elif format == "webp":
        cdn_base = LOBEHUB_CDN_BASE_WEBP

    return f"{cdn_base}/{size}/{slug}.{format}"


@lru_cache(maxsize=128)
def get_model_icon_slug(model_id: str, name: str = None) -> Optional[str]:
    """
    Get a specific model icon slug if available.

    Some models have specific icons (e.g., "claude", "gemini", "chatgpt").
    This function checks for model-specific icons based on the model ID and name.

    Performance: Results are cached in memory (LRU cache) for repeated calls.

    Args:
        model_id: Full model ID from OpenRouter (e.g., "anthropic/claude-3-opus")
        name: Display name of the model (e.g., "GLM 4.5V") - used for special pattern matching

    Returns:
        Model-specific icon slug if available, None otherwise

    Examples:
        >>> get_model_icon_slug("anthropic/claude-3-opus")
        'claude'
        >>> get_model_icon_slug("google/gemini-pro")
        'gemini'
        >>> get_model_icon_slug("openai/gpt-4")
        'chatgpt'
        >>> get_model_icon_slug("xai/grok-beta")
        'xai'
        >>> get_model_icon_slug("z.ai/glm-4.5v", "GLM 4.5V")
        'glmv'
    """
    if not model_id:
        return None

    model_lower = model_id.lower()

    # Determine which string to check for uppercase 'V' pattern
    # Prefer name (display name) since it has correct casing, fallback to model_id
    name_to_check = name if name else model_id

    # Special case: GLM-V models
    # Contains "GLM" (case insensitive) and uppercase "V" anywhere in the name
    # Examples: "GLM 4.5V", "GLM-V", "ChatGLM-V-Plus", "zhipu/GLM-4V-9B"
    # Check model_id for 'glm' but check name for uppercase 'V' (display name has correct casing)
    if 'glm' in model_lower and 'V' in name_to_check:
        return "glmv"

    # Model-specific icon mappings
    # Maps model name patterns to icon slugs that exist in frontend registry
    # These must match keys in frontend PROVIDER_ICON_COMPONENTS
    model_mappings = {
        "claude": "claude",
        "gemini": "gemini",
        # "gpt" intentionally omitted - will fallback to openai provider icon
        # "llama" intentionally omitted - will fallback to meta provider icon
        "mistral": "mistral",
        "deepseek": "deepseek",
        "qwen": "qwen",
        "yi": "yi",
        "command": "cohere",  # Cohere Command models
        "grok": "grok",  # xAI Grok models (dedicated icon)
        "palm": "google",  # Google PaLM models
        "bard": "gemini",  # Google Bard (now Gemini)
        "phi": "azure",  # Microsoft Phi models
        "wizardlm": "azure",  # Microsoft WizardLM
        "orca": "azure",  # Microsoft Orca
        "falcon": "aws",  # TII Falcon (often on AWS)
        "nova": "nova",  # Amazon Nova models (dedicated icon)
        # "vicuna" and "alpaca" intentionally omitted - will fallback to provider icon (usually meta)
        "baichuan": "baichuan",
        "chatglm": "chatglm",
    }

    # Check if any model keyword is in the model ID
    for keyword, icon_slug in model_mappings.items():
        if keyword in model_lower:
            return icon_slug

    return None
