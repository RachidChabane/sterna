"""Collaborators that make up the streaming chat agent.

`llm.langchain_agent` stays the published import path (llm/views.py,
llm/__init__.py, the usage_quota tests) and composes the pieces defined
here:

- `generation_id_patch` -- LangChain monkey-patch, applied on import.
- `cost_ledger`         -- cost classification and aggregate usage rows.
- `tool_arguments` / `tool_naming` -- pure tool-payload coercions.
"""
