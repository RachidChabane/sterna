"""TTS Provider Factory.

This module provides a factory for creating TTS provider instances
and manages provider selection based on configuration.
"""

import logging
from typing import Dict, List, Optional, Type

from django.conf import settings

from .tts_base import TTSProvider, TTSVoice, TTSModel, TTSSettings
from .openai_tts import OpenAITTSProvider
from .elevenlabs_tts import ElevenLabsTTSProvider
from usage_quota.models import FeatureType

logger = logging.getLogger(__name__)


# Registry of available TTS providers
TTS_PROVIDERS: Dict[str, Type[TTSProvider]] = {
    "openai": OpenAITTSProvider,
    "elevenlabs": ElevenLabsTTSProvider,
}

# Default provider (OpenAI for now, ElevenLabs will be for premium users later)
DEFAULT_PROVIDER = "openai"


def get_available_providers() -> List[str]:
    """
    Get list of available TTS providers based on configured API keys.

    Returns:
        List of provider IDs that have API keys configured
    """
    available = []

    # Check OpenAI
    if getattr(settings, 'OPENAI_API_KEY', None):
        available.append("openai")

    # Check ElevenLabs
    if getattr(settings, 'ELEVENLABS_API_KEY', None):
        available.append("elevenlabs")

    return available


def get_provider(
    provider_id: Optional[str] = None,
    user=None,
    session_id: Optional[str] = None,
    feature: str = FeatureType.VOICE_ROOM,
) -> TTSProvider:
    """
    Get a TTS provider instance.

    Args:
        provider_id: Provider ID ('openai', 'elevenlabs', etc.)
                    If None, uses the default provider
        user, session_id, feature: forwarded to the provider for billing.
            `feature` defaults to VOICE_ROOM; preview flows pass CHAT.

    Returns:
        TTSProvider instance

    Raises:
        ValueError: If provider is not available or not configured
    """
    # Use default if not specified
    provider_id = provider_id or DEFAULT_PROVIDER

    # Check if provider exists
    if provider_id not in TTS_PROVIDERS:
        available = list(TTS_PROVIDERS.keys())
        raise ValueError(f"Unknown TTS provider: {provider_id}. Available: {available}")

    # Check if provider is available (has API key)
    available = get_available_providers()
    if provider_id not in available:
        # Fall back to any available provider
        if available:
            fallback = available[0]
            logger.warning(
                f"TTS provider '{provider_id}' not configured, falling back to '{fallback}'"
            )
            provider_id = fallback
        else:
            raise ValueError("No TTS providers are configured. Please set API keys.")

    # Create and return provider instance
    provider_class = TTS_PROVIDERS[provider_id]
    return provider_class(user=user, session_id=session_id, feature=feature)


class TTSService:
    """
    High-level TTS service that abstracts provider selection.

    This is the main entry point for TTS functionality.
    It handles provider initialization, caching, and cleanup.
    """

    def __init__(
        self,
        provider_id: Optional[str] = None,
        user=None,
        session_id: Optional[str] = None,
        feature: str = FeatureType.VOICE_ROOM,
    ):
        """
        Initialize TTS service.

        Args:
            provider_id: Specific provider to use, or None for default
            user, session_id, feature: forwarded to the provider for billing.
                Voice room flows leave `feature` at VOICE_ROOM; preview flows
                pass `feature=CHAT` so the resulting UsageLog row is
                attributed to CHAT (matrix row #34).
        """
        self._provider_id = provider_id
        self._provider: Optional[TTSProvider] = None
        self._user = user
        self._session_id = session_id
        self._feature = feature

    async def _get_provider(self) -> TTSProvider:
        """Get or create the provider instance."""
        if self._provider is None:
            self._provider = get_provider(
                self._provider_id,
                user=self._user,
                session_id=self._session_id,
                feature=self._feature,
            )
            await self._provider.initialize()
        return self._provider

    async def cleanup(self) -> None:
        """Cleanup the provider."""
        if self._provider:
            await self._provider.cleanup()
            self._provider = None

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        settings: Optional[TTSSettings] = None,
    ) -> Optional[bytes]:
        """
        Convert text to speech.

        Args:
            text: Text to convert
            voice_id: Voice ID (provider-specific)
            model_id: Model ID (provider-specific)
            settings: TTS settings

        Returns:
            Audio bytes or None if failed
        """
        provider = await self._get_provider()

        # Use provider defaults if not specified
        voice_id = voice_id or provider.get_default_voice_id()
        model_id = model_id or provider.get_default_model_id()

        return await provider.text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            settings=settings,
        )

    async def get_voices(self) -> List[TTSVoice]:
        """Get available voices for the current provider."""
        provider = await self._get_provider()
        return await provider.get_voices()

    async def get_models(self) -> List[TTSModel]:
        """Get available models for the current provider."""
        provider = await self._get_provider()
        return await provider.get_models()

    def get_provider_id(self) -> str:
        """Get the current provider ID."""
        return self._provider_id or DEFAULT_PROVIDER

    def get_supported_settings(self) -> List[str]:
        """Get supported settings for the current provider."""
        if self._provider:
            return self._provider.get_supported_settings()
        # Return settings for the target provider without initializing
        provider_class = TTS_PROVIDERS.get(self._provider_id or DEFAULT_PROVIDER)
        if provider_class:
            return provider_class().get_supported_settings()
        return ["speed"]


# Convenience function for one-shot TTS
async def generate_speech(
    text: str,
    provider_id: Optional[str] = None,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    settings: Optional[TTSSettings] = None,
) -> Optional[bytes]:
    """
    Generate speech from text (one-shot convenience function).

    This creates a provider, generates speech, and cleans up.
    For multiple requests, use TTSService directly for efficiency.

    Args:
        text: Text to convert
        provider_id: Provider to use ('openai', 'elevenlabs')
        voice_id: Voice ID
        model_id: Model ID
        settings: TTS settings

    Returns:
        Audio bytes or None if failed
    """
    service = TTSService(provider_id)
    try:
        return await service.text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            settings=settings,
        )
    finally:
        await service.cleanup()
