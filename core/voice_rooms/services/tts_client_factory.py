"""TTS Client Factory for Voice Rooms.

Provides factory functions to create the appropriate TTS client
based on the TTS model being used. Supports both ElevenLabs and OpenAI.
"""

import logging
from typing import Any, Callable, Optional, Awaitable, Protocol, Dict, List

logger = logging.getLogger(__name__)


# OpenAI TTS voice IDs
OPENAI_VOICE_IDS = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# OpenAI TTS model prefixes
OPENAI_MODEL_PREFIXES = ["tts-1", "tts-"]


class TTSClientProtocol(Protocol):
    """Protocol defining the interface that all TTS clients must implement."""

    async def initialize(self) -> None:
        """Initialize the client."""
        ...

    async def cleanup(self) -> None:
        """Cleanup all connections."""
        ...

    async def connect_voice(
        self,
        voice_id: str,
        voice_settings: Any = None,
        model: Optional[str] = None,
    ) -> bool:
        """Connect/register a voice for TTS."""
        ...

    async def disconnect_voice(self, voice_id: str) -> None:
        """Disconnect a voice."""
        ...

    async def send_text(self, voice_id: str, text: str) -> None:
        """Send text to be synthesized."""
        ...

    async def flush(self, voice_id: str) -> None:
        """Flush buffer and generate remaining audio."""
        ...

    async def stop_generation(self, voice_id: str) -> None:
        """Stop audio generation (for interruption handling)."""
        ...

    async def wait_for_completion(
        self,
        voice_id: str,
        timeout: float = 120.0,
        audio_silence_timeout: float = 5.0,
    ) -> bool:
        """Wait for audio generation to complete."""
        ...


def detect_tts_provider(tts_model: str, voice_id: str) -> str:
    """
    Detect which TTS provider to use based on model and voice ID.

    Args:
        tts_model: The TTS model ID (e.g., 'tts-1', 'eleven_turbo_v2')
        voice_id: The voice ID

    Returns:
        Provider ID: 'openai' or 'elevenlabs'
    """
    tts_model_lower = (tts_model or "").lower()
    voice_id_lower = (voice_id or "").lower()

    # Check if it's an OpenAI model
    for prefix in OPENAI_MODEL_PREFIXES:
        if tts_model_lower.startswith(prefix):
            return "openai"

    # Check if it's an OpenAI voice
    if voice_id_lower in OPENAI_VOICE_IDS:
        return "openai"

    # Default to ElevenLabs
    return "elevenlabs"


def create_tts_client(
    provider: str,
    on_audio: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
    on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
    on_audio_complete: Optional[Callable[[str], Awaitable[None]]] = None,
    on_alignment: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    user=None,
    session_id: Optional[str] = None,
) -> TTSClientProtocol:
    """
    Create a TTS client for the specified provider.

    Args:
        provider: Provider ID ('openai' or 'elevenlabs')
        on_audio: Callback for audio chunks (voice_id, base64_audio, sequence)
        on_error: Callback for errors (voice_id, error_message)
        on_audio_complete: Callback when generation is complete (voice_id)
        on_alignment: Callback for word timing alignment (voice_id, alignment_data)
                      - ElevenLabs: Native character-level timing from API
                      - OpenAI: Estimated timing based on speaking rate

    Returns:
        TTS client instance

    Raises:
        ValueError: If provider is not supported
    """
    if provider == "openai":
        from .openai_tts_client import OpenAITTSClient
        logger.info("Creating OpenAI TTS client")
        return OpenAITTSClient(
            on_audio=on_audio,
            on_error=on_error,
            on_audio_complete=on_audio_complete,
            on_alignment=on_alignment,  # OpenAI uses estimated timing
            user=user,
            session_id=session_id,
        )
    elif provider == "elevenlabs":
        from .elevenlabs_tts import ElevenLabsTTSClient
        logger.info("Creating ElevenLabs TTS client")
        return ElevenLabsTTSClient(
            on_audio=on_audio,
            on_error=on_error,
            on_audio_complete=on_audio_complete,
            on_alignment=on_alignment,
            user=user,
            session_id=session_id,
        )
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")


class MultiProviderTTSClient:
    """
    TTS client that supports multiple providers simultaneously.

    This allows a voice room to have agents using different TTS providers.
    It routes calls to the appropriate underlying client based on voice ID.
    """

    def __init__(
        self,
        on_audio: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_audio_complete: Optional[Callable[[str], Awaitable[None]]] = None,
        on_alignment: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        user=None,
        session_id: Optional[str] = None,
    ):
        self.on_audio = on_audio
        self.on_error = on_error
        self.on_audio_complete = on_audio_complete
        self.on_alignment = on_alignment
        self._user = user
        self._session_id = session_id

        self._clients: Dict[str, TTSClientProtocol] = {}  # provider -> client
        self._voice_to_provider: Dict[str, str] = {}  # voice_id -> provider

    async def initialize(self) -> None:
        """Initialize all clients."""
        # Clients are initialized lazily when voices are connected
        pass

    async def cleanup(self) -> None:
        """Cleanup all clients."""
        for client in self._clients.values():
            await client.cleanup()
        self._clients.clear()
        self._voice_to_provider.clear()

    async def _get_or_create_client(self, provider: str) -> TTSClientProtocol:
        """Get or create a client for the given provider."""
        if provider not in self._clients:
            client = create_tts_client(
                provider=provider,
                on_audio=self.on_audio,
                on_error=self.on_error,
                on_audio_complete=self.on_audio_complete,
                on_alignment=self.on_alignment,
                user=self._user,
                session_id=self._session_id,
            )
            await client.initialize()
            self._clients[provider] = client
        return self._clients[provider]

    async def connect_voice(
        self,
        voice_id: str,
        voice_settings: Optional[object] = None,
        model: Optional[str] = None,
    ) -> bool:
        """
        Connect a voice, automatically detecting the right provider.

        Args:
            voice_id: Voice ID
            voice_settings: Voice settings
            model: TTS model ID (used to detect provider)

        Returns:
            True if successful
        """
        # Detect provider from model and voice
        provider = detect_tts_provider(model or "", voice_id)
        logger.info(f"Connecting voice {voice_id} with model {model} -> provider: {provider}")

        # Get or create the client
        client = await self._get_or_create_client(provider)

        # Connect the voice
        success = await client.connect_voice(voice_id, voice_settings, model)

        if success:
            self._voice_to_provider[voice_id] = provider

        return success

    async def disconnect_voice(self, voice_id: str) -> None:
        """Disconnect a voice."""
        provider = self._voice_to_provider.get(voice_id)
        if provider and provider in self._clients:
            await self._clients[provider].disconnect_voice(voice_id)
        self._voice_to_provider.pop(voice_id, None)

    async def send_text(self, voice_id: str, text: str) -> None:
        """Send text to be synthesized."""
        provider = self._voice_to_provider.get(voice_id)
        if provider and provider in self._clients:
            await self._clients[provider].send_text(voice_id, text)

    async def flush(self, voice_id: str) -> None:
        """Flush buffer and generate audio."""
        provider = self._voice_to_provider.get(voice_id)
        if provider and provider in self._clients:
            await self._clients[provider].flush(voice_id)

    async def stop_generation(self, voice_id: str) -> None:
        """Stop audio generation."""
        provider = self._voice_to_provider.get(voice_id)
        if provider and provider in self._clients:
            await self._clients[provider].stop_generation(voice_id)

    async def wait_for_completion(
        self,
        voice_id: str,
        timeout: float = 120.0,
        audio_silence_timeout: float = 5.0,
    ) -> bool:
        """Wait for audio generation to complete."""
        provider = self._voice_to_provider.get(voice_id)
        if provider and provider in self._clients:
            return await self._clients[provider].wait_for_completion(
                voice_id, timeout, audio_silence_timeout
            )
        return True

    def get_provider_for_voice(self, voice_id: str) -> Optional[str]:
        """Get the provider being used for a voice."""
        return self._voice_to_provider.get(voice_id)

    def get_connected_voices(self) -> List[str]:
        """Get all connected voice IDs."""
        return list(self._voice_to_provider.keys())

    def is_voice_connected(self, voice_id: str) -> bool:
        """Check if a voice is connected."""
        return voice_id in self._voice_to_provider

    async def generate_audio_direct(self, voice_id: str, text: str) -> Optional[str]:
        """
        Generate audio directly without callbacks (OpenAI only).

        For pipelined generation where we pre-generate audio while
        previous agent's audio is playing.

        Args:
            voice_id: Voice ID
            text: Text to synthesize

        Returns:
            Base64-encoded audio or None (only works for OpenAI provider)
        """
        provider = self._voice_to_provider.get(voice_id)
        if provider != "openai":
            logger.warning(f"generate_audio_direct only supported for OpenAI, got {provider}")
            return None

        client = self._clients.get(provider)
        if client and hasattr(client, 'generate_audio_direct'):
            return await client.generate_audio_direct(voice_id, text)
        return None
