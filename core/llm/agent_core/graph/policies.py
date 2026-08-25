"""The knobs that govern one agent turn: model request shape, retries, pacing.

A turn is configured entirely by value. `AgentTurnConfig` carries what
the loop needs to build each `ChatCompletionRequest` plus the two
policies the loop applies on its own behalf — how many model/tool
round trips it will take before it stops, and whether a failed
provider call is retried before the turn ends.

A third policy, `ApprovalPolicy`, governs a call the loop is about to
gate: it is a `GraphDependencies` field rather than part of
`AgentTurnConfig`, since a caller with no opinion supplies none at all
and gets each `ToolDefinition`'s own `approval` back unchanged.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional, Tuple, Type, Union

from ..events import JsonDict, ToolCall
from ..provider_errors import (
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTransportError,
)
from ..registry import ToolApproval, ToolDefinition

ApprovalPolicy = Callable[[ToolDefinition, ToolCall], ToolApproval]
"""Overrides a tool call's approval requirement ahead of its own `ToolDefinition`.

`gated_calls` (`graph.approval_nodes`) calls this, when
`GraphDependencies.approval_policy` supplies one, with the call's
`ToolDefinition` and the `ToolCall` itself, and gates the call on
whatever `ToolApproval` comes back — regardless of what the
definition's own `approval` says. A caller that wants every tool to
run without a pause (V2's wiring) passes a policy that always returns
`ToolApproval.AUTO`; one that wants V1's classification passes no
policy at all, since that classification is already each
`ToolDefinition`'s default.
"""

DEFAULT_MAX_ITERATIONS = 10
"""Model calls one turn may make before the loop stops on its own."""

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0
"""Seconds between keep-alives while a tool call is in flight."""

TRANSIENT_PROVIDER_ERRORS: Tuple[Type[ProviderError], ...] = (
    ProviderRateLimitError,
    ProviderOverloadedError,
    ProviderTransportError,
)
"""Provider failures a caller may reasonably ask the loop to retry."""


@dataclasses.dataclass(frozen=True, slots=True)
class RetryPolicy:
    """When a failed provider call is attempted again.

    A retry re-issues the whole request, so it is only sound while
    nothing from the failed attempt has reached the caller: once a
    content or reasoning fragment has been streamed, replaying the
    request would duplicate it. The loop enforces that condition
    itself, and this policy only says how many attempts are permitted
    and which failures qualify.
    """

    max_attempts: int = 1
    retryable_errors: Tuple[Type[ProviderError], ...] = TRANSIENT_PROVIDER_ERRORS
    backoff_seconds: float = 0.0

    def permits_another_attempt(self, attempt: int, error: ProviderError) -> bool:
        """Whether `error` on attempt number `attempt` (1-based) may be retried."""

        return attempt < self.max_attempts and isinstance(error, self.retryable_errors)


@dataclasses.dataclass(frozen=True, slots=True)
class AgentTurnConfig:
    """Everything about one turn that does not depend on the conversation.

    `tool_choice` and `extra` are passed through to the provider port
    verbatim; the loop has no opinion on their contents.
    `heartbeat_interval_seconds` of `None` disables keep-alives, which
    is what a test wants and what a caller with its own keep-alive
    channel wants.
    """

    model: str
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tool_choice: Optional[Union[str, JsonDict]] = None
    extra: Optional[JsonDict] = None
    retry: RetryPolicy = dataclasses.field(default_factory=RetryPolicy)
    heartbeat_interval_seconds: Optional[float] = DEFAULT_HEARTBEAT_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
