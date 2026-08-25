"""The ports and fixtures a golden scenario is replayed against.

Everything the agent loop reaches outside itself is supplied here, in
the shape the golden fixtures established: a tool catalog with fixed
results, an approval store that mints integer primary keys, a cost
accountant per pricing model, and the derivation that turns a search
result into citations. None of it belongs to `llm.agent_core`, which is
why the loop takes it as ports.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import json
from typing import Dict, List, Optional, Sequence, Tuple

from llm.agent_core.events import (
    Approval,
    JsonDict,
    StreamEvent,
    ToolCall,
    Usage,
    WebSource,
    WebSourcesEvent,
)
from llm.agent_core.graph import CostBreakdown
from llm.agent_core.graph.ports import PENDING_APPROVAL_STATUS
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderImageChunk,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.agent_core.registry import (
    ToolApproval,
    ToolDefinition,
    ToolDisplay,
    ToolExecutionContext,
)

TOKENS_PER_PRICE_UNIT = 1000
"""Catalog prices are quoted per this many tokens."""

RESULTS_FIELD = "results"
"""The key a search tool's result carries its citations under."""

URL_FIELD = "url"
TITLE_FIELD = "title"


# --- Tool catalog --------------------------------------------------------


def tool_definition(
    tool_id: str,
    *,
    display_name: str,
    description: str,
    result: JsonDict,
    approval: ToolApproval,
    server_name: Optional[str] = None,
    parameters: Optional[JsonDict] = None,
) -> ToolDefinition:
    """A tool whose handler returns `result` whatever it is called with."""

    async def _handle(_arguments: JsonDict, _context: ToolExecutionContext) -> JsonDict:
        return copy.deepcopy(result)

    return ToolDefinition(
        id=tool_id,
        display=ToolDisplay(name=display_name, server_name=server_name),
        description=description,
        input_schema=parameters or {"type": "object", "properties": {}},
        handler=_handle,
        approval=approval,
    )


# --- Approval store -------------------------------------------------------


class StoredApprovals:
    """Approval records addressed by the integer keys their store issues.

    Both the approval and the tool it names are identified by a
    primary key, which is what the golden transcripts carry and what
    the comparison normalizes away. The tool's wire name comes from
    the call itself, so the record says what the model asked for
    rather than how the catalog labels it.
    """

    def __init__(self) -> None:
        self._approval_keys = itertools.count(1)
        self._tool_keys = itertools.count(1)
        self._tool_key_by_id: Dict[str, str] = {}

    async def open(
        self, requests: Sequence[Tuple[ToolCall, ToolDefinition]]
    ) -> List[Approval]:
        return [
            Approval(
                id=str(next(self._approval_keys)),
                tool_id=self._tool_key(definition.id),
                tool_name=call.function.name,
                tool_description=definition.description,
                server_name=definition.display.server_name or "",
                arguments=json.loads(call.function.arguments or "{}"),
                status=PENDING_APPROVAL_STATUS,
            )
            for call, definition in requests
        ]

    def _tool_key(self, tool_id: str) -> str:
        if tool_id not in self._tool_key_by_id:
            self._tool_key_by_id[tool_id] = str(next(self._tool_keys))
        return self._tool_key_by_id[tool_id]


# --- Cost accounting -------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class PriceTableCostAccountant:
    """Prices a generation from the catalog row the scenario seeded.

    The per-token price is derived once from the quoted per-1K price
    and then multiplied by the token count, which is the arithmetic
    the figures in the golden transcripts were produced by.
    """

    prompt_price_per_1k: float
    completion_price_per_1k: float

    def account(
        self, *, model: str, usage: Usage, reported_cost: Optional[float]
    ) -> CostBreakdown:
        prompt = self.prompt_price_per_1k / TOKENS_PER_PRICE_UNIT * usage.prompt_tokens
        completion = (
            self.completion_price_per_1k / TOKENS_PER_PRICE_UNIT * usage.completion_tokens
        )
        return CostBreakdown(total=prompt + completion, prompt=prompt, completion=completion)


class ReportedCostSplit:
    """Replays the split a provider reported, one entry per generation.

    A provider that returns prompt and completion costs alongside its
    total leaves nothing to derive; the last entry answers any further
    generation the turn takes.
    """

    def __init__(self, breakdowns: Sequence[CostBreakdown]) -> None:
        self._breakdowns = list(breakdowns)
        self._answered = 0

    def account(
        self, *, model: str, usage: Usage, reported_cost: Optional[float]
    ) -> CostBreakdown:
        position = min(self._answered, len(self._breakdowns) - 1)
        self._answered += 1
        return self._breakdowns[position]


# --- Derived tool events -----------------------------------------------------


class SearchResultCitations:
    """Reads the citations a search tool returns out of its result."""

    def derive(self, call: object, result: JsonDict) -> Sequence[StreamEvent]:
        found = result.get(RESULTS_FIELD)
        if not isinstance(found, list):
            return ()
        return (
            WebSourcesEvent(
                sources=[
                    WebSource(url=entry[URL_FIELD], title=entry[TITLE_FIELD])
                    for entry in found
                ]
            ),
        )


# --- Provider chunk builders ---------------------------------------------------


def generation_id_chunk(generation_id: str) -> ProviderGenerationIdChunk:
    return ProviderGenerationIdChunk(generation_id=generation_id)


def content_chunk(text: str) -> ProviderContentDeltaChunk:
    return ProviderContentDeltaChunk(content=text)


def reasoning_chunk(text: str) -> ProviderReasoningDeltaChunk:
    return ProviderReasoningDeltaChunk(content=text)


def image_chunk(image_url: str) -> ProviderImageChunk:
    return ProviderImageChunk(image=image_url)


def tool_call_chunk(
    index: int, call_id: str, name: str, arguments: str
) -> ProviderToolCallDeltaChunk:
    return ProviderToolCallDeltaChunk(
        index=index, id=call_id, name=name, arguments_delta=arguments
    )


def usage_chunk(
    prompt_tokens: int, completion_tokens: int, *, cost: Optional[float] = None
) -> ProviderUsageChunk:
    return ProviderUsageChunk(
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        cost=cost,
    )


def done_chunk(finish_reason: str) -> ProviderDoneChunk:
    return ProviderDoneChunk(finish_reason=finish_reason)
