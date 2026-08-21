"""Shared fixtures/helpers for llm/tests.

Test pattern (mirrors usage_quota/tests/test_billing_coverage.py):
    Use sync `def test_*` methods on `django.test.TestCase`. Async
    entry points are wrapped with `async_to_sync`. Django's TestCase
    does NOT run `async def test_*` methods -- pytest collects them but
    the coroutine is never awaited, the test silently passes, and the
    assertion never runs.

    `_astream_with_direct_client` / `astream_chat` are ASYNC GENERATORS,
    not coroutines -- `async_to_sync` alone does not drain them. Use
    `drain()` below, which wraps the async-generator consumption in a
    coroutine before handing it to `async_to_sync`.
"""

import inspect
from decimal import Decimal

from asgiref.sync import async_to_sync

from llm.langchain_agent import LangChainStreamingAgent


def drain(agen):
    """Synchronously collect every event yielded by an async generator.

    Usage: events = drain(agent._astream_with_direct_client(...))
    """
    async def _collect():
        return [event async for event in agen]
    return async_to_sync(_collect)()


def make_agent(**overrides):
    """Construct a real LangChainStreamingAgent with no DB/network I/O.

    Defaults deliberately omit user_id/conversation_id so V2 tool
    discovery (which hits the DB) never activates -- see
    `has_tool_features` gating in LangChainStreamingAgent.__init__.
    """
    defaults = dict(
        model="openai/gpt-4o-mini",
        api_key="sk-test",
        enable_file_tools=False,
    )
    defaults.update(overrides)
    return LangChainStreamingAgent(**defaults)


class FakeTool:
    """Minimal stand-in for a langchain StructuredTool.

    `handler` may be:
      - a plain value (dict or JSON string) returned unconditionally, or
      - a callable(args) -> value (sync or async), for tests that need
        to assert on the arguments the agent passed through.
    """

    def __init__(self, name, handler, description="A fake tool for tests.", args_schema=None):
        self.name = name
        self.description = description
        self.args_schema = args_schema
        self._handler = handler

    async def ainvoke(self, args):
        if callable(self._handler):
            result = self._handler(args)
            if inspect.isawaitable(result):
                result = await result
            return result
        return self._handler


def stream_sequence(*iteration_chunks):
    """Build a `complete_stream`-compatible side_effect.

    Each positional arg is the list of chunk dicts (event/data pairs, in
    client.py's SSE-chunk shape) yielded for one call to
    `complete_stream` -- i.e. one iteration of the agent's tool loop.
    `complete_stream` itself is a SYNC generator (run in a worker
    thread by `_astream_with_direct_client`), so each returned value
    must be a plain iterable, not an async generator.
    """
    remaining = list(iteration_chunks)

    def _complete_stream(**kwargs):
        if remaining:
            chunks = remaining.pop(0)
        else:
            chunks = []
        return iter(chunks)

    return _complete_stream


def content_chunk(text):
    return {"event": "content", "data": {"content": text}}


def generation_id_chunk(gen_id):
    return {"event": "generation_id", "data": {"generation_id": gen_id}}


def done_chunk(
    finish_reason="stop",
    tool_calls=None,
    prompt_tokens=10,
    completion_tokens=5,
    generation_id=None,
):
    data = {
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        "finish_reason": finish_reason,
    }
    if tool_calls:
        data["tool_calls"] = tool_calls
    if generation_id:
        data["generation_id"] = generation_id
    return {"event": "done", "data": data}


def make_tool_call(call_id, name, arguments="{}"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class FakeChunk:
    """Stand-in for a LangChain `AIMessageChunk` as consumed by
    `astream_chat`'s streaming loop. Only the attributes that loop
    actually reads via `hasattr`/direct access are modeled."""

    def __init__(
        self,
        content="",
        tool_call_chunks=None,
        tool_calls=None,
        usage_metadata=None,
        response_metadata=None,
        additional_kwargs=None,
    ):
        self.content = content
        self.tool_call_chunks = tool_call_chunks
        self.tool_calls = tool_calls
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}
        self.additional_kwargs = additional_kwargs or {}


class FakeStreamingLLM:
    """Stand-in for `self.llm_with_tools` (a bound ChatOpenAI). Each call
    to `.astream()` consumes the next queued list of FakeChunks -- one
    list per tool-loop iteration, mirroring `stream_sequence` for the
    direct-client path."""

    def __init__(self, *iteration_chunks):
        self._iterations = list(iteration_chunks)

    def astream(self, _messages):
        chunks = self._iterations.pop(0) if self._iterations else []

        async def _gen():
            for chunk in chunks:
                yield chunk
        return _gen()

    def bind_tools(self, _tools, **_kwargs):
        return self


def seed_billing_plan(plan_name="llm-tests-plan"):
    """Minimal active SubscriptionPlan for record_usage()/check_quota() calls.

    The langchain_agent aggregate billing path (`_record_chat_aggregate_usage`
    / the direct-client tool-cost deduct) bills from `_calculate_costs`, not
    `ServicePricing`, so no ServicePricing rows are seeded here -- only a
    plan with `features={"chat": True}` (required by the pre-stream
    `check_quota(feature_name='chat')` gate) for the user's UserSubscription
    to resolve to.
    """
    from usage_quota.models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        name=plan_name,
        defaults={
            "display_name": "LLM Tests Plan",
            "weekly_limit_usd": Decimal("50.00"),
            "session_limit_usd": Decimal("20.00"),
            # `check_quota(feature_name='chat')` gates on plan.features
            # having the matching flag (see usage_quota/feature_registry.py).
            "features": {"chat": True},
        },
    )
    return plan


def make_billing_user(email, plan):
    from authentication.models import User
    from usage_quota.models import UserSubscription

    user = User.objects.create_user(email=email, password="x")
    UserSubscription.objects.create(user=user, plan=plan, is_active=True)
    return user
