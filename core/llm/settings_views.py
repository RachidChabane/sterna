"""
Settings views for OpenRouter, Image, Video Generation, and Coding Agent Model configuration.

Now integrates with per-user API key system. Authenticated users
store their API key in the encrypted user model field.
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from authentication.models import User

logger = logging.getLogger(__name__)


class OpenRouterSettingsView(APIView):
    """
    View for managing OpenRouter API settings.

    Stores the key in the encrypted user model field (BYOK).

    Security note: this view used to be AllowAny with a session-backed
    branch "for onboarding", but nothing in the backend ever consumed
    the session-stored key and no frontend flow reaches this endpoint
    unauthenticated — it was only an anonymous session-write primitive.
    It now requires authentication.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Save OpenRouter API key in the encrypted user field
        (BYOK - Bring Your Own Key).
        """
        api_key = request.data.get("api_key")

        if not api_key:
            return Response(
                {"error": "API key is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Store in encrypted user field.
        # Null the platform-side provisioning markers so the
        # resolve_with_origin() discriminator (provisioned_at IS NULL)
        # classifies this as BYOK. Without this reset, a previously
        # auto-provisioned user who uploads their own key gets
        # double-billed (their OpenRouter account + their Sterna
        # quota).
        request.user.openrouter_api_key = api_key
        request.user.openrouter_key_provisioned_at = None
        request.user.openrouter_key_hash = None
        request.user.save(update_fields=[
            'openrouter_api_key',
            'openrouter_key_provisioned_at',
            'openrouter_key_hash',
        ])
        logger.info(f"OpenRouter API key (BYOK) saved for user {request.user.id}")

        return Response({
            "success": True,
            "message": "API key saved successfully",
            "source": "user_byok"
        })

    def get(self, request):
        """
        Check if OpenRouter API key is configured and return status.
        """
        has_key = False
        source = None
        is_provisioned = False

        # Check user's encrypted field
        if request.user.openrouter_api_key:
            has_key = True
            # Check if it was auto-provisioned or BYOK
            if request.user.openrouter_key_provisioned_at:
                source = "provisioned"
                is_provisioned = True
            else:
                source = "user_byok"

        # Also check if system fallback is available
        from llm.services.api_key_resolver import get_resolver
        has_fallback = get_resolver().has_fallback_key

        return Response({
            "configured": has_key,
            "source": source,
            "is_provisioned": is_provisioned,
            "has_system_fallback": has_fallback,
        })

    def delete(self, request):
        """
        Remove user's custom API key.

        For users with provisioned keys, this restores the provisioned key.
        For BYOK users, this removes their key and falls back to provisioned/system key.
        """
        had_provisioned = request.user.openrouter_key_provisioned_at is not None

        # Clear the API key
        request.user.openrouter_api_key = None
        request.user.save(update_fields=['openrouter_api_key'])

        # If user had a provisioned key, re-provision it
        if had_provisioned:
            from llm.services.openrouter_keys import OpenRouterKeyService
            service = OpenRouterKeyService()
            try:
                key = service.provision_key_for_user(request.user)
                if key:
                    logger.info(f"Re-provisioned API key for user {request.user.id}")
                    return Response({
                        "success": True,
                        "message": "Custom key removed, using provisioned key",
                        "source": "provisioned"
                    })
            except Exception as e:
                logger.warning(f"Failed to re-provision key: {e}")

        return Response({
            "success": True,
            "message": "API key removed successfully"
        })


def _mask_key(key: str) -> str:
    """Mask an API key, keeping only the last 4 characters."""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


# Trivial prefix sanity checks only — reject obviously wrong keys, never
# attempt full validation. Providers without a stable prefix are omitted.
_PROVIDER_KEY_PREFIXES = {
    "openai": "sk-",
    "anthropic": "sk-ant-",
    "deepseek": "sk-",
    "x-ai": "xai-",
    "google": "AIza",
}


class ProviderKeysView(APIView):
    """List provider-scoped BYOK key status for all supported providers.

    Never returns (or logs) a full key — only a masked suffix.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from llm.provider_registry import BYOK_PROVIDERS

        providers = []
        for slug, cfg in BYOK_PROVIDERS.items():
            key = request.user.get_provider_key(slug)
            providers.append({
                "provider": slug,
                "label": cfg["label"],
                "configured": bool(key),
                "masked_key": _mask_key(key) if key else None,
            })
        return Response({"providers": providers})


class ProviderKeyDetailView(APIView):
    """Set (PUT/POST) or remove (DELETE) a single provider BYOK key.

    Models with a matching first-party prefix (e.g. anthropic/...) are
    then routed directly to that provider's OpenAI-compatible endpoint
    and billed to the user's own provider account ('byok' origin).
    """

    permission_classes = [IsAuthenticated]

    def _validate_provider(self, provider):
        from llm.provider_registry import BYOK_PROVIDERS

        if provider not in BYOK_PROVIDERS:
            return Response(
                {"error": f"Unknown provider '{provider}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return None

    def put(self, request, provider):
        error = self._validate_provider(provider)
        if error:
            return error

        api_key = request.data.get("api_key")
        if not isinstance(api_key, str) or not api_key.strip():
            return Response(
                {"error": "API key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        api_key = api_key.strip()

        expected_prefix = _PROVIDER_KEY_PREFIXES.get(provider)
        if expected_prefix and not api_key.startswith(expected_prefix):
            return Response(
                {
                    "error": (
                        f"That does not look like a valid key for this "
                        f"provider (expected it to start with "
                        f"'{expected_prefix}')"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_provider_key(provider, api_key)
        request.user.save(update_fields=["provider_api_keys"])
        logger.info(
            f"Provider BYOK key saved for user {request.user.id} "
            f"(provider={provider})"
        )
        return Response({
            "success": True,
            "provider": provider,
            "configured": True,
            "masked_key": _mask_key(api_key),
        })

    # POST behaves identically to PUT (idempotent upsert).
    post = put

    def delete(self, request, provider):
        error = self._validate_provider(provider)
        if error:
            return error

        request.user.delete_provider_key(provider)
        request.user.save(update_fields=["provider_api_keys"])
        logger.info(
            f"Provider BYOK key removed for user {request.user.id} "
            f"(provider={provider})"
        )
        return Response({
            "success": True,
            "provider": provider,
            "configured": False,
        })


class ImageSettingsView(APIView):
    """
    View for managing image generation settings.

    Allows authenticated users to get/set their preferred image model.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the user's image generation settings."""
        user = request.user

        # Build model info from choices with descriptions
        IMAGE_MODEL_INFO = {
            "google/gemini-2.5-flash-image": {
                "name": "Nano Banana",
                "description": "Fast generation, good for quick iterations",
                "provider": "Google",
                "price_info": "Standard pricing",
            },
            "google/gemini-3-pro-image-preview": {
                "name": "Nano Banana Pro",
                "description": "Higher quality, better for final outputs",
                "provider": "Google",
                "price_info": "Premium pricing",
            },
        }

        return Response({
            "preferred_image_model": user.preferred_image_model,
            "available_models": [
                {
                    "id": choice[0],
                    "name": IMAGE_MODEL_INFO.get(choice[0], {}).get("name", choice[1]),
                    "description": IMAGE_MODEL_INFO.get(choice[0], {}).get("description", ""),
                    "provider": IMAGE_MODEL_INFO.get(choice[0], {}).get("provider", ""),
                    "price_info": IMAGE_MODEL_INFO.get(choice[0], {}).get("price_info", ""),
                }
                for choice in User.IMAGE_MODEL_CHOICES
            ],
        })

    def patch(self, request):
        """Update the user's image generation settings."""
        user = request.user

        preferred_model = request.data.get("preferred_image_model")

        if preferred_model:
            # Validate model ID
            valid_models = [choice[0] for choice in User.IMAGE_MODEL_CHOICES]
            if preferred_model not in valid_models:
                return Response(
                    {
                        "error": f"Invalid model. Must be one of: {', '.join(valid_models)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.preferred_image_model = preferred_model
            user.save(update_fields=["preferred_image_model"])
            logger.info(f"Updated image model preference for user {user.id}: {preferred_model}")

        return Response({
            "success": True,
            "preferred_image_model": user.preferred_image_model,
        })


class VideoSettingsView(APIView):
    """
    View for managing video generation settings.

    Allows authenticated users to get/set their preferred video model.
    All model information is fetched from the database (VideoModelCatalog).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the user's video generation settings from database."""
        from llm.models import VideoModelCatalog

        user = request.user

        # Fetch all active video models from database
        models = VideoModelCatalog.objects.filter(is_active=True).order_by('sort_order')

        available_models = []
        for model in models:
            capabilities = model.capabilities or {}

            # Build pricing info
            if model.current_price_per_second:
                price_info = f"${model.current_price_per_second}/second"
            elif model.current_price_per_request:
                price_info = f"${model.current_price_per_request}/request"
            else:
                price_info = "Contact for pricing"

            available_models.append({
                "id": model.canonical_id,
                "model_id": model.model_id,
                "name": model.display_name,
                "description": model.description,
                "best_for": model.best_for,
                "provider": model.provider.title(),
                "price_info": price_info,
                "input_type": model.input_type,
                "output_type": model.output_type,
                "max_duration": capabilities.get("max_duration"),
                "min_duration": capabilities.get("min_duration"),
                "valid_durations": capabilities.get("valid_durations"),
                "supported_resolutions": capabilities.get("supported_resolutions"),
                "supported_aspect_ratios": capabilities.get("supported_aspect_ratios"),
                "is_pro": model.is_pro,
                "is_default": model.is_default,
            })

        return Response({
            "preferred_video_model": user.preferred_video_model,
            "available_models": available_models,
        })

    def patch(self, request):
        """Update the user's video generation settings."""
        from llm.models import VideoModelCatalog

        user = request.user
        preferred_model = request.data.get("preferred_video_model")

        if preferred_model:
            # Validate model exists in database
            model = VideoModelCatalog.get_by_canonical_id(preferred_model)
            if not model:
                # Also try by model_id
                model = VideoModelCatalog.get_by_model_id(preferred_model)
                if model:
                    # Use canonical_id for storage
                    preferred_model = model.canonical_id

            if not model:
                # Get valid models for error message
                valid_models = list(
                    VideoModelCatalog.objects.filter(is_active=True)
                    .values_list('canonical_id', flat=True)
                )
                return Response(
                    {
                        "error": f"Invalid model. Available models: {', '.join(valid_models)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.preferred_video_model = preferred_model
            user.save(update_fields=["preferred_video_model"])
            logger.info(f"Updated video model preference for user {user.id}: {preferred_model}")

        return Response({
            "success": True,
            "preferred_video_model": user.preferred_video_model,
        })


class CodingAgentModelPreferencesView(APIView):
    """
    View for managing coding agent model tier preferences.

    Users can map abstract tiers (fast/balanced/powerful) to any OpenRouter model.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the user's coding agent model preferences."""
        from code_sessions.models import UserModelPreferences
        from code_sessions.serializers import UserModelPreferencesSerializer

        prefs = UserModelPreferences.get_or_create_for_user(request.user)
        serializer = UserModelPreferencesSerializer(prefs)
        return Response(serializer.data)

    def patch(self, request):
        """Update the user's coding agent model preferences."""
        from code_sessions.models import UserModelPreferences
        from code_sessions.serializers import UserModelPreferencesSerializer

        prefs = UserModelPreferences.get_or_create_for_user(request.user)
        serializer = UserModelPreferencesSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info(f"Updated coding agent model preferences for user {request.user.id}")
        return Response(serializer.data)
