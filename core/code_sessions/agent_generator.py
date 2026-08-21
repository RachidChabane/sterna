"""Sub-Agent AI Generator.

Uses LLM to generate complete sub-agent configurations from natural language
descriptions. Mirrors the pattern from voice_rooms/room_generator.py.
"""

import json
import logging
import re

import httpx

from llm.generation_models import get_generation_assistant_model, log_generation_usage

logger = logging.getLogger(__name__)

VALID_TOOLS = [
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebSearch", "WebFetch", "Task", "NotebookEdit",
]

VALID_MODEL_TIERS = {"fast", "balanced", "powerful", "inherit"}
VALID_PERMISSION_MODES = {"default", "plan", "autoEdit", "fullAuto"}
NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


async def generate_agent_from_description(description: str, user=None) -> dict:
    """Generate a sub-agent configuration from a natural language description.

    Args:
        description: User's description of the agent they want.
        user: User object for API key resolution.

    Returns:
        Dict matching SubAgentCreateData shape.
    """
    from llm.services.api_key_resolver import get_api_key_with_fallback

    prompt = f"""You are helping create a sub-agent configuration for a coding assistant platform.
A sub-agent is a specialized AI assistant that can be dispatched by the main chat to handle specific tasks.

User's request: "{description}"

Generate a configuration for this sub-agent.

RULES:
1. The "name" must be a short slug: start with a letter, only letters, digits, hyphens, underscores (e.g. "security-reviewer")
2. The "description" should be 1-2 sentences explaining what the agent does
3. Choose a "model_tier" from: "fast" (cheap quick tasks), "balanced" (most coding tasks), "powerful" (complex analysis), "inherit" (use chat's model)
4. The "system_prompt" should be detailed instructions (3-10 sentences) telling the agent:
   - What its role is
   - What it should focus on
   - How it should format its output
   - Any domain-specific guidelines
5. Select "tools" (allowed) and "disallowed_tools" from this list: {json.dumps(VALID_TOOLS)}
   - Only include tools the agent actually needs
   - Disallow tools that would be dangerous for this agent's purpose
   - Tools not in either list remain at their default setting
6. Set "max_turns" between 3 and 50 (how many back-and-forth iterations the agent gets)
7. Choose "permission_mode" from: "default" (ask before writes), "plan" (read-only exploration), "autoEdit" (auto-approve edits), "fullAuto" (no confirmations)

Return ONLY valid JSON:
{{
  "name": "slug-name",
  "description": "What this agent does",
  "model_tier": "balanced",
  "system_prompt": "Detailed instructions...",
  "tools": ["Read", "Grep"],
  "disallowed_tools": [],
  "max_turns": 10,
  "permission_mode": "default"
}}"""

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
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.4,
                },
            )

            if response.status_code != 200:
                logger.error("OpenRouter API error: %s - %s", response.status_code, response.text)
                raise Exception(f"OpenRouter API error: {response.status_code}")

            data = response.json()
            log_generation_usage(data, get_generation_assistant_model(), user=user, request_source="agent_generation")
            content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON (handle markdown code blocks)
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)
        return _validate_config(parsed)

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM response as JSON: %s", e)
        return _create_fallback_config(description)
    except Exception as e:
        logger.error("Agent generation failed: %s", e)
        raise


def _validate_config(raw: dict) -> dict:
    """Validate and sanitise the LLM-generated config."""
    name = str(raw.get("name", "custom-agent"))
    if not NAME_RE.match(name):
        name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-") or "custom-agent"
        if not name[0].isalpha():
            name = "agent-" + name

    model_tier = raw.get("model_tier", "balanced")
    if model_tier not in VALID_MODEL_TIERS:
        model_tier = "balanced"

    tools = [t for t in raw.get("tools", []) if t in VALID_TOOLS]
    disallowed = [t for t in raw.get("disallowed_tools", []) if t in VALID_TOOLS]

    max_turns = raw.get("max_turns", 10)
    if not isinstance(max_turns, int) or max_turns < 1:
        max_turns = 10
    max_turns = min(max(max_turns, 1), 100)

    permission_mode = raw.get("permission_mode", "default")
    if permission_mode not in VALID_PERMISSION_MODES:
        permission_mode = "default"

    return {
        "name": name[:60],
        "description": str(raw.get("description", ""))[:500],
        "model_tier": model_tier,
        "system_prompt": str(raw.get("system_prompt", ""))[:50000],
        "tools": tools,
        "disallowed_tools": disallowed,
        "max_turns": max_turns,
        "permission_mode": permission_mode,
    }


def _create_fallback_config(description: str) -> dict:
    """Create a basic fallback config when LLM generation fails."""
    # Derive a name slug from the description
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", description[:40]).strip("-").lower()
    if not slug or not slug[0].isalpha():
        slug = "custom-agent"

    return {
        "name": slug,
        "description": description[:500],
        "model_tier": "balanced",
        "system_prompt": f"You are a specialized assistant. Your task: {description}",
        "tools": ["Read", "Glob", "Grep"],
        "disallowed_tools": [],
        "max_turns": 10,
        "permission_mode": "default",
    }
