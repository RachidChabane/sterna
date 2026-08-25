"""System-prompt assembly for one chat turn.

Two steps, and the endpoint uses both. `build_effective_system_prompt`
folds what the user configured -- the global instructions, the chat's
own, the chat's custom prompt, and the priority an `@mention` implies
-- into the one custom prompt a turn is created with.
`build_agent_system_prompt` then builds the full prompt from the
layered prompts_v2 builder around it and appends the
media-generation hints an `@mention` may have carried.
"""

import logging
from typing import Any, Dict, List, Mapping, Optional

from .feature_flags import AgentFeatureFlags, FEATURE_VOICE_MODE

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Tools whose generation parameters the user can pre-select via @mention.
MEDIA_TOOL_NAMES = frozenset({
    'generate_image',
    'generate_video',
    'animate_image',
    'upscale_video',
    'animate_character',
})

# @mention parameter key -> the tool-argument name the model should use.
_MEDIA_PARAM_HINT_LABELS = (
    ('model', 'model'),
    ('ratio', 'aspect_ratio'),
    ('res', 'resolution'),
    ('dur', 'duration'),
    ('quality', 'quality'),
)

VOICE_MODE_PROMPT_MARKER = "[VOICE CONVERSATION MODE]"

CONTENT_FIELD = "content"
ENABLED_FIELD = "enabled"
MODE_FIELD = "mode"
OVERRIDE_MODE = "override"

SECTION_SEPARATOR = "\n\n"


def build_effective_system_prompt(
    *,
    system_prompt: Optional[str],
    global_instructions: Mapping[str, Any],
    chat_instructions: Mapping[str, Any],
    mention_priority_prompt: Optional[str],
) -> Optional[str]:
    """The custom prompt a turn is created with, from what the user configured.

    The user's instructions lead, wrapped against prompt injection; the
    chat's own custom prompt follows; the priority an `@mention` implies
    closes. A chat whose instructions are in override mode replaces the
    global ones rather than adding to them.
    """

    instructions = _user_instructions(global_instructions, chat_instructions)
    effective = system_prompt
    if instructions:
        from conversations.prompt_protection import wrap_instructions_safely

        wrapped = wrap_instructions_safely(SECTION_SEPARATOR.join(instructions))
        effective = f"{wrapped}{SECTION_SEPARATOR}{effective}" if effective else wrapped

    if mention_priority_prompt:
        effective = (
            f"{effective}{SECTION_SEPARATOR}{mention_priority_prompt}"
            if effective
            else mention_priority_prompt
        )
        logger.info("[LangChain] Added mention priority prompt to system prompt")
    return effective


def _user_instructions(
    global_instructions: Mapping[str, Any], chat_instructions: Mapping[str, Any]
) -> List[str]:
    chat_content = chat_instructions.get(CONTENT_FIELD)
    if chat_content and chat_instructions.get(MODE_FIELD) == OVERRIDE_MODE:
        logger.info(f"[LangChain] Using chat instructions (override mode, {len(chat_content)} chars)")
        return [chat_content]

    parts: List[str] = []
    global_content = global_instructions.get(CONTENT_FIELD)
    if global_instructions.get(ENABLED_FIELD) and global_content:
        parts.append(global_content)
        logger.info(f"[LangChain] Added global instructions ({len(global_content)} chars)")
    if chat_content:
        parts.append(chat_content)
        logger.info(f"[LangChain] Added chat instructions (append mode, {len(chat_content)} chars)")
    return parts


def _build_prompt(
    custom_prompt,
    flags: AgentFeatureFlags,
    discovery_context,
    model_name,
    user_first_name,
    user_last_name,
    user_email,
    spark_fix_request,
    spark_ignite_request,
) -> str:
    # Lazy import to avoid circular imports
    from ..prompts_v2 import get_prompt_builder

    prompt_builder = get_prompt_builder()
    enabled_features = flags.prompt_feature_names()

    logger.info(f"[LangChain] Building prompt with enabled_features: {enabled_features}")
    if FEATURE_VOICE_MODE in enabled_features:
        logger.info("[LangChain] 🎤 VOICE MODE IS ENABLED - conversational prompts will be used")

    system_prompt, metadata = prompt_builder.build_full_prompt(
        custom_prompt=custom_prompt,
        enabled_features=enabled_features,
        discovery_context=discovery_context,  # Can be None
        discovered_tools=[],
        model_name=model_name,
        user_first_name=user_first_name,
        user_last_name=user_last_name,
        user_email=user_email,
        spark_fix_request=spark_fix_request,
        spark_ignite_request=spark_ignite_request,
    )
    logger.info(f"[LangChain] Optimized prompt: ~{metadata['estimated_tokens']} tokens")
    if FEATURE_VOICE_MODE in enabled_features:
        # Log if voice mode prompt is actually in the system prompt
        if VOICE_MODE_PROMPT_MARKER in system_prompt:
            logger.info("[LangChain] ✅ Voice mode system prompt confirmed in final prompt")
        else:
            logger.warning("[LangChain] ⚠️ Voice mode was enabled but NOT found in final system prompt!")
    return system_prompt


def _media_param_hint(media_tool_params: Dict[str, str]) -> Optional[str]:
    """Prompt suffix restating the media parameters the user pre-selected."""
    param_parts = [
        f"{argument_name}={media_tool_params[mention_key]}"
        for mention_key, argument_name in _MEDIA_PARAM_HINT_LABELS
        if mention_key in media_tool_params
    ]
    if not param_parts:
        return None
    logger.info(f"[LangChain] Added media param hint to system prompt: {param_parts}")
    return (
        "\n\n## Media Generation Parameters\n"
        f"The user pre-selected the following parameters: {', '.join(param_parts)}. "
        "Use these exact values when calling the tool."
    )


def build_agent_system_prompt(
    *,
    custom_prompt: Optional[str],
    flags: AgentFeatureFlags,
    discovery_context,
    model_name: Optional[str],
    user_first_name: Optional[str],
    user_last_name: Optional[str],
    user_email: Optional[str],
    spark_fix_request: Optional[Dict[str, str]],
    spark_ignite_request: Optional[Dict[str, str]],
    forced_tool_name: Optional[str],
    media_tool_params: Optional[Dict[str, str]],
) -> str:
    """The full system prompt for this agent instance."""
    system_prompt = _build_prompt(
        custom_prompt,
        flags,
        discovery_context,
        model_name,
        user_first_name,
        user_last_name,
        user_email,
        spark_fix_request,
        spark_ignite_request,
    )

    # Append media generation parameter hints if user pre-selected via @mention
    if media_tool_params and forced_tool_name in MEDIA_TOOL_NAMES:
        hint = _media_param_hint(media_tool_params)
        if hint:
            system_prompt = (system_prompt or "") + hint

    return system_prompt
