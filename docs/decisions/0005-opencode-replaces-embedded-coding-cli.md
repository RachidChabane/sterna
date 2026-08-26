# 0005 — The sandboxed coding-agent CLI is opencode, not an embedded proprietary CLI

- Status: Accepted.
- Date: 2026-08-27.

## Context

The coding-agent sandbox needs an autonomous CLI that can plan and
implement changes against a cloned repository, reachable through
OpenRouter so its usage is billed the same way as every other model
call in Sterna. Sterna's billing model depends on that: a user's
model access, including inside the sandbox, is metered and charged
through a single shared OpenRouter key, priced through
`BillingService`.

An embedded proprietary coding CLI was evaluated against that
requirement. Its licensing terms govern how the CLI may be embedded
and metered, and do not permit the shared-key, resold-access model
Sterna's billing is built on. That is a hard constraint, not a
preference: no amount of integration work makes a CLI usable under
terms that forbid the deployment shape the product needs.

## Decision

The sandboxed coding-agent CLI is opencode: open source, with a
native OpenRouter provider speaking the OpenAI-compatible format
directly, so every model — including inside the sandbox — routes
through the same endpoint and the same billing path as the rest of
Sterna.

`core/sandbox/orchestrator/coding_agent_runner.py` spawns and drives
opencode inside the sandbox container. `opencode_harness.py` builds
the invocation and the permission profile (mirroring the previous
CLI's restrictions: plan mode denies edits and restricts `bash` to a
read-only allowlist, enforced doubly by a filesystem `chmod`).
`opencode_output_adapter.py` parses opencode's streamed JSON events
into the same `coding_agent_step`/`coding_agent_question`/
`coding_agent_completed` event vocabulary the rest of the system
already consumed. `mcp_ask_user_opencode.py` implements the
ask-user round trip as an opencode MCP server. The CLI is installed
into the sandbox base image via a pinned `npm install -g
opencode-ai@<version>` layer.

## Rationale

1. opencode's native OpenRouter provider means every model call,
   sandboxed or not, is billed through the one path
   (`BillingService`) already auditing every other billable action —
   no second billing integration for a CLI-specific vendor bridge.
2. opencode is open source, so its embedding is governed by its own
   license rather than by a vendor's usage terms that constrain the
   deployment shape Sterna needs.
3. Preserving the same event vocabulary
   (`coding_agent_step`/`question`/`completed`) through the output
   adapter meant the runner, the billing integration, and the
   frontend's progress rendering did not need to change shape for
   the swap — only the process being driven and the adapter parsing
   its output changed.
4. opencode's plan/build agent modes map directly onto the
   read-only-exploration versus implement distinction the product
   already exposed, so the permission model transferred without a
   redesign.

## Trade-off accepted

opencode's plan/build agent-mode semantics and its JSON event schema
are opencode's own, not something Sterna controls; a future breaking
change in either requires updating `opencode_harness.py` and
`opencode_output_adapter.py` to match, in a way that an in-house CLI
integration would not have required.
