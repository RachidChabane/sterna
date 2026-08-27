"""Per-request context every tool implementation reads from.

Installer. The tool functions are plain callables invoked by the agent
loop's bound-callable invoker; they cannot be handed the request, so the
turn publishes it into a set of ContextVars (and one FileToolsContext)
before the loop starts and tears it down in `finally`.

`install` deliberately mutates the session: it stores the file-tools
context for cancellation. Everything it does is request-scoped setup,
none of it yields.
"""

import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from ..agent_tool_handlers import (
    FileToolsContext,
    clear_file_tools_context,
    set_file_tools_context,
)
from ..brave_search_tools import BRAVE_SEARCH_USER_CONTEXT
from ..google_maps_tools import GOOGLE_MAPS_USER_CONTEXT
from ..image_tools import set_image_tool_context
from ..knowledge_base_tools import KNOWLEDGE_BASE_USER_CONTEXT
from ..spark_tools import set_spark_tool_context
from ..video_tools import set_video_tool_context

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# @mention parameter key -> image tool context override key.
IMAGE_PARAM_OVERRIDES = {
    'model': 'override_model',
    'ratio': 'override_aspect_ratio',
    'res': 'override_resolution',
}
# @mention parameter key -> video tool context override key.
VIDEO_PARAM_OVERRIDES = {
    'model': 'override_model',
    'ratio': 'override_aspect_ratio',
    'dur': 'override_duration',
    'quality': 'override_quality',
}


def _authorization_header(auth_token: Optional[str]) -> Optional[str]:
    return f"Bearer {auth_token}" if auth_token else None


def _apply_media_overrides(context: dict, media_tool_params, overrides: Dict[str, str]) -> None:
    if not media_tool_params:
        return
    for mention_key, context_key in overrides.items():
        if mention_key in media_tool_params:
            context[context_key] = media_tool_params[mention_key]


async def _install_file_tools_context(
    agent,
    *,
    user_id: str,
    conversation_id: str,
    chat_id: str,
    auth_token: str,
    model_metadata: Optional[Dict[str, Any]],
    uploaded_files: Optional[List[Dict[str, str]]],
) -> str:
    def metadata(key):
        return model_metadata.get(key) if model_metadata else None

    # Always pass agent.model as fallback so Sterna-resolved models
    # reach the coding agent even when catalog lookup fails.
    context = FileToolsContext(
        user_id=user_id,
        conversation_id=conversation_id,
        chat_id=chat_id,
        auth_token=auth_token,
        model_name=metadata("model_name") or agent.model_name,
        model_id=metadata("model_id") or agent.model,
        provider=metadata("provider"),
        model_icon_slug=metadata("model_icon_slug"),
        model_icon_url=metadata("model_icon_url"),
        provider_icon_slug=metadata("provider_icon_slug"),
        provider_icon_url=metadata("provider_icon_url"),
        message_id=metadata("message_id"),
        is_cancelled_callback=lambda: agent.is_cancelled,
        uploaded_files=uploaded_files,  # for execute_code
        # Coding Agent always runs against OpenRouter — never hand
        # it a provider-scoped BYOK key.
        api_key=await agent._openrouter_key_for_tools(),
        spark_ignite_request=agent.spark_ignite_request,
    )
    execution_id = set_file_tools_context(context)
    logger.info(f"[LangChain] Set file tools context with execution ID: {execution_id[:8]}...")
    # Store context reference for request cancellation
    agent.file_tools_context = context
    return execution_id


async def install(
    agent,
    *,
    user_id: str,
    conversation_id: str,
    chat_id: str,
    auth_token: str,
    model_metadata: Optional[Dict[str, Any]] = None,
    uploaded_files: Optional[List[Dict[str, str]]] = None,
) -> Optional[str]:
    """Publish the request into every tool-visible context.

    Returns the file-tools execution id (None when file tools are off) —
    the caller must pass it to `clear` in a `finally` block.
    """
    execution_id = None
    if agent.enable_file_tools and agent.tools:
        execution_id = await _install_file_tools_context(
            agent,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            auth_token=auth_token,
            model_metadata=model_metadata,
            uploaded_files=uploaded_files,
        )

    # The brave-search service handles quota checking/deduction when
    # X-User-ID is provided.
    if agent.enable_brave_search:
        BRAVE_SEARCH_USER_CONTEXT.set({
            "user_id": user_id,
            "authorization": _authorization_header(auth_token) or "",
        })
        logger.debug("[LangChain] Set Brave Search user context for quota tracking")

    if agent.enable_google_maps:
        GOOGLE_MAPS_USER_CONTEXT.set({
            "user_id": user_id,
            "authorization": _authorization_header(auth_token) or "",
        })
        logger.debug("[LangChain] Set Google Maps user context for quota tracking")

    if agent.enable_image_generation:
        image_context = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "user": None,  # Will be looked up from user_id in the tool
        }
        _apply_media_overrides(image_context, agent.media_tool_params, IMAGE_PARAM_OVERRIDES)
        set_image_tool_context(image_context)
        logger.debug("[LangChain] Set image tool context for storage/billing")

    if agent.enable_video_generation:
        video_context = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
        }
        _apply_media_overrides(video_context, agent.media_tool_params, VIDEO_PARAM_OVERRIDES)
        set_video_tool_context(video_context)
        logger.debug("[LangChain] Set video tool context for storage/billing")

    if agent.enable_sparks:
        set_spark_tool_context({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "auth_token": auth_token,
        })
        logger.debug("[LangChain] Set spark tool context for storage")

    # Knowledge base tools need the user object.
    try:
        from authentication.models import User
        user_obj = await sync_to_async(User.objects.get)(id=user_id)
        KNOWLEDGE_BASE_USER_CONTEXT.set({
            "user": user_obj,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
        })
        logger.debug("[LangChain] Set user context for KB tools")
    except Exception as e:
        logger.warning(f"[LangChain] Failed to set user context: {e}")

    return execution_id


def clear(agent, execution_id: Optional[str]) -> None:
    """Tear down everything `install` published."""
    if execution_id:
        clear_file_tools_context(execution_id)
        logger.info(f"[LangChain] Cleared file tools context for execution {execution_id[:8]}...")

    if agent.enable_brave_search:
        BRAVE_SEARCH_USER_CONTEXT.set(None)

    if agent.enable_google_maps:
        GOOGLE_MAPS_USER_CONTEXT.set(None)
