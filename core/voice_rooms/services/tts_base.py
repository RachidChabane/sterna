"""Base TTS Provider Interface.

This module defines the abstract interface for TTS providers,
allowing for multiple TTS backends (OpenAI, ElevenLabs, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class TTSVoice:
    """Information about an available voice."""
    voice_id: str
    name: str
    provider: str
    description: Optional[str] = None
    preview_url: Optional[str] = None
    category: str = "premade"  # premade, cloned, generated
    labels: Dict[str, str] = field(default_factory=dict)
    languages: List[str] = field(default_factory=list)
    # Provider-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSModel:
    """Information about an available TTS model."""
    model_id: str
    name: str
    provider: str
    description: Optional[str] = None
    languages: List[Dict[str, str]] = field(default_factory=list)
    # Model capabilities
    can_use_style: bool = False
    can_use_speaker_boost: bool = False
    supports_streaming: bool = False
    # Provider-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSSettings:
    """
    Provider-agnostic TTS settings.

    Each provider may use a subset of these settings.
    """
    # Common settings
    speed: float = 1.0  # Speech speed (typically 0.5-2.0)

    # ElevenLabs-specific
    stability: Optional[float] = None  # 0-1
    similarity_boost: Optional[float] = None  # 0-1
    style: Optional[float] = None  # 0-1
    use_speaker_boost: Optional[bool] = None

    # OpenAI-specific
    response_format: str = "mp3"  # mp3, opus, aac, flac, wav, pcm

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class TTSProvider(ABC):
    """
    Abstract base class for TTS providers.

    Implement this class to add support for a new TTS provider.
    """

    # Provider identifier (e.g., 'openai', 'elevenlabs')
    PROVIDER_ID: str = "base"
    PROVIDER_NAME: str = "Base Provider"

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider (e.g., create HTTP clients)."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources (e.g., close HTTP clients)."""
        pass

    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        model_id: Optional[str] = None,
        settings: Optional[TTSSettings] = None,
    ) -> Optional[bytes]:
        """
        Convert text to speech.

        Args:
            text: Text to convert to speech
            voice_id: Voice identifier
            model_id: Optional model identifier
            settings: Optional TTS settings

        Returns:
            Audio bytes (typically MP3) or None if failed
        """
        pass

    @abstractmethod
    async def get_voices(self) -> List[TTSVoice]:
        """
        Get list of available voices.

        Returns:
            List of TTSVoice objects
        """
        pass

    @abstractmethod
    async def get_models(self) -> List[TTSModel]:
        """
        Get list of available TTS models.

        Returns:
            List of TTSModel objects
        """
        pass

    def get_default_voice_id(self) -> str:
        """Get the default voice ID for this provider."""
        return ""

    def get_default_model_id(self) -> str:
        """Get the default model ID for this provider."""
        return ""

    def get_supported_settings(self) -> List[str]:
        """
        Get list of supported settings for this provider.

        Returns:
            List of setting names (e.g., ['speed', 'stability'])
        """
        return ["speed"]
