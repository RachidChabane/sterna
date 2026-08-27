"""
Tool Catalog Registry

Centralized registry for all tool definitions.
Provides lookup, filtering, and management of tools from all providers.
"""

import logging
from typing import List, Optional, Dict, Set, Any
import threading

from .models import (
    ToolDefinition,
    ToolCatalogEntry,
    ToolCategory,
    ToolProvider,
    LoadingStrategy,
)
from .core_tools import CORE_TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


class ToolCatalogRegistry:
    """
    Centralized registry for tool definitions.

    Manages:
    - Core built-in tools
    - System MCP tools
    - User-specific MCP tools (per-user isolation)

    Thread-safe for concurrent access.
    """

    _instance: Optional['ToolCatalogRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'ToolCatalogRegistry':
        """Singleton pattern for global registry access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the registry with core tools."""
        if self._initialized:
            return

        self._catalog: Dict[str, ToolCatalogEntry] = {}
        self._user_tools: Dict[str, Dict[str, ToolCatalogEntry]] = {}  # user_id -> {tool_id -> entry}
        self._category_index: Dict[ToolCategory, Set[str]] = {}
        self._feature_index: Dict[str, Set[str]] = {}  # feature_flag -> tool_ids
        self._provider_index: Dict[ToolProvider, Set[str]] = {}
        self._registry_lock = threading.RLock()

        # Load core tools
        self._load_core_tools()
        self._initialized = True

        logger.info(f"[ToolCatalog] Initialized with {len(self._catalog)} core tools")

    def _load_core_tools(self):
        """Load all core tool definitions into the registry."""
        for tool_def in CORE_TOOL_DEFINITIONS:
            entry = ToolCatalogEntry(definition=tool_def)
            self._register_entry(entry)

    def _register_entry(self, entry: ToolCatalogEntry):
        """Register a tool entry and update indexes."""
        tool_id = entry.definition.id

        with self._registry_lock:
            self._catalog[tool_id] = entry

            # Update category index
            category = entry.definition.category
            if category not in self._category_index:
                self._category_index[category] = set()
            self._category_index[category].add(tool_id)

            # Update feature index
            feature = entry.definition.feature_flag
            if feature:
                if feature not in self._feature_index:
                    self._feature_index[feature] = set()
                self._feature_index[feature].add(tool_id)

            # Update provider index
            provider = entry.definition.provider
            if provider not in self._provider_index:
                self._provider_index[provider] = set()
            self._provider_index[provider].add(tool_id)

    def get_tool(self, tool_id: str, user_id: Optional[str] = None) -> Optional[ToolDefinition]:
        """
        Get a tool definition by ID.

        Args:
            tool_id: Tool identifier
            user_id: Optional user ID to also search user-specific tools (e.g., MCP tools)

        Returns:
            ToolDefinition or None if not found
        """
        with self._registry_lock:
            # First check main catalog
            entry = self._catalog.get(tool_id)
            if entry:
                return entry.definition

            # Then check user-specific tools
            if user_id and user_id in self._user_tools:
                user_entry = self._user_tools[user_id].get(tool_id)
                if user_entry:
                    return user_entry.definition

            return None

    def get_entry(self, tool_id: str, user_id: Optional[str] = None) -> Optional[ToolCatalogEntry]:
        """
        Get a full catalog entry by ID.

        Args:
            tool_id: Tool identifier
            user_id: Optional user ID to also search user-specific tools

        Returns:
            ToolCatalogEntry or None if not found
        """
        with self._registry_lock:
            # First check main catalog
            entry = self._catalog.get(tool_id)
            if entry:
                return entry

            # Then check user-specific tools
            if user_id and user_id in self._user_tools:
                return self._user_tools[user_id].get(tool_id)

            return None

    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tool definitions."""
        with self._registry_lock:
            return [entry.definition for entry in self._catalog.values()]

    def list_tools(self, user_id: Optional[str] = None) -> List[str]:
        """
        List all tool IDs in the catalog.

        Args:
            user_id: Optional user ID to include user-specific tools

        Returns:
            List of tool IDs (strings)
        """
        with self._registry_lock:
            result = list(self._catalog.keys())

            # Include user-specific tools
            if user_id and user_id in self._user_tools:
                result.extend(self._user_tools[user_id].keys())

            return result

    def get_tools_by_category(self, category: ToolCategory) -> List[ToolDefinition]:
        """
        Get all tools in a category.

        Args:
            category: Tool category

        Returns:
            List of tool definitions
        """
        with self._registry_lock:
            tool_ids = self._category_index.get(category, set())
            return [
                self._catalog[tid].definition
                for tid in tool_ids
                if tid in self._catalog
            ]

    def get_tools_by_feature(self, feature_flag: str) -> List[ToolDefinition]:
        """
        Get all tools for a feature flag.

        Args:
            feature_flag: Feature flag (e.g., "brave_search", "file_tools")

        Returns:
            List of tool definitions
        """
        with self._registry_lock:
            tool_ids = self._feature_index.get(feature_flag, set())
            return [
                self._catalog[tid].definition
                for tid in tool_ids
                if tid in self._catalog
            ]

    def get_tools_by_provider(self, provider: ToolProvider) -> List[ToolDefinition]:
        """
        Get all tools from a provider.

        Args:
            provider: Tool provider

        Returns:
            List of tool definitions
        """
        with self._registry_lock:
            tool_ids = self._provider_index.get(provider, set())
            return [
                self._catalog[tid].definition
                for tid in tool_ids
                if tid in self._catalog
            ]

    def get_always_loaded_tools(
        self,
        enabled_features: Optional[Set[str]] = None
    ) -> List[ToolDefinition]:
        """
        Get tools that should always be loaded.

        Args:
            enabled_features: Set of enabled feature flags

        Returns:
            List of always-loaded tool definitions
        """
        enabled_features = enabled_features or set()

        with self._registry_lock:
            result = []
            for entry in self._catalog.values():
                tool_def = entry.definition

                # Check loading strategy
                if tool_def.loading_strategy != LoadingStrategy.ALWAYS:
                    continue

                # Check feature flag
                if tool_def.feature_flag and tool_def.feature_flag not in enabled_features:
                    continue

                # Check availability
                if not entry.is_available:
                    continue

                result.append(tool_def)

            # Sort by priority
            result.sort(key=lambda t: t.priority)
            return result

    def get_on_demand_tools(
        self,
        enabled_features: Optional[Set[str]] = None
    ) -> List[ToolDefinition]:
        """
        Get tools available for on-demand discovery.

        Args:
            enabled_features: Set of enabled feature flags

        Returns:
            List of on-demand tool definitions
        """
        enabled_features = enabled_features or set()

        with self._registry_lock:
            result = []
            for entry in self._catalog.values():
                tool_def = entry.definition

                # Check loading strategy
                if tool_def.loading_strategy != LoadingStrategy.ON_DEMAND:
                    continue

                # Check feature flag
                if tool_def.feature_flag and tool_def.feature_flag not in enabled_features:
                    continue

                # Check availability
                if not entry.is_available:
                    continue

                result.append(tool_def)

            return result

    def get_available_tools(
        self,
        enabled_features: Set[str],
        include_always_loaded: bool = True,
        include_on_demand: bool = True,
    ) -> List[ToolDefinition]:
        """
        Get all available tools based on enabled features.

        Args:
            enabled_features: Set of enabled feature flags
            include_always_loaded: Include always-loaded tools
            include_on_demand: Include on-demand tools

        Returns:
            List of available tool definitions
        """
        result = []

        if include_always_loaded:
            result.extend(self.get_always_loaded_tools(enabled_features))

        if include_on_demand:
            result.extend(self.get_on_demand_tools(enabled_features))

        return result

    def get_all_searchable_tools(self, user_id: Optional[str] = None) -> List[ToolDefinition]:
        """
        Get all tools that can be searched/discovered, regardless of enabled features.

        This allows users to discover what tools are available even if the
        required feature isn't enabled or they haven't connected to a server.
        The discovery service will mark tools appropriately for display.

        Args:
            user_id: Optional user ID to include user-specific tools (e.g., MCP tools)

        Returns:
            List of all tool definitions (including those not yet connected)
        """
        with self._registry_lock:
            result = []

            # Include global catalog tools
            for entry in self._catalog.values():
                # Skip deprecated tools
                if entry.is_deprecated:
                    continue

                # Include all loading strategies for discovery
                result.append(entry.definition)

            # Include user-specific tools (e.g., MCP tools)
            if user_id:
                # Load tools from DB if not in memory cache
                self._ensure_user_tools_loaded(user_id)

                if user_id in self._user_tools:
                    for entry in self._user_tools[user_id].values():
                        # Include ALL tools - even not connected ones
                        # The discovery service will check is_available for connection status
                        if not entry.is_deprecated:
                            result.append(entry.definition)

            return result

    def invalidate_user_tools_cache(self, user_id: str):
        """
        Invalidate the user tools cache to force reload from database.

        Call this when:
        - User connects/disconnects from a server
        - Tools are discovered/refreshed
        - Server configuration changes
        """
        with self._registry_lock:
            if user_id in self._user_tools:
                del self._user_tools[user_id]
            # Also clear the preconfigured loaded marker
            cache_key = f"_preconfigured_loaded_{user_id}"
            if hasattr(self, cache_key):
                delattr(self, cache_key)
            logger.info(f"[ToolCatalog] Invalidated tools cache for user {user_id}")

    def _ensure_user_tools_loaded(self, user_id: str):
        """
        Load user's MCP tools from database if not already in cache.

        This loads:
        1. User's own custom server tools (connected servers)
        2. Tools from preconfigured servers (both connected and not connected)

        For preconfigured servers the user hasn't connected to, tools are
        marked with is_available=False so the LLM can suggest connecting.

        This ensures tools persist across server restarts.
        """
        # Check if preconfigured server tools have been loaded
        # We use a special marker to track this since _user_tools might be
        # populated by V2 registration before this is called
        cache_key = f"_preconfigured_loaded_{user_id}"
        if hasattr(self, cache_key) and getattr(self, cache_key):
            return
        setattr(self, cache_key, True)

        try:
            # Import here to avoid circular imports
            from mcp.models import MCPServer
            from mcp.tool_discovery_adapter import get_mcp_adapter

            # NOTE: Django ORM queries are safe in async contexts (they block the thread).
            # We load preconfigured tools here to supplement runtime-discovered tools,
            # ensuring users can discover all capabilities even if some aren't available at runtime.

            adapter = get_mcp_adapter()
            tools_loaded = 0

            logger.info(f"[ToolCatalog] Loading MCP tools from DB for user {user_id}")

            # 1. Load user's own custom server tools (connected)
            user_servers = MCPServer.objects.filter(
                user_id=user_id,
                is_active=True,
                is_preconfigured=False,
            ).prefetch_related('tools')

            for server in user_servers:
                db_tools = server.tools.all()  # type: ignore[attr-defined]  # reverse FK, needs django-stubs plugin
                if not db_tools.exists():
                    continue

                mcp_tools = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in db_tools
                ]

                # Use proper server_id format for UnifiedMCPRegistry compatibility
                # Format: "custom:{db_id}" matches what UnifiedMCPRegistry expects
                proper_server_id = f"custom:{server.pk}"
                converted = adapter._convert_mcp_tools(
                    mcp_tools=mcp_tools,
                    server_id=proper_server_id,
                    user_id=user_id,
                    server_name=server.name,  # For searchability and category inference
                )

                for tool in converted:
                    # Add server name to tags and keywords for searchability
                    tool.tags.append(f"server:{server.name}")
                    tool.tags.append(server.name.lower())
                    if server.name.lower() not in tool.search_keywords:
                        tool.search_keywords.append(server.name.lower())

                    with self._registry_lock:
                        if user_id not in self._user_tools:
                            self._user_tools[user_id] = {}

                        # Don't overwrite entries that are already available (have runtime callables)
                        existing_entry = self._user_tools[user_id].get(tool.id)
                        if existing_entry and existing_entry.is_available:
                            # Already registered with runtime callable, just update metadata
                            existing_entry.mcp_server_id = str(server.pk)
                            existing_entry.mcp_server_name = server.name
                            existing_entry.mcp_server_icon = server.icon_url
                            existing_entry.mcp_server_icon_invert = getattr(server, 'icon_invert_in_dark_mode', False)
                        else:
                            # Create entry with is_available=False (no runtime callable yet)
                            entry = ToolCatalogEntry(
                                definition=tool,
                                user_id=user_id,
                                discovered_in_session=True,
                                is_available=False,  # Will be updated by V2 registration if runtime available
                                mcp_server_id=str(server.pk),
                                mcp_server_name=server.name,
                                mcp_server_icon=server.icon_url,
                                mcp_server_icon_invert=getattr(server, 'icon_invert_in_dark_mode', False),
                            )
                            self._user_tools[user_id][tool.id] = entry
                    tools_loaded += 1

            # 2. Load tools from preconfigured servers
            # First, find which preconfigured servers the user has connected to
            # (user has a copy with same npm_package or remote_url)
            user_connected_packages = set(
                MCPServer.objects.filter(
                    user_id=user_id,
                    is_active=True,
                    npm_package__isnull=False,
                ).exclude(npm_package='').values_list('npm_package', flat=True)
            )
            user_connected_urls = set(
                MCPServer.objects.filter(
                    user_id=user_id,
                    is_active=True,
                    remote_url__isnull=False,
                ).values_list('remote_url', flat=True)
            )

            # Get all preconfigured servers with tools
            preconfigured_servers = MCPServer.objects.filter(
                is_preconfigured=True,
                is_active=True,
            ).prefetch_related('tools')

            logger.info(f"[ToolCatalog] Found {preconfigured_servers.count()} preconfigured servers to check")

            for server in preconfigured_servers:
                db_tools = server.tools.all()  # type: ignore[attr-defined]
                tool_count = db_tools.count()
                if tool_count == 0:
                    logger.debug(f"[ToolCatalog] Server '{server.name}' has no tools, skipping")
                    continue
                logger.info(f"[ToolCatalog] Loading {tool_count} tools from preconfigured '{server.name}'")

                # Check if user is connected to this preconfigured server
                # and find the user's actual server instance for execution routing
                is_connected = False
                user_server_id = None  # The user's connected server ID for execution

                if server.npm_package and server.npm_package in user_connected_packages:
                    is_connected = True
                    # Find the user's actual server by npm_package
                    user_server = MCPServer.objects.filter(
                        user_id=user_id,
                        is_active=True,
                        npm_package=server.npm_package,
                    ).first()
                    if user_server:
                        user_server_id = user_server.pk
                elif server.remote_url and server.remote_url in user_connected_urls:
                    is_connected = True
                    # Find the user's actual server by remote_url
                    user_server = MCPServer.objects.filter(
                        user_id=user_id,
                        is_active=True,
                        remote_url=server.remote_url,
                    ).first()
                    if user_server:
                        user_server_id = user_server.pk

                mcp_tools = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in db_tools
                ]

                # Use proper server_id format for UnifiedMCPRegistry compatibility
                # Format: "custom:{db_id}" - use USER's server ID if connected, otherwise preconfigured
                # This ensures execution routes to the user's OAuth-authenticated server instance
                execution_server_id = user_server_id if user_server_id else server.pk
                proper_server_id = f"custom:{execution_server_id}"
                converted = adapter._convert_mcp_tools(
                    mcp_tools=mcp_tools,
                    server_id=proper_server_id,
                    user_id=user_id,
                    server_name=server.name,  # For searchability and category inference
                )

                for tool in converted:
                    # Mark tool with connection status
                    tool.feature_flag = "mcp_tools"  # Keep feature flag
                    # Always add server name to tags for searchability
                    tool.tags.append(f"server:{server.name}")
                    tool.tags.append(server.name.lower())
                    # Add server name to keywords for better search
                    if server.name.lower() not in tool.search_keywords:
                        tool.search_keywords.append(server.name.lower())
                    if not is_connected:
                        # Add metadata for unavailable tools
                        tool.tags.append("not_connected")

                    # Store with custom metadata for connection hints
                    with self._registry_lock:
                        if user_id not in self._user_tools:
                            self._user_tools[user_id] = {}

                        # Don't overwrite entries that are already available (have runtime callables)
                        existing_entry = self._user_tools[user_id].get(tool.id)
                        if existing_entry and existing_entry.is_available:
                            # Already registered with runtime callable, just update metadata
                            existing_entry.mcp_server_id = str(execution_server_id)
                            existing_entry.mcp_server_name = server.name
                            existing_entry.mcp_server_icon = server.icon_url
                            existing_entry.mcp_server_icon_invert = getattr(server, 'icon_invert_in_dark_mode', False)
                            logger.debug(f"[ToolCatalog] Preconfigured tool {tool.id} already runtime-available, updated metadata")
                        else:
                            entry = ToolCatalogEntry(
                                definition=tool,
                                user_id=user_id,
                                discovered_in_session=True,
                                is_available=is_connected,  # Only available if connected
                                mcp_server_id=str(execution_server_id),
                                mcp_server_name=server.name,
                                mcp_server_icon=server.icon_url,
                                mcp_server_icon_invert=getattr(server, 'icon_invert_in_dark_mode', False),
                            )
                            self._user_tools[user_id][tool.id] = entry
                            logger.info(f"[ToolCatalog] Added preconfigured tool {tool.id} (available={is_connected})")
                    tools_loaded += 1

            if tools_loaded > 0:
                logger.info(f"[ToolCatalog] Loaded {tools_loaded} MCP tools from DB for user {user_id}")

        except Exception as e:
            logger.warning(f"[ToolCatalog] Failed to load MCP tools for user {user_id}: {e}")

    def register_dynamic_tool(
        self,
        tool_def: ToolDefinition,
        user_id: Optional[str] = None
    ):
        """
        Register a dynamically discovered tool (e.g., from MCP).

        Args:
            tool_def: Tool definition
            user_id: User ID for user-specific tools
        """
        entry = ToolCatalogEntry(
            definition=tool_def,
            user_id=user_id,
            discovered_in_session=True
        )

        with self._registry_lock:
            if user_id:
                # User-specific tool
                if user_id not in self._user_tools:
                    self._user_tools[user_id] = {}
                self._user_tools[user_id][tool_def.id] = entry
                logger.info(f"[ToolCatalog] Registered user tool {tool_def.id} for user {user_id}")
            else:
                # Global tool
                self._register_entry(entry)
                logger.info(f"[ToolCatalog] Registered dynamic tool {tool_def.id}")

    def unregister_tool(self, tool_id: str, user_id: Optional[str] = None):
        """
        Unregister a tool.

        Args:
            tool_id: Tool ID to remove
            user_id: User ID for user-specific tools
        """
        with self._registry_lock:
            if user_id and user_id in self._user_tools:
                self._user_tools[user_id].pop(tool_id, None)
            elif tool_id in self._catalog:
                entry = self._catalog.pop(tool_id)

                # Clean up indexes
                category = entry.definition.category
                if category in self._category_index:
                    self._category_index[category].discard(tool_id)

                feature = entry.definition.feature_flag
                if feature and feature in self._feature_index:
                    self._feature_index[feature].discard(tool_id)

                provider = entry.definition.provider
                if provider in self._provider_index:
                    self._provider_index[provider].discard(tool_id)

    def get_user_tools(self, user_id: str) -> List[ToolDefinition]:
        """
        Get all tools for a specific user (including global tools).

        Args:
            user_id: User ID

        Returns:
            List of tool definitions available to the user
        """
        with self._registry_lock:
            # Start with global tools
            tools = [entry.definition for entry in self._catalog.values()]

            # Add user-specific tools
            if user_id in self._user_tools:
                tools.extend([
                    entry.definition
                    for entry in self._user_tools[user_id].values()
                ])

            return tools

    def update_tool_metrics(
        self,
        tool_id: str,
        success: bool,
        latency_ms: float,
        user_id: Optional[str] = None
    ):
        """
        Update tool usage metrics.

        Args:
            tool_id: Tool ID
            success: Whether the call succeeded
            latency_ms: Call latency in milliseconds
            user_id: User ID for user-specific tools
        """
        with self._registry_lock:
            entry = None

            if user_id and user_id in self._user_tools:
                entry = self._user_tools[user_id].get(tool_id)

            if entry is None:
                entry = self._catalog.get(tool_id)

            if entry:
                entry.update_usage(success, latency_ms)

    def search_tools(
        self,
        query: str,
        enabled_features: Set[str],
        categories: Optional[List[ToolCategory]] = None,
        max_results: int = 10,
        user_id: Optional[str] = None
    ) -> List[ToolCatalogEntry]:
        """
        Search for tools matching a query.

        This is a basic search - the ToolDiscoveryService provides more
        sophisticated relevance scoring.

        Args:
            query: Search query
            enabled_features: Set of enabled feature flags
            categories: Optional category filter
            max_results: Maximum results
            user_id: Optional user ID to include user-specific tools

        Returns:
            List of matching catalog entries
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        with self._registry_lock:
            results = []

            # Include both global catalog tools AND user-specific tools
            all_entries = list(self._catalog.values())
            if user_id and user_id in self._user_tools:
                all_entries.extend(self._user_tools[user_id].values())

            for entry in all_entries:
                tool_def = entry.definition

                # Check feature flag
                if tool_def.feature_flag and tool_def.feature_flag not in enabled_features:
                    continue

                # Check category filter
                if categories and tool_def.category not in categories:
                    continue

                # Check availability
                if not entry.is_available:
                    continue

                # Basic relevance scoring
                score = 0.0

                # Name match
                if query_lower in tool_def.name.lower():
                    score += 0.4

                # Description match
                if query_lower in tool_def.description.lower():
                    score += 0.3

                # Keyword match
                keywords_lower = [k.lower() for k in tool_def.search_keywords]
                keyword_matches = len(query_words & set(keywords_lower))
                if keyword_matches:
                    score += 0.2 * (keyword_matches / len(query_words))

                # Tag match
                tags_lower = [t.lower() for t in tool_def.tags]
                tag_matches = len(query_words & set(tags_lower))
                if tag_matches:
                    score += 0.1 * (tag_matches / len(query_words))

                if score > 0:
                    results.append((score, entry))

            # Sort by score
            results.sort(key=lambda x: x[0], reverse=True)

            return [entry for _, entry in results[:max_results]]

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._registry_lock:
            return {
                "total_tools": len(self._catalog),
                "tools_by_category": {
                    cat.value: len(ids)
                    for cat, ids in self._category_index.items()
                },
                "tools_by_provider": {
                    prov.value: len(ids)
                    for prov, ids in self._provider_index.items()
                },
                "tools_by_feature": {
                    feat: len(ids)
                    for feat, ids in self._feature_index.items()
                },
                "user_tools_count": sum(
                    len(tools) for tools in self._user_tools.values()
                ),
            }


# Global registry instance
def get_tool_catalog() -> ToolCatalogRegistry:
    """Get the global tool catalog registry instance."""
    return ToolCatalogRegistry()
