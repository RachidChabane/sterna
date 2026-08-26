"""The streaming HTTP response a V2 chat request served by the agent core gets.

The endpoint parses the request, resolves the model, the key and the
system prompt, and then needs one thing: a response that streams the
turn. This module is that step. It puts the routing decision on the
wire ahead of the answer, runs the turn, and owns what happens when
the client goes away mid-stream -- cancelling the turn, closing the
sandbox connection, and settling the generations the turn already
spent so an abandoned stream is still billed.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict, List, Optional, Sequence

from django.http import StreamingHttpResponse

from ..agent.feature_flags import AgentFeatureFlags
from ..agent.key_resolution import EndpointKeyResolver
from ..agent.prompt_assembly import build_agent_system_prompt
from ..agent_core import sse
from ..provider_registry import OPENROUTER_BASE_URL, is_openrouter_url, native_model_name
from .dependencies import TurnRequest
from .provider_extra import reasoning_extra
from .stream import V2TurnRunner

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

SUMMARIZER_MODEL = "openai/gpt-4o-mini"
"""The model the context summarizer runs on, whatever the chat runs on."""

STREAM_CONTENT_TYPE = "text/event-stream"
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

ROUTE_EVENT_NAME = "sterna_route"

REASONING_FIELD = "reasoning"
MODALITIES_FIELD = "modalities"
IMAGE_MODALITY = "image"


class SmartRouterReroute:
    """Answers a rate-limited model with the router's next choice."""

    def __init__(self, *, user, messages: Sequence[Any]) -> None:
        self._user = user
        self._messages = list(messages)

    async def alternative(
        self, failed: TurnRequest, excluded: Sequence[str]
    ) -> Optional[TurnRequest]:
        from asgiref.sync import sync_to_async

        from llm.services.api_key_resolver import resolve_endpoint
        from llm.smart_router.router import SmartRouter

        alternative = await sync_to_async(SmartRouter().reroute_on_rate_limit)(
            failed_model=failed.model,
            messages=self._messages,
            conversation_id=failed.conversation_id,
            user=self._user,
            excluded_models=list(excluded),
        )
        if not alternative:
            return None
        try:
            api_key, base_url, _origin, slug = await sync_to_async(resolve_endpoint)(
                user=self._user, model_id=alternative
            )
        except ValueError:
            api_key, base_url, slug = failed.api_key, failed.base_url, None
        return _rebound(failed, model=alternative, api_key=api_key, base_url=base_url, slug=slug)


def agent_core_streaming_response(
    *,
    request,
    model: str,
    messages: Sequence[Dict[str, Any]],
    conversation_id: str,
    chat_id: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
    system_prompt: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    provider_slug: Optional[str],
    flags: AgentFeatureFlags,
    auth_token: str,
    model_display_name: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
    uploaded_files: Optional[List[Dict[str, str]]] = None,
    sterna_resolution: Optional[Any] = None,
    media_tool_params: Optional[Dict[str, Any]] = None,
    spark_fix_request: Optional[Dict[str, Any]] = None,
    spark_ignite_request: Optional[Dict[str, Any]] = None,
    forced_tool_name: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    reasoning_max_tokens: Optional[int] = None,
    output_modalities: Optional[Sequence[str]] = None,
) -> StreamingHttpResponse:
    """Stream this request's turn through the agent core."""

    user_id = str(request.user.id)
    resolved_base_url = base_url or OPENROUTER_BASE_URL
    is_openrouter = is_openrouter_url(resolved_base_url)
    keys = EndpointKeyResolver(
        resolve_user_id=lambda: user_id,
        api_key=api_key or "",
        base_url=resolved_base_url,
        is_openrouter=is_openrouter,
        provider_slug=provider_slug,
    )

    turn = TurnRequest(
        user_id=user_id,
        conversation_id=conversation_id,
        chat_id=chat_id,
        model=model,
        request_model=(native_model_name(model) or model) if provider_slug else model,
        api_key=api_key or "",
        base_url=resolved_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        flags=flags,
        extra=_provider_extra(
            is_openrouter=is_openrouter,
            model=model,
            enable_reasoning=flags.reasoning,
            reasoning_effort=reasoning_effort,
            reasoning_max_tokens=reasoning_max_tokens,
            output_modalities=output_modalities,
        ),
    )
    runner = V2TurnRunner(
        turn=turn,
        messages=messages,
        system_prompt=build_agent_system_prompt(
            custom_prompt=system_prompt,
            flags=flags,
            discovery_context=None,
            model_name=model_display_name,
            user_first_name=getattr(request.user, "first_name", None),
            user_last_name=getattr(request.user, "last_name", None),
            user_email=getattr(request.user, "email", None),
            spark_fix_request=spark_fix_request,
            spark_ignite_request=spark_ignite_request,
            forced_tool_name=forced_tool_name,
            media_tool_params=media_tool_params,
        ),
        auth_token=auth_token,
        openrouter_key_for_tools=keys.openrouter_key_for_tools,
        summarizer_endpoint=lambda: keys.summarizer_endpoint(SUMMARIZER_MODEL),
        model_display_name=model_display_name,
        model_metadata=model_metadata,
        uploaded_files=uploaded_files,
        is_openrouter=is_openrouter,
        reroute=SmartRouterReroute(user=request.user, messages=messages),
        media_tool_params=media_tool_params,
        spark_ignite_request=spark_ignite_request,
    )

    return StreamingHttpResponse(
        _streamed(runner, request=request, chat_id=chat_id, route=sterna_resolution),
        content_type=STREAM_CONTENT_TYPE,
        headers=dict(STREAM_HEADERS),
    )


async def _streamed(runner: V2TurnRunner, *, request, chat_id, route):
    """The turn's frames, with the routing announcement and the teardown."""

    session = runner.session
    try:
        if route is not None:
            yield sse.render_frame(ROUTE_EVENT_NAME, _route_payload(route))
        async for frame in runner.frames():
            yield frame
    except GeneratorExit:
        logger.warning("agent_service.client_disconnected")
        session.cancel()
        _settle_abandoned(session, user_id=str(request.user.id), chat_id=chat_id)
    finally:
        await _close_sandbox(session)


def _route_payload(route) -> Dict[str, Any]:
    return {
        "resolved_model": route.resolved_model_id,
        "resolved_model_name": route.resolved_model_name,
        "score": route.final_score,
        "tier": route.tier,
        "reason": route.reason,
        "cost_tier": route.cost_tier,
    }


def _settle_abandoned(session, *, user_id: str, chat_id: Optional[str]) -> None:
    """Bill what an abandoned stream already spent.

    Skipped once the turn's aggregate row has been written, and for a
    turn that never went through OpenRouter: its generation ids are the
    provider's own and cannot be settled against OpenRouter's records.
    """

    if session.final_usage_recorded or not session.is_openrouter:
        return
    try:
        from llm.tasks import enqueue_abort_settlement

        enqueue_abort_settlement(
            user_id=user_id,
            generation_ids=list(session.all_generation_ids),
            model_id=session.model,
            chat_id=chat_id or "",
        )
    except Exception:
        logger.error("billing.abort_settlement_hook_failed", exc_info=True)


async def _close_sandbox(session) -> None:
    if not session.file_tools_context:
        return
    try:
        await session.file_tools_context.close()
    except Exception:
        logger.warning("agent_service.file_tools_close_failed", exc_info=True)


def _rebound(
    turn: TurnRequest,
    *,
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
    slug: Optional[str],
) -> TurnRequest:
    """`turn` as it would have been made for `model`."""

    resolved = base_url or OPENROUTER_BASE_URL
    return dataclasses.replace(
        turn,
        model=model,
        request_model=(native_model_name(model) or model) if slug else model,
        api_key=api_key or turn.api_key,
        base_url=resolved,
    )


def _provider_extra(
    *,
    is_openrouter: bool,
    model: str,
    enable_reasoning: bool,
    reasoning_effort: Optional[str],
    reasoning_max_tokens: Optional[int],
    output_modalities: Optional[Sequence[str]],
) -> Optional[Dict[str, Any]]:
    """The request fields this turn's provider call carries beyond the wire's own.

    Both a native reasoning trace and model-native image output are
    OpenRouter extensions: a direct provider endpoint gets neither.
    """

    extra: Dict[str, Any] = {}

    reasoning = reasoning_extra(
        is_openrouter=is_openrouter,
        enable_reasoning=enable_reasoning,
        model=model,
        reasoning_effort=reasoning_effort,
        reasoning_max_tokens=reasoning_max_tokens,
    )
    if reasoning is not None:
        extra[REASONING_FIELD] = reasoning

    if is_openrouter and output_modalities and IMAGE_MODALITY in output_modalities:
        extra[MODALITIES_FIELD] = list(output_modalities)

    return extra or None
