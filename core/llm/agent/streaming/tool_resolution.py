"""Finding the callable behind a tool name the model just emitted.

Resolver, used only by the LangChain path. Models routinely ask for a
simplified name (``notion_create_comment``) instead of the catalog id
that was bound (``mcp_custom_463_notion-create-comment``), so lookup runs
in widening circles:

1. exact match against the bound tools,
2. fuzzy match against the bound tools,
3. fuzzy match against the MCP catalog (binding the winner on the fly),
4. the local stdio MCP cache,
5. remote execution through the MCP adapter -- which returns a *result*
   rather than a callable, hence the third element of the return tuple.

Non-yielding by construction: it reports what it found and leaves every
SSE decision to the caller.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..tool_arguments import parse_json_string_values
from ..tool_naming import unsanitize_tool_name

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

MCP_TOOL_NAME_PREFIX = "mcp_"


@dataclass
class ResolvedTool:
    """Outcome of a tool lookup.

    Exactly one of `tool` / `direct_result` is meaningful; both are None
    when the name could not be resolved at all.
    """

    tool: Optional[Any] = None
    # The resolved name may differ from the requested one (fuzzy match).
    name: str = ""
    # Set when the MCP adapter executed the call itself.
    direct_result: Optional[Any] = None
    # True when the caller must re-bind tools on the model.
    tools_changed: bool = False


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


class ToolResolver:
    """Resolves a model-supplied tool name against the agent's registry."""

    def __init__(self, registry, discovery_context):
        self._registry = registry
        self._discovery_context = discovery_context

    async def resolve(self, tool_name: str, tool_args: Dict[str, Any]) -> ResolvedTool:
        tool_func = next((t for t in self._registry.tools if t.name == tool_name), None)
        if tool_func:
            return ResolvedTool(tool=tool_func, name=tool_name)

        resolved = ResolvedTool(name=tool_name)

        if self._discovery_context:
            self._fuzzy_match_loaded_tools(resolved)
            if not resolved.tool:
                self._fuzzy_match_catalog(resolved)
        if resolved.tool:
            return resolved

        if not resolved.name.startswith(MCP_TOOL_NAME_PREFIX):
            return resolved

        self._match_local_mcp_cache(resolved)
        if resolved.tool:
            return resolved

        if self._discovery_context:
            await self._execute_via_mcp_adapter(resolved, tool_args)
        return resolved

    # --- Step 2: fuzzy match against already-bound tools ---------------

    def _fuzzy_match_loaded_tools(self, resolved: ResolvedTool) -> None:
        normalized_request = _normalize(resolved.name)
        for t in self._registry.tools:
            normalized_tool = t.name.lower().replace("-", "_")
            if normalized_tool.endswith(normalized_request) or normalized_request in normalized_tool:
                logger.info(f"[LangChain] Fuzzy match: '{resolved.name}' -> '{t.name}'")
                resolved.tool = t
                resolved.name = t.name
                return

    # --- Step 3: fuzzy match against the MCP catalog ------------------

    def _fuzzy_match_catalog(self, resolved: ResolvedTool) -> None:
        normalized_request = _normalize(resolved.name)
        try:
            from llm.tool_catalog.registry import get_tool_catalog
            catalog = get_tool_catalog()
            user_id = str(self._discovery_context.user_id)

            for catalog_tool_id in catalog.list_tools(user_id=user_id):
                if not catalog_tool_id.startswith(MCP_TOOL_NAME_PREFIX):
                    continue
                normalized_catalog = catalog_tool_id.lower().replace("-", "_").replace(":", "_")
                if not (normalized_catalog.endswith(normalized_request) or normalized_request in normalized_catalog):
                    continue

                logger.info(f"[LangChain] Catalog fuzzy match: '{resolved.name}' -> '{catalog_tool_id}'")
                entry = catalog.get_entry(catalog_tool_id, user_id=user_id)
                if not (entry and entry.is_available):
                    continue
                wrapper_tool = self._registry.create_mcp_catalog_tool(catalog_tool_id, entry)
                if not wrapper_tool:
                    continue
                self._registry.tools.append(wrapper_tool)
                resolved.tool = wrapper_tool
                resolved.name = wrapper_tool.name
                self._registry.remember_catalog_entry(resolved.name, entry)
                resolved.tools_changed = True
                return
        except Exception as e:
            logger.warning(f"[LangChain] Catalog fuzzy match failed: {e}")

    # --- Step 4: local stdio MCP cache --------------------------------

    def _match_local_mcp_cache(self, resolved: ResolvedTool) -> None:
        cache = self._registry.mcp_tools_cache
        if not cache:
            return

        from mcp.utils import mcp_tools_to_langchain_tools, sanitize_tool_name

        logger.info(f"[LangChain] MCP fallback: Looking for '{resolved.name}' in local cache ({len(cache)} tools)")
        for mcp_tool_name, mcp_tool in cache.items():
            server_name = mcp_tool.server.name if hasattr(mcp_tool, 'server') and mcp_tool.server else "mcp"
            server_prefix = sanitize_tool_name(server_name).lower()
            expected_name = f"mcp_{server_prefix}_{sanitize_tool_name(mcp_tool_name)}"
            if expected_name != resolved.name:
                continue
            mcp_langchain_tools = mcp_tools_to_langchain_tools(
                [mcp_tool],
                user_id=self._discovery_context.user_id if self._discovery_context else None,
            )
            if mcp_langchain_tools:
                self._registry.tools.extend(mcp_langchain_tools)
                resolved.tool = mcp_langchain_tools[0]
                logger.info(f"[LangChain] Dynamically added MCP tool from local cache: {resolved.name}")
            return

    # --- Step 5: remote execution through the MCP adapter -------------

    async def _execute_via_mcp_adapter(self, resolved: ResolvedTool, tool_args) -> None:
        logger.info(f"[LangChain] MCP fallback: Trying remote execution via adapter for '{resolved.name}'")
        try:
            from mcp.tool_discovery_adapter import get_mcp_adapter
            from llm.tool_catalog.registry import get_tool_catalog
            adapter = get_mcp_adapter()

            # Convert the sanitized name back to the catalog/adapter format,
            # e.g. mcp_custom_463_notion-create-comment
            #   -> mcp_custom:463_notion-create-comment
            original_tool_id = unsanitize_tool_name(resolved.name)

            # Ensure display name and icon are set (the model may have
            # called the tool without ever running a search).
            if resolved.name not in self._registry.display_names:
                catalog_entry = get_tool_catalog().get_entry(
                    original_tool_id, user_id=str(self._discovery_context.user_id)
                )
                if catalog_entry:
                    self._registry.remember_catalog_entry(resolved.name, catalog_entry)

            # LLMs sometimes stringify nested objects in arguments.
            parsed_args = parse_json_string_values(tool_args)

            resolved.direct_result = await adapter.execute_mcp_tool(
                user_id=str(self._discovery_context.user_id),
                tool_id=original_tool_id,
                arguments=parsed_args,
            )
            logger.info(f"[LangChain] MCP adapter execution result: {str(resolved.direct_result)[:200]}")
        except Exception:
            logger.error("langchain.mcp_adapter_failed", exc_info=True)
            resolved.direct_result = None
