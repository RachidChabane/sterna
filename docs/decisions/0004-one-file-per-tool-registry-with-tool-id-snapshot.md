# 0004 — One file per tool, discovered into a registry, with a committed tool-id snapshot

- Status: Accepted.
- Date: 2026-08-27.

## Context

Every tool the agent can call needs its schema, handler, prompt
snippet, display metadata, and approval requirement co-located
somewhere, and the frontend needs to know the current set of tool ids
so its per-tool renderer coverage can be checked against it. A tool
catalog that is a single file with one entry per tool turns adding a
tool into an edit of that shared file — a touchpoint every new tool
collides on, and a diff that says nothing about which tool actually
changed.

## Decision

Each tool is one module under `llm.agent_core.tools`, exposing a
module-level `TOOL: ToolDefinition` (`registry.py`). `discover_tools`
imports every module in that package whose name does not start with
`_` and collects its `TOOL`. Adding a tool means adding one such
module; nothing else is edited to register it.

`core/frontend/src/api/generated/agent-core-tool-ids.json` is a
committed, sorted snapshot of `discover_tools().keys()`.
`script/tool-ids-snapshot` regenerates it; `script/tool-ids-diff`
regenerates it into a temp file and diffs against the committed copy,
failing `script/verify` on drift.

## Rationale

1. One file per tool keeps a `ToolDefinition`'s five properties
   (schema, handler, prompt snippet, display, approval) at a single
   definition site, so adding or changing a tool touches only that
   tool's file — no shared list to edit, and no other tool's diff
   noise from an unrelated change.
2. `discover_tools`'s import-and-collect approach means the registry
   itself carries no per-tool knowledge to keep in sync; the set of
   available tools is exactly the set of modules present.
3. The frontend's tool-renderer coverage test needs the backend's
   current tool-id set as data, not as a manually maintained list
   that can silently drift from what the backend actually registers.
   A generated, committed snapshot gives it that without a live
   backend call at frontend build or test time.
4. Committing the snapshot and gating on it in `script/verify` turns
   "the frontend's tool list drifted from the backend's" into a CI
   failure with a diff, instead of a runtime gap discovered when a
   tool call arrives with no renderer.

## Trade-off accepted

The snapshot is a generated artifact checked into version control,
so every backend tool addition or removal requires a
`script/tool-ids-snapshot` run and committing its output as a
deliberate step, rather than the frontend simply reading the current
set at runtime. That extra step is what makes the drift visible as a
diff instead of a silent runtime mismatch.
