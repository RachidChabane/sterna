"""The set of tools this agent may call, and how it grows during a turn.

Registry. Owns three pieces of mutable state that the streaming loops and
the SSE layer both read:

* ``tools``           -- the LangChain tool objects bound to the model.
* ``display_names``   -- tool id -> human label shown in the UI.
* ``server_icons``    -- tool id -> MCP server icon descriptor.

plus ``mcp_tools_cache``, the stdio-server MCP tools kept for late binding.

Loading has two shapes. V2 (tool discovery) loads a small always-on set
and lets the model discover the rest through ``search_available_tools``;
V1 loads everything up front. Any failure inside the V2 path falls back
to V1 — that fallback is deliberate and preserved verbatim.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..asset_tools import ASSET_TOOLS
from ..brave_search_tools import BRAVE_SEARCH_TOOLS
from ..constants import ENABLE_PTC, ENABLE_TOOL_DISCOVERY
from ..google_maps_tools import GOOGLE_MAPS_TOOLS
from ..image_tools import IMAGE_TOOLS
from ..knowledge_base_tools import KNOWLEDGE_BASE_TOOLS
from ..langchain_file_tools import CODING_AGENT_TOOL, FILE_TOOLS, PLAN_TOOLS
from ..list_tools import LIST_TOOLS
from ..spark_tools import SPARK_TOOLS
from ..video_tools import VIDEO_TOOLS
from ..web_fetch_tools import WEB_FETCH_TOOLS
from .feature_flags import AgentFeatureFlags
from .tool_arguments import parse_json_string_values
from .tool_naming import unsanitize_tool_name

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# The file tools that stay bound even under V2 discovery: the most
# frequently used ones, which should never cost a discovery round-trip.
ALWAYS_LOADED_TOOL_NAMES = frozenset({
    "execute_code", "list_files", "read_file", "write_file", "edit_file",
    "create_directory", "delete_file", "rename_file", "run_bash",
    "update_todos", "start_preview", "stop_preview", "list_processes",
    "check_process_health",
})

SPARK_TOOL_DISPLAY_NAMES = {
    "create_spark": "Create Spark",
    "update_spark": "Update Spark",
}

KNOWLEDGE_BASE_TOOL_DISPLAY_NAMES = {
    "list_knowledge_base_documents": "List Knowledge Base",
    "query_knowledge_base": "Query Knowledge Base",
}

LIST_TOOL_DISPLAY_NAMES = {
    "list_sparks": "List Sparks",
    "list_generated_images": "List Images",
    "list_generated_videos": "List Videos",
    "list_voice_rooms": "List Voice Rooms",
    "list_mcp_servers": "List MCP Servers",
    "list_available_models": "List AI Models",
    "list_coding_agents": "List Coding Agents",
    "update_coding_agent": "Update Coding Agent",
}

ASSET_TOOL_DISPLAY_NAMES = {
    "get_image": "Get Image",
    "get_video": "Get Video",
    "get_spark": "Get Spark",
    "get_document": "Get Document",
    "export_asset": "Export Asset",
    "save_asset_to_workspace": "Save to Workspace",
}

# Timeout for the sync bridge around an async MCP catalog tool call.
MCP_SYNC_EXECUTION_TIMEOUT_SECONDS = 120
# Server id used when an MCP tool carries no server relation.
FALLBACK_MCP_SERVER_ID = "mcp"


class AgentToolRegistry:
    """Owns the agent's tool set and every path that extends it."""

    def __init__(
        self,
        flags: AgentFeatureFlags,
        discovery_service=None,
        discovery_context=None,
    ):
        self._flags = flags
        self._discovery_service = discovery_service
        self._discovery_context = discovery_context

        self.tools: List[Any] = []
        # Mapping of tool_id -> display_name for user-friendly UI display
        self.display_names: Dict[str, str] = {}
        # Mapping of tool_id -> server icon info (url, invert) for MCP tools
        self.server_icons: Dict[str, Dict[str, Any]] = {}
        # Cache for dynamic MCP tool binding
        self.mcp_tools_cache: Dict[str, Any] = {}
        self.ptc_enabled = False

    # --- Initial load -------------------------------------------------

    def load_initial_tools(self) -> None:
        """Populate `tools` for this turn (V2 discovery set, or V1 all)."""
        if ENABLE_TOOL_DISCOVERY and self._discovery_context:
            try:
                self._load_discovery_tools()
                return
            except Exception as e:
                logger.warning(f"[LangChain] V2 Tool Discovery setup failed: {e}, falling back to V1")
                self._load_all_tools(log_counts=False)
                return

        self._load_all_tools(log_counts=True)

    def _load_discovery_tools(self) -> None:
        """V2: only search_available_tools + the user-facing essentials."""
        # Lazy import to avoid circular imports
        from ..tool_discovery import create_tool_search_tool, create_get_tool_details_tool

        self.tools.append(create_tool_search_tool(
            discovery_service=self._discovery_service,
            context=self._discovery_context,
        ))
        logger.info("[LangChain] V2 search_available_tools enabled")

        # get_tool_details gives full schema access when needed
        self.tools.append(create_get_tool_details_tool(
            discovery_service=self._discovery_service,
            context=self._discovery_context,
        ))
        logger.info("[LangChain] V2 get_tool_details enabled")

        if self._flags.file_tools:
            essential_file_tools = [t for t in FILE_TOOLS if t.name in ALWAYS_LOADED_TOOL_NAMES]
            self.tools.extend(essential_file_tools)
            logger.info(f"[LangChain] V2 loaded {len(essential_file_tools)} essential file tools (others via discovery)")

        # Pre-load Brave Search when enabled - these are user-facing features
        # that users explicitly enable, they should work immediately without discovery
        if self._flags.brave_search:
            self.tools.extend(BRAVE_SEARCH_TOOLS)
            self.tools.extend(WEB_FETCH_TOOLS)
            logger.info(f"[LangChain] V2 loaded {len(BRAVE_SEARCH_TOOLS)} Brave Search tools + {len(WEB_FETCH_TOOLS)} Web Fetch tools")

        # Pre-load Google Maps when enabled - same reasoning as Brave Search
        if self._flags.google_maps:
            self.tools.extend(GOOGLE_MAPS_TOOLS)
            logger.info(f"[LangChain] V2 loaded {len(GOOGLE_MAPS_TOOLS)} Google Maps tools")

        # Pre-load image and video generation tools since they're user-facing
        # features that users explicitly enable
        if self._flags.image_generation:
            self.tools.extend(IMAGE_TOOLS)
            logger.info(f"[LangChain] V2 loaded {len(IMAGE_TOOLS)} Image Generation tools")
        if self._flags.video_generation:
            self.tools.extend(VIDEO_TOOLS)
            logger.info(f"[LangChain] V2 loaded {len(VIDEO_TOOLS)} Video Generation tools")
        if self._flags.sparks:
            self.tools.extend(SPARK_TOOLS)
            self.display_names.update(SPARK_TOOL_DISPLAY_NAMES)
            logger.info(f"[LangChain] V2 loaded {len(SPARK_TOOLS)} Spark tools")

        if self._flags.knowledge_base:
            self.tools.extend(KNOWLEDGE_BASE_TOOLS)
            self.display_names.update(KNOWLEDGE_BASE_TOOL_DISPLAY_NAMES)
            logger.info(f"[LangChain] V2 loaded {len(KNOWLEDGE_BASE_TOOLS)} Knowledge Base tools")

        # Always add list tools for resource discovery
        self.tools.extend(LIST_TOOLS)
        self.display_names.update(LIST_TOOL_DISPLAY_NAMES)
        logger.info(f"[LangChain] V2 loaded {len(LIST_TOOLS)} List tools")

        # Asset access tools for reading images, videos, sparks, documents
        self.tools.extend(ASSET_TOOLS)
        self.display_names.update(ASSET_TOOL_DISPLAY_NAMES)
        logger.info(f"[LangChain] V2 loaded {len(ASSET_TOOLS)} Asset access tools")

        if self._flags.file_tools:
            self.tools.append(CODING_AGENT_TOOL)
            self.tools.extend(PLAN_TOOLS)
            logger.info("[LangChain] V2 Added Coding Agent + Plan tools")

        # V2 PTC: execute_programming_task for complex file operations
        if ENABLE_PTC and self._flags.file_tools:
            try:
                self.ptc_enabled = True
                logger.info("[LangChain] V2 PTC enabled for complex programming tasks")
            except Exception as ptc_e:
                logger.warning(f"[LangChain] PTC setup failed: {ptc_e}")
                self.ptc_enabled = False

    def _load_all_tools(self, *, log_counts: bool) -> None:
        """V1: load every enabled tool upfront.

        Also the fallback when the V2 discovery setup raises. `log_counts`
        distinguishes the two: the fallback path stays quiet about counts,
        exactly as it did inline.
        """
        if self._flags.file_tools:
            self.tools.extend(FILE_TOOLS)
        if self._flags.brave_search:
            self.tools.extend(BRAVE_SEARCH_TOOLS)
            self.tools.extend(WEB_FETCH_TOOLS)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(BRAVE_SEARCH_TOOLS)} Brave Search + {len(WEB_FETCH_TOOLS)} Web Fetch tools")
        if self._flags.google_maps:
            self.tools.extend(GOOGLE_MAPS_TOOLS)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(GOOGLE_MAPS_TOOLS)} Google Maps tools")
        if self._flags.image_generation:
            self.tools.extend(IMAGE_TOOLS)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(IMAGE_TOOLS)} Image Generation tools")
        if self._flags.video_generation:
            self.tools.extend(VIDEO_TOOLS)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(VIDEO_TOOLS)} Video Generation tools")
        if self._flags.sparks:
            self.tools.extend(SPARK_TOOLS)
            self.display_names.update(SPARK_TOOL_DISPLAY_NAMES)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(SPARK_TOOLS)} Spark tools")
        if self._flags.knowledge_base:
            self.tools.extend(KNOWLEDGE_BASE_TOOLS)
            self.display_names.update(KNOWLEDGE_BASE_TOOL_DISPLAY_NAMES)
            if log_counts:
                logger.info(f"[LangChain] Enabled {len(KNOWLEDGE_BASE_TOOLS)} Knowledge Base tools")

        # Always add list tools (they use KB context for user info)
        self.tools.extend(LIST_TOOLS)
        self.display_names.update(LIST_TOOL_DISPLAY_NAMES)
        if log_counts:
            logger.info(f"[LangChain] Enabled {len(LIST_TOOLS)} List tools")

        # Asset access tools for reading images, videos, sparks, documents
        self.tools.extend(ASSET_TOOLS)
        self.display_names.update(ASSET_TOOL_DISPLAY_NAMES)
        if log_counts:
            logger.info(f"[LangChain] Enabled {len(ASSET_TOOLS)} Asset access tools")

        if self._flags.file_tools:
            self.tools.append(CODING_AGENT_TOOL)
            self.tools.extend(PLAN_TOOLS)
            logger.info(
                "[LangChain] V1 Enabled Coding Agent + Plan tools"
                if log_counts
                else "[LangChain] Added Coding Agent + Plan tools (fallback)"
            )

    # --- MCP registration ---------------------------------------------

    def register_mcp_tools(self, mcp_tools: List[Any], user_id: Optional[str]) -> None:
        """Make the user's MCP tools reachable for this turn.

        Under V2 they are registered in the catalog (discoverable on
        demand); otherwise they are converted and bound immediately.
        """
        if not mcp_tools:
            return

        if ENABLE_TOOL_DISCOVERY and self._discovery_context:
            try:
                self._register_mcp_tools_in_catalog(mcp_tools, user_id)
            except Exception as e:
                logger.warning(f"[LangChain] V2 MCP registration failed: {e}, falling back to V1 direct loading")
                self._load_mcp_tools_directly(mcp_tools, user_id, v1_legacy=False)
            return

        self._load_mcp_tools_directly(mcp_tools, user_id, v1_legacy=True)

    def _register_mcp_tools_in_catalog(self, mcp_tools: List[Any], user_id: Optional[str]) -> None:
        from mcp.tool_discovery_adapter import get_mcp_adapter
        mcp_adapter = get_mcp_adapter()

        for mcp_tool in mcp_tools:
            # Use proper server_id format: "custom:{db_id}" for UnifiedMCPRegistry compatibility
            if hasattr(mcp_tool, 'server') and mcp_tool.server:
                server_id = f"custom:{mcp_tool.server.id}"
            else:
                server_id = FALLBACK_MCP_SERVER_ID

            # Get server name for searchability
            server_name = mcp_tool.server.name if hasattr(mcp_tool, 'server') and mcp_tool.server else None

            tool_def = mcp_adapter._convert_mcp_tools(
                mcp_tools=[{
                    "name": mcp_tool.name,
                    "description": mcp_tool.description,
                    "inputSchema": mcp_tool.input_schema,
                }],
                server_id=server_id,
                user_id=user_id or "anonymous",
                server_name=server_name,
            )
            for td in tool_def:
                mcp_adapter.tool_catalog.register_dynamic_tool(td, user_id=user_id)
                # td.id is the function name, td.name is the display name
                self.display_names[td.id] = td.name
                if hasattr(mcp_tool, 'server') and mcp_tool.server:
                    server = mcp_tool.server
                    if server.icon_url:
                        self.server_icons[td.id] = {
                            "url": server.icon_url,
                            "invert": getattr(server, 'icon_invert_in_dark_mode', False),
                        }

        # Store MCP tools for later dynamic binding
        self.mcp_tools_cache = {t.name: t for t in mcp_tools}
        logger.info(f"[LangChain] V2 Registered {len(mcp_tools)} MCP tools in catalog (available via discovery)")

    def _load_mcp_tools_directly(self, mcp_tools: List[Any], user_id: Optional[str], *, v1_legacy: bool) -> None:
        try:
            from mcp.utils import mcp_tools_to_langchain_tools
            mcp_langchain_tools = mcp_tools_to_langchain_tools(mcp_tools, user_id=user_id)
            self.tools.extend(mcp_langchain_tools)
            if v1_legacy:
                logger.info(f"[LangChain] V1 Enabled {len(mcp_langchain_tools)} MCP tools from {len(mcp_tools)} MCP definitions")
            else:
                logger.info(f"[LangChain] V1 Enabled {len(mcp_langchain_tools)} MCP tools")
        except Exception:
            logger.error("langchain.mcp_tools_load_failed", exc_info=True)

    # --- Growth during a turn -----------------------------------------

    def add_discovered(self, tool_ids: List[str]) -> List[str]:
        """Bind tools the model just found via `search_available_tools`.

        Returns the names actually added (empty when nothing changed, so
        the caller can skip re-binding the model).
        """
        if not tool_ids or not self._discovery_context:
            return []

        added_tools: List[str] = []

        for tool_id in tool_ids:
            if tool_id:
                self._discovery_context.add_discovered_tool(tool_id)

        if self._flags.brave_search:
            self._add_matching(BRAVE_SEARCH_TOOLS, tool_ids, added_tools)
            self._add_matching(WEB_FETCH_TOOLS, tool_ids, added_tools)
        if self._flags.google_maps:
            self._add_matching(GOOGLE_MAPS_TOOLS, tool_ids, added_tools)
        if self._flags.image_generation:
            self._add_matching(IMAGE_TOOLS, tool_ids, added_tools)
        if self._flags.video_generation:
            self._add_matching(VIDEO_TOOLS, tool_ids, added_tools)

        if self._flags.mcp_tools:
            try:
                self._add_discovered_mcp_tools(tool_ids, added_tools)
            except Exception:
                logger.error("langchain.mcp_discovered_tools_failed", exc_info=True)

        if added_tools:
            logger.info(f"[LangChain] Added discovered tools: {added_tools}")
        return added_tools

    def _add_matching(self, candidates, tool_ids: List[str], added_tools: List[str]) -> None:
        for tool in candidates:
            if tool.name in tool_ids and tool not in self.tools:
                self.tools.append(tool)
                added_tools.append(tool.name)

    def _add_discovered_mcp_tools(self, tool_ids: List[str], added_tools: List[str]) -> None:
        existing_tool_names = {t.name for t in self.tools}

        # First, check local cache (stdio-based MCP servers)
        if self.mcp_tools_cache:
            self._add_cached_mcp_tools(tool_ids, added_tools, existing_tool_names)

        # Second, check catalog for OAuth-based MCP tools (like Notion).
        # These need wrapper tools that call the adapter.
        if not self._discovery_context:
            return

        from llm.tool_catalog.registry import get_tool_catalog
        catalog = get_tool_catalog()

        for tool_id in tool_ids:
            # Sanitize for Anthropic compatibility (only [a-zA-Z0-9_-] allowed)
            sanitized_id = tool_id.replace(":", "_")
            # Unsanitize for catalog lookup (catalog uses the colon format)
            original_id = unsanitize_tool_name(tool_id)

            if not tool_id.startswith("mcp_") or sanitized_id in existing_tool_names:
                continue
            entry = catalog.get_entry(original_id, user_id=str(self._discovery_context.user_id))
            if not (entry and entry.is_available):
                continue
            # Pass original_id so execution uses the correct format
            wrapper_tool = self.create_mcp_catalog_tool(original_id, entry)
            if not wrapper_tool:
                continue
            self.tools.append(wrapper_tool)
            added_tools.append(sanitized_id)
            existing_tool_names.add(sanitized_id)
            self.remember_catalog_entry(sanitized_id, entry)

        if added_tools:
            logger.info(f"[LangChain] Dynamically added MCP tools from catalog: {added_tools}")

    def _add_cached_mcp_tools(self, tool_ids, added_tools, existing_tool_names) -> None:
        from mcp.utils import mcp_tools_to_langchain_tools, sanitize_tool_name

        mcp_tools_to_add = []
        for tool_id in tool_ids:
            for mcp_tool_name, mcp_tool in self.mcp_tools_cache.items():
                if mcp_tool_name in tool_id or tool_id.endswith(mcp_tool_name):
                    server_prefix = sanitize_tool_name(mcp_tool.server.name).lower() if hasattr(mcp_tool, 'server') else FALLBACK_MCP_SERVER_ID
                    langchain_name = f"mcp_{server_prefix}_{sanitize_tool_name(mcp_tool_name)}"
                    if langchain_name not in existing_tool_names:
                        mcp_tools_to_add.append(mcp_tool)
                        existing_tool_names.add(langchain_name)

        if not mcp_tools_to_add:
            return

        langchain_tools = mcp_tools_to_langchain_tools(
            mcp_tools_to_add,
            user_id=self._discovery_context.user_id if self._discovery_context else None,
        )
        self.tools.extend(langchain_tools)
        added_tools.extend([t.name for t in langchain_tools])

        for mcp_tool in mcp_tools_to_add:
            server_prefix = sanitize_tool_name(mcp_tool.server.name).lower() if hasattr(mcp_tool, 'server') else FALLBACK_MCP_SERVER_ID
            langchain_name = f"mcp_{server_prefix}_{sanitize_tool_name(mcp_tool.name)}"
            self.display_names[langchain_name] = mcp_tool.name.replace("_", " ").title()
            if hasattr(mcp_tool, 'server') and mcp_tool.server and mcp_tool.server.icon_url:
                self.server_icons[langchain_name] = {
                    "url": mcp_tool.server.icon_url,
                    "invert": getattr(mcp_tool.server, 'icon_invert_in_dark_mode', False),
                }

        logger.info(f"[LangChain] Dynamically added {len(langchain_tools)} MCP tools from local cache")

    def preload_from_context(self) -> List[str]:
        """Re-bind MCP tools discovered in earlier turns of this conversation.

        Uses the ToolDiscoveryContext's `discovered_tool_ids`, which
        persists across messages. Returns the names actually added.
        """
        if not self._discovery_context:
            return []

        discovered_ids = self._discovery_context.discovered_tool_ids
        if not discovered_ids:
            logger.info("[LangChain] Pre-load: No previously discovered tools in context")
            return []

        # Filter for MCP tools and normalize to sanitized format (underscores)
        used_tool_names = {
            tid.replace(":", "_") for tid in discovered_ids if tid.startswith("mcp_")
        }

        logger.info(f"[LangChain] Pre-load: Found {len(used_tool_names)} MCP tools in context: {list(used_tool_names)[:5]}...")

        if not used_tool_names:
            return []

        try:
            from llm.tool_catalog.registry import get_tool_catalog
            catalog = get_tool_catalog()
            user_id = str(self._discovery_context.user_id)

            # Existing tool names (all in sanitized format) to avoid duplicates
            existing_tool_names = {t.name for t in self.tools}
            added_tools: List[str] = []

            for sanitized_name in used_tool_names:
                if sanitized_name in existing_tool_names:
                    continue

                original_id = unsanitize_tool_name(sanitized_name)
                entry = catalog.get_entry(original_id, user_id=user_id)
                if not (entry and entry.is_available):
                    continue

                wrapper_tool = self.create_mcp_catalog_tool(original_id, entry)
                if not wrapper_tool or wrapper_tool.name in existing_tool_names:
                    continue

                self.tools.append(wrapper_tool)
                added_tools.append(wrapper_tool.name)
                existing_tool_names.add(wrapper_tool.name)
                self.remember_catalog_entry(wrapper_tool.name, entry)

            if added_tools:
                logger.info(f"[LangChain] Pre-loaded {len(added_tools)} tools from context: {added_tools}")
            return added_tools

        except Exception as e:
            logger.warning(f"[LangChain] Failed to pre-load tools from history: {e}")
            return []

    def remember_catalog_entry(self, tool_name: str, entry) -> None:
        """Record the UI label and MCP server icon for a catalog tool."""
        self.display_names[tool_name] = entry.definition.name
        if entry.mcp_server_icon:
            self.server_icons[tool_name] = {
                "url": entry.mcp_server_icon,
                "invert": entry.mcp_server_icon_invert,
            }

    def remember_search_result_metadata(self, tools_list: List[Dict[str, Any]]) -> None:
        """Record display names / icons carried by search_available_tools rows."""
        for tool_info in tools_list:
            func_name = tool_info.get("function_name")
            if not func_name:
                continue
            # Sanitize for Anthropic compatibility
            sanitized_name = func_name.replace(":", "_")
            display_name = tool_info.get("name")
            if display_name:
                self.display_names[sanitized_name] = display_name
            server_icon = tool_info.get("server_icon")
            if server_icon:
                self.server_icons[sanitized_name] = {
                    "url": server_icon,
                    "invert": tool_info.get("server_icon_invert", False),
                }

    def create_mcp_catalog_tool(self, tool_id: str, entry):
        """
        Create a LangChain tool wrapper for a catalog-based MCP tool.

        This allows OAuth-based MCP tools (like Notion) to be called directly
        by the model without going through the fallback path.

        Args:
            tool_id: The tool ID (e.g., mcp_custom:463_notion-create-comment)
            entry: The ToolCatalogEntry from the catalog

        Returns:
            A LangChain StructuredTool or None if creation fails
        """
        try:
            from langchain_core.tools import StructuredTool
            from mcp.tool_discovery_adapter import get_mcp_adapter

            tool_def = entry.definition
            user_id = str(self._discovery_context.user_id) if self._discovery_context else None

            async def execute_mcp_tool(**kwargs):
                adapter = get_mcp_adapter()
                # Unwrap if the LLM wrapped arguments in a 'kwargs' key.
                # Happens when args_schema=None and the LLM bundles all args there.
                if 'kwargs' in kwargs and len(kwargs) == 1 and isinstance(kwargs['kwargs'], dict):
                    kwargs = kwargs['kwargs']
                parsed_args = parse_json_string_values(kwargs)
                return await adapter.execute_mcp_tool(
                    user_id=user_id,
                    tool_id=tool_id,
                    arguments=parsed_args,
                )

            def sync_execute(**kwargs):
                """Sync bridge LangChain calls when it cannot await."""
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(execute_mcp_tool(**kwargs), loop)
                        return future.result(timeout=MCP_SYNC_EXECUTION_TIMEOUT_SECONDS)
                    return loop.run_until_complete(execute_mcp_tool(**kwargs))
                except RuntimeError:
                    return asyncio.run(execute_mcp_tool(**kwargs))

            # Anthropic only allows [a-zA-Z0-9_-]: replace colons with underscores
            sanitized_name = tool_id.replace(":", "_")

            return StructuredTool.from_function(
                func=sync_execute,
                coroutine=execute_mcp_tool,
                name=sanitized_name,
                description=tool_def.description,
                args_schema=None,  # Will use kwargs
            )

        except Exception:
            logger.error(
                "langchain.mcp_catalog_tool_create_failed",
                extra={"tool_id": tool_id},
                exc_info=True,
            )
            return None
