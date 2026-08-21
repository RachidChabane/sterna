"""Voice room services for STT, TTS, and LLM."""

from .deepgram_stt import DeepgramSTTClient
from .elevenlabs_tts import ElevenLabsTTSClient, ElevenLabsTTSProvider
from .openai_tts import OpenAITTSProvider
from .tts_base import TTSProvider, TTSVoice, TTSModel, TTSSettings
from .tts_factory import TTSService, get_provider, get_available_providers, generate_speech
from .llm_router import LLMRouter
from .orchestrator import VoiceRoomOrchestrator

__all__ = [
    # STT
    "DeepgramSTTClient",
    # TTS - Legacy (for voice rooms WebSocket)
    "ElevenLabsTTSClient",
    # TTS - Provider interface
    "TTSProvider",
    "TTSVoice",
    "TTSModel",
    "TTSSettings",
    # TTS - Providers
    "OpenAITTSProvider",
    "ElevenLabsTTSProvider",
    # TTS - Factory
    "TTSService",
    "get_provider",
    "get_available_providers",
    "generate_speech",
    # LLM
    "LLMRouter",
    # Orchestrator
    "VoiceRoomOrchestrator",
]
