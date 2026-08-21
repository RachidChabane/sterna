"""
Dynamic provider capabilities service.

This module fetches provider capabilities from OpenRouter's documentation
and API, caching the results in Redis for performance.

Instead of hardcoding provider lists, we:
1. Scrape OpenRouter's streaming documentation to get supported providers
2. Fetch provider slugs from OpenRouter API (/api/v1/providers)
3. Map provider names to slugs
4. Cache results in Redis (TTL: 1 week)
5. Fallback to JSON config if scraping fails

Reference: https://openrouter.ai/docs/api-reference/streaming
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, Dict, Any, Optional, List

import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_KEY_STREAM_CANCELLATION = "openrouter:provider_capabilities:stream_cancellation"
CACHE_TTL = 604800  # 7 days in seconds

# Fallback JSON file path
FALLBACK_JSON_PATH = Path(__file__).parent / "config" / "provider_capabilities.json"

# OpenRouter API and docs URLs
OPENROUTER_API_BASE = getattr(settings, "OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
OPENROUTER_STREAMING_DOCS_URL = "https://openrouter.ai/docs/api-reference/streaming"

# Documentation provider names that differ from the API provider names.
# Keys and values are normalized forms (see _normalize_provider_name).
PROVIDER_NAME_ALIASES = {
    "awsbedrock": "amazonbedrock",  # docs say "AWS Bedrock", API says "Amazon Bedrock"
}


def _scrape_streaming_docs() -> Dict[str, List[str]]:
    """
    Scrape OpenRouter streaming documentation to extract provider support lists.

    Returns:
        Dictionary with 'supported' and 'unsupported' provider name lists

    Raises:
        Exception if scraping fails
    """
    try:
        logger.info(f"Scraping OpenRouter streaming docs: {OPENROUTER_STREAMING_DOCS_URL}")

        response = requests.get(OPENROUTER_STREAMING_DOCS_URL, timeout=10)
        response.raise_for_status()

        content = response.text.lower()

        # The documentation lists providers in text format like:
        # "Supported: OpenAI, Azure, Anthropic, ..."
        # "Not supported: AWS Bedrock, Groq, ..."

        # Try to extract using patterns (this is brittle but best we can do)
        # Pattern 1: Look for list after "supported" keyword
        supported_match = re.search(
            r'(?:supported|support).*?[:\-]\s*([^\.]+)',
            content,
            re.IGNORECASE | re.DOTALL
        )

        # Pattern 2: Look for list after "not supported" or "unsupported"
        unsupported_match = re.search(
            r'(?:not\s+supported|unsupported).*?[:\-]\s*([^\.]+)',
            content,
            re.IGNORECASE | re.DOTALL
        )

        supported_providers = []
        unsupported_providers = []

        if supported_match:
            # Extract provider names from comma-separated list
            provider_text = supported_match.group(1)
            # Split by comma, clean up whitespace and "and"
            providers = [p.strip() for p in re.split(r',|\sand\s', provider_text)]
            supported_providers = [p for p in providers if p and len(p) > 2]

        if unsupported_match:
            provider_text = unsupported_match.group(1)
            providers = [p.strip() for p in re.split(r',|\sand\s', provider_text)]
            unsupported_providers = [p for p in providers if p and len(p) > 2]

        if not supported_providers:
            raise Exception("Could not extract supported providers from documentation")

        logger.info(f"Scraped {len(supported_providers)} supported providers, {len(unsupported_providers)} unsupported")

        return {
            "supported": supported_providers,
            "unsupported": unsupported_providers,
        }

    except Exception as e:
        logger.error(f"Failed to scrape streaming docs: {e}")
        raise


def _fetch_provider_slugs() -> Dict[str, str]:
    """
    Fetch provider information from OpenRouter API.

    Returns:
        Dictionary mapping provider names to slugs
        Example: {"OpenAI": "openai", "Google AI Studio": "google-ai-studio"}
    """
    try:
        api_key = getattr(settings, "OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not configured, using empty key")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{OPENROUTER_API_BASE}/providers"
        logger.info(f"Fetching providers from API: {url}")

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        providers = data.get("data", [])

        # Build mapping: name -> slug
        provider_map = {}
        for provider in providers:
            name = provider.get("name", "")
            slug = provider.get("slug", "")
            if name and slug:
                provider_map[name] = slug

        logger.info(f"Fetched {len(provider_map)} providers from API")
        return provider_map

    except Exception as e:
        logger.error(f"Failed to fetch providers from API: {e}")
        raise


def _normalize_provider_name(name: str) -> str:
    """
    Normalize a provider name for matching.

    Examples:
        "OpenAI" -> "openai"
        "Google AI Studio" -> "googleaistudio"
        "AWS Bedrock" -> "awsbedrock"
    """
    # Remove special characters, convert to lowercase
    normalized = re.sub(r'[^a-z0-9]', '', name.lower())
    return normalized


def _map_provider_names_to_slugs(provider_names: List[str], api_provider_map: Dict[str, str]) -> Set[str]:
    """
    Map provider names from documentation to API slugs.

    Args:
        provider_names: List of provider names from documentation
        api_provider_map: Dictionary mapping provider names to slugs from API

    Returns:
        Set of provider slugs
    """
    slugs = set()

    # Build reverse lookup: normalized name -> slug
    normalized_lookup = {}
    for api_name, slug in api_provider_map.items():
        normalized = _normalize_provider_name(api_name)
        normalized_lookup[normalized] = slug

    # Also add slug as its own normalized form
    for slug in api_provider_map.values():
        normalized = _normalize_provider_name(slug)
        normalized_lookup[normalized] = slug

    # Try to match each documentation provider name
    for doc_name in provider_names:
        normalized_doc = _normalize_provider_name(doc_name)

        # Apply known aliases (e.g. docs "AWS Bedrock" -> API "Amazon Bedrock")
        normalized_doc = PROVIDER_NAME_ALIASES.get(normalized_doc, normalized_doc)

        # Direct match
        if normalized_doc in normalized_lookup:
            slugs.add(normalized_lookup[normalized_doc])
            continue

        # Partial match (for cases like "Google" matching "google-ai-studio")
        for normalized_api, slug in normalized_lookup.items():
            if normalized_doc in normalized_api or normalized_api in normalized_doc:
                slugs.add(slug)
                break
        else:
            # No match found - log warning but continue
            logger.warning(f"Could not map provider name '{doc_name}' to API slug")

    return slugs


def _load_fallback_data() -> Optional[Dict[str, Any]]:
    """
    Load fallback data from JSON file.

    Returns:
        Dictionary with fallback provider capabilities, or None if file doesn't exist
    """
    try:
        if not FALLBACK_JSON_PATH.exists():
            logger.warning(f"Fallback JSON not found: {FALLBACK_JSON_PATH}")
            return None

        with open(FALLBACK_JSON_PATH, 'r') as f:
            data = json.load(f)

        logger.info(f"Loaded fallback data from {FALLBACK_JSON_PATH}")
        return data

    except Exception as e:
        logger.error(f"Failed to load fallback JSON: {e}")
        return None


def _save_fallback_data(data: Dict[str, Any]) -> bool:
    """
    Save provider capabilities data to fallback JSON file.

    Args:
        data: Provider capabilities data to save

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure config directory exists
        FALLBACK_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(FALLBACK_JSON_PATH, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved fallback data to {FALLBACK_JSON_PATH}")
        return True

    except Exception as e:
        logger.error(f"Failed to save fallback JSON: {e}")
        return False


def fetch_stream_cancellation_providers(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch stream cancellation provider support from OpenRouter docs and API.

    This function:
    1. Scrapes OpenRouter streaming documentation
    2. Fetches provider slugs from API
    3. Maps provider names to slugs
    4. Returns structured data with metadata

    Args:
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Dictionary with:
        - supported_slugs: Set of provider slugs that support stream cancellation
        - source: URL of documentation
        - fetched_at: ISO timestamp of when data was fetched
        - expires_at: ISO timestamp of when cache expires

    Raises:
        Exception if both scraping and fallback fail
    """
    try:
        # Step 1: Scrape documentation
        doc_data = _scrape_streaming_docs()
        supported_names = doc_data["supported"]

        # Step 2: Fetch API provider slugs
        api_provider_map = _fetch_provider_slugs()

        # Step 3: Map names to slugs
        supported_slugs = _map_provider_names_to_slugs(supported_names, api_provider_map)

        # Validate: we should have at least 10 providers
        # If scraping returned 0-9 providers, something went wrong
        if len(supported_slugs) < 10:
            raise Exception(
                f"Scraping returned too few providers ({len(supported_slugs)}). "
                "This suggests the scraping logic failed. Falling back to JSON."
            )

        # Step 4: Build result
        now = datetime.utcnow()
        expires = now + timedelta(seconds=CACHE_TTL)

        result = {
            "supported_slugs": list(supported_slugs),
            "source": OPENROUTER_STREAMING_DOCS_URL,
            "fetched_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }

        # Step 5: Save as fallback for future use (only if valid)
        _save_fallback_data({
            "stream_cancellation": result,
            "last_verified": now.isoformat(),
        })

        logger.info(f"Successfully fetched {len(supported_slugs)} providers supporting stream cancellation")
        return result

    except Exception as e:
        logger.error(f"Failed to fetch provider capabilities: {e}")

        # Try fallback
        fallback = _load_fallback_data()
        if fallback and "stream_cancellation" in fallback:
            logger.warning("Using fallback JSON data for provider capabilities")
            return fallback["stream_cancellation"]

        # No fallback available
        raise Exception(f"Failed to fetch provider capabilities and no fallback available: {e}")


def get_stream_cancellation_providers(force_refresh: bool = False) -> Set[str]:
    """
    Get the set of provider slugs that support stream cancellation.

    This is the main entry point for checking stream cancellation support.
    Results are cached in Redis for performance.

    Args:
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Set of provider slugs (lowercase) that support stream cancellation

    Examples:
        >>> providers = get_stream_cancellation_providers()
        >>> 'openai' in providers
        True
        >>> 'google' in providers
        False
    """
    # Check cache first
    if not force_refresh:
        cached_data = cache.get(CACHE_KEY_STREAM_CANCELLATION)
        if cached_data:
            logger.debug("Using cached stream cancellation providers")
            return set(cached_data.get("supported_slugs", []))

    # Cache miss or force refresh - fetch fresh data
    try:
        data = fetch_stream_cancellation_providers(force_refresh=force_refresh)

        # Cache the result
        cache.set(CACHE_KEY_STREAM_CANCELLATION, data, CACHE_TTL)

        return set(data.get("supported_slugs", []))

    except Exception as e:
        logger.error(f"Failed to get stream cancellation providers: {e}")
        # Return empty set as last resort
        return set()


def supports_stream_cancellation(provider: str) -> bool:
    """
    Check if a provider supports stream cancellation.

    Args:
        provider: Provider slug (e.g., 'openai', 'google', 'anthropic')

    Returns:
        True if provider supports stream cancellation, False otherwise

    Examples:
        >>> supports_stream_cancellation('openai')
        True
        >>> supports_stream_cancellation('google')
        False
    """
    if not provider:
        return False

    supported_providers = get_stream_cancellation_providers()
    provider_normalized = provider.lower().strip()

    return provider_normalized in supported_providers


def get_cache_status() -> Dict[str, Any]:
    """
    Get information about the current cache status.

    Returns:
        Dictionary with cache status information
    """
    cached_data = cache.get(CACHE_KEY_STREAM_CANCELLATION)

    if not cached_data:
        return {
            "cached": False,
            "message": "No data in cache",
        }

    return {
        "cached": True,
        "provider_count": len(cached_data.get("supported_slugs", [])),
        "source": cached_data.get("source"),
        "fetched_at": cached_data.get("fetched_at"),
        "expires_at": cached_data.get("expires_at"),
    }
