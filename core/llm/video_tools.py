"""
LangChain tools for video generation.

Supports multiple video operation types:
- Text-to-video (generate_video)
- Image-to-video (animate_image)
- Video upscaling (upscale_video)
- Character animation (animate_character)

All model configuration is fetched from the database (VideoModelCatalog).
"""

import hashlib
import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from asgiref.sync import sync_to_async
from django.utils import timezone
from langchain_core.tools import tool

from usage_quota.billing.service import get_billing_service
from usage_quota.billing.operations import BillableOperation
from usage_quota.models import ServiceType, FeatureType
from workspaces.models import Asset
from conversations.models import Chat
from workspaces.services.asset_storage import get_asset_storage_service

from .video_providers import (
    BaseVideoProvider,
    OpenAISoraProvider,
    RunwayProvider,
    VideoProviderError,
    RateLimitError,
    GenerationTimeoutError,
    ContentPolicyError,
    InvalidPromptError,
)
from .video_providers.base import (
    VideoGenerationInput,
    VideoInputType,
    InvalidInputError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Default Values
# =============================================================================

DEFAULT_DURATION_SECONDS = 4
DEFAULT_ASPECT_RATIO = "16:9"
SUPPORTED_ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")

# Asset URL resolution
ASSET_URL_PATTERN = re.compile(r'/api/workspaces/assets/([0-9a-fA-F-]+)/download/?')
PRESIGNED_URL_EXPIRATION = 7200  # 2 hours - enough for long video generation


# =============================================================================
# Context Management
# =============================================================================

VIDEO_TOOL_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "video_tool_context", default=None
)


def set_video_tool_context(context: Dict[str, Any]) -> None:
    """
    Set the video tool context for the current async context.

    Args:
        context: Dictionary containing user_id and conversation_id
    """
    VIDEO_TOOL_CONTEXT.set(context)


def get_video_tool_context() -> Dict[str, Any]:
    """Get the current video tool context."""
    return VIDEO_TOOL_CONTEXT.get() or {}


def clear_video_tool_context() -> None:
    """Clear the video tool context."""
    VIDEO_TOOL_CONTEXT.set(None)


# =============================================================================
# Provider Factory
# =============================================================================


def _get_provider_for_model(provider_name: str) -> BaseVideoProvider:
    """
    Get the appropriate provider instance for a given provider name.

    Args:
        provider_name: The provider name (e.g., 'openai', 'runway')

    Returns:
        The appropriate provider instance

    Raises:
        ValueError: If the provider is unknown
    """
    if provider_name == "openai":
        return OpenAISoraProvider()
    elif provider_name == "runway":
        return RunwayProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


# =============================================================================
# Asset URL Resolution
# =============================================================================


def _get_asset_type_from_mime(mime_type: str) -> str:
    """Determine asset type from MIME type for R2 path structure."""
    if mime_type and mime_type.startswith('image/'):
        return 'image'
    elif mime_type and mime_type.startswith('video/'):
        return 'video'
    elif mime_type and mime_type.startswith('audio/'):
        return 'audio'
    return 'file'


def _upload_inline_asset_to_r2_sync(
    asset: Asset,
    storage_service: Any,
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Upload inline asset to R2 and return presigned URL.

    For small assets stored in PostgreSQL, we need to upload to R2
    to generate a presigned URL for external providers.
    """
    if not asset.content:
        return None

    content = bytes(asset.content)
    user_id = context.get("user_id")
    chat_id = context.get("chat_id")

    # Generate R2 key for temporary storage
    r2_key = storage_service.generate_r2_key(
        user_id=str(user_id),
        chat_id=str(chat_id),
        asset_id=str(asset.id),
        asset_type=_get_asset_type_from_mime(asset.mime_type),
    )

    # Upload to R2
    success = storage_service._upload_to_r2(r2_key, content, asset.mime_type)
    if not success:
        logger.error(f"[VideoTool] Failed to upload inline asset {asset.id} to R2")
        return None

    # Update asset record to track R2 location (keeps inline as backup)
    asset.r2_key = r2_key
    asset.r2_bucket = storage_service.config.bucket_name
    asset.save(update_fields=['r2_key', 'r2_bucket'])

    logger.info(f"[VideoTool] Uploaded inline asset {asset.id} to R2: {r2_key}")

    # Generate presigned URL
    try:
        client = storage_service._workspace_storage._get_r2_client()
        if not client:
            logger.error("[VideoTool] R2 client not available for presigning")
            return None

        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': storage_service.config.bucket_name,
                'Key': r2_key,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRATION,
        )
        return url
    except Exception as e:
        logger.error(f"[VideoTool] Failed to presign uploaded inline asset: {e}")
        return None


async def _resolve_asset_url(url: str, context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve internal asset URLs to presigned R2 URLs for external access.

    External providers (Runway, OpenAI) cannot access our authenticated
    asset endpoints. This function detects internal URLs and converts them
    to presigned R2 URLs that are publicly accessible for a limited time.

    Args:
        url: The URL to resolve (may be internal or external)
        context: Video tool context with user_id

    Returns:
        Presigned R2 URL if internal asset, original URL otherwise.
        Returns None if resolution fails for an internal URL.
    """
    if not url:
        return url

    # Check if this is an internal asset URL
    match = ASSET_URL_PATTERN.search(url)
    if not match:
        # External URL, return as-is
        return url

    asset_id = match.group(1)
    logger.info(f"[VideoTool] Resolving internal asset URL: {asset_id}")

    @sync_to_async
    def get_asset_and_presign():
        try:
            asset = Asset.objects.get(id=asset_id)
        except Asset.DoesNotExist:
            logger.warning(f"[VideoTool] Asset not found: {asset_id}")
            return None

        # Verify ownership
        user_id = context.get("user_id")
        if str(asset.user_id) != str(user_id):
            logger.warning(
                f"[VideoTool] Asset ownership mismatch: {asset_id} "
                f"(asset user: {asset.user_id}, context user: {user_id})"
            )
            return None

        storage_service = get_asset_storage_service()

        # Handle inline storage - need to upload to R2 first
        if asset.storage_type == Asset.STORAGE_INLINE:
            logger.info(f"[VideoTool] Asset {asset_id} is inline, uploading to R2")
            return _upload_inline_asset_to_r2_sync(asset, storage_service, context)

        # Generate presigned URL for R2 storage
        presigned_url = storage_service.get_presigned_url(
            asset,
            expiration=PRESIGNED_URL_EXPIRATION
        )

        if presigned_url:
            logger.info(f"[VideoTool] Resolved asset {asset_id} to presigned URL")
            return presigned_url

        logger.error(f"[VideoTool] Failed to generate presigned URL for {asset_id}")
        return None

    return await get_asset_and_presign()


# =============================================================================
# Smart Model Selection
# =============================================================================


def _is_compatible_input_type(model_input_type: str, required_input_type: str) -> bool:
    """
    Check if a model's input_type is compatible with the required input type.

    Models with 'image_video' input type accept both image and video inputs,
    so they are compatible with both IMAGE and VIDEO operations.
    """
    if model_input_type == required_input_type:
        return True
    # image_video models accept both image and video inputs
    if model_input_type == "image_video" and required_input_type in ("image", "video"):
        return True
    return False


async def _select_model_for_input_type(
    input_type: VideoInputType,
    context: Dict[str, Any],
    explicit_model_id: Optional[str] = None,
    quality: str = "standard",
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Select the best model for the given input type with smart fallback.

    Priority:
    1. Explicit model_id (if provided and supports input type)
    2. User's preferred model (if supports input type)
    3. Default model for input type
    4. Any active model supporting input type

    The fallback is silent - users won't see an error, but logs will
    record the fallback reason for debugging.

    Args:
        input_type: Required input type (TEXT, IMAGE, VIDEO, IMAGE_AUDIO)
        context: Tool context with user_id
        explicit_model_id: Specific model requested (optional)
        quality: "standard" or "pro"

    Returns:
        Tuple of (VideoModelCatalog, fallback_reason or None)
        fallback_reason is None if no fallback occurred
    """
    from authentication.models import User
    from llm.models import VideoModelCatalog

    @sync_to_async
    def get_user():
        return User.objects.filter(id=context.get("user_id")).first()

    @sync_to_async
    def get_model_by_id(model_id):
        return VideoModelCatalog.get_by_model_id(model_id)

    @sync_to_async
    def get_model_by_canonical(canonical_id):
        return VideoModelCatalog.get_by_canonical_id(canonical_id)

    @sync_to_async
    def get_default_for_type(it):
        return VideoModelCatalog.get_default_for_input_type(it.value)

    @sync_to_async
    def get_pro_model(base_model, it):
        return VideoModelCatalog.objects.filter(
            provider=base_model.provider,
            input_type=it.value,
            is_pro=True,
            is_active=True,
        ).first()

    fallback_reason = None

    # 0. Check override from @mention params (highest priority)
    override_model = context.get('override_model')
    if override_model:
        model = await get_model_by_id(override_model)
        if not model:
            model = await get_model_by_canonical(override_model)
        if model and _is_compatible_input_type(model.input_type, input_type.value):
            logger.info(f"[VideoTool] Using override model from @mention: {override_model}")
            if quality == "pro" and not model.is_pro:
                pro_model = await get_pro_model(model, input_type)
                if pro_model:
                    return pro_model, None
            return model, None
        elif model:
            fallback_reason = (
                f"Override model '{override_model}' requires {model.input_type} input, "
                f"but operation needs {input_type.value}"
            )
            logger.info(f"[VideoTool] {fallback_reason}, finding alternative")

    # 1. Check explicit model_id
    if explicit_model_id:
        model = await get_model_by_id(explicit_model_id)
        if model:
            if _is_compatible_input_type(model.input_type, input_type.value):
                # Model matches required input type
                if quality == "pro" and not model.is_pro:
                    pro_model = await get_pro_model(model, input_type)
                    if pro_model:
                        return pro_model, None
                return model, None
            else:
                # Model doesn't support this input type - fall through
                fallback_reason = (
                    f"Requested model '{explicit_model_id}' requires {model.input_type} input, "
                    f"but operation needs {input_type.value}"
                )
                logger.info(f"[VideoTool] {fallback_reason}, finding alternative")

    # 2. Check user's preferred model (if applicable)
    user = await get_user()
    if user and user.preferred_video_model:
        preferred = await get_model_by_canonical(user.preferred_video_model)
        if not preferred:
            preferred = await get_model_by_id(user.preferred_video_model)

        if preferred and _is_compatible_input_type(preferred.input_type, input_type.value):
            # User's preferred model matches required input type
            if quality == "pro" and not preferred.is_pro:
                pro_model = await get_pro_model(preferred, input_type)
                if pro_model:
                    return pro_model, fallback_reason
            return preferred, fallback_reason
        elif preferred:
            if not fallback_reason:
                fallback_reason = (
                    f"User's preferred model '{preferred.canonical_id}' requires {preferred.input_type} input, "
                    f"but operation needs {input_type.value}"
                )
            logger.info(
                f"[VideoTool] User's preferred model doesn't support {input_type.value}, "
                f"finding alternative"
            )

    # 3. Get default model for this input type
    default = await get_default_for_type(input_type)
    if default:
        if not fallback_reason:
            # No fallback occurred, this is the expected path for non-text input types
            pass
        else:
            logger.info(f"[VideoTool] Using default model for {input_type.value}: {default.canonical_id}")

        # Pro upgrade if requested
        if quality == "pro" and not default.is_pro:
            pro_model = await get_pro_model(default, input_type)
            if pro_model:
                return pro_model, fallback_reason
        return default, fallback_reason

    # 4. No model found
    logger.error(f"[VideoTool] No active model found for input type: {input_type.value}")
    return None, f"No model available for {input_type.value}"


# =============================================================================
# Text-to-Video Tool
# =============================================================================


@tool("generate_video")
async def generate_video(
    prompt: str,
    duration: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    quality: str = "standard",
) -> str:
    """
    Generate a video from a text prompt using AI.

    The model used depends on the user's preferred video model setting.

    Args:
        prompt: Detailed description of the video to generate. Be specific about
            the scene, action, lighting, camera movement, and style.
        duration: Video length in seconds. Supported durations vary by model.
            Defaults to 4-5 seconds.
        aspect_ratio: Video aspect ratio. Options: "16:9" (landscape),
            "9:16" (portrait/mobile). Defaults to "16:9".
        quality: Video quality level. "standard" or "pro". Defaults to "standard".

    Returns:
        JSON string with video asset information including asset_id, download_url,
        dimensions, duration, and cost. Or error details if generation failed.
    """

    return await _execute_video_generation(
        input_type=VideoInputType.TEXT,
        prompt=prompt,
        duration=duration,
        aspect_ratio=aspect_ratio,
        quality=quality,
    )


# =============================================================================
# Image-to-Video Tool
# =============================================================================


@tool("animate_image")
async def animate_image(
    image_url: str,
    prompt: Optional[str] = None,
    duration: Optional[int] = None,
) -> str:
    """
    Animate a static image into a video.

    Uses image-to-video models (Gen-4 Turbo/Aleph) to bring images to life.

    Args:
        image_url: URL of the image to animate. Can be a public URL or an
            internal asset URL (/api/workspaces/assets/{id}/download/).
            Supported formats: JPEG, PNG, WebP.
        prompt: Optional text prompt to guide the animation. Describe the desired
            motion, camera movement, and effects.
        duration: Video length in seconds. Options: 5 or 10 seconds.
            Defaults to 5 seconds.

    Returns:
        JSON string with video asset information or error details.
    """
    return await _execute_video_generation(
        input_type=VideoInputType.IMAGE,
        image_url=image_url,
        prompt=prompt,
        duration=duration,
    )


# =============================================================================
# Video Upscaling Tool
# =============================================================================


@tool("upscale_video")
async def upscale_video(
    video_url: str,
) -> str:
    """
    Upscale a video to higher resolution.

    Note: Video upscaling is currently unavailable via the API.

    Args:
        video_url: URL of the video to upscale.

    Returns:
        JSON string with error details (currently unsupported).
    """
    return json.dumps({
        "status": "error",
        "error_type": "unsupported",
        "message": "Video upscaling is currently unavailable. The upscale API endpoint has been deprecated.",
    })


# =============================================================================
# Character Animation Tool (Act Two)
# =============================================================================


@tool("animate_character")
async def animate_character(
    image_url: str,
    reference_video_url: str,
) -> str:
    """
    Animate a character using a reference performance video (Act Two).

    Creates an animated video where the character mimics the performance
    (facial expressions, lip movements, gestures) from the reference video.

    Args:
        image_url: URL of the character image or video. Can be a public URL or an
            internal asset URL (/api/workspaces/assets/{id}/download/).
            Must show a recognizable face. Supported formats: JPEG, PNG, WebP, MP4.
        reference_video_url: URL of the reference performance video. Must be a video
            of a person performing (talking, expressing, gesturing). Duration: 3-30 seconds.
            Can be a public URL or an internal asset URL.
            Supported formats: MP4, WebM, MOV.

    Returns:
        JSON string with animated video asset information or error details.
    """
    return await _execute_video_generation(
        input_type=VideoInputType.IMAGE_AUDIO,
        image_url=image_url,
        audio_url=reference_video_url,  # Mapped to reference in provider
    )


# =============================================================================
# Unified Execution Function
# =============================================================================


async def _execute_video_generation(
    input_type: VideoInputType,
    prompt: Optional[str] = None,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    audio_url: Optional[str] = None,
    duration: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    quality: str = "standard",
    model_id: Optional[str] = None,
) -> str:
    """
    Execute video generation with the appropriate provider and model.

    This is the core function that handles all video generation operations.
    It selects the correct model based on input type and user preferences,
    resolves internal asset URLs to presigned R2 URLs for external provider access,
    and handles billing with the actual model used (including after fallback).
    """
    start_time = time.time()
    context = get_video_tool_context()

    if not context:
        logger.error("[VideoTool] Context not set")
        return json.dumps({
            "status": "error",
            "error_type": "context_missing",
            "message": "Video generation context not set. This is an internal error.",
        })

    user_id = context.get("user_id")

    if not user_id:
        return json.dumps({
            "status": "error",
            "error_type": "context_invalid",
            "message": "User ID not found in context.",
        })

    # Honor overrides from @mention params
    if context.get('override_aspect_ratio'):
        aspect_ratio = context['override_aspect_ratio']
        logger.info(f"[VideoTool] Using override aspect_ratio from @mention: {aspect_ratio}")
    if context.get('override_duration'):
        try:
            duration = int(context['override_duration'])
            logger.info(f"[VideoTool] Using override duration from @mention: {duration}")
        except (ValueError, TypeError):
            pass
    if context.get('override_quality'):
        quality = context['override_quality']
        logger.info(f"[VideoTool] Using override quality from @mention: {quality}")

    # =========================================================================
    # Resolve internal asset URLs to presigned R2 URLs
    # =========================================================================
    if image_url:
        resolved_image_url = await _resolve_asset_url(image_url, context)
        if resolved_image_url is None:
            return json.dumps({
                "status": "error",
                "error_type": "asset_resolution_failed",
                "message": "Failed to resolve image asset URL. The asset may not exist or you may not have access.",
            })
        image_url = resolved_image_url

    if video_url:
        resolved_video_url = await _resolve_asset_url(video_url, context)
        if resolved_video_url is None:
            return json.dumps({
                "status": "error",
                "error_type": "asset_resolution_failed",
                "message": "Failed to resolve video asset URL. The asset may not exist or you may not have access.",
            })
        video_url = resolved_video_url

    if audio_url:
        resolved_audio_url = await _resolve_asset_url(audio_url, context)
        if resolved_audio_url is None:
            return json.dumps({
                "status": "error",
                "error_type": "asset_resolution_failed",
                "message": "Failed to resolve audio asset URL. The asset may not exist or you may not have access.",
            })
        audio_url = resolved_audio_url

    # =========================================================================
    # Select model with smart fallback
    # =========================================================================
    model_config, fallback_reason = await _select_model_for_input_type(
        input_type=input_type,
        context=context,
        explicit_model_id=model_id,
        quality=quality,
    )

    if not model_config:
        return json.dumps({
            "status": "error",
            "error_type": "model_not_found",
            "message": f"No suitable model found for {input_type.value} operation",
        })

    # Log fallback (silent to user, visible in logs for debugging)
    if fallback_reason:
        logger.info(f"[VideoTool] Model fallback: {fallback_reason}")

    logger.info(
        f"[VideoTool] Using model: {model_config.canonical_id} "
        f"(input_type={input_type.value})"
    )

    # Apply defaults
    duration = duration or DEFAULT_DURATION_SECONDS
    aspect_ratio = aspect_ratio or DEFAULT_ASPECT_RATIO

    # Validate aspect ratio
    if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
        logger.warning(
            f"[VideoTool] Invalid aspect ratio '{aspect_ratio}', "
            f"using default '{DEFAULT_ASPECT_RATIO}'"
        )
        aspect_ratio = DEFAULT_ASPECT_RATIO

    # Clamp duration to model's max
    capabilities = model_config.capabilities or {}
    max_duration = capabilities.get("max_duration", 12)
    original_duration = duration
    duration = min(duration, max_duration)
    if duration != original_duration:
        logger.info(
            f"[VideoTool] Duration clamped from {original_duration}s "
            f"to {duration}s (model max)"
        )

    # Pre-flight quota check
    try:
        quota_result = await _check_video_quota(context, model_config, duration)
        if quota_result:
            return quota_result
    except Exception as e:
        logger.exception("[VideoTool] Quota check failed")
        return json.dumps({
            "status": "error",
            "error_type": "quota_check_failed",
            "message": f"Failed to check quota: {str(e)}",
        })

    # Initialize provider
    try:
        provider = _get_provider_for_model(model_config.provider)
    except ValueError as e:
        logger.error(f"[VideoTool] Unknown provider: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "provider_error",
            "message": str(e),
        })

    # Build input data
    input_data = VideoGenerationInput(
        prompt=prompt,
        image_url=image_url,
        video_url=video_url,
        audio_url=audio_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
    )

    try:
        # Validate input for the model's expected type
        model_input_type_str = model_config.input_type
        model_input_type = VideoInputType(model_input_type_str)
        input_data.validate_for_input_type(model_input_type)
    except InvalidInputError as e:
        return json.dumps({
            "status": "error",
            "error_type": "invalid_input",
            "message": str(e),
        })

    try:
        # Start generation job
        result = await provider.generate(
            model_id=model_config.model_id,
            input_data=input_data,
        )

        logger.info(f"[VideoTool] Job started: {result.job_id}")

        # Poll until complete
        result = await provider.poll_until_complete(job_id=result.job_id)

        if result.is_failed():
            logger.error(f"[VideoTool] Generation failed: {result.error_message}")
            return json.dumps({
                "status": "error",
                "error_type": "generation_failed",
                "message": result.error_message or "Video generation failed",
                "error_code": result.error_code,
            })

        # Download video bytes
        video_bytes = await provider.download(result.job_id)
        logger.info(f"[VideoTool] Downloaded {len(video_bytes)} bytes")

        # Calculate cost using database pricing
        cost_usd = model_config.calculate_cost(duration_seconds=result.duration_seconds)

        # Store video asset
        asset = await _store_generated_video(
            video_bytes=video_bytes,
            context=context,
            prompt=prompt or "",
            model_config=model_config,
            width=result.width,
            height=result.height,
            duration_seconds=result.duration_seconds,
        )

        logger.info(f"[VideoTool] Asset stored: {asset.id}")

        # Record billing
        await _record_video_billing(
            context=context,
            cost_usd=cost_usd,
            model_config=model_config,
            duration_seconds=result.duration_seconds,
        )

        generation_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"[VideoTool] Generation complete: asset_id={asset.id}, "
            f"cost=${cost_usd}, time={generation_time_ms}ms"
        )

        # Return info for LLM and frontend
        # NOTE: cost_usd is used by the chat turn's cost ledger to accumulate message costs
        # The LLM is instructed via system prompt NOT to mention costs/URLs to users
        # video.asset_id is required by frontend to display the video
        return json.dumps({
            "status": "success",
            "message": "Video generated successfully and displayed to user.",
            "video": {
                "asset_id": str(asset.id),
                "duration_seconds": result.duration_seconds,
                "width": result.width,
                "height": result.height,
            },
            "cost_usd": float(cost_usd),  # For the chat turn's cost-ledger accumulation
        })

    except ContentPolicyError as e:
        logger.warning(f"[VideoTool] Content policy violation: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "content_policy",
            "message": str(e),
        })

    except InvalidPromptError as e:
        logger.warning(f"[VideoTool] Invalid prompt: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "invalid_prompt",
            "message": str(e),
        })

    except InvalidInputError as e:
        logger.warning(f"[VideoTool] Invalid input: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "invalid_input",
            "message": str(e),
        })

    except RateLimitError as e:
        logger.warning(f"[VideoTool] Rate limit exceeded: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "rate_limit",
            "message": "Video generation rate limit exceeded. Please try again later.",
        })

    except GenerationTimeoutError as e:
        logger.error(f"[VideoTool] Generation timeout: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "timeout",
            "message": "Video generation timed out. Please try again with a shorter duration.",
        })

    except VideoProviderError as e:
        logger.error(f"[VideoTool] Provider error: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "provider_error",
            "message": str(e),
        })

    except Exception as e:
        logger.exception("[VideoTool] Unexpected error")
        return json.dumps({
            "status": "error",
            "error_type": "unexpected",
            "message": f"An unexpected error occurred: {str(e)}",
        })

    finally:
        await provider.close()


# =============================================================================
# Helper Functions
# =============================================================================


async def _check_video_quota(
    context: Dict[str, Any],
    model_config: Any,  # VideoModelCatalog
    duration: int,
) -> Optional[str]:
    """
    Pre-flight quota check before video generation.

    Returns None if quota is available, or a JSON error string if exceeded.
    """
    from authentication.models import User

    @sync_to_async
    def get_user():
        return User.objects.filter(id=context.get("user_id")).first()

    user = await get_user()
    if not user:
        return json.dumps({
            "status": "error",
            "error_type": "user_not_found",
            "message": "User not found",
        })

    # Estimate cost using database pricing
    estimated_cost = model_config.calculate_cost(duration_seconds=duration)

    billing = get_billing_service()

    @sync_to_async
    def check_quota():
        return billing.check_quota(
            user=user,
            service=ServiceType.VIDEO_GENERATION,
            estimated_cost=estimated_cost,
            feature=FeatureType.CHAT,
            feature_name='video_generation_seconds',
            request_units=int(duration or 0),
        )

    try:
        await check_quota()
    except Exception as exc:
        # Map FeatureNotAvailable / QuotaExceeded raised by the cascading
        # guard to the tool's JSON error envelope so the LLM sees a
        # structured response (it should not retry).
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        if isinstance(exc, (FeatureNotAvailableException, QuotaExceededException)):
            hours_until_reset = 24
            resets = getattr(exc, 'resets_in_seconds', None)
            if resets is not None:
                hours_until_reset = max(0, resets / 3600)
            logger.info(
                f"[VideoTool] Tier gate denied for user {user.id}: "
                f"code={exc.code}, estimated_cost=${estimated_cost}"
            )
            return json.dumps({
                "status": "error",
                "error_type": exc.code,
                "message": (
                    exc.message
                    if exc.code == 'feature_not_available'
                    else f"Video generation quota exceeded. Resets in {hours_until_reset:.1f} hours."
                ),
                "estimated_cost": str(estimated_cost),
            })
        raise

    return None


async def _store_generated_video(
    video_bytes: bytes,
    context: Dict[str, Any],
    prompt: str,
    model_config: Any,  # VideoModelCatalog
    width: int,
    height: int,
    duration_seconds: float,
) -> Asset:
    """Store generated video in R2/PostgreSQL."""
    # Generate asset ID upfront so R2 key is valid
    asset_id = uuid.uuid4()

    @sync_to_async
    def get_chat():
        chat_id = context.get("chat_id")
        if chat_id:
            return Chat.objects.filter(id=chat_id).first()
        return None

    @sync_to_async
    def create_asset(chat, sha256_hash, storage_result):
        return Asset.objects.create(
            id=asset_id,  # Use pre-generated ID
            user_id=context.get("user_id"),
            chat=chat,
            asset_type="generated",
            filename=f"generated_video_{timezone.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            mime_type="video/mp4",
            size_bytes=len(video_bytes),
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            storage_type=storage_result.storage_type,
            content=video_bytes if storage_result.storage_type == "inline" else None,
            r2_bucket=storage_result.r2_bucket,
            r2_key=storage_result.r2_key,
            sha256_hash=sha256_hash,
            generation_prompt=prompt[:2000],  # Truncate to model max
            generation_model=model_config.canonical_id,
        )

    chat = await get_chat()
    sha256_hash = hashlib.sha256(video_bytes).hexdigest()

    storage_service = get_asset_storage_service()

    @sync_to_async
    def store_asset():
        return storage_service.store_asset(
            content=video_bytes,
            user_id=context.get("user_id"),
            chat_id=context.get("chat_id"),
            asset_id=str(asset_id),  # Pass the pre-generated ID
            mime_type="video/mp4",
            asset_type="video",  # Store in videos/ subdirectory
        )

    storage_result = await store_asset()

    asset = await create_asset(chat, sha256_hash, storage_result)
    return asset


async def _record_video_billing(
    context: Dict[str, Any],
    cost_usd: Decimal,
    model_config: Any,  # VideoModelCatalog
    duration_seconds: float,
) -> None:
    """Record video generation cost in billing system."""
    from authentication.models import User

    @sync_to_async
    def get_user():
        return User.objects.filter(id=context.get("user_id")).first()

    user = await get_user()
    if not user:
        logger.warning("[VideoTool] Cannot record billing: user not found")
        return

    operation = BillableOperation(
        service=ServiceType.VIDEO_GENERATION,
        feature=FeatureType.CHAT,
        model_id=model_config.canonical_id,
        request_count=1,
        cost_usd=cost_usd,
        extra_data={
            "duration_seconds": duration_seconds,
            "conversation_id": str(context.get("conversation_id", "")),
        },
    )

    billing = get_billing_service()

    @sync_to_async
    def record_usage():
        # Video generation is always platform-billed; the BillingService
        # guard rejects 'byok' for VIDEO_GENERATION but we set it
        # explicitly here for clarity (belt + suspenders).
        billing.record_usage(user, operation, billing_origin='platform')

    await record_usage()

    logger.info(
        f"[VideoTool] Billing recorded: user={user.id}, "
        f"model={model_config.canonical_id}, cost=${cost_usd}"
    )


# =============================================================================
# Tool Export
# =============================================================================

VIDEO_TOOLS = [
    generate_video,
    animate_image,
    animate_character,
]
