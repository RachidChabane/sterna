"""Voice utility functions for voice rooms."""

import logging
from typing import List

logger = logging.getLogger(__name__)

# Default voices per provider - used when no voice is specified or voice is invalid
DEFAULT_VOICES = {
    "openai": [
        {"voice_id": "alloy", "voice_name": "Alloy"},
        {"voice_id": "echo", "voice_name": "Echo"},
        {"voice_id": "fable", "voice_name": "Fable"},
        {"voice_id": "onyx", "voice_name": "Onyx"},
        {"voice_id": "nova", "voice_name": "Nova"},
        {"voice_id": "shimmer", "voice_name": "Shimmer"},
    ],
    "elevenlabs": [
        {"voice_id": "21m00Tcm4TlvDq8ikWAM", "voice_name": "Rachel"},
        {"voice_id": "AZnzlk1XvdvUeBnXmlld", "voice_name": "Domi"},
        {"voice_id": "EXAVITQu4vr4xnSDxMaL", "voice_name": "Bella"},
        {"voice_id": "ErXwobaYiN019PkySvjV", "voice_name": "Antoni"},
        {"voice_id": "MF3mGyEYCl7XYWbV9V6O", "voice_name": "Elli"},
        {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "voice_name": "Josh"},
        {"voice_id": "VR6AewLTigWG4xSOukaG", "voice_name": "Arnold"},
        {"voice_id": "pNInz6obpgDQGcFmaJgB", "voice_name": "Adam"},
    ],
}

# Valid voice IDs per provider (for quick validation)
VALID_VOICE_IDS = {
    provider: {v["voice_id"] for v in voices}
    for provider, voices in DEFAULT_VOICES.items()
}


def get_provider_from_model(tts_model: str) -> str:
    """Detect TTS provider from model ID."""
    if not tts_model:
        return "elevenlabs"  # Default

    model_lower = tts_model.lower()
    if model_lower.startswith("tts-"):
        return "openai"
    elif "eleven" in model_lower:
        return "elevenlabs"

    return "elevenlabs"  # Default fallback


def is_valid_voice_for_provider(voice_id: str, provider: str) -> bool:
    """Check if a voice ID is valid for a given provider."""
    if not voice_id or not provider:
        return False

    valid_ids = VALID_VOICE_IDS.get(provider.lower(), set())

    # For OpenAI, do exact match (case-insensitive)
    if provider.lower() == "openai":
        return voice_id.lower() in {v.lower() for v in valid_ids}

    # For ElevenLabs, check if it looks like an ElevenLabs ID (alphanumeric, ~20 chars)
    # We can't validate all possible ElevenLabs voices, so we check format
    if provider.lower() == "elevenlabs":
        # ElevenLabs voice IDs are alphanumeric, typically 20 chars
        if len(voice_id) >= 15 and voice_id.isalnum():
            return True
        # Also check against known defaults
        return voice_id in valid_ids

    return False


def get_default_voice(provider: str, index: int = 0) -> dict:
    """Get a default voice for a provider.

    Args:
        provider: TTS provider ID ('openai' or 'elevenlabs')
        index: Index to cycle through available voices for variety

    Returns:
        Dict with 'voice_id' and 'voice_name'
    """
    voices = DEFAULT_VOICES.get(provider.lower(), DEFAULT_VOICES["elevenlabs"])
    return voices[index % len(voices)]


def get_default_voices(provider: str, count: int) -> List[dict]:
    """Get multiple default voices for a provider.

    Args:
        provider: TTS provider ID
        count: Number of voices needed

    Returns:
        List of dicts with 'voice_id' and 'voice_name'
    """
    voices = DEFAULT_VOICES.get(provider.lower(), DEFAULT_VOICES["elevenlabs"])
    return [voices[i % len(voices)] for i in range(count)]


def validate_and_fix_agent_voice(
    agent_data: dict,
    provider: str,
    index: int = 0
) -> dict:
    """Validate an agent's voice and fix if invalid.

    Args:
        agent_data: Agent configuration dict
        provider: TTS provider to validate against
        index: Index for selecting default voice

    Returns:
        Agent data with valid voice
    """
    voice_id = agent_data.get("voice_id", "")

    if not voice_id or not is_valid_voice_for_provider(voice_id, provider):
        default_voice = get_default_voice(provider, index)
        logger.warning(
            f"Invalid voice '{voice_id}' for provider '{provider}', "
            f"using default '{default_voice['voice_name']}'"
        )
        agent_data["voice_id"] = default_voice["voice_id"]
        agent_data["voice_name"] = default_voice["voice_name"]

    return agent_data
