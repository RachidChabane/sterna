"""
MCP Tool Discovery Adapter

Integrates MCP servers with the Tool Discovery system.
Converts MCP tools to ToolDefinition format for unified discovery.
"""

import logging
from typing import List, Dict, Optional, Any

from llm.tool_catalog.models import (
    ToolDefinition,
    ToolCategory,
    ToolProvider,
    LoadingStrategy,
    ToolInputExample,
)
from llm.tool_catalog.registry import ToolCatalogRegistry, get_tool_catalog
from mcp.unified_registry import UnifiedMCPRegistry, get_mcp_registry
from mcp.utils import sanitize_tool_name

logger = logging.getLogger(__name__)


async def _resolve_user_by_id(user_id):
    """Resolve a User instance from user_id. Returns None on missing/DNE.

    Distinct from Google Maps' `_resolve_user()` in `google_maps_tools.py`,
    which reads from a ContextVar with no args — MCP receives user_id as
    a function parameter so each module keeps its own helper.
    """
    if not user_id:
        return None
    from asgiref.sync import sync_to_async
    try:
        from authentication.models import User
    except ImportError:
        from django.contrib.auth import get_user_model
        User = get_user_model()
    try:
        return await sync_to_async(User.objects.get)(id=user_id)
    except User.DoesNotExist:
        return None
    except Exception:
        return None


class MCPToolDiscoveryAdapter:
    """
    Adapter to integrate MCP servers with Tool Discovery.

    Responsibilities:
    - Discover tools from MCP servers on-demand
    - Convert MCP tool format to ToolDefinition
    - Register discovered tools in the catalog
    - Handle tool execution routing
    """

    def __init__(
        self,
        mcp_registry: Optional[UnifiedMCPRegistry] = None,
        tool_catalog: Optional[ToolCatalogRegistry] = None
    ):
        """
        Initialize the adapter.

        Args:
            mcp_registry: Unified MCP registry instance
            tool_catalog: Tool catalog registry instance
        """
        self.mcp_registry = mcp_registry or get_mcp_registry()
        self.tool_catalog = tool_catalog or get_tool_catalog()

        # Cache of converted tools per user
        self._user_tool_cache: Dict[str, Dict[str, ToolDefinition]] = {}

        logger.info("[MCPAdapter] Initialized with UnifiedMCPRegistry")

    async def discover_user_mcp_tools(
        self,
        user_id: str,
        server_ids: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> List[ToolDefinition]:
        """
        Discover MCP tools for a user.

        Called on-demand when Tool Search detects a need for
        external capabilities.

        Args:
            user_id: User identifier
            server_ids: Optional list of specific servers to query
            force_refresh: Force re-discovery even if cached

        Returns:
            List of discovered ToolDefinitions
        """
        all_tools: List[ToolDefinition] = []

        # Get servers from the unified registry
        user_servers = await self.mcp_registry.get_user_servers(user_id)

        # Filter to specific server_ids if provided
        if server_ids is not None:
            user_servers = [s for s in user_servers if s.server_id in server_ids]

        if not user_servers:
            logger.debug(f"[MCPAdapter] No MCP servers configured for user {user_id}")
            return []

        # Discover tools from each server
        for server_info in user_servers:
            try:
                mcp_tools = await self.mcp_registry.discover_tools(
                    user_id=user_id,
                    server_id=server_info.server_id,
                    force_refresh=force_refresh
                )

                # Convert to dict format for _convert_mcp_tools
                mcp_tools_dicts = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    }
                    for t in mcp_tools
                ]

                # Convert to ToolDefinition format
                converted = self._convert_mcp_tools(
                    mcp_tools=mcp_tools_dicts,
                    server_id=server_info.server_id,
                    user_id=user_id,
                    server_name=server_info.name,  # For searchability and category inference
                )

                all_tools.extend(converted)

                # Register in catalog for this user
                for tool in converted:
                    self.tool_catalog.register_dynamic_tool(
                        tool,
                        user_id=user_id
                    )

                logger.info(
                    f"[MCPAdapter] Discovered {len(converted)} tools "
                    f"from {server_info.name} for user {user_id}"
                )

            except Exception as e:
                logger.error(
                    f"[MCPAdapter] Failed to discover tools from {server_info.server_id}: {e}"
                )

        return all_tools

    async def _get_user_configured_servers(self, user_id: str) -> List[str]:
        """
        Get MCP server IDs configured by a user.

        Args:
            user_id: User identifier

        Returns:
            List of server IDs
        """
        # Get all servers for this user from the unified registry
        user_servers = await self.mcp_registry.get_user_servers(user_id)
        return [s.server_id for s in user_servers]

    def _convert_mcp_tools(
        self,
        mcp_tools: List[Dict[str, Any]],
        server_id: str,
        user_id: str,
        server_name: Optional[str] = None
    ) -> List[ToolDefinition]:
        """
        Convert MCP tool definitions to ToolDefinition format.

        Args:
            mcp_tools: Raw MCP tool definitions
            server_id: Source server ID (e.g., "custom:462") for execution routing
            user_id: User who owns this tool instance
            server_name: Optional server display name (e.g., "Notion") for search/category

        Returns:
            List of ToolDefinition objects
        """
        converted = []

        # Use server_name for search/category if provided, otherwise extract from server_id
        search_name = server_name or server_id

        for mcp_tool in mcp_tools:
            if mcp_tool.get("from_cache"):
                # Cached entry - minimal info, need full discovery
                continue

            tool_name = mcp_tool.get("name", "")
            if not tool_name:
                continue

            # Generate unique ID with server prefix
            # Use the same naming convention as mcp_tools_to_langchain_tools in mcp/utils.py
            # This ensures the function_name returned by search_available_tools matches
            # the actual LangChain tool name that gets created
            # Sanitize to ensure Anthropic-compatible names (only [a-zA-Z0-9_-])
            server_prefix = sanitize_tool_name(server_id).lower()
            tool_name_sanitized = sanitize_tool_name(tool_name)
            tool_id = f"mcp_{server_prefix}_{tool_name_sanitized}"

            # Determine category based on server name and tool hints
            category = self._infer_category(search_name, mcp_tool)

            # Build ToolDefinition
            tool_def = ToolDefinition(
                id=tool_id,
                name=self._humanize_name(tool_name),
                description=mcp_tool.get("description", f"MCP tool: {tool_name}"),
                category=category,
                provider=ToolProvider.MCP_USER,
                tags=self._extract_tags(search_name, mcp_tool),
                loading_strategy=LoadingStrategy.ON_DEMAND,
                priority=50,  # Medium priority for MCP tools
                input_schema=mcp_tool.get("inputSchema", {}),
                output_schema=mcp_tool.get("outputSchema"),
                input_examples=self._convert_examples(mcp_tool.get("examples", [])),
                allowed_callers=["code_execution"],  # Allow PTC
                is_idempotent=self._infer_idempotent(mcp_tool),
                sandbox_isolated=True,
                feature_flag="mcp_tools",
                search_keywords=self._generate_keywords(search_name, tool_name, mcp_tool),
                mcp_server_id=server_id,  # Store original server_id for execution routing
                mcp_tool_name=tool_name,  # Store raw tool name for execution
            )

            converted.append(tool_def)

            # Cache the conversion
            user_cache = self._user_tool_cache.setdefault(user_id, {})
            user_cache[tool_id] = tool_def

        return converted

    def _infer_category(
        self,
        server_id: str,
        mcp_tool: Dict[str, Any]
    ) -> ToolCategory:
        """
        Infer tool category from server and tool info.

        Priority order:
        1. Tool name/description-based hints (specific tool capabilities)
        2. Server-based defaults (general server type)

        Args:
            server_id: Server identifier
            mcp_tool: MCP tool definition

        Returns:
            Best matching category
        """
        tool_name = mcp_tool.get("name", "").lower()
        server_lower = server_id.lower()

        # FIRST: Check tool name for specific capability hints
        # This takes priority over server-level defaults so that tools like
        # `search_repositories` from GitHub are categorized as SEARCH
        # Note: Only check tool NAME for search keywords, not description - descriptions
        # often contain words like "find" in non-search contexts (e.g., "to find a user id")
        if any(word in tool_name for word in ["search", "find", "query", "lookup"]):
            return ToolCategory.SEARCH

        # Check for file/document operations (name-based only)
        if any(word in tool_name for word in ["file", "upload", "download", "read_file", "write_file"]):
            return ToolCategory.FILE_SYSTEM

        # Check for communication operations (name-based only)
        if any(word in tool_name for word in ["message", "send", "email", "chat", "post_message"]):
            return ToolCategory.COMMUNICATION

        # SECOND: Fall back to server-based category defaults
        category_hints = {
            "slack": ToolCategory.COMMUNICATION,
            "email": ToolCategory.COMMUNICATION,
            "gmail": ToolCategory.COMMUNICATION,
            "notion": ToolCategory.PRODUCTIVITY,
            "jira": ToolCategory.PRODUCTIVITY,
            "asana": ToolCategory.PRODUCTIVITY,
            "github": ToolCategory.DATA,
            "database": ToolCategory.DATA,
            "postgres": ToolCategory.DATA,
            "mysql": ToolCategory.DATA,
            "drive": ToolCategory.FILE_SYSTEM,
            "dropbox": ToolCategory.FILE_SYSTEM,
            "s3": ToolCategory.FILE_SYSTEM,
        }

        for hint, category in category_hints.items():
            if hint in server_lower:
                return category

        return ToolCategory.CUSTOM

    def _humanize_name(self, tool_name: str) -> str:
        """Convert tool_name to Human Readable Name."""
        # Handle snake_case and camelCase
        name = tool_name.replace("_", " ").replace("-", " ")

        # Add spaces before capitals in camelCase
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0 and name[i-1].islower():
                result.append(" ")
            result.append(char)

        return "".join(result).title()

    def _extract_tags(
        self,
        server_id: str,
        mcp_tool: Dict[str, Any]
    ) -> List[str]:
        """Extract tags from MCP tool definition."""
        tags = [server_id]  # Always include server as tag

        # Add any explicit tags
        if "tags" in mcp_tool:
            tags.extend(mcp_tool["tags"])

        # Extract keywords from name
        name = mcp_tool.get("name", "")
        name_parts = name.replace("_", " ").replace("-", " ").split()
        tags.extend([p.lower() for p in name_parts if len(p) > 2])

        return list(set(tags))

    def _convert_examples(
        self,
        mcp_examples: List[Dict[str, Any]]
    ) -> List[ToolInputExample]:
        """Convert MCP examples to ToolInputExample format."""
        examples = []

        for ex in mcp_examples[:3]:  # Limit to 3 examples
            examples.append(ToolInputExample(
                description=ex.get("description", "Example usage"),
                inputs=ex.get("input", ex.get("arguments", {})),
                expected_output_summary=ex.get("output_description"),
            ))

        return examples

    def _infer_idempotent(self, mcp_tool: Dict[str, Any]) -> bool:
        """Infer if a tool is idempotent based on its definition."""
        name = mcp_tool.get("name", "").lower()
        description = mcp_tool.get("description", "").lower()

        # Read operations are usually idempotent
        read_hints = ["get", "list", "search", "find", "query", "fetch", "read"]
        if any(hint in name or hint in description for hint in read_hints):
            return True

        # Write operations are usually not
        write_hints = ["create", "update", "delete", "send", "post", "put", "write"]
        if any(hint in name or hint in description for hint in write_hints):
            return False

        return False

    def _generate_keywords(
        self,
        server_id: str,
        tool_name: str,
        mcp_tool: Dict[str, Any]
    ) -> List[str]:
        """Generate search keywords for a tool."""
        keywords = set()

        # From server ID
        keywords.update(server_id.lower().split("-"))
        keywords.update(server_id.lower().split("_"))

        # From tool name
        keywords.update(tool_name.lower().replace("_", " ").split())
        keywords.update(tool_name.lower().replace("-", " ").split())

        # From description
        description = mcp_tool.get("description", "")
        # Extract significant words (longer than 3 chars)
        desc_words = [w.lower() for w in description.split() if len(w) > 3]
        keywords.update(desc_words[:10])  # Limit

        # Remove common words
        stop_words = {"the", "and", "for", "with", "this", "that", "from", "will"}
        keywords -= stop_words

        return list(keywords)

    async def execute_mcp_tool(
        self,
        user_id: str,
        tool_id: str,
        arguments: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool.

        Routes the execution to the appropriate MCP server via the unified registry.

        Args:
            user_id: User identifier
            tool_id: Tool ID from catalog (e.g., "mcp_notion_notion-create-comment")
            arguments: Tool arguments
            auth_token: Optional auth token (not used, kept for compatibility)

        Returns:
            Execution result
        """
        user = await _resolve_user_by_id(user_id)
        if user is not None:
            try:
                from asgiref.sync import sync_to_async
                from usage_quota.billing.service import get_billing_service
                from usage_quota.exceptions import (
                    FeatureNotAvailableException,
                    QuotaExceededException,
                )
                from usage_quota.models import ServiceType, FeatureType
                from usage_quota.services.cost_calculator import get_cost_calculator

                # Cost lookup hits the DB (ServicePricing) — must be wrapped
                # for async context or SynchronousOnlyOperation kills the
                # pre-check silently (fail-open).
                estimated = await sync_to_async(
                    get_cost_calculator().calculate_mcp_invocation_cost
                )(1)
                try:
                    await sync_to_async(get_billing_service().check_quota)(
                        user=user,
                        service=ServiceType.MCP_TOOL_INVOCATION,
                        estimated_cost=estimated,
                        feature=FeatureType.CHAT,
                        feature_name='mcp_tool_invocation',
                    )
                except (FeatureNotAvailableException, QuotaExceededException) as exc:
                    return {
                        "success": False,
                        "error": exc.code,
                        "message": exc.message,
                        "denial_reason": getattr(exc, 'limit_type', None),
                    }
            except Exception:
                logger.error("[MCPAdapter] quota pre-check failed", exc_info=True)

        try:
            # Look up the tool in the catalog to get server_id and tool_name
            tool_def = self.tool_catalog.get_tool(tool_id, user_id=user_id)

            if tool_def and tool_def.mcp_server_id and tool_def.mcp_tool_name:
                # Use stored server_id and tool_name for execution
                server_id = tool_def.mcp_server_id
                tool_name = tool_def.mcp_tool_name
                logger.info(f"[MCPAdapter] Executing via catalog: server={server_id}, tool={tool_name}")

                result = await self.mcp_registry.execute_tool_by_name(
                    user_id=user_id,
                    server_id=server_id,
                    tool_name=tool_name,
                    arguments=arguments,
                )
            else:
                # Fallback: try to parse tool_id if not in catalog
                # Format: mcp_{server_prefix}_{tool_name}
                if tool_id.startswith("mcp_"):
                    parts = tool_id[4:].split("_", 1)  # Remove "mcp_" prefix
                    if len(parts) == 2:
                        server_id = parts[0]  # e.g., "notion"
                        tool_name = parts[1]  # e.g., "notion-create-comment"
                        logger.info(f"[MCPAdapter] Executing via parsed ID: server={server_id}, tool={tool_name}")
                        result = await self.mcp_registry.execute_tool_by_name(
                            user_id=user_id,
                            server_id=server_id,
                            tool_name=tool_name,
                            arguments=arguments,
                        )
                    else:
                        return {"success": False, "error": f"Invalid tool ID format: {tool_id}"}
                else:
                    # Last resort: try direct execution
                    result = await self.mcp_registry.execute_tool(
                        user_id=user_id,
                        tool_id=tool_id,
                        arguments=arguments,
                    )

        except Exception as e:
            logger.error(f"[MCPAdapter] Tool execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

        # Only successful tool calls bill — failures don't consume quota.
        if user is not None and isinstance(result, dict) and result.get("success"):
            try:
                from asgiref.sync import sync_to_async
                from usage_quota.billing.service import get_billing_service
                from usage_quota.billing.operations import BillableOperation
                from usage_quota.models import ServiceType, FeatureType

                op = BillableOperation(
                    service=ServiceType.MCP_TOOL_INVOCATION,
                    feature=FeatureType.CHAT,
                    model_id=tool_id,
                    request_count=1,
                )
                await sync_to_async(get_billing_service().record_usage)(user, op)
            except Exception:
                logger.error("[MCPAdapter] billing record_usage failed", exc_info=True)

        return result

    def get_user_mcp_tools(self, user_id: str) -> List[ToolDefinition]:
        """
        Get all MCP tools currently available to a user.

        Args:
            user_id: User identifier

        Returns:
            List of ToolDefinitions
        """
        if user_id not in self._user_tool_cache:
            return []

        return list(self._user_tool_cache[user_id].values())

    def clear_user_cache(self, user_id: str):
        """Clear cached tools for a user."""
        if user_id in self._user_tool_cache:
            del self._user_tool_cache[user_id]

        logger.info(f"[MCPAdapter] Cleared tool cache for user {user_id}")


# Global adapter instance
_mcp_adapter: Optional[MCPToolDiscoveryAdapter] = None


def get_mcp_adapter() -> MCPToolDiscoveryAdapter:
    """Get the global MCP adapter instance."""
    global _mcp_adapter

    if _mcp_adapter is None:
        _mcp_adapter = MCPToolDiscoveryAdapter()

    return _mcp_adapter
