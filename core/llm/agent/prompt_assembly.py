"""System-prompt assembly for one chat turn.

Builder. Tries the V2 optimized prompt builder, falls back to the V1
`build_system_prompt` on any failure or when V2 is switched off, then
appends the media-generation hints that an `@mention` may have carried.
"""

import logging
from typing import Dict, Optional

from ..constants import ENABLE_OPTIMIZED_PROMPTS
from ..prompt_builder import build_system_prompt
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


def _build_v1_prompt(custom_prompt, flags: AgentFeatureFlags, model_name) -> str:
    return build_system_prompt(
        custom_prompt=custom_prompt,
        enable_brave_search=flags.brave_search,
        enable_google_maps=flags.google_maps,
        enable_reasoning=flags.reasoning,
        enable_file_tools=flags.file_tools,
        enable_image_generation=flags.image_generation,
        enable_video_generation=flags.video_generation,
        enable_sparks=flags.sparks,
        has_mcp_tools=False,
        mcp_tools=None,
        model_name=model_name,
    )


def _build_v2_prompt(
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
    logger.info(f"[LangChain] V2 Optimized prompt: ~{metadata['estimated_tokens']} tokens")
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
    """The full system prompt for this agent instance.

    Always uses V2 optimized prompts when enabled — `discovery_context`
    is optional there — and degrades to V1 on any V2 failure.
    """
    if ENABLE_OPTIMIZED_PROMPTS:
        try:
            system_prompt = _build_v2_prompt(
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
        except Exception as e:
            logger.warning(f"[LangChain] V2 prompt builder failed: {e}, falling back to V1")
            system_prompt = _build_v1_prompt(custom_prompt, flags, model_name)
    else:
        # V1 legacy prompt building
        system_prompt = _build_v1_prompt(custom_prompt, flags, model_name)

    # Append media generation parameter hints if user pre-selected via @mention
    if media_tool_params and forced_tool_name in MEDIA_TOOL_NAMES:
        hint = _media_param_hint(media_tool_params)
        if hint:
            system_prompt = (system_prompt or "") + hint

    return system_prompt
