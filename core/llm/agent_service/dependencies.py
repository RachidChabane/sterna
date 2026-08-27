"""Assembling the collaborators one chat request runs its turn against.

`GraphDependencies` is everything the agent loop reaches outside
itself, and every one of those collaborators is request-scoped: the
provider carries this user's key and endpoint, the registry carries
the tools this request's switches entitle it to, the accountant
carries this model's prices, the approval store and the tool
execution context carry this user and this chat.

This module is the one place they are put together, so the shape of a
turn is stated once and a request only supplies its own values. The
two endpoints assemble different turns and each has its own builder:
V2 runs every catalog and file tool call it is given but still gates
one an MCP server surfaces, compacts a history that no longer fits,
derives citations and previews from what a tool returned, and reports
a coding-agent run's progress while the call is still in flight; V1
gates every call outside its sandboxed workspace tools, sends the
history as it stands, and speaks a vocabulary with no derived event in
it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

import httpx

from ..agent.feature_flags import AgentFeatureFlags
from ..agent_core.graph import (
    AgentTurnConfig,
    GraphDependencies,
    NoDerivedToolEvents,
    UnboundedContextWindow,
)
from ..agent_core.mcp_bridge import MCPToolSource
from ..agent_core.openrouter_provider import OpenRouterProvider
from ..agent_core.registry import ToolExecutionContext, ToolRegistry
from ..constants import TOOL_HEARTBEAT_INTERVAL_SECONDS
from .approvals import StoredToolApprovals
from .coding_agent_progress import CodingAgentProgress, ResolveContext
from .context_window import CompactingContextWindow
from .cost_accounting import CatalogPriceCostAccountant
from .mcp_port import RegistryMCPTools, published_tool_id
from .policy import run_every_call_except_mcp
from .registry_factory import RequestToolSet, build_tool_set
from .tool_invoker import BoundToolInvoker
from .tool_result_events import V2ToolResultEvents
from .v1_tools import SandboxToolInvoker, build_v1_tool_registry

PROVIDER_TIMEOUT_SECONDS = 600.0
"""Ceiling on one streamed generation, matching the endpoint's own patience."""

MAX_TURN_ITERATIONS = 10
"""Model calls one turn may make before the loop stops and reports what is pending."""

MAX_V1_TURN_ITERATIONS = 2
"""Model calls one direct-completion turn may make: the answer, and one recall.

A V1 turn is sent the conversation as it stands and never relieves
context pressure mid-turn, so the round trip it may take is the single
one the endpoint has always taken -- ask, run what the model called,
ask once more with the results.
"""

AUTOMATIC_TOOL_CHOICE = "auto"
"""What a turn offering tools leaves the choice among them to."""


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
    request: TurnRequest, *, summarizer_endpoint, resolve_file_tools_context: ResolveContext
) -> TurnStack:
    """The dependencies one turn runs against, and the client it streams over.

    `resolve_file_tools_context` is read rather than passed by value:
    the context the coding-agent progress port polls through is
    installed once these dependencies exist.
    """

    tool_set = await build_tool_set(
        request.flags,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
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
        approval_policy=run_every_call_except_mcp,
        context_window=CompactingContextWindow(
            summarizer_endpoint=summarizer_endpoint, model_id=request.model
        ),
        cost_accountant=CatalogPriceCostAccountant.for_model(request.model),
        tool_result_events=V2ToolResultEvents(
            web_search_enabled=request.flags.brave_search
        ),
        tool_progress=CodingAgentProgress(resolve_file_tools_context),
    )
    return TurnStack(
        dependencies=dependencies, tool_set=tool_set, http_client=http_client
    )


def bound_tool_list(tool_set: RequestToolSet) -> List[Any]:
    """The callables this request bound, in the order they were bound."""

    return list(tool_set.bound_callables.values())


@dataclasses.dataclass(frozen=True, slots=True)
class V1TurnStack:
    """The assembled loop dependencies of a V1 turn, plus its client."""

    dependencies: GraphDependencies
    http_client: httpx.AsyncClient


async def build_v1_turn_stack(
    request: TurnRequest,
    *,
    mcp_tools: Optional[MCPToolSource] = None,
    auth_token: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> V1TurnStack:
    """The dependencies one V1 turn runs against, and the client it streams over.

    Every collaborator here states one V1 rule: the tool set is what
    the direct-completion endpoint has always offered, the sign-off
    requirement is each tool's own, the history is sent as it stands,
    and no keep-alive or derived event reaches a client that has never
    parsed one.
    """

    registry = await build_v1_tool_registry(
        request.flags,
        user_id=request.user_id,
        mcp_tools=mcp_tools
        or MCPToolSource(RegistryMCPTools(naming=published_tool_id)),
    )
    http_client = httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS)
    dependencies = GraphDependencies(
        provider=OpenRouterProvider(
            api_key=request.api_key,
            http_client=http_client,
            base_url=request.base_url,
        ),
        registry=registry,
        config=AgentTurnConfig(
            model=request.request_model,
            max_iterations=MAX_V1_TURN_ITERATIONS,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tool_choice=_tool_choice_for(registry),
            extra=request.extra or None,
            heartbeat_interval_seconds=None,
        ),
        tool_context=ToolExecutionContext(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            invoker=SandboxToolInvoker(
                auth_token=auth_token, model_metadata=model_metadata
            ),
            chat_id=request.chat_id,
        ),
        approvals=StoredToolApprovals(
            user_id=request.user_id, session_id=request.chat_id or ""
        ),
        context_window=UnboundedContextWindow(),
        cost_accountant=CatalogPriceCostAccountant.for_model(request.model),
        tool_result_events=NoDerivedToolEvents(),
    )
    return V1TurnStack(dependencies=dependencies, http_client=http_client)


def _tool_choice_for(registry: ToolRegistry) -> Optional[str]:
    """How the model is told to choose among the tools it was offered."""

    return AUTOMATIC_TOOL_CHOICE if registry.all() else None
