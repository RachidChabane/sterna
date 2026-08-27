"""Test doubles for driving `llm.agent_core.graph` without a model or a tool.

Kept out of the `test_*` namespace so pytest imports it only when a
test asks for it, and deliberately free of any Django import so the
agent-core suite can run against the package on its own terms.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from llm.agent_core.events import JsonDict, ToolCall, ToolCallFunction, Usage
from llm.agent_core.graph import (
    AgentLoop,
    AgentTurnConfig,
    GraphDependencies,
    UnboundedContextWindow,
)
from llm.agent_core.provider import (
    ChatCompletionRequest,
    ModelProvider,
    ProviderChunk,
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderMessage,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.agent_core.registry import (
    ToolApproval,
    ToolDefinition,
    ToolDisplay,
    ToolExecutionContext,
    ToolRegistry,
)

FIXTURE_MODEL = "fixture/graph-model"


class ScriptedProvider(ModelProvider):
    """Replays a prepared list of chunks per call, or raises a prepared error.

    Each entry of `script` is one generation: either a sequence of
    `ProviderChunk`s to yield, or a `ProviderError` to raise. A
    trailing entry is reused if the loop asks for more generations
    than the script holds, so a test only writes the rounds it cares
    about.
    """

    def __init__(self, script: Sequence[Any]) -> None:
        self._script = list(script)
        self.requests: List[ChatCompletionRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderChunk]:
        self.requests.append(request)
        entry = self._script[min(len(self.requests) - 1, len(self._script) - 1)]
        return self._replay(entry)

    async def _replay(self, entry: Any) -> AsyncIterator[ProviderChunk]:
        if isinstance(entry, BaseException):
            raise entry
        for chunk in entry:
            if isinstance(chunk, BaseException):
                raise chunk
            await asyncio.sleep(0)
            yield chunk


def text_generation(
    generation_id: str, *fragments: str, usage: Optional[Usage] = None
) -> List[ProviderChunk]:
    """A generation that streams plain text and stops."""

    chunks: List[ProviderChunk] = [ProviderGenerationIdChunk(generation_id=generation_id)]
    chunks.extend(ProviderContentDeltaChunk(content=fragment) for fragment in fragments)
    if usage is not None:
        chunks.append(ProviderUsageChunk(usage=usage, cost=0.001))
    chunks.append(ProviderDoneChunk(finish_reason="stop"))
    return chunks


def tool_call_generation(
    generation_id: str, *calls: ToolCall, preamble: str = ""
) -> List[ProviderChunk]:
    """A generation that asks for tool calls, streamed one delta per call."""

    chunks: List[ProviderChunk] = [ProviderGenerationIdChunk(generation_id=generation_id)]
    if preamble:
        chunks.append(ProviderContentDeltaChunk(content=preamble))
    for index, call in enumerate(calls):
        chunks.append(
            ProviderToolCallDeltaChunk(
                index=index,
                id=call.id,
                name=call.function.name,
                arguments_delta=call.function.arguments,
            )
        )
    chunks.append(ProviderDoneChunk(finish_reason="tool_calls"))
    return chunks


def tool_call(call_id: str, name: str, **arguments: Any) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=ToolCallFunction(name=name, arguments=json.dumps(arguments)),
    )


class RecordingTool:
    """A tool whose handler records its arguments and returns a fixed result."""

    def __init__(
        self,
        tool_id: str,
        *,
        result: Optional[JsonDict] = None,
        approval: ToolApproval = ToolApproval.AUTO,
        raises: Optional[BaseException] = None,
        delay_seconds: float = 0.0,
        server_name: Optional[str] = None,
    ) -> None:
        self.tool_id = tool_id
        self.calls: List[JsonDict] = []
        self._result = result if result is not None else {"success": True, "tool": tool_id}
        self._approval = approval
        self._raises = raises
        self._delay_seconds = delay_seconds
        self._server_name = server_name

    async def _handle(self, arguments: JsonDict, context: ToolExecutionContext) -> JsonDict:
        self.calls.append(dict(arguments))
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        if self._raises is not None:
            raise self._raises
        return dict(self._result)

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id=self.tool_id,
            display=ToolDisplay(
                name=self.tool_id.replace("_", " ").title(),
                server_name=self._server_name,
            ),
            description=f"Fixture tool {self.tool_id}.",
            input_schema={"type": "object", "properties": {}},
            handler=self._handle,
            approval=self._approval,
        )


class NullInvoker:
    """A legacy-tool invoker no fixture tool ever reaches."""

    async def invoke(
        self, tool_id: str, arguments: JsonDict, context: ToolExecutionContext
    ) -> JsonDict:
        raise AssertionError(f"no fixture tool should delegate to the legacy invoker: {tool_id}")


def execution_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="user-1", conversation_id="conversation-1", invoker=NullInvoker()
    )


def dependencies(
    provider: ModelProvider,
    tools: Sequence[RecordingTool] = (),
    *,
    config: Optional[AgentTurnConfig] = None,
    **overrides: Any,
) -> GraphDependencies:
    """A dependency container wired for a test: no heartbeats, no retries."""

    return GraphDependencies(
        provider=provider,
        registry=ToolRegistry(tool.definition() for tool in tools),
        config=config
        or AgentTurnConfig(model=FIXTURE_MODEL, heartbeat_interval_seconds=None),
        tool_context=execution_context(),
        context_window=overrides.pop("context_window", UnboundedContextWindow()),
        **overrides,
    )


def user_message(text: str) -> ProviderMessage:
    return ProviderMessage(role="user", content=text)


async def collect(events: AsyncIterator[Any]) -> List[Any]:
    return [event async for event in events]


async def run_turn(
    loop: AgentLoop, prompt: str = "hello", *, thread_id: str = "thread-1"
) -> List[Any]:
    return await collect(loop.start([user_message(prompt)], thread_id=thread_id))


def event_names(events: Sequence[Any]) -> List[str]:
    return [str(event.event_type) for event in events]


def first_of(events: Sequence[Any], event_type: str) -> Any:
    for event in events:
        if str(event.event_type) == event_type:
            return event
    raise AssertionError(f"no {event_type} event in {event_names(events)}")


def all_of(events: Sequence[Any], event_type: str) -> List[Any]:
    return [event for event in events if str(event.event_type) == event_type]


def usage(prompt_tokens: int, completion_tokens: int) -> Usage:
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def tool_result_messages(messages: Sequence[ProviderMessage]) -> List[Dict[str, Any]]:
    """The decoded payload of every tool-role message, in order."""

    return [
        json.loads(message.content or "{}")
        for message in messages
        if message.role == "tool"
    ]
