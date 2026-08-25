"""Assembling the collaborators one V2 chat request runs its turn against.

`GraphDependencies` is everything the agent loop reaches outside
itself, and every one of those collaborators is request-scoped: the
provider carries this user's key and endpoint, the registry carries
the tools this request's switches entitle it to, the accountant
carries this model's prices, the approval store and the tool
execution context carry this user and this chat.

This module is the one place they are put together, so the shape of a
V2 turn is stated once and a request only supplies its own values.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

import httpx

from ..agent.feature_flags import AgentFeatureFlags
from ..agent_core.graph import AgentTurnConfig, GraphDependencies
from ..agent_core.mcp_bridge import MCPToolSource
from ..agent_core.openrouter_provider import OpenRouterProvider
from ..agent_core.registry import ToolExecutionContext
from ..constants import TOOL_HEARTBEAT_INTERVAL_SECONDS
from .approvals import StoredToolApprovals
from .context_window import CompactingContextWindow
from .cost_accounting import CatalogPriceCostAccountant
from .mcp_port import RegistryMCPTools
from .policy import run_every_call
from .registry_factory import RequestToolSet, build_tool_set
from .tool_invoker import BoundToolInvoker
from .tool_result_events import V2ToolResultEvents

PROVIDER_TIMEOUT_SECONDS = 600.0
"""Ceiling on one streamed generation, matching the endpoint's own patience."""

MAX_TURN_ITERATIONS = 10
"""Model calls one turn may make before the loop stops and reports what is pending."""


@dataclasses.dataclass(frozen=True, slots=True)
class TurnRequest:
    """Everything about one chat request the loop's collaborators need."""

    user_id: str
    conversation_id: str
    chat_id: Optional[str]
    model: str
    request_model: str
    api_key: str
    base_url: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    flags: AgentFeatureFlags
    extra: Optional[Dict[str, Any]] = None
    tool_choice: Optional[Any] = None


@dataclasses.dataclass(frozen=True, slots=True)
class TurnStack:
    """The assembled loop dependencies, plus what the endpoint reads alongside."""

    dependencies: GraphDependencies
    tool_set: RequestToolSet
    http_client: httpx.AsyncClient


async def build_turn_stack(
    request: TurnRequest, *, summarizer_endpoint
) -> TurnStack:
    """The dependencies one turn runs against, and the client it streams over."""

    tool_set = await build_tool_set(
        request.flags,
        user_id=request.user_id,
        mcp_tools=MCPToolSource(RegistryMCPTools()),
    )
    http_client = httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS)
    dependencies = GraphDependencies(
        provider=OpenRouterProvider(
            api_key=request.api_key,
            http_client=http_client,
            base_url=request.base_url,
        ),
        registry=tool_set.registry,
        config=AgentTurnConfig(
            model=request.request_model,
            max_iterations=MAX_TURN_ITERATIONS,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tool_choice=request.tool_choice,
            extra=request.extra or None,
            heartbeat_interval_seconds=TOOL_HEARTBEAT_INTERVAL_SECONDS,
        ),
        tool_context=ToolExecutionContext(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            invoker=BoundToolInvoker(tool_set.bound_callables),
            chat_id=request.chat_id,
        ),
        approvals=StoredToolApprovals(
            user_id=request.user_id, session_id=request.chat_id or ""
        ),
        approval_policy=run_every_call,
        context_window=CompactingContextWindow(
            summarizer_endpoint=summarizer_endpoint, model_id=request.model
        ),
        cost_accountant=CatalogPriceCostAccountant.for_model(request.model),
        tool_result_events=V2ToolResultEvents(
            web_search_enabled=request.flags.brave_search
        ),
    )
    return TurnStack(
        dependencies=dependencies, tool_set=tool_set, http_client=http_client
    )


def bound_tool_list(tool_set: RequestToolSet) -> List[Any]:
    """The callables this request bound, in the order they were bound."""

    return list(tool_set.bound_callables.values())
