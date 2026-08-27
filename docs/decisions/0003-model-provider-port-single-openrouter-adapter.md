# 0003 — Model access behind a `ModelProvider` port, with a single OpenRouter adapter

- Status: Accepted.
- Date: 2026-08-27.

## Context

The agent execution loop (`core/llm/agent_core/`) needs to stream a
chat completion from some model. Every model Sterna offers — across
vendors, each with its own request shape and streaming format — is
reachable through OpenRouter's single OpenAI-compatible endpoint,
which normalizes vendor differences on OpenRouter's side. The loop
still should not depend on OpenRouter's SDK or wire format directly:
doing so would make the loop's high-level policy (when to call the
model, how to route on the result) depend on a concrete client
library, and would make it untestable without mocking that library's
internals.

## Decision

`core/llm/agent_core/provider.py` defines `ModelProvider`, an
abstract port: given a `ChatCompletionRequest` (OpenAI-shaped
messages, tools, and parameters), it streams `ProviderChunk`s and
raises a `provider_errors.ProviderError` subtype on failure. The loop
depends only on this abstraction.

`core/llm/agent_core/openrouter_provider.py` is the sole concrete
implementation: it speaks OpenRouter's OpenAI-compatible HTTP API
directly over Server-Sent Events, translating each SSE chunk into the
port's typed `ProviderChunk` and each HTTP/stream failure into a
`ProviderError` subtype.

## Rationale

1. The loop programs against `ModelProvider`, not against
   OpenRouter's request/response shapes — high-level policy depends
   on an abstraction, not on a concrete provider's HTTP contract.
2. A single adapter is what the actual requirement calls for:
   OpenRouter already normalizes every vendor model behind one
   endpoint, so there is no second wire format for a second adapter
   to speak. Adding provider-specific adapters before a second
   provider is actually needed would be speculative generality with
   nothing to validate it against.
3. The port makes the loop testable with a fake `ModelProvider` that
   yields scripted `ProviderChunk`s, independent of any real network
   call or SSE parser.
4. Errors surface through one typed hierarchy
   (`provider_errors.ProviderError` and its subtypes) regardless of
   which failure mode produced them (HTTP status, malformed SSE,
   stream disconnect), so the loop's error-routing logic branches on
   a closed set of typed cases instead of inspecting adapter-specific
   exceptions.

## Trade-off accepted

The port's shape is inferred from OpenRouter's OpenAI-compatible
contract, since it is the only implementation exercising it. A
provider with a materially different capability model (no streaming,
a non-OpenAI tool-call format) may need the port's shape revisited
when it is actually added, rather than today, speculatively.
