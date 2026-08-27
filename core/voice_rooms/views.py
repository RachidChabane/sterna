"""Views for Voice Rooms API."""

import logging
import uuid
from asgiref.sync import async_to_sync
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from django.db.models import Prefetch
from .models import VoiceRoom, VoiceRoomAgent, VoiceRoomSession, VoiceRoomMessage
from .serializers import (
    VoiceRoomSerializer,
    VoiceRoomCreateSerializer,
    VoiceRoomUpdateSerializer,
    VoiceRoomListSerializer,
    VoiceRoomAgentSerializer,
    VoiceRoomSessionSerializer,
    VoiceRoomMessageSerializer,
)
# Legacy import for voice rooms WebSocket streaming
# New provider-based TTS
from .services.tts_factory import (
    TTSService,
    get_available_providers,
    TTS_PROVIDERS,
    DEFAULT_PROVIDER,
)
from .services.tts_base import TTSSettings
from .room_generator import generate_room_from_description, generated_room_to_dict
from .constants import VOICE_ROOM_MODELS, ACTIVE_SESSION_STATUSES

# Quota and cost tracking
from usage_quota.services.quota_service import get_quota_service
from usage_quota.services.cost_calculator import get_cost_calculator
from usage_quota.models import ServiceType, FeatureType

logger = logging.getLogger(__name__)

# Cache keys and TTLs
VOICES_CACHE_KEY_PREFIX = "voice_rooms:voices"  # Will be suffixed with provider
VOICES_CACHE_TTL = 3600  # 1 hour
TTS_MODELS_CACHE_KEY_PREFIX = "voice_rooms:tts_models"  # Will be suffixed with provider
TTS_MODELS_CACHE_TTL = 86400 * 7  # 7 days

# Language code to ISO country code mapping for flags
LANGUAGE_TO_COUNTRY = {
    "en": "us", "en-US": "us", "en-GB": "gb", "en-AU": "au", "en-CA": "ca",
    "es": "es", "es-ES": "es", "es-MX": "mx", "es-AR": "ar",
    "fr": "fr", "fr-FR": "fr", "fr-CA": "ca",
    "de": "de", "de-DE": "de", "de-AT": "at", "de-CH": "ch",
    "it": "it", "it-IT": "it",
    "pt": "pt", "pt-PT": "pt", "pt-BR": "br",
    "nl": "nl", "nl-NL": "nl", "nl-BE": "be",
    "pl": "pl", "pl-PL": "pl",
    "ru": "ru", "ru-RU": "ru",
    "ja": "jp", "ja-JP": "jp",
    "ko": "kr", "ko-KR": "kr",
    "zh": "cn", "zh-CN": "cn", "zh-TW": "tw", "zh-HK": "hk",
    "hi": "in", "hi-IN": "in",
    "ar": "sa", "ar-SA": "sa", "ar-AE": "ae", "ar-EG": "eg",
    "tr": "tr", "tr-TR": "tr",
    "sv": "se", "sv-SE": "se",
    "da": "dk", "da-DK": "dk",
    "no": "no", "nb": "no", "nb-NO": "no",
    "fi": "fi", "fi-FI": "fi",
    "el": "gr", "el-GR": "gr",
    "cs": "cz", "cs-CZ": "cz",
    "sk": "sk", "sk-SK": "sk",
    "hu": "hu", "hu-HU": "hu",
    "ro": "ro", "ro-RO": "ro",
    "bg": "bg", "bg-BG": "bg",
    "hr": "hr", "hr-HR": "hr",
    "uk": "ua", "uk-UA": "ua",
    "id": "id", "id-ID": "id",
    "ms": "my", "ms-MY": "my",
    "th": "th", "th-TH": "th",
    "vi": "vn", "vi-VN": "vn",
    "fil": "ph", "tl": "ph",
    "ta": "in", "ta-IN": "in", "ta-LK": "lk",
    "he": "il", "he-IL": "il",
    "af": "za", "af-ZA": "za",
    "sw": "ke", "sw-KE": "ke",
    "bn": "bd", "bn-BD": "bd", "bn-IN": "in",
    "mr": "in", "mr-IN": "in",
    "te": "in", "te-IN": "in",
    "ml": "in", "ml-IN": "in",
    "kn": "in", "kn-IN": "in",
    "gu": "in", "gu-IN": "in",
    "pa": "in", "pa-IN": "in",
    "ur": "pk", "ur-PK": "pk",
    "fa": "ir", "fa-IR": "ir",
}


async def _fetch_voices_for_provider(provider_id: str):
    """Fetch voices from a TTS provider."""
    service = TTSService(provider_id)
    try:
        voices = await service.get_voices()
        return [
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "provider": v.provider,
                "category": v.category,
                "description": v.description,
                "preview_url": v.preview_url,
                "labels": v.labels,
                "languages": v.languages,
                # Include provider-specific metadata
                **v.metadata,
            }
            for v in voices
        ]
    finally:
        await service.cleanup()


async def _fetch_models_for_provider(provider_id: str):
    """Fetch TTS models from a provider."""
    service = TTSService(provider_id)
    try:
        models = await service.get_models()
        result = []
        for m in models:
            # Add country codes to languages for flag display
            languages_with_flags = []
            for lang in m.languages:
                if isinstance(lang, dict):
                    lang_id = lang.get("language_id", "")
                    lang_name = lang.get("name", lang_id)
                else:
                    lang_id = lang
                    lang_name = lang
                country_code = LANGUAGE_TO_COUNTRY.get(
                    lang_id, LANGUAGE_TO_COUNTRY.get(lang_id.split("-")[0], "")
                )
                languages_with_flags.append({
                    "language_id": lang_id,
                    "name": lang_name,
                    "country_code": country_code,
                })

            result.append({
                "model_id": m.model_id,
                "name": m.name,
                "provider": m.provider,
                "description": m.description,
                "can_use_style": m.can_use_style,
                "can_use_speaker_boost": m.can_use_speaker_boost,
                "supports_streaming": m.supports_streaming,
                "languages": languages_with_flags,
                **m.metadata,
            })
        return result
    finally:
        await service.cleanup()


# Legacy ElevenLabs-specific functions (for voice rooms)
async def _fetch_voices_from_api():
    """Fetch voices from ElevenLabs API (legacy for voice rooms)."""
    return await _fetch_voices_for_provider("elevenlabs")


async def _fetch_tts_models_from_api():
    """Fetch TTS models from ElevenLabs API (legacy for voice rooms)."""
    return await _fetch_models_for_provider("elevenlabs")


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def tts_providers(request):
    """Get list of available TTS providers (only those with API keys configured)."""
    available = get_available_providers()
    providers = []

    # Determine the actual default (first available if configured default isn't available)
    actual_default = DEFAULT_PROVIDER if DEFAULT_PROVIDER in available else (available[0] if available else None)

    for provider_id in available:
        provider_class = TTS_PROVIDERS.get(provider_id)
        if provider_class:
            providers.append({
                "id": provider_class.PROVIDER_ID,
                "name": provider_class.PROVIDER_NAME,
                "is_default": provider_id == actual_default,
            })
    return Response(providers)


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def list_voices(request):
    """Fetch available voices (cached). Supports ?provider= query param."""
    requested_provider = request.query_params.get("provider", DEFAULT_PROVIDER)

    # Check if requested provider is available, fall back if not
    available = get_available_providers()
    if requested_provider not in available:
        if available:
            provider_id = available[0]
            logger.info(f"Provider '{requested_provider}' not available, using '{provider_id}'")
        else:
            return Response(
                {"error": "No TTS providers configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    else:
        provider_id = requested_provider

    cache_key = f"{VOICES_CACHE_KEY_PREFIX}:{provider_id}"

    # Try cache first
    cached_voices = cache.get(cache_key)
    if cached_voices:
        return Response(cached_voices)

    # Fetch from provider
    try:
        voices = async_to_sync(_fetch_voices_for_provider)(provider_id)
        cache.set(cache_key, voices, VOICES_CACHE_TTL)
        return Response(voices)
    except Exception as e:
        logger.error(f"Failed to fetch voices from {provider_id}: {e}")
        return Response(
            {"error": f"Failed to fetch voices from {provider_id}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def recommended_voices(request):
    """Get recommended/premade voices. Supports ?provider= query param."""
    requested_provider = request.query_params.get("provider", DEFAULT_PROVIDER)

    # Check if requested provider is available, fall back if not
    available = get_available_providers()
    if requested_provider not in available:
        if available:
            provider_id = available[0]
            logger.info(f"Provider '{requested_provider}' not available, using '{provider_id}'")
        else:
            return Response(
                {"error": "No TTS providers configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    else:
        provider_id = requested_provider

    cache_key = f"{VOICES_CACHE_KEY_PREFIX}:{provider_id}"

    # Try cache first
    cached_voices = cache.get(cache_key)
    if not cached_voices:
        try:
            cached_voices = async_to_sync(_fetch_voices_for_provider)(provider_id)
            cache.set(cache_key, cached_voices, VOICES_CACHE_TTL)
        except Exception as e:
            logger.error(f"Failed to fetch voices from {provider_id}: {e}")
            return Response(
                {"error": f"Failed to fetch voices from {provider_id}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    # For OpenAI, all voices are "premade"
    # For ElevenLabs, filter to premade category
    if provider_id == "openai":
        return Response(cached_voices)
    else:
        premade = [v for v in cached_voices if v.get("category") == "premade"]
        return Response(premade)


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def tts_models(request):
    """Get available TTS models. Supports ?provider= query param."""
    requested_provider = request.query_params.get("provider", DEFAULT_PROVIDER)

    # Check if requested provider is available, fall back if not
    available = get_available_providers()
    if requested_provider not in available:
        if available:
            provider_id = available[0]
            logger.info(f"Provider '{requested_provider}' not available, using '{provider_id}'")
        else:
            return Response(
                {"error": "No TTS providers configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    else:
        provider_id = requested_provider

    cache_key = f"{TTS_MODELS_CACHE_KEY_PREFIX}:{provider_id}"

    # Try cache first
    cached_models = cache.get(cache_key)
    if cached_models:
        return Response(cached_models)

    # Fetch from provider
    try:
        models = async_to_sync(_fetch_models_for_provider)(provider_id)
        cache.set(cache_key, models, TTS_MODELS_CACHE_TTL)
        return Response(models)
    except Exception as e:
        logger.error(f"Failed to fetch TTS models from {provider_id}: {e}")
        return Response(
            {"error": f"Failed to fetch TTS models from {provider_id}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


async def _generate_tts_audio(
    text: str,
    provider_id: str | None = None,
    voice_id: str | None = None,
    model_id: str | None = None,
    speed: float | None = None,
    # ElevenLabs-specific settings
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
    use_speaker_boost: bool | None = None,
    user=None,
    session_id: str | None = None,
    feature: str = FeatureType.VOICE_ROOM,
) -> bytes | None:
    """Generate TTS audio using the specified provider."""
    service = TTSService(
        provider_id,
        user=user,
        session_id=session_id,
        feature=feature,
    )
    try:
        # Build settings object
        settings = TTSSettings(
            speed=speed or 1.0,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
        )

        audio = await service.text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            settings=settings,
        )
        return audio
    finally:
        await service.cleanup()


# Sample text for voice previews (short, demonstrates voice character)
VOICE_PREVIEW_TEXT = "Hello! This is a preview of my voice. I hope you find it pleasant to listen to."

# Cache for translated preview texts (language_code -> translated_text)
_translation_cache: dict = {}


async def _translate_preview_text(text: str, target_language: str, user=None) -> str:
    """
    Translate the preview text to the target language using LLMRouter.
    Results are cached to avoid repeated API calls.
    """
    from .services.llm_router import LLMRouter

    # Check cache first
    cache_key = f"{target_language}"
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    router = LLMRouter(user=user)
    try:
        await router.initialize()

        result = await router.complete(
            model="google/gemma-3n-e4b-it",
            messages=[
                {
                    "role": "user",
                    "content": f"Translate the following text to {target_language}. Return ONLY the translated text, nothing else. Keep it natural and conversational.\n\nText: {text}"
                }
            ],
            max_tokens=100,
            temperature=0.3,
        )

        translated = result.get("content", "").strip()
        if translated:
            # Cache the result
            _translation_cache[cache_key] = translated
            logger.info(f"Translated preview to {target_language}: {translated}")
            return translated

        return text

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return text
    finally:
        await router.cleanup()


async def _get_preview_text(language: str | None = None, user=None) -> str:
    """Get the preview text, translated if a language is specified.

    Args:
        language: Language name (e.g., "French", "Japanese") - not a code.
        user: User whose quota covers the translation LLM call.
    """
    if not language or language.lower() in ('auto', 'english'):
        return VOICE_PREVIEW_TEXT

    return await _translate_preview_text(VOICE_PREVIEW_TEXT, language, user=user)


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def voice_preview(request):
    """
    Generate a voice preview audio sample.

    Used for providers like OpenAI that don't offer static preview URLs.
    The audio is generated on-demand with sample text.

    Query params:
        - provider: str (required) - TTS provider ('openai' or 'elevenlabs')
        - voice_id: str (required) - Voice ID to preview
        - model_id: str (optional) - Model to use (defaults to provider default)
        - language: str (optional) - Language code for preview text translation
        - speed: float (optional) - Speech speed (default 1.0)
        - stability: float (optional) - ElevenLabs stability (0-1)
        - similarity_boost: float (optional) - ElevenLabs similarity boost (0-1)
        - style: float (optional) - ElevenLabs style exaggeration (0-1)
        - use_speaker_boost: bool (optional) - ElevenLabs speaker boost

    Returns:
        Audio file (audio/mpeg) or error response
    """
    from django.http import HttpResponse

    provider_id = request.query_params.get("provider", DEFAULT_PROVIDER)
    voice_id = request.query_params.get("voice_id")
    model_id = request.query_params.get("model_id")
    language = request.query_params.get("language")

    # Voice tuning settings
    speed = request.query_params.get("speed")
    stability = request.query_params.get("stability")
    similarity_boost = request.query_params.get("similarity_boost")
    style = request.query_params.get("style")
    use_speaker_boost = request.query_params.get("use_speaker_boost")

    # Convert string params to appropriate types
    if speed:
        try:
            speed = float(speed)
        except ValueError:
            speed = 1.0
    else:
        speed = 1.0

    if stability:
        try:
            stability = float(stability)
        except ValueError:
            stability = None

    if similarity_boost:
        try:
            similarity_boost = float(similarity_boost)
        except ValueError:
            similarity_boost = None

    if style:
        try:
            style = float(style)
        except ValueError:
            style = None

    if use_speaker_boost is not None:
        use_speaker_boost = use_speaker_boost.lower() in ('true', '1', 'yes')

    if not voice_id:
        return Response(
            {"error": "voice_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if provider is available
    available = get_available_providers()
    if provider_id not in available:
        return Response(
            {"error": f"Provider '{provider_id}' not available"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Pre-check quota BEFORE making an upstream TTS call (matrix row #34).
    # The post-record bill happens inside the provider (F4).
    from decimal import Decimal

    service_type = (
        ServiceType.OPENAI_TTS if provider_id == "openai"
        else ServiceType.ELEVENLABS_TTS
    )
    # Estimate using the static preview text length (good enough for pre-check
    # — actual cost is reconciled by the provider's post-record bill).
    estimated_char_count = len(VOICE_PREVIEW_TEXT)
    try:
        estimated_cost = get_cost_calculator().calculate_cost(
            service=service_type,
            model_id=model_id,
            character_count=estimated_char_count,
        )
    except Exception:
        estimated_cost = Decimal('0.001')

    from usage_quota.billing.service import get_billing_service
    get_billing_service().check_quota(
        user=request.user,
        service=service_type,
        estimated_cost=estimated_cost,
        feature=FeatureType.CHAT,
        feature_name='voice_tts',
    )

    try:
        # Get preview text (translated if language specified)
        preview_text = async_to_sync(_get_preview_text)(language, user=request.user)

        audio_bytes = async_to_sync(_generate_tts_audio)(
            preview_text,
            provider_id=provider_id,
            voice_id=voice_id,
            model_id=model_id,
            speed=speed,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            user=request.user,
            session_id=f"preview:{request.user.id}",
            feature=FeatureType.CHAT,
        )

        if not audio_bytes:
            return Response(
                {"error": "Failed to generate preview"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return HttpResponse(
            audio_bytes,
            content_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache",  # Don't cache - settings may change
            }
        )

    except Exception as e:
        logger.error(f"Voice preview error: {e}")
        return Response(
            {"error": "Failed to generate preview"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(["POST"])
@perm_classes([IsAuthenticated])
def text_to_speech(request):
    """
    Convert text to speech.

    Request body:
        - text: str (required) - Text to convert to speech (max 5000 chars)
        - provider: str (optional) - TTS provider ('openai' or 'elevenlabs', default: openai)
        - voice_id: str (optional) - Voice ID (provider-specific)
        - model_id: str (optional) - TTS model ID (provider-specific)
        - speed: float (optional) - Speech speed
        - feature: str (optional) - Feature context for usage tracking (default: 'chat')

        ElevenLabs-specific settings:
        - stability: float (optional) - Voice stability (0-1)
        - similarity_boost: float (optional) - Similarity boost (0-1)
        - style: float (optional) - Style exaggeration (0-1)
        - use_speaker_boost: bool (optional) - Enable speaker boost

    Returns:
        Audio file (audio/mpeg) or error response
    """
    import time
    from django.http import HttpResponse

    request_start = time.time()
    text = request.data.get("text", "").strip()
    logger.info(f"[TTS] Request received: {len(text)} chars, preview: {text[:50]}...")
    provider_id = request.data.get("provider", DEFAULT_PROVIDER)
    voice_id = request.data.get("voice_id")
    model_id = request.data.get("model_id")
    speed = request.data.get("speed")
    feature = request.data.get("feature", FeatureType.CHAT)
    # ElevenLabs-specific
    stability = request.data.get("stability")
    similarity_boost = request.data.get("similarity_boost")
    style = request.data.get("style")
    use_speaker_boost = request.data.get("use_speaker_boost")

    if not text:
        return Response(
            {"error": "Text is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Limit text length to prevent abuse
    max_chars = 5000
    if len(text) > max_chars:
        return Response(
            {"error": f"Text too long. Maximum {max_chars} characters allowed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Determine service type based on provider
    if provider_id == "elevenlabs":
        service_type = ServiceType.ELEVENLABS_TTS
    else:
        service_type = ServiceType.OPENAI_TTS

    # Calculate cost before generating audio
    cost_calculator = get_cost_calculator()
    character_count = len(text)
    cost_usd = cost_calculator.calculate_cost(
        service=service_type,
        model_id=model_id,
        character_count=character_count,
    )

    # Pre-flight: feature flag + per-feature gate. Raises FeatureNotAvailable
    # or QuotaExceeded on denial → DRF handler returns 402.
    from usage_quota.billing.service import get_billing_service
    get_billing_service().check_quota(
        user=request.user,
        service=service_type,
        estimated_cost=cost_usd,
        feature=feature,
        feature_name='voice_tts',
    )

    # Atomic USD deduct. Raises QuotaExceeded if the deduct itself hits
    # the weekly/session window — handled by the DRF exception handler.
    quota_service = get_quota_service()
    quota_service.check_and_deduct(
        user=request.user,
        service=service_type,
        cost_usd=cost_usd,
        feature=feature,
        model_id=model_id or '',
        character_count=character_count,
    )

    try:
        audio_bytes = async_to_sync(_generate_tts_audio)(
            text,
            provider_id=provider_id,
            voice_id=voice_id,
            model_id=model_id,
            speed=speed,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
        )

        if not audio_bytes:
            return Response(
                {"error": "Failed to generate audio"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        elapsed = time.time() - request_start
        logger.info(
            f"[TTS] Generated in {elapsed:.2f}s: user={request.user.id}, provider={provider_id}, "
            f"model={model_id}, chars={character_count}, cost=${cost_usd}"
        )

        return HttpResponse(
            audio_bytes,
            content_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache",
            }
        )

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return Response(
            {"error": "Failed to generate speech"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(["GET"])
@perm_classes([IsAuthenticated])
def eligible_models(request):
    """
    Get list of models allowed for voice rooms.

    Returns:
        List of allowed model IDs (fast & cheap models only)
    """
    return Response({"models": VOICE_ROOM_MODELS})


@api_view(["POST"])
@perm_classes([IsAuthenticated])
def generate_room(request):
    """
    Generate a voice room configuration from a natural language description.

    Uses AI to create a complete room setup with agents, voices, and personalities
    based on the user's description. Following the MCP config helper pattern.

    Request body:
        - description: str (required) - Natural language description of the room
          Example: "A debate room with two opposing viewpoints on AI safety"
        - provider: str (optional) - TTS provider ID (e.g., "elevenlabs", "openai", "kokoro")
          If provided, voices will be fetched from this provider for the AI to choose from.

    Returns:
        Generated room configuration ready for creation:
        {
            "name": "Room Name",
            "description": "Room description",
            "language": "auto",
            "agents": [
                {
                    "display_name": "Agent Name",
                    "model_id": "provider/model",
                    "system_prompt": "...",
                    "voice_id": "...",
                    "voice_name": "...",
                    "order": 1,
                    "color": "#hexcolor",
                    "voice_settings": {...}
                }
            ]
        }
    """
    description = request.data.get("description", "").strip()
    provider_id = request.data.get("provider", "").strip()

    if not description:
        return Response(
            {"error": "description is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Limit description length
    max_chars = 1000
    if len(description) > max_chars:
        return Response(
            {"error": f"Description too long. Maximum {max_chars} characters allowed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Fetch voices for the provider if specified
    available_voices = None
    if provider_id:
        try:
            # Check if provider is available
            available_providers = get_available_providers()
            if provider_id in available_providers:
                cache_key = f"{VOICES_CACHE_KEY_PREFIX}:{provider_id}"
                cached_voices = cache.get(cache_key)
                if not cached_voices:
                    cached_voices = async_to_sync(_fetch_voices_for_provider)(provider_id)
                    cache.set(cache_key, cached_voices, VOICES_CACHE_TTL)

                # Filter to recommended/premade voices for better quality
                if provider_id == "openai":
                    available_voices = cached_voices
                else:
                    available_voices = [v for v in cached_voices if v.get("category") == "premade"]

                # If no premade voices, use all voices
                if not available_voices:
                    available_voices = cached_voices

                logger.info(f"Using {len(available_voices)} voices from {provider_id} for room generation")
        except Exception as e:
            logger.warning(f"Failed to fetch voices from {provider_id}, using defaults: {e}")

    try:
        generated = async_to_sync(generate_room_from_description)(
            description, available_voices, user=request.user
        )
        result = generated_room_to_dict(generated)
        return Response(result)

    except Exception as e:
        logger.error(f"Room generation failed: {e}")
        return Response(
            {"error": "Failed to generate room configuration. Please try again."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


class VoiceRoomViewSet(viewsets.ModelViewSet):
    """ViewSet for managing voice rooms."""

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Disable pagination - users won't have many rooms

    def get_queryset(self):
        """Return rooms for the current user with active agents."""
        return VoiceRoom.objects.filter(
            user=self.request.user,
            is_active=True
        ).prefetch_related(
            Prefetch(
                "agents",
                queryset=VoiceRoomAgent.objects.filter(is_active=True).order_by("order")
            )
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "list":
            return VoiceRoomListSerializer
        elif self.action == "create":
            return VoiceRoomCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return VoiceRoomUpdateSerializer
        return VoiceRoomSerializer

    def perform_create(self, serializer):
        """Set the user when creating a room."""
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create room and return full serializer with id."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return the created room with full serializer (includes id)
        response_serializer = VoiceRoomSerializer(serializer.instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update room and return full serializer with id."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        # Return the updated room with full serializer (includes id)
        response_serializer = VoiceRoomSerializer(serializer.instance)
        return Response(response_serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Soft delete by setting is_active=False."""
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def add_agent(self, request, pk=None):
        """Add an agent to a room."""
        room = self.get_object()

        if room.agents.filter(is_active=True).count() >= 6:
            return Response(
                {"error": "Maximum 6 agents allowed per room"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = VoiceRoomAgentSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-set order if not provided
            if not serializer.validated_data.get("order"):
                max_order = room.agents.filter(is_active=True).order_by("-order").first()
                order = (max_order.order + 1) if max_order else 1
                serializer.save(room=room, order=order)
            else:
                serializer.save(room=room)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["delete"], url_path="agents/(?P<agent_id>[^/.]+)")
    def remove_agent(self, request, pk=None, agent_id=None):
        """Remove an agent from a room."""
        room = self.get_object()
        agent = get_object_or_404(VoiceRoomAgent, id=agent_id, room=room)

        if room.agents.filter(is_active=True).count() <= 1:
            return Response(
                {"error": "Cannot remove the last agent"},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent.is_active = False
        agent.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def conversation(self, request, pk=None):
        """
        Get a session's conversation messages for a room.

        Used to resume conversations when reconnecting to a voice session,
        and to let past (ended) transcripts render in the UI.

        Resolution order:
        - ``?session=<id>``: that exact session, if it belongs to this room.
        - Otherwise: the most recent active (non-ended) session.
        - Otherwise: the most recent session of any status (e.g. ended),
          so a room with only past conversations still returns its transcript.
        - Otherwise (no sessions at all): an empty conversation.
        """
        room = self.get_object()

        requested_session_id = request.query_params.get("session")
        if requested_session_id:
            try:
                session_uuid = uuid.UUID(requested_session_id)
            except (ValueError, AttributeError, TypeError):
                return Response(
                    {"error": "session must be a valid UUID"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            session = get_object_or_404(
                VoiceRoomSession, id=session_uuid, room=room
            )
        else:
            session = VoiceRoomSession.objects.filter(
                room=room, status__in=ACTIVE_SESSION_STATUSES
            ).order_by("-started_at").first()

            if not session:
                # No live session — fall back to the most recent session of
                # any status (e.g. "ended") so past transcripts still render.
                session = VoiceRoomSession.objects.filter(
                    room=room
                ).order_by("-started_at").first()

        if not session:
            return Response({
                "session_id": None,
                "messages": [],
            })

        # Get messages for this session
        messages = session.messages.select_related("agent").order_by("created_at")
        serializer = VoiceRoomMessageSerializer(messages, many=True)

        return Response({
            "session_id": str(session.id),
            "messages": serializer.data,
        })

    @action(detail=True, methods=["post"])
    def clear_conversation(self, request, pk=None):
        """
        End the current session and start fresh.

        This allows users to explicitly clear conversation history. Since
        `conversation` above falls back to the most recent session of any
        status, clearing must delete the message history itself (not just
        end the active session) or the very messages this action ends up
        "clearing" would immediately resurface on the next GET. Session
        rows are kept — only their messages are removed — so session-level
        metrics (duration, speaking time) used elsewhere are unaffected.
        """
        room = self.get_object()

        VoiceRoomMessage.objects.filter(session__room=room).delete()

        # End any active sessions for this room
        VoiceRoomSession.objects.filter(
            room=room,
            status__in=ACTIVE_SESSION_STATUSES
        ).update(status="ended")

        return Response({"status": "cleared"})


class VoiceRoomSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing voice room sessions."""

    permission_classes = [IsAuthenticated]
    serializer_class = VoiceRoomSessionSerializer
    pagination_class = None  # Disable pagination for consistency

    def get_queryset(self):
        """Return sessions for the current user's rooms."""
        return VoiceRoomSession.objects.filter(
            room__user=self.request.user
        ).select_related("room").prefetch_related("messages")

    def create(self, request, *args, **kwargs):
        """Create a new session for a room."""
        room_id = request.data.get("room_id")
        if not room_id:
            return Response(
                {"error": "room_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        room = get_object_or_404(
            VoiceRoom,
            id=room_id,
            user=request.user,
            is_active=True
        )

        session = VoiceRoomSession.objects.create(room=room)
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def add_message(self, request, pk=None):
        """Add a message to a session."""
        session = self.get_object()

        serializer = VoiceRoomMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(session=session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End a session."""
        from django.utils import timezone

        session = self.get_object()
        session.status = "ended"
        session.ended_at = timezone.now()
        session.save()

        serializer = self.get_serializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"])
    def update_status(self, request, pk=None):
        """Update session status."""
        session = self.get_object()
        new_status = request.data.get("status")
        current_speaker = request.data.get("current_speaker")

        if new_status:
            session.status = new_status
        if current_speaker is not None:
            session.current_speaker = current_speaker

        session.save()
        serializer = self.get_serializer(session)
        return Response(serializer.data)
