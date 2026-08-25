"""
Image Generation Tools for LangChain.

Provides image generation capabilities using Nano Banana models with provider fallback:
1. Google AI Studio (Free tier, system API key)
2. OpenRouter (Fallback, uses user's API key)

Model constants are centralized in llm/image_providers/constants.py.
"""

import json
import logging
import uuid
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from asgiref.sync import sync_to_async
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from llm.image_providers import (
    ImageProviderChain,
    ImageGenerationResult,
    AllProvidersFailedError,
    ImageProviderError,
    get_default_model_id,
    is_valid_model,
)

logger = logging.getLogger(__name__)

# Default estimated cost for image generation when provider doesn't return actual cost.
# Used for quota estimation and billing fallback.
# Google AI Studio is free; OpenRouter returns actual cost from API.
DEFAULT_IMAGE_GENERATION_COST = Decimal("0.02")


# Context variable for passing user info to image tools
# Set this before invoking tools that need user context
IMAGE_TOOL_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    'image_tool_context', default=None
)


def set_image_tool_context(context: Dict[str, Any]) -> None:
    """Set the image tool context for the current execution."""
    IMAGE_TOOL_CONTEXT.set(context)


def get_image_tool_context() -> Optional[Dict[str, Any]]:
    """Get the current image tool context."""
    return IMAGE_TOOL_CONTEXT.get()


class ImageGenerateInput(BaseModel):
    """Input schema for image generation."""
    prompt: str = Field(
        ...,
        description=(
            "Detailed description of the image to generate. "
            "Be specific about: subjects, style (photorealistic/cartoon/artistic), "
            "composition, lighting, mood, colors, and background."
        )
    )
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = Field(
        "1:1",
        description="Image aspect ratio: 1:1 (square), 16:9 (landscape), 9:16 (portrait)"
    )
    resolution: Literal["1K", "2K", "4K"] = Field(
        "1K",
        description="Output resolution: 1K (fast), 2K (balanced), 4K (highest quality, slower)"
    )


class ImageEditInput(BaseModel):
    """Input schema for image editing."""
    image_url: str = Field(
        ...,
        description="URL of the image to edit (must be accessible)"
    )
    prompt: str = Field(
        ...,
        description="Description of the edit to make to the image"
    )


async def _store_generated_image(
    result: ImageGenerationResult,
    context: Dict[str, Any],
    prompt: str,
) -> Dict[str, Any]:
    """
    Store a generated image in R2 and create an Asset record.

    Returns dict with asset info or error.
    """
    try:
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        user_id = str(context.get("user_id", ""))
        chat_id = str(context.get("chat_id", ""))

        if not user_id or not chat_id:
            logger.error("[ImageTool] Missing user_id or chat_id in context")
            return {"error": "Missing context for storage"}

        # Validate chat_id is a valid UUID
        try:
            uuid.UUID(chat_id)
        except ValueError:
            logger.error(f"[ImageTool] Invalid chat_id: {chat_id}")
            return {"error": "Invalid chat ID - cannot store image"}

        # Generate asset ID
        asset_id = str(uuid.uuid4())

        # Store in R2/inline (in images/ subdirectory)
        storage_service = get_asset_storage_service()
        storage_result = storage_service.store_asset(
            user_id=user_id,
            chat_id=chat_id,
            asset_id=asset_id,
            content=result.image_data,
            mime_type=result.mime_type,
            asset_type="image",
        )

        if not storage_result.success:
            logger.error(f"[ImageTool] Storage failed: {storage_result.error}")
            return {"error": f"Failed to store image: {storage_result.error}"}

        # Determine file extension from mime type
        ext_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
        }
        ext = ext_map.get(result.mime_type, "png")
        filename = f"generated_{asset_id[:8]}.{ext}"

        # Create Asset record (using sync_to_async for ORM operations)
        from conversations.models import Chat

        @sync_to_async
        def get_chat():
            return Chat.objects.filter(id=chat_id).first()

        chat = await get_chat()

        if not chat:
            logger.error(f"[ImageTool] Chat {chat_id} not found")
            return {"error": "Chat not found"}

        @sync_to_async
        def create_asset():
            return Asset.objects.create(
                id=asset_id,
                user_id=user_id,
                chat=chat,
                asset_type=Asset.TYPE_GENERATED,
                filename=filename,
                mime_type=result.mime_type,
                size_bytes=len(result.image_data),
                storage_type=storage_result.storage_type,
                r2_bucket=storage_result.r2_bucket,
                r2_key=storage_result.r2_key,
                content=storage_result.content,  # Only for inline storage
                sha256_hash=storage_result.sha256_hash or result.get_sha256(),
                width=result.width,
                height=result.height,
                generation_prompt=prompt[:2000],  # Truncate if too long
                # Store canonical model ID (e.g., "google/gemini-2.5-flash-image")
                # NOT provider/model which would create "openrouter/google/..." for OpenRouter
                generation_model=result.model,
            )

        asset = await create_asset()

        logger.info(
            f"[ImageTool] Stored generated image: asset_id={asset_id}, "
            f"storage={storage_result.storage_type}, size={len(result.image_data)}"
        )

        # Build URL for the asset
        # Frontend will fetch via /api/workspaces/assets/{asset_id}/download/
        asset_url = f"/api/workspaces/assets/{asset_id}/download/"

        return {
            "asset_id": str(asset.id),
            "url": asset_url,
            "filename": filename,
            "width": result.width,
            "height": result.height,
            "mime_type": result.mime_type,
            "size_bytes": len(result.image_data),
        }

    except Exception as e:
        logger.exception(f"[ImageTool] Failed to store image: {e}")
        return {"error": f"Failed to store image: {str(e)}"}


async def _get_user_from_context(context: Dict[str, Any]):
    """Get user object from context, looking up by user_id if needed."""
    user = context.get("user")
    if user:
        return user

    user_id = context.get("user_id")
    if not user_id:
        return None

    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()

        @sync_to_async
        def get_user():
            return User.objects.filter(id=user_id).first()

        return await get_user()
    except Exception as e:
        logger.error(f"[ImageTool] Failed to look up user: {e}")
        return None


async def _get_user_api_key(context: Dict[str, Any]) -> Optional[str]:
    """
    Get the user's OpenRouter API key for the fallback provider.

    This uses the same key the user uses for chat messages.
    Returns None if user has no provisioned key (will cause OpenRouter fallback to fail).
    """
    user = await _get_user_from_context(context)
    if not user:
        logger.warning("[ImageTool] No user in context, cannot get API key")
        return None

    # Get user's personal key - same as used for chat messages
    try:
        @sync_to_async
        def get_user_key():
            # Access the user's encrypted OpenRouter API key
            return getattr(user, 'openrouter_api_key', None)

        api_key = await get_user_key()
        if api_key:
            logger.debug("[ImageTool] Using user's provisioned OpenRouter API key")
            return api_key
        else:
            logger.warning("[ImageTool] User has no provisioned OpenRouter API key")
            return None
    except Exception as e:
        logger.error(f"[ImageTool] Failed to get user API key: {e}")
        return None


async def _get_user_preferred_model(context: Dict[str, Any]) -> str:
    """
    Get the user's preferred image generation model from their settings.

    Returns the default model if user not found or no preference set.
    Model IDs are centralized in llm/image_providers/constants.py.

    Honors override_model from context (set via @generate_image [model:X] mention).
    """
    # Check for override from @mention params first
    override = context.get('override_model')
    if override and is_valid_model(override):
        logger.info(f"[ImageTool] Using override model from @mention: {override}")
        return override

    default_model = get_default_model_id()

    user = await _get_user_from_context(context)
    if not user:
        logger.warning("[ImageTool] No user context, using default model")
        return default_model

    # Get the user's preferred model from their settings
    preferred = getattr(user, "preferred_image_model", None)
    if preferred and is_valid_model(preferred):
        return preferred

    return default_model


# Shared constant tagged on every per-image UsageLog row so the count
# provider in feature_registry.py can attribute count without false
# positives from the agent's accumulated_tool_cost aggregate.
IMAGE_GEN_EXTRA = {'tool': 'generate_image'}


async def _record_billing(
    context: Dict[str, Any],
    result: ImageGenerationResult,
    model: str,
    *,
    billing_origin: str = 'platform',
) -> None:
    """Record billing for the image generation.

    Writes one UsageLog row per image with service=IMAGE_GENERATION and
    extra_data={'tool': 'generate_image'} — feeding the image-gen count
    provider used by the tier matrix.
    """
    try:
        user = await _get_user_from_context(context)
        if not user:
            logger.warning("[ImageTool] No user in context, skipping billing")
            return

        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.models import ServiceType, FeatureType

        operation = BillableOperation(
            service=ServiceType.IMAGE_GENERATION,
            feature=FeatureType.CHAT,
            model_id=f"{result.provider}/{model}",
            request_count=1,
            cost_usd=result.cost_usd or DEFAULT_IMAGE_GENERATION_COST,
            extra_data=IMAGE_GEN_EXTRA,
        )

        @sync_to_async
        def do_record():
            billing = get_billing_service()
            billing.record_usage(user, operation, billing_origin=billing_origin)

        await do_record()

        logger.info(
            f"[ImageTool] Recorded billing: model={model}, "
            f"provider={result.provider}, cost=${result.cost_usd}, "
            f"origin={billing_origin}"
        )

    except Exception as e:
        logger.error(f"[ImageTool] Failed to record billing: {e}")
        # Don't fail the whole operation for billing errors


async def _check_quota(context: Dict[str, Any], model: str) -> Optional[str]:
    """Tier + USD pre-flight for image generation.

    Routes through ``BillingService.check_quota(feature_name='image_generation')``,
    which raises ``FeatureNotAvailable`` / ``QuotaExceeded`` on denial.
    Returns ``None`` on pass, or an error string on tier/quota denial
    (the tool returns this in its JSON envelope; the LLM sees the
    structured error).
    """
    try:
        user = await _get_user_from_context(context)
        if not user:
            return None  # No user context, skip quota check

        from usage_quota.billing.service import get_billing_service
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        from usage_quota.models import ServiceType, FeatureType

        estimated_cost = DEFAULT_IMAGE_GENERATION_COST

        @sync_to_async
        def do_check():
            billing = get_billing_service()
            return billing.check_quota(
                user=user,
                service=ServiceType.IMAGE_GENERATION,
                estimated_cost=estimated_cost,
                feature=FeatureType.CHAT,
                feature_name='image_generation',
            )

        try:
            await do_check()
        except FeatureNotAvailableException as exc:
            return exc.message
        except QuotaExceededException as exc:
            return exc.message

        return None

    except Exception as e:
        logger.error(f"[ImageTool] Quota check failed: {e}")
        return None  # Don't block on quota check errors


@tool("generate_image", args_schema=ImageGenerateInput)
async def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
) -> str:
    """
    Generate an image from a text description using AI.

    Use this tool when the user asks you to:
    - Create, generate, draw, or make an image
    - Visualize something
    - Create artwork, illustrations, logos, or graphics
    - Generate a picture of anything

    Provide detailed prompts for best results. Include:
    - Main subjects and their appearance
    - Setting and background
    - Style (photorealistic, cartoon, artistic, anime, etc.)
    - Lighting and mood
    - Composition and perspective

    Examples:
    - "A serene mountain lake at sunset, photorealistic, golden hour lighting, reflections in water"
    - "Cute cartoon cat wearing a wizard hat, digital art style, whimsical, colorful"
    - "Modern minimalist logo for a coffee shop, clean lines, earth tones, professional"
    - "Futuristic city skyline at night, cyberpunk style, neon lights, rain-slicked streets"
    """
    context = get_image_tool_context()
    if not context:
        logger.warning("[ImageTool] No context set, proceeding without user tracking")
        context = {}

    # Honor overrides from @mention params
    if context.get('override_aspect_ratio'):
        aspect_ratio = context['override_aspect_ratio']
        logger.info(f"[ImageTool] Using override aspect_ratio from @mention: {aspect_ratio}")
    if context.get('override_resolution'):
        resolution = context['override_resolution']
        logger.info(f"[ImageTool] Using override resolution from @mention: {resolution}")

    # Get user's preferred model from settings
    model = await _get_user_preferred_model(context)

    logger.info(f"[ImageTool] Generating image: prompt={prompt[:100]}..., model={model}, resolution={resolution}")

    # Check quota first
    quota_error = await _check_quota(context, model)
    if quota_error:
        return json.dumps({
            "status": "error",
            "error_type": "quota_exceeded",
            "message": quota_error,
        })

    try:
        # Get user's OpenRouter API key for fallback provider
        user_api_key = await _get_user_api_key(context)

        # Initialize provider chain with user's API key
        provider_chain = ImageProviderChain(user_api_key=user_api_key)

        if not provider_chain.is_available():
            return json.dumps({
                "status": "error",
                "error_type": "configuration",
                "message": "No image generation providers configured. Please contact support.",
            })

        result = await provider_chain.generate(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            user_api_key=user_api_key,
        )

        # Store the image
        storage_info = await _store_generated_image(result, context, prompt)

        if "error" in storage_info:
            return json.dumps({
                "status": "error",
                "error_type": "storage",
                "message": storage_info["error"],
            })

        # Always write a per-image UsageLog row (service=IMAGE_GENERATION,
        # tagged 'tool': 'generate_image') so the image-gen count provider
        # has a single attribution path. The OpenRouter aggregate in
        # The chat aggregate cost-ledger row subtracts image-gen cost before writing its
        # aggregate row — see Section 2.11 of the task-10 plan.
        # For non-OpenRouter providers, bill the platform (default).
        # For OpenRouter, billing_origin follows the user's API-key
        # resolution (BYOK vs platform).
        bill_origin = 'platform'
        if result.provider == 'openrouter':
            try:
                user_for_origin = await _get_user_from_context(context)
                if user_for_origin is not None:
                    from llm.services.api_key_resolver import resolve_with_origin
                    _, bill_origin = await sync_to_async(resolve_with_origin)(
                        user=user_for_origin,
                    )
            except Exception:
                bill_origin = 'platform'
        await _record_billing(context, result, model, billing_origin=bill_origin)

        # Generate a short name from the prompt (first ~50 chars, break at word boundary)
        def generate_short_name(p: str, max_len: int = 50) -> str:
            p = p.strip()
            if len(p) <= max_len:
                return p
            # Find last space before max_len
            truncated = p[:max_len]
            last_space = truncated.rfind(' ')
            if last_space > 20:
                return truncated[:last_space]
            return truncated

        # Build asset URL for use with edit_image tool
        asset_url = f"/api/workspaces/assets/{storage_info['asset_id']}/download/"

        # Calculate cost for frontend display
        cost_usd = result.cost_usd or DEFAULT_IMAGE_GENERATION_COST

        # Return success response
        # Note: The image is automatically displayed to the user via the frontend.
        # The asset_url is included only for use with the edit_image tool if the user wants modifications.
        response = {
            "status": "success",
            "message": "Image generated successfully. The image is now displayed to the user. Do NOT output the asset_url - it is only for use with edit_image tool.",
            "image": {
                "asset_id": storage_info["asset_id"],
                "asset_url": asset_url,  # For use with edit_image tool
                "width": storage_info["width"],
                "height": storage_info["height"],
                "name": generate_short_name(prompt),
                "description": prompt,
            },
            "model": model,
            "provider": result.provider,  # Used by the cost ledger to determine billing path
            "generation_time_ms": result.generation_time_ms,
            "cost_usd": float(cost_usd),  # Include cost for frontend to add to message total
        }

        if result.revised_prompt:
            response["revised_prompt"] = result.revised_prompt

        return json.dumps(response, ensure_ascii=False)

    except AllProvidersFailedError as e:
        logger.error(f"[ImageTool] All providers failed: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "generation_failed",
            "message": "Image generation failed. All providers are currently unavailable. Please try again later.",
        })

    except ImageProviderError as e:
        logger.error(f"[ImageTool] Provider error: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "provider_error",
            "message": f"Image generation failed: {str(e)}",
        })

    except Exception as e:
        logger.exception(f"[ImageTool] Unexpected error: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "unexpected",
            "message": "An unexpected error occurred while generating the image.",
        })


@tool("edit_image", args_schema=ImageEditInput)
async def edit_image(
    image_url: str,
    prompt: str,
) -> str:
    """
    Edit an existing image based on a text description.

    Use this tool when the user wants to:
    - Modify or change an existing image
    - Add or remove elements from an image
    - Edit specific parts of an image
    - Apply transformations to an image

    Args:
        image_url: URL of the image to edit (can be an asset URL from a previous generation)
        prompt: Description of the edit to make

    Examples:
    - "Add a rainbow in the sky"
    - "Change the background to a beach scene"
    - "Make the car red instead of blue"
    - "Remove the person in the background"
    """
    context = get_image_tool_context()
    if not context:
        context = {}

    # Get user's preferred model from settings
    model = await _get_user_preferred_model(context)

    logger.info(f"[ImageTool] Editing image: url={image_url[:50]}..., prompt={prompt[:100]}..., model={model}")

    # Check quota
    quota_error = await _check_quota(context, model)
    if quota_error:
        return json.dumps({
            "status": "error",
            "error_type": "quota_exceeded",
            "message": quota_error,
        })

    try:
        # Fetch the source image
        image_data = await _fetch_image(image_url, context)
        if image_data is None:
            return json.dumps({
                "status": "error",
                "error_type": "fetch_failed",
                "message": "Could not fetch the source image. Please check the URL.",
            })

        # Get user's OpenRouter API key for fallback provider
        user_api_key = await _get_user_api_key(context)

        # Initialize provider chain with user's API key
        provider_chain = ImageProviderChain(user_api_key=user_api_key)

        if not provider_chain.is_available():
            return json.dumps({
                "status": "error",
                "error_type": "configuration",
                "message": "No image generation providers configured.",
            })

        result = await provider_chain.edit(
            image_data=image_data,
            prompt=prompt,
            model=model,
            user_api_key=user_api_key,
        )

        # Store the edited image
        storage_info = await _store_generated_image(result, context, f"Edit: {prompt}")

        if "error" in storage_info:
            return json.dumps({
                "status": "error",
                "error_type": "storage",
                "message": storage_info["error"],
            })

        # Always write a per-image UsageLog row (service=IMAGE_GENERATION,
        # tagged 'tool': 'generate_image'). For OpenRouter-routed
        # edit_image calls, billing_origin follows the user's API-key
        # resolution. The chat aggregate cost-ledger row subtracts
        # image-gen cost so the same dollars aren't double-billed.
        bill_origin = 'platform'
        if result.provider == 'openrouter':
            try:
                user_for_origin = await _get_user_from_context(context)
                if user_for_origin is not None:
                    from llm.services.api_key_resolver import resolve_with_origin
                    _, bill_origin = await sync_to_async(resolve_with_origin)(
                        user=user_for_origin,
                    )
            except Exception:
                bill_origin = 'platform'
        await _record_billing(context, result, model, billing_origin=bill_origin)

        # Generate a short name from the prompt
        def generate_short_name(p: str, max_len: int = 50) -> str:
            p = p.strip()
            if len(p) <= max_len:
                return p
            truncated = p[:max_len]
            last_space = truncated.rfind(' ')
            if last_space > 20:
                return truncated[:last_space]
            return truncated

        # Calculate cost for frontend display
        cost_usd = result.cost_usd or DEFAULT_IMAGE_GENERATION_COST

        # Note: We don't include the URL - the frontend uses asset_id to load via AssetImage component
        return json.dumps({
            "status": "success",
            "message": "Image edited successfully. The image is now displayed to the user.",
            "image": {
                "asset_id": storage_info["asset_id"],
                "width": storage_info["width"],
                "height": storage_info["height"],
                "name": f"Edit: {generate_short_name(prompt, 40)}",
                "description": prompt,
            },
            "model": model,
            "provider": result.provider,  # Used by the cost ledger to determine billing path
            "generation_time_ms": result.generation_time_ms,
            "cost_usd": float(cost_usd),  # Include cost for frontend to add to message total
        }, ensure_ascii=False)

    except AllProvidersFailedError as e:
        logger.error(f"[ImageTool] All providers failed for edit: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "generation_failed",
            "message": "Image editing failed. Please try again later.",
        })

    except Exception as e:
        logger.exception(f"[ImageTool] Edit error: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "unexpected",
            "message": f"An error occurred while editing the image: {str(e)}",
        })


async def _fetch_image(url: str, context: Dict[str, Any]) -> Optional[bytes]:
    """
    Fetch image data from a URL.

    Handles both external URLs and internal asset URLs.
    """
    import httpx

    # Check if it's an internal asset URL
    if "/api/workspaces/assets/" in url and "/download/" in url:
        try:
            # Extract asset ID from URL
            parts = url.split("/")
            asset_id_idx = parts.index("assets") + 1
            asset_id = parts[asset_id_idx]

            # Fetch from storage (using sync_to_async for ORM)
            from workspaces.models import Asset
            from workspaces.services.asset_storage import get_asset_storage_service

            @sync_to_async
            def get_asset_and_retrieve():
                asset = Asset.objects.filter(id=asset_id).first()
                if asset:
                    storage_service = get_asset_storage_service()
                    return storage_service.retrieve_asset(asset)
                return None

            asset_data = await get_asset_and_retrieve()
            if asset_data:
                return asset_data

        except Exception as e:
            logger.error(f"[ImageTool] Failed to fetch internal asset: {e}")

    # Fetch from external URL
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"[ImageTool] Failed to fetch image from {url}: {e}")
        return None


# Export all tools
IMAGE_TOOLS = [
    generate_image,
    edit_image,
]
