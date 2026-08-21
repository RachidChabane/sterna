"""Voice Room AI Generator.

Uses LLM to generate complete voice room configurations from natural language descriptions.
Following the pattern from mcp/config_helper.py for AI-powered configuration extraction.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from llm.generation_models import get_generation_assistant_model, log_generation_usage
from .constants import (
    VOICE_ROOM_MODELS,
    AGENT_COLORS,
    VOICE_PERSONALITIES,
    DEFAULT_AGENT_VOICE_SETTINGS,
)

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAgent:
    """A generated agent configuration."""
    display_name: str
    model_id: str
    system_prompt: str
    voice_id: str
    voice_name: str
    order: int
    color: str = "#38bdf8"  # Default sky-400
    voice_settings: dict = field(default_factory=lambda: dict(DEFAULT_AGENT_VOICE_SETTINGS))


@dataclass
class GeneratedRoom:
    """A generated voice room configuration."""
    name: str
    description: str
    agents: list[GeneratedAgent]
    language: str = "auto"


def _get_voice_options_text(voices: list[dict] | None = None) -> str:
    """Get formatted text of available voices for the prompt.

    Args:
        voices: List of voice dicts with voice_id, name, and optionally description/labels.
                If None, uses hardcoded VOICE_PERSONALITIES as fallback.
    """
    if voices:
        lines = []
        for v in voices:
            voice_id = v.get("voice_id", "")
            name = v.get("name", "Unknown")
            # Build personality hint from description and labels
            desc = v.get("description", "")
            labels = v.get("labels", {})
            if isinstance(labels, dict):
                label_parts = [f"{k}: {v}" for k, v in labels.items() if v]
                personality = ", ".join(filter(None, [desc] + label_parts)) or "versatile voice"
            else:
                personality = desc or "versatile voice"
            lines.append(f'  - voice_id: "{voice_id}", name: "{name}", personality: {personality}')
        return "\n".join(lines)
    else:
        # Fallback to hardcoded voices
        lines = []
        for voice_id, info in VOICE_PERSONALITIES.items():
            lines.append(f'  - voice_id: "{voice_id}", name: "{info["name"]}", personality: {info["personality"]}')
        return "\n".join(lines)


def _get_model_options_text(models: list[str]) -> str:
    """Get formatted text of available models for the prompt."""
    return "\n".join([f'  - "{m}"' for m in models])


async def generate_room_from_description(
    description: str,
    available_voices: list[dict] | None = None,
    user=None,
) -> GeneratedRoom:
    """Generate a complete voice room configuration from a natural language description.

    Args:
        description: User's description of the room they want (e.g.,
                     "A debate room with two opposing viewpoints on AI safety")
        available_voices: List of voice dicts from the TTS provider. Each dict should have
                         voice_id, name, and optionally description/labels.
                         If None, uses hardcoded ElevenLabs voices as fallback.
        user: User object for API key resolution

    Returns:
        GeneratedRoom with all configuration ready for creation
    """
    from llm.services.api_key_resolver import get_api_key_with_fallback

    voice_options = _get_voice_options_text(available_voices)
    model_options = _get_model_options_text(VOICE_ROOM_MODELS)

    # Build set of valid voice IDs for validation
    if available_voices:
        valid_voice_ids = {v.get("voice_id") for v in available_voices}
        voice_list = available_voices
    else:
        valid_voice_ids = set(VOICE_PERSONALITIES.keys())
        voice_list = [{"voice_id": k, "name": v["name"]} for k, v in VOICE_PERSONALITIES.items()]

    prompt = f"""You are helping create a voice room configuration for an AI conversation platform.
A voice room has multiple AI agents that can discuss topics with the user.

User's request: "{description}"

Based on this description, generate a voice room configuration.

LANGUAGE DETECTION:
- Detect the language of the user's request above
- ALL content you generate (room name, description, agent names, system prompts) MUST be written in the SAME language as the user's request
- Set the "language" field to the detected ISO 639-1 language code (e.g., "en", "fr", "es", "de", "ja", "zh", "ar", etc.)

RULES:
1. Create 2-4 agents with distinct personalities that fit the room's theme
2. Each agent should have a unique perspective or role
3. Match voice personalities to agent characters (e.g., authoritative roles get deeper voices)
4. Use varied models - mix different providers for diversity
5. System prompts should be concise (2-3 sentences) defining the agent's personality and role
6. System prompts should include how the agent should interact with other agents and the user
7. Room name should be short and catchy (2-5 words)
8. Each agent gets a different color from this list: {json.dumps(AGENT_COLORS)}

AVAILABLE VOICES:
{voice_options}

AVAILABLE MODELS:
{model_options}

Return ONLY valid JSON with this structure:
{{
  "name": "Room Name (in detected language)",
  "description": "Brief description of the room's purpose (in detected language)",
  "language": "detected-language-code",
  "agents": [
    {{
      "display_name": "Agent Name (in detected language)",
      "model_id": "provider/model-name",
      "system_prompt": "System prompt in detected language. Define persona, behavior, and interaction style.",
      "voice_id": "voice-id-from-list",
      "voice_name": "Voice Name",
      "order": 1,
      "color": "#hexcolor"
    }}
  ]
}}

IMPORTANT:
- voice_id MUST be exactly one from the AVAILABLE VOICES list above
- model_id MUST be exactly one from the AVAILABLE MODELS list above
- Generate agents that will create interesting, dynamic conversations
- Avoid generic personalities - make each agent memorable and distinct
- Write ALL text content in the detected language (except voice_id, model_id, and color which are technical identifiers)"""

    try:
        api_key = get_api_key_with_fallback(user=user)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": get_generation_assistant_model(),
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7,  # Higher temperature for creativity
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                raise Exception(f"OpenRouter API error: {response.status_code}")

            data = response.json()
            model_used = get_generation_assistant_model()
            log_generation_usage(data, model_used, user=user, request_source="voice_room_generation")
            content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON (handle markdown code blocks)
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        # Build agents
        agents = []
        for i, agent_data in enumerate(parsed.get("agents", [])):
            # Validate voice_id - fall back to default if invalid
            voice_id = agent_data.get("voice_id", "")
            voice_name = agent_data.get("voice_name", "")
            if voice_id not in valid_voice_ids:
                # Use a voice from the list
                fallback_voice = voice_list[i % len(voice_list)]
                voice_id = fallback_voice.get("voice_id", "")
                voice_name = fallback_voice.get("name", "Unknown")
                logger.warning(f"Invalid voice_id, using fallback: {voice_name}")

            # Validate model_id against allowed models
            model_id = agent_data.get("model_id", "")
            if model_id not in VOICE_ROOM_MODELS:
                model_id = VOICE_ROOM_MODELS[i % len(VOICE_ROOM_MODELS)]
                logger.warning(f"Invalid model_id, using default: {model_id}")

            # Validate color
            color = agent_data.get("color", AGENT_COLORS[i % len(AGENT_COLORS)])
            if not color.startswith("#"):
                color = AGENT_COLORS[i % len(AGENT_COLORS)]

            # Get voice name from the voice list if not provided
            if not voice_name:
                matching_voice = next((v for v in voice_list if v.get("voice_id") == voice_id), None)
                voice_name = matching_voice.get("name", "Unknown") if matching_voice else "Unknown"

            agents.append(GeneratedAgent(
                display_name=agent_data.get("display_name", f"Agent {i + 1}"),
                model_id=model_id,
                system_prompt=agent_data.get("system_prompt", "You are a helpful AI assistant."),
                voice_id=voice_id,
                voice_name=voice_name,
                order=agent_data.get("order", i + 1),
                color=color,
            ))

        return GeneratedRoom(
            name=parsed.get("name", "Generated Room"),
            description=parsed.get("description", description),
            agents=agents,
            language=parsed.get("language", "auto"),
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        # Return a basic default room
        return _create_fallback_room(description)
    except Exception as e:
        logger.error(f"Room generation failed: {e}")
        raise


def _create_fallback_room(description: str) -> GeneratedRoom:
    """Create a basic fallback room when LLM fails."""
    default_voices = list(VOICE_PERSONALITIES.items())

    return GeneratedRoom(
        name="Discussion Room",
        description=description,
        agents=[
            GeneratedAgent(
                display_name="Assistant",
                model_id=VOICE_ROOM_MODELS[0],
                system_prompt="You are a helpful and knowledgeable assistant. Engage thoughtfully with the user and other agents.",
                voice_id=default_voices[0][0],
                voice_name=default_voices[0][1]["name"],
                order=1,
                color=AGENT_COLORS[0],
            ),
            GeneratedAgent(
                display_name="Analyst",
                model_id=VOICE_ROOM_MODELS[1],
                system_prompt="You are an analytical thinker who examines topics from multiple angles. Provide balanced perspectives.",
                voice_id=default_voices[3][0],
                voice_name=default_voices[3][1]["name"],
                order=2,
                color=AGENT_COLORS[1],
            ),
        ],
    )


def generated_room_to_dict(room: GeneratedRoom) -> dict:
    """Convert GeneratedRoom to a dict suitable for the API response."""
    return {
        "name": room.name,
        "description": room.description,
        "language": room.language,
        "agents": [
            {
                "display_name": agent.display_name,
                "model_id": agent.model_id,
                "system_prompt": agent.system_prompt,
                "voice_id": agent.voice_id,
                "voice_name": agent.voice_name,
                "order": agent.order,
                "color": agent.color,
                "voice_settings": agent.voice_settings,
            }
            for agent in room.agents
        ],
    }
