"""OpenAI Text-to-Speech Provider.

Uses OpenAI's TTS API for speech synthesis.
Models: tts-1, tts-1-hd
Voices: alloy, echo, fable, onyx, nova, shimmer
"""

import logging
from typing import List, Optional

import httpx
from django.conf import settings

from .tts_base import TTSProvider, TTSVoice, TTSModel, TTSSettings
from usage_quota.models import FeatureType

logger = logging.getLogger(__name__)


# OpenAI TTS voice metadata
OPENAI_VOICES = [
    {
        "voice_id": "alloy",
        "name": "Alloy",
        "description": "A balanced, versatile voice suitable for many applications",
        "labels": {"gender": "neutral", "tone": "balanced"},
    },
    {
        "voice_id": "echo",
        "name": "Echo",
        "description": "A warm, conversational voice with natural intonation",
        "labels": {"gender": "male", "tone": "warm"},
    },
    {
        "voice_id": "fable",
        "name": "Fable",
        "description": "An expressive, narrative voice great for storytelling",
        "labels": {"gender": "neutral", "tone": "expressive"},
    },
    {
        "voice_id": "onyx",
        "name": "Onyx",
        "description": "A deep, authoritative voice with presence",
        "labels": {"gender": "male", "tone": "deep"},
    },
    {
        "voice_id": "nova",
        "name": "Nova",
        "description": "A friendly, upbeat voice with energy",
        "labels": {"gender": "female", "tone": "friendly"},
    },
    {
        "voice_id": "shimmer",
        "name": "Shimmer",
        "description": "A clear, pleasant voice with warmth",
        "labels": {"gender": "female", "tone": "clear"},
    },
]

# OpenAI TTS models
OPENAI_MODELS = [
    {
        "model_id": "tts-1",
        "name": "TTS-1",
        "description": "Standard quality, optimized for speed and low latency",
    },
    {
        "model_id": "tts-1-hd",
        "name": "TTS-1 HD",
        "description": "High quality audio, better for production use",
    },
]


class OpenAITTSProvider(TTSProvider):
    """
    OpenAI TTS Provider.

    Features:
    - Simple, reliable TTS
    - 6 high-quality voices
    - Speed control (0.25 to 4.0)
    - Multiple output formats
    """

    PROVIDER_ID = "openai"
    PROVIDER_NAME = "OpenAI"
    API_URL = "https://api.openai.com/v1/audio/speech"

    def __init__(self, user=None, session_id: Optional[str] = None,
                 feature: str = FeatureType.VOICE_ROOM):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', None)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._user = user
        self._session_id = session_id
        self._feature = feature

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )

    async def cleanup(self) -> None:
        """Cleanup HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        model_id: Optional[str] = None,
        settings: Optional[TTSSettings] = None,
    ) -> Optional[bytes]:
        """
        Convert text to speech using OpenAI TTS API.

        Args:
            text: Text to convert (max 4096 characters)
            voice_id: One of: alloy, echo, fable, onyx, nova, shimmer
            model_id: tts-1 or tts-1-hd (defaults to tts-1)
            settings: TTS settings (speed, response_format)

        Returns:
            Audio bytes (MP3 by default) or None if failed
        """
        if not self._http_client:
            await self.initialize()

        if not self.api_key:
            logger.error("OpenAI API key not configured")
            return None

        # Apply defaults
        model_id = model_id or self.get_default_model_id()
        voice_id = voice_id or self.get_default_voice_id()
        settings = settings or TTSSettings()

        # Validate and clamp speed (OpenAI supports 0.25 to 4.0)
        speed = max(0.25, min(4.0, settings.speed or 1.0))

        # Build request
        request_body = {
            "model": model_id,
            "input": text[:4096],  # OpenAI limit
            "voice": voice_id,
            "speed": speed,
            "response_format": settings.response_format or "mp3",
        }

        try:
            logger.info(f"OpenAI TTS: Generating speech with voice={voice_id}, model={model_id}, speed={speed}")

            response = await self._http_client.post(
                self.API_URL,
                json=request_body,
            )
            response.raise_for_status()

            logger.info(f"OpenAI TTS: Generated {len(response.content)} bytes of audio")
            await self._record_billing(text=text, model_id=model_id)
            return response.content

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI TTS API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"OpenAI TTS error: {e}")
            return None

    async def get_voices(self) -> List[TTSVoice]:
        """
        Get available OpenAI TTS voices.

        OpenAI has 6 built-in voices (no API call needed).
        """
        return [
            TTSVoice(
                voice_id=v["voice_id"],
                name=v["name"],
                provider=self.PROVIDER_ID,
                description=v.get("description"),
                category="premade",
                labels=v.get("labels", {}),
                languages=["en"],  # OpenAI TTS supports many languages automatically
            )
            for v in OPENAI_VOICES
        ]

    async def get_models(self) -> List[TTSModel]:
        """
        Get available OpenAI TTS models.

        OpenAI has 2 TTS models (no API call needed).
        """
        return [
            TTSModel(
                model_id=m["model_id"],
                name=m["name"],
                provider=self.PROVIDER_ID,
                description=m.get("description"),
                languages=[
                    {"language_id": "en", "name": "English"},
                    {"language_id": "es", "name": "Spanish"},
                    {"language_id": "fr", "name": "French"},
                    {"language_id": "de", "name": "German"},
                    {"language_id": "it", "name": "Italian"},
                    {"language_id": "pt", "name": "Portuguese"},
                    {"language_id": "pl", "name": "Polish"},
                    {"language_id": "ja", "name": "Japanese"},
                    {"language_id": "ko", "name": "Korean"},
                    {"language_id": "zh", "name": "Chinese"},
                    {"language_id": "ar", "name": "Arabic"},
                    {"language_id": "hi", "name": "Hindi"},
                    {"language_id": "ru", "name": "Russian"},
                ],
                supports_streaming=False,  # We're using the non-streaming endpoint
            )
            for m in OPENAI_MODELS
        ]

    async def _record_billing(self, text: str, model_id: str) -> None:
        """Mirror of OpenAITTSClient._deduct_tts_usage. Inlined because
        OpenAITTSProvider does not wrap OpenAITTSClient (it talks to the
        REST API directly via httpx).
        """
        if not self._user:
            return
        try:
            from asgiref.sync import sync_to_async
            from usage_quota.billing.service import get_billing_service
            from usage_quota.billing.operations import BillableOperation
            from usage_quota.services.cost_calculator import get_cost_calculator
            from usage_quota.models import ServiceType

            char_count = len(text or "")
            cost = get_cost_calculator().calculate_openai_tts_cost(
                character_count=char_count,
                model_id=model_id,
            )
            op = BillableOperation(
                service=ServiceType.OPENAI_TTS,
                feature=self._feature,
                model_id=model_id,
                character_count=char_count,
                cost_usd=cost,
                session_id=self._session_id or "",
            )
            await sync_to_async(get_billing_service().record_usage)(
                self._user, op, billing_origin='platform',
            )
        except Exception:
            logger.error("openai_tts.record_billing_failed", exc_info=True)

    def get_default_voice_id(self) -> str:
        """Default to 'alloy' voice."""
        return "alloy"

    def get_default_model_id(self) -> str:
        """Default to 'tts-1' for speed."""
        return "tts-1"

    def get_supported_settings(self) -> List[str]:
        """OpenAI TTS supports speed and response_format."""
        return ["speed", "response_format"]
