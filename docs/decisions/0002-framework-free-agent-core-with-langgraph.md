# 0002 — Agent execution loop as a framework-free core with typed events, driven by LangGraph

- Status: Accepted.
- Date: 2026-08-27.

## Context

The agent execution loop — the code that turns a user turn into a
provider call, tool calls, and a stream of events back to the client —
needs a home. Two properties are in tension:

a. it must be testable and reasoned about without a Django project,
   a database, or an HTTP request in scope: the loop's correctness is
   "given these messages and this provider response, emit these
   events and make these tool calls", a claim that a unit test can
   check directly only if nothing in the loop reaches for
   `django.conf.settings` or an ORM model;
b. it still needs a stepwise, resumable control flow — model call,
   route on the result, run tools, route again, finalize — with
   support for interrupting mid-turn (a tool awaiting approval) and
   resuming from that exact point.

Building (b) by hand as nested `if`/`while` control flow makes the
interrupt-and-resume requirement invasive: every point that can pause
has to thread its own resumption state through the caller. A graph
library that models steps as nodes and resumption as a first-class
operation removes that by construction, at the cost of a dependency
the core would otherwise not need.

## Decision

`core/llm/agent_core/` is a package with no import on `django` or any
Django-adjacent module. It defines:

- a typed event vocabulary (`events.py`): one dataclass per
  `EventType` the loop can stream, plus `EVENT_PAYLOAD_TYPES` mapping
  wire names to their payload type, so a caller goes from event name
  to shape without re-deriving it from raw JSON;
- the execution loop itself as a LangGraph `StateGraph`
  (`graph/builder.py`, `graph/runner.py`): one node per phase (model
  call, tool execution, approval gate, finalize), routed by
  `graph/routing.py`, with `AgentTurnState` as the graph's typed
  state and interrupts (`langgraph.types.Interrupt`) as the mechanism
  for a tool awaiting approval to pause a run and later resume it
  from that point via `Command`.

Everything that reaches Django — settings, models, the ORM — is
injected into the graph through ports (`graph/ports.py`,
`graph/dependencies.py`) and constructed by callers outside this
package.

## Rationale

1. A package with zero framework imports can be unit-tested by
   constructing its inputs directly and asserting on the events and
   state it produces — no Django test harness, database, or running
   server needed to exercise the loop's branches.
2. The typed event model gives the loop and any consumer of its
   stream (a replay harness, a future non-HTTP transport) one
   authoritative definition of what each event carries, instead of
   each side re-deriving the shape from an untyped JSON payload.
3. LangGraph's `Interrupt`/`Command` pair is exactly the
   pause-and-resume primitive the approval-gate requirement needs;
   implementing the equivalent by hand means every future node that
   can pause has to invent its own way of serializing "where was I"
   and threading it back in on resume.
4. Keeping Django-reaching code behind ports (`LegacyToolInvoker` and
   friends) means a tool's handler in this package never calls back
   into legacy execution logic directly — it goes through the port
   supplied on the execution context, so the module that actually
   reaches a sandbox, a search API, or a Django model is wired in by
   whoever constructs that context, not hardcoded in the loop.

## Trade-off accepted

The core now depends on LangGraph's state-graph and checkpoint
abstractions, which is more machinery than a hand-rolled loop needs
for its current handful of phases. That cost is paid once, at the
boundary; it buys resumable interrupts and a graph structure that new
phases (a future node) plug into without redesigning control flow.
