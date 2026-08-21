"""
Speech-to-text transcription endpoint for chat.

Uses Deepgram's pre-recorded API for batch transcription of audio files.
"""

import logging
from typing import Optional

import httpx
from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Deepgram Nova-2 supported languages
# Source: https://developers.deepgram.com/docs/models-languages-overview
DEEPGRAM_LANGUAGES = [
    {"code": "auto", "name": "Auto-detect", "country_code": ""},
    {"code": "en", "name": "English", "country_code": "us"},
    {"code": "en-US", "name": "English (US)", "country_code": "us"},
    {"code": "en-GB", "name": "English (UK)", "country_code": "gb"},
    {"code": "en-AU", "name": "English (Australia)", "country_code": "au"},
    {"code": "en-NZ", "name": "English (New Zealand)", "country_code": "nz"},
    {"code": "en-IN", "name": "English (India)", "country_code": "in"},
    {"code": "es", "name": "Spanish", "country_code": "es"},
    {"code": "es-419", "name": "Spanish (Latin America)", "country_code": "mx"},
    {"code": "fr", "name": "French", "country_code": "fr"},
    {"code": "fr-CA", "name": "French (Canada)", "country_code": "ca"},
    {"code": "de", "name": "German", "country_code": "de"},
    {"code": "de-CH", "name": "German (Switzerland)", "country_code": "ch"},
    {"code": "it", "name": "Italian", "country_code": "it"},
    {"code": "pt", "name": "Portuguese", "country_code": "pt"},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "country_code": "br"},
    {"code": "pt-PT", "name": "Portuguese (Portugal)", "country_code": "pt"},
    {"code": "nl", "name": "Dutch", "country_code": "nl"},
    {"code": "nl-BE", "name": "Flemish", "country_code": "be"},
    {"code": "ru", "name": "Russian", "country_code": "ru"},
    {"code": "ja", "name": "Japanese", "country_code": "jp"},
    {"code": "ko", "name": "Korean", "country_code": "kr"},
    {"code": "zh", "name": "Chinese (Mandarin)", "country_code": "cn"},
    {"code": "zh-CN", "name": "Chinese (Simplified)", "country_code": "cn"},
    {"code": "zh-TW", "name": "Chinese (Traditional)", "country_code": "tw"},
    {"code": "zh-HK", "name": "Chinese (Cantonese)", "country_code": "hk"},
    {"code": "hi", "name": "Hindi", "country_code": "in"},
    {"code": "pl", "name": "Polish", "country_code": "pl"},
    {"code": "tr", "name": "Turkish", "country_code": "tr"},
    {"code": "uk", "name": "Ukrainian", "country_code": "ua"},
    {"code": "vi", "name": "Vietnamese", "country_code": "vn"},
    {"code": "th", "name": "Thai", "country_code": "th"},
    {"code": "id", "name": "Indonesian", "country_code": "id"},
    {"code": "ms", "name": "Malay", "country_code": "my"},
    {"code": "da", "name": "Danish", "country_code": "dk"},
    {"code": "sv", "name": "Swedish", "country_code": "se"},
    {"code": "no", "name": "Norwegian", "country_code": "no"},
    {"code": "fi", "name": "Finnish", "country_code": "fi"},
    {"code": "el", "name": "Greek", "country_code": "gr"},
    {"code": "cs", "name": "Czech", "country_code": "cz"},
    {"code": "sk", "name": "Slovak", "country_code": "sk"},
    {"code": "ro", "name": "Romanian", "country_code": "ro"},
    {"code": "hu", "name": "Hungarian", "country_code": "hu"},
    {"code": "bg", "name": "Bulgarian", "country_code": "bg"},
    {"code": "ca", "name": "Catalan", "country_code": "es"},
    {"code": "et", "name": "Estonian", "country_code": "ee"},
    {"code": "lv", "name": "Latvian", "country_code": "lv"},
    {"code": "lt", "name": "Lithuanian", "country_code": "lt"},
    {"code": "multi", "name": "Multilingual (Spanish + English)", "country_code": ""},
]

# Cache key for languages
LANGUAGES_CACHE_KEY = "deepgram:languages"
LANGUAGES_CACHE_TTL = 86400  # 24 hours

# Deepgram configuration
DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_AUDIO_TYPES = [
    "audio/webm",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/ogg",
    "audio/flac",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
]


def _deduct_stt_usage(user, audio_seconds: float, model_id: str = "nova-2") -> None:
    """Record chat STT usage via BillingService (platform-only)."""
    try:
        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.services import get_cost_calculator
        from usage_quota.models import ServiceType, FeatureType

        cost_calculator = get_cost_calculator()
        cost_usd = cost_calculator.calculate_deepgram_cost(
            audio_seconds=audio_seconds,
            model_id=model_id,
        )

        op = BillableOperation(
            service=ServiceType.DEEPGRAM_STT,
            feature=FeatureType.CHAT,
            model_id=model_id,
            audio_seconds=audio_seconds,
            cost_usd=cost_usd,
        )
        # Deepgram STT is always platform-billed; route through BillingService
        # so the guard catches accidental BYOK calls.
        get_billing_service().record_usage(user, op, billing_origin='platform')

        logger.info(f"Chat STT usage recorded: {audio_seconds:.1f}s audio, ${cost_usd:.6f}")

    except Exception as e:
        logger.error(f"Failed to record chat STT usage: {e}")


def _check_stt_quota(user, estimated_seconds: float = 60.0) -> tuple[bool, Optional[str]]:
    """
    Check if user has quota for STT.

    Returns:
        Tuple of (allowed, error_message)
    """
    try:
        from usage_quota.services import get_quota_service, get_cost_calculator
        from usage_quota.models import ServiceType, FeatureType

        quota_service = get_quota_service()
        cost_calculator = get_cost_calculator()

        model_id = getattr(settings, 'DEEPGRAM_MODEL', 'nova-2')
        estimated_cost = cost_calculator.calculate_deepgram_cost(
            audio_seconds=estimated_seconds,
            model_id=model_id,
        )

        # Sync check
        check_result = quota_service.check_quota(
            user=user,
            service=ServiceType.DEEPGRAM_STT,
            estimated_cost_usd=estimated_cost,
            feature=FeatureType.CHAT,
        )

        if not check_result.allowed:
            return False, check_result.reason or "Speech-to-text quota exceeded"

        return True, None

    except Exception as e:
        logger.error(f"Failed to check STT quota: {e}")
        # Allow on quota check failure (fail open)
        return True, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def transcribe_audio(request):
    """
    Transcribe audio file to text using Deepgram.

    POST /api/llm/transcribe/

    Request:
        - Content-Type: multipart/form-data
        - audio: Audio file (webm, wav, mp3, etc.)
        - language: Optional language code (default: auto-detect)

    Response:
        {
            "success": true,
            "transcript": "Hello world",
            "confidence": 0.95,
            "duration": 3.5,
            "language": "en"
        }
    """
    # Get audio file
    audio_file = request.FILES.get("audio")
    if not audio_file:
        return Response(
            {"success": False, "error": "No audio file provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate file size
    if audio_file.size > MAX_AUDIO_SIZE_BYTES:
        return Response(
            {"success": False, "error": f"Audio file too large. Maximum size is {MAX_AUDIO_SIZE_BYTES // (1024 * 1024)}MB"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate content type
    content_type = audio_file.content_type
    if content_type not in ALLOWED_AUDIO_TYPES:
        # Also check if it's a valid audio type based on file extension
        file_name = audio_file.name.lower() if audio_file.name else ""
        valid_extensions = [".webm", ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".mp4"]
        if not any(file_name.endswith(ext) for ext in valid_extensions):
            return Response(
                {"success": False, "error": f"Unsupported audio format: {content_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Check quota
    # Estimate ~60 seconds for quota pre-check
    allowed, error_message = _check_stt_quota(request.user, estimated_seconds=60.0)
    if not allowed:
        return Response(
            {"success": False, "error": error_message},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Get API key
    api_key = getattr(settings, 'DEEPGRAM_API_KEY', None)
    if not api_key:
        logger.error("Deepgram API key not configured")
        return Response(
            {"success": False, "error": "Speech-to-text service not configured"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Get language preference
    language = request.data.get("language", "auto")

    # Build Deepgram request
    model = getattr(settings, 'DEEPGRAM_MODEL', 'nova-2')
    params = {
        "model": model,
        "punctuate": "true",
        "smart_format": "true",
    }

    # Only set language if not auto-detect
    if language and language != "auto":
        params["language"] = language
    else:
        params["detect_language"] = "true"

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type or "audio/webm",
    }

    # Read audio data
    audio_data = audio_file.read()

    try:
        # Call Deepgram API
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                DEEPGRAM_API_URL,
                params=params,
                headers=headers,
                content=audio_data,
            )

        if response.status_code != 200:
            logger.error(f"Deepgram API error: {response.status_code} - {response.text}")
            return Response(
                {"success": False, "error": "Transcription failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result = response.json()

        # Extract transcript from response
        channels = result.get("results", {}).get("channels", [])
        if not channels:
            return Response(
                {"success": True, "transcript": "", "confidence": 0, "duration": 0},
                status=status.HTTP_200_OK,
            )

        alternatives = channels[0].get("alternatives", [])
        if not alternatives:
            return Response(
                {"success": True, "transcript": "", "confidence": 0, "duration": 0},
                status=status.HTTP_200_OK,
            )

        best_alternative = alternatives[0]
        transcript = best_alternative.get("transcript", "")
        confidence = best_alternative.get("confidence", 0)

        # Get duration from metadata
        metadata = result.get("metadata", {})
        duration = metadata.get("duration", 0)
        detected_language = metadata.get("detected_language", language)

        # Deduct usage
        if duration > 0:
            _deduct_stt_usage(request.user, duration, model)

        return Response({
            "success": True,
            "transcript": transcript,
            "confidence": confidence,
            "duration": duration,
            "language": detected_language,
        })

    except httpx.TimeoutException:
        logger.error("Deepgram API timeout")
        return Response(
            {"success": False, "error": "Transcription timed out. Please try again."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except Exception as e:
        logger.exception(f"Transcription error: {e}")
        return Response(
            {"success": False, "error": "An error occurred during transcription."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_stt_languages(request):
    """
    Get available STT languages for Deepgram.

    GET /api/llm/stt-languages/

    Response:
        {
            "languages": [
                {"code": "auto", "name": "Auto-detect", "country_code": ""},
                {"code": "en", "name": "English", "country_code": "us"},
                ...
            ]
        }

    Results are cached for 24 hours.
    """
    # Try cache first
    cached = cache.get(LANGUAGES_CACHE_KEY)
    if cached is not None:
        return Response({"languages": cached})

    # Cache and return the static list
    cache.set(LANGUAGES_CACHE_KEY, DEEPGRAM_LANGUAGES, timeout=LANGUAGES_CACHE_TTL)

    return Response({"languages": DEEPGRAM_LANGUAGES})
