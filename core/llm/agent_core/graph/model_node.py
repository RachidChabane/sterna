"""The node that asks the model for the next step of the turn.

Relieves context-window pressure, streams one generation from the
provider port, translates each provider chunk into the matching typed
event, and reassembles any tool calls the generation asked for. A
provider failure ends the turn here: the node records the terminal
`error` event and returns, leaving the router to end the graph without
a `done` event.

Retrying is deliberately narrow. Re-issuing a request replays it from
the beginning, so it stays sound only while nothing from the failed
attempt reached the caller. Once a fragment has been streamed the
attempt is final, whatever the configured policy allows.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from ..events import (
    ContentEvent,
    ErrorEvent,
    GenerationIdEvent,
    ImageEvent,
    ReasoningEvent,
    UsageUpdateEvent,
)
from ..provider import (
    ChatCompletionRequest,
    ProviderChunk,
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderImageChunk,
    ProviderMessage,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
    ToolDefinition,
    ToolFunctionDefinition,
)
from ..provider_errors import ProviderError
from ..tool_call_accumulator import ToolCallAccumulator
from .dependencies import GraphDependencies
from .emission import EventStream
from .errors import to_error_event
from .state import AgentTurnState, GenerationAccounting

ASSISTANT_ROLE = "assistant"


class _Generation:
    """The mutable running total of one streamed generation.

    `visible_output` records whether anything a caller can already see
    has been emitted, which is what makes a retry unsound from that
    point on.
    """

    __slots__ = (
        "accounting",
        "content",
        "finish_reason",
        "generation_id",
        "prior_generation_ids",
        "tool_calls",
        "visible_output",
    )

    def __init__(self, prior_generation_ids: List[str]) -> None:
        self.content: List[str] = []
        self.generation_id: Optional[str] = None
        self.prior_generation_ids = prior_generation_ids
        self.accounting: Optional[GenerationAccounting] = None
        self.tool_calls = ToolCallAccumulator()
        self.visible_output = False
        self.finish_reason: Optional[str] = None

    def known_generation_ids(self) -> List[str]:
        """Every generation id of the turn so far, this one included."""

        known = list(self.prior_generation_ids)
        if self.generation_id is not None and self.generation_id not in known:
            known.append(self.generation_id)
        return known


async def model_node(state: AgentTurnState, deps: GraphDependencies, stream: EventStream) -> Dict[str, Any]:
    """Stream one generation and record what it produced."""

    relief = await deps.context_window.relieve(state["messages"], model=deps.config.model)
    stream.emit_all(relief.events)
    messages = list(relief.messages)
    request = _build_request(messages, deps)

    generation, error = await _stream_generation(
        request, deps, stream, state["generation_ids"]
    )
    if error is not None:
        return {
            "messages": messages,
            "generation_ids": generation.known_generation_ids(),
            "error": error,
        }

    tool_calls = generation.tool_calls.tool_calls()
    messages.append(
        ProviderMessage(
            role=ASSISTANT_ROLE,
            content="".join(generation.content) or None,
            tool_calls=tool_calls or None,
        )
    )
    return {
        "messages": messages,
        "iteration": state["iteration"] + 1,
        "pending_tool_calls": tool_calls,
        "generation_ids": generation.known_generation_ids(),
        "accounting": generation.accounting or state["accounting"],
        "finish_reason": generation.finish_reason,
    }


def _build_request(
    messages: List[ProviderMessage], deps: GraphDependencies
) -> ChatCompletionRequest:
    """Build the request for this round.

    The request carries its own copy of the history, so appending the
    assistant's reply to the node's working list afterwards cannot
    change what the request says was sent.
    """

    config = deps.config
    return ChatCompletionRequest(
        model=config.model,
        messages=list(messages),
        tools=_offered_tools(deps),
        tool_choice=config.tool_choice,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        extra=config.extra,
    )


def _offered_tools(deps: GraphDependencies) -> Optional[List[ToolDefinition]]:
    definitions = [
        ToolDefinition(
            function=ToolFunctionDefinition(
                name=tool.id,
                description=tool.description,
                parameters=tool.input_schema,
            )
        )
        for tool in deps.registry.all()
    ]
    return definitions or None


async def _stream_generation(
    request: ChatCompletionRequest,
    deps: GraphDependencies,
    stream: EventStream,
    prior_generation_ids: List[str],
) -> Tuple[_Generation, Optional[ErrorEvent]]:
    """Run the request, retrying only while nothing has reached the caller."""

    retry = deps.config.retry
    attempt = 0
    while True:
        attempt += 1
        generation = _Generation(prior_generation_ids)
        try:
            async for chunk in deps.provider.stream_chat(request):
                _absorb(chunk, generation, deps, stream)
            return generation, None
        except ProviderError as error:
            if generation.visible_output or not retry.permits_another_attempt(attempt, error):
                event = to_error_event(error)
                stream.emit(event)
                return generation, event
            if retry.backoff_seconds > 0:
                await asyncio.sleep(retry.backoff_seconds)


def _absorb(
    chunk: ProviderChunk, generation: _Generation, deps: GraphDependencies, stream: EventStream
) -> None:
    """Fold one provider chunk into the running generation and stream its event."""

    if isinstance(chunk, ProviderGenerationIdChunk):
        generation.generation_id = chunk.generation_id
        stream.emit(GenerationIdEvent(generation_id=chunk.generation_id))
    elif isinstance(chunk, ProviderContentDeltaChunk):
        generation.content.append(chunk.content)
        generation.visible_output = True
        stream.emit(ContentEvent(content=chunk.content))
    elif isinstance(chunk, ProviderReasoningDeltaChunk):
        generation.visible_output = True
        stream.emit(ReasoningEvent(content=chunk.content))
    elif isinstance(chunk, ProviderImageChunk):
        generation.visible_output = True
        stream.emit(ImageEvent(image=chunk.image))
    elif isinstance(chunk, ProviderToolCallDeltaChunk):
        generation.tool_calls.absorb(chunk)
    elif isinstance(chunk, ProviderUsageChunk):
        generation.accounting = _account(chunk, deps)
        stream.emit(_usage_event(generation, deps))
    elif isinstance(chunk, ProviderDoneChunk):
        generation.finish_reason = chunk.finish_reason


def _account(chunk: ProviderUsageChunk, deps: GraphDependencies) -> GenerationAccounting:
    breakdown = deps.cost_accountant.account(
        model=deps.config.model, usage=chunk.usage, reported_cost=chunk.cost
    )
    return GenerationAccounting(
        usage=chunk.usage,
        cost=breakdown.total,
        prompt_cost=breakdown.prompt,
        completion_cost=breakdown.completion,
    )


def _usage_event(generation: _Generation, deps: GraphDependencies) -> UsageUpdateEvent:
    accounting = generation.accounting or GenerationAccounting()
    return UsageUpdateEvent(
        usage=accounting.usage,
        cost=accounting.cost,
        prompt_cost=accounting.prompt_cost,
        completion_cost=accounting.completion_cost,
        generation_id=generation.generation_id or "",
        generation_ids=generation.known_generation_ids(),
    )
