"""
Catalog population and query building for image generation models.

Owns the fetch from the image-generation service (falling back to a
hardcoded default catalog when that service is unavailable) and the
filtering, sorting, and response caching `ImageModelCatalogViewSet.list`
returns; the view keeps only request parsing and response building.
"""

import hashlib
import json
import logging

from django.core.cache import cache
from django.db import models

from ..models import ImageModelCatalog
from ..serializers import ImageModelCatalogSerializer

logger = logging.getLogger(__name__)


def populate_from_service():
    """Fetch models from image-generation service and populate catalog."""
    import httpx

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get("http://image-generation:8006/models")
            response.raise_for_status()
            data = response.json()

            for model_info in data.get("models", []):
                ImageModelCatalog.objects.update_or_create(
                    model_id=model_info["id"],
                    defaults={
                        "name": model_info.get("name", model_info["id"]),
                        "provider": model_info.get("provider", "unknown"),
                        "price_per_image": model_info.get("base_price"),
                        "supports_generation": model_info.get("supports_generation", True),
                        "supports_editing": model_info.get("supports_editing", False),
                        "supports_variations": model_info.get("supports_variations", False),
                        "supported_sizes": model_info.get("supported_sizes", []),
                        "max_images_per_request": model_info.get("max_images", 1),
                        "is_available": True,
                        "description": model_info.get("description", ""),
                    }
                )
            logger.info(f"[ImageModels] Populated {len(data.get('models', []))} models from service")
    except Exception as e:
        logger.warning(f"[ImageModels] Failed to populate from service: {e}")
        # Populate with hardcoded defaults if service is unavailable
        populate_defaults()

def populate_defaults():
    """Populate with default image models."""
    from django.utils import timezone

    default_models = [
        {
            "model_id": "openai/dall-e-3",
            "name": "DALL-E 3",
            "provider": "openai",
            "price_per_image": 0.040,
            "supports_generation": True,
            "supports_editing": False,
            "supports_variations": False,
            "supported_sizes": ["1024x1024", "1792x1024", "1024x1792"],
            "supported_qualities": ["standard", "hd"],
            "supported_styles": ["vivid", "natural"],
            "max_images_per_request": 1,
            "description": "Most capable DALL-E model with excellent prompt following",
            "best_for_photorealism": True,
            "best_for_illustration": True,
        },
        {
            "model_id": "openai/dall-e-2",
            "name": "DALL-E 2",
            "provider": "openai",
            "price_per_image": 0.020,
            "supports_generation": True,
            "supports_editing": True,
            "supports_variations": True,
            "supported_sizes": ["256x256", "512x512", "1024x1024"],
            "max_images_per_request": 10,
            "description": "Fast and affordable, supports editing and variations",
        },
        {
            "model_id": "openai/gpt-image-1",
            "name": "GPT Image 1",
            "provider": "openai",
            "price_per_image": 0.011,
            "supports_generation": True,
            "supports_editing": True,
            "supported_sizes": ["1024x1024", "1536x1024", "1024x1536"],
            "supported_qualities": ["low", "medium", "high"],
            "max_images_per_request": 1,
            "description": "Native GPT-4 image generation with transparent background support",
        },
        {
            "model_id": "bfl/flux-1.1-pro",
            "name": "FLUX 1.1 Pro",
            "provider": "bfl",
            "price_per_image": 0.040,
            "supports_generation": True,
            "supported_sizes": ["1024x1024"],
            "max_images_per_request": 1,
            "description": "State-of-the-art image quality from Black Forest Labs",
            "best_for_photorealism": True,
        },
        {
            "model_id": "bfl/flux-pro-ultra",
            "name": "FLUX Pro Ultra",
            "provider": "bfl",
            "price_per_image": 0.060,
            "supports_generation": True,
            "supported_sizes": ["up to 4MP"],
            "max_images_per_request": 1,
            "description": "Ultra high resolution up to 4 megapixels",
        },
        {
            "model_id": "bfl/flux-schnell",
            "name": "FLUX Schnell",
            "provider": "bfl",
            "price_per_image": 0.003,
            "supports_generation": True,
            "max_images_per_request": 1,
            "description": "Fast generation at lower cost",
            "is_fast": True,
        },
        {
            "model_id": "stability/stable-image-ultra",
            "name": "Stable Image Ultra",
            "provider": "stability",
            "price_per_image": 0.080,
            "supports_generation": True,
            "supported_aspect_ratios": ["1:1", "16:9", "21:9", "3:2", "2:3", "4:5", "5:4", "9:16", "9:21"],
            "max_images_per_request": 1,
            "description": "Stability AI's most advanced model",
            "best_for_photorealism": True,
        },
        {
            "model_id": "stability/stable-image-core",
            "name": "Stable Image Core",
            "provider": "stability",
            "price_per_image": 0.030,
            "supports_generation": True,
            "max_images_per_request": 1,
            "description": "Balanced quality and speed",
        },
        {
            "model_id": "ideogram/v2",
            "name": "Ideogram V2",
            "provider": "ideogram",
            "price_per_image": 0.080,
            "supports_generation": True,
            "max_images_per_request": 1,
            "description": "Excellent text rendering in images",
            "best_for_text": True,
        },
        {
            "model_id": "ideogram/v2-turbo",
            "name": "Ideogram V2 Turbo",
            "provider": "ideogram",
            "price_per_image": 0.050,
            "supports_generation": True,
            "max_images_per_request": 1,
            "description": "Fast version with good text rendering",
            "best_for_text": True,
            "is_fast": True,
        },
        {
            "model_id": "google/imagen-3",
            "name": "Imagen 3",
            "provider": "google",
            "price_per_image": 0.040,
            "supports_generation": True,
            "max_images_per_request": 4,
            "description": "Google's latest image generation model",
            "best_for_photorealism": True,
        },
        {
            "model_id": "google/imagen-3-fast",
            "name": "Imagen 3 Fast",
            "provider": "google",
            "price_per_image": 0.020,
            "supports_generation": True,
            "max_images_per_request": 4,
            "description": "Fast version of Imagen 3",
            "is_fast": True,
        },
        {
            "model_id": "google/gemini-2.5-flash-image",
            "name": "Nano Banana",
            "provider": "google",
            "price_per_image": 0.00,
            "supports_generation": True,
            "supported_sizes": ["1024x1024", "2048x2048"],
            "max_images_per_request": 1,
            "description": "Fast, good quality image generation",
            "is_fast": True,
        },
        {
            "model_id": "google/gemini-3-pro-image-preview",
            "name": "Nano Banana Pro",
            "provider": "google",
            "price_per_image": 0.04,
            "supports_generation": True,
            "supported_sizes": ["1024x1024", "2048x2048", "4096x4096"],
            "max_images_per_request": 1,
            "description": "Best quality, supports 4K resolution",
            "best_for_photorealism": True,
        },
    ]

    for model_data in default_models:
        model_id = model_data.pop("model_id")
        ImageModelCatalog.objects.update_or_create(
            model_id=model_id,
            defaults={
                **model_data,
                "is_available": True,
                "first_seen_at": timezone.now(),
            }
        )
    logger.info(f"[ImageModels] Populated {len(default_models)} default models")

def build_image_model_list_response(filters: dict, query_params, queryset) -> dict:
    """Build the cached, filtered, sorted image-model-list response body.

    `queryset` is the view's own `ImageModelCatalog` queryset; it is
    repopulated from the image-generation service when empty.
    """
    # Build cache key based on all filter parameters
    cache_key_data = {
        'filters': filters,
        'page': query_params.get('page', 1),
        'page_size': query_params.get('page_size', 25)
    }
    cache_key_hash = hashlib.md5(
        json.dumps(cache_key_data, sort_keys=True).encode()
    ).hexdigest()
    cache_key = f"image_models:list:{cache_key_hash}"

    # Try to get cached response
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        logger.debug(f"Cache HIT for image models list: {cache_key}")
        return cached_response

    logger.debug(f"Cache MISS for image models list: {cache_key}")

    # Try to fetch from image-generation service if catalog is empty
    queryset = queryset
    if not queryset.exists():
        populate_from_service()
        queryset = queryset

    # Apply filters
    if filters.get("search"):
        search_term = filters["search"]
        queryset = queryset.filter(
            models.Q(name__icontains=search_term) |
            models.Q(provider__icontains=search_term)
        )

    if filters.get("provider"):
        queryset = queryset.filter(provider__iexact=filters["provider"])

    if filters.get("available_only", True):
        queryset = queryset.filter(is_available=True)

    if "supports_editing" in query_params:
        queryset = queryset.filter(supports_editing=filters["supports_editing"])

    if "supports_variations" in query_params:
        queryset = queryset.filter(supports_variations=filters["supports_variations"])

    if "best_for_text" in query_params:
        queryset = queryset.filter(best_for_text=filters["best_for_text"])

    if "best_for_photorealism" in query_params:
        queryset = queryset.filter(best_for_photorealism=filters["best_for_photorealism"])

    if "is_fast" in query_params:
        queryset = queryset.filter(is_fast=filters["is_fast"])

    if filters.get("max_price"):
        queryset = queryset.filter(price_per_image__lte=filters["max_price"])

    # Apply sorting
    sort_by = filters.get("sort_by", "none")
    order = filters.get("order", "asc")
    order_prefix = "" if order == "asc" else "-"

    if sort_by == "price":
        queryset = queryset.order_by(f"{order_prefix}price_per_image")
    elif sort_by == "name":
        queryset = queryset.order_by(f"{order_prefix}name")
    elif sort_by == "provider":
        queryset = queryset.order_by(f"{order_prefix}provider", "name")

    # Serialize the results
    serializer = ImageModelCatalogSerializer(queryset, many=True)
    response_data = {
        "count": queryset.count(),
        "results": serializer.data
    }

    # Cache for 5 minutes
    cache.set(cache_key, response_data, timeout=300)

    return response_data
