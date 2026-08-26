"""
Tool Search Tool

The meta-tool that enables on-demand tool discovery.
Implements Anthropic's Tool Search Tool pattern.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field

from .service import ToolDiscoveryService, ToolDiscoveryContext
from ..tool_catalog.models import ToolCategory, ToolDefinition, ToolProvider, LoadingStrategy

logger = logging.getLogger(__name__)


class ToolSearchInput(BaseModel):
    """Input schema for tool search."""

    query: str = Field(
        ...,
        description="Description of what you need to do. Be specific about the task (e.g., 'search the web for news', 'read a file', 'get directions')."
    )
    category: Optional[str] = Field(
        None,
        description="Optional category filter: search, location, file_system, code, communication, productivity, data, media"
    )
    max_results: Optional[int] = Field(
        20,
        description="Maximum number of tools to return (1-50)",
        ge=1,
        le=50
    )


def create_tool_search_tool(
    discovery_service: ToolDiscoveryService,
    context: ToolDiscoveryContext
) -> BaseTool:
    """
    Factory to create the Tool Search Tool with injected context.

    This tool implements Anthropic's "Tool Search Tool" pattern:
    - LLM calls this tool to discover available capabilities
    - Returns tool definitions with examples
    - Discovered tools are cached for the session

    Args:
        discovery_service: The discovery service instance
        context: The discovery context for this session

    Returns:
        LangChain tool function
    """

    @tool("search_available_tools", args_schema=ToolSearchInput)
    async def search_available_tools(
        query: str,
        category: Optional[str] = None,
        max_results: int = 20
    ) -> str:
        """
        Search for available tools that can help with your task.

        Use this tool when you need to:
        - Find tools for a specific task (web search, file operations, maps, etc.)
        - Discover what capabilities are available
        - Get tool details and examples before using them

        After using this tool, you can directly call any discovered tools.

        Args:
            query: Description of what you need to do
            category: Optional filter (search, location, file_system, code)
            max_results: Maximum number of tools to return

        Returns:
            JSON with matching tools, their parameters, and usage examples
        """
        logger.info(f"[ToolSearch] Query: '{query}', category: {category}")

        # Parse category filter
        category_filter = None
        if category:
            try:
                category_filter = ToolCategory(category.lower())
            except ValueError:
                # Invalid category - ignore filter
                logger.warning(f"[ToolSearch] Invalid category: {category}")

        # Perform search
        results = discovery_service.search_tools(
            query=query,
            context=context,
            max_results=max_results,
            category_filter=category_filter
        )

        if not results:
            return json.dumps({
                "found": 0,
                "message": f"No tools found for '{query}'. Try a different search term or check available categories.",
                "available_categories": [
                    {"name": "search", "description": "Web search, news, images, videos"},
                    {"name": "location", "description": "Maps, directions, places, air quality"},
                    {"name": "file_system", "description": "Read, write, list files"},
                    {"name": "code", "description": "Execute Python, JavaScript, Bash code"},
                ],
                "tips": [
                    "Try broader terms like 'search' or 'file'",
                    "Use category filter to narrow results",
                    "Be specific about what you want to accomplish"
                ]
            }, indent=2)

        # Format results for LLM
        formatted_tools = []
        enabled_count = 0
        disabled_tools = []

        for result in results:
            tool_info = result.to_search_result()
            formatted_tools.append(tool_info)
            if result.is_enabled:
                enabled_count += 1
            else:
                disabled_tools.append({
                    "name": result.definition.name,
                    "requires": result.required_feature
                })

        response = {
            "found": len(formatted_tools),
            "available": enabled_count,
            "tools": formatted_tools,
        }

        # Add note based on availability
        if enabled_count == len(formatted_tools):
            response["note"] = "Call tools using the exact 'function_name' value shown above."
        elif enabled_count > 0:
            response["note"] = f"{enabled_count} tools available. Call using the exact 'function_name' value."
            response["disabled_tools_info"] = disabled_tools
        else:
            response["note"] = "No tools currently available. Enable required features in settings."
            response["disabled_tools_info"] = disabled_tools

        return json.dumps(response, indent=2)

    return search_available_tools


def create_tool_search_tool_sync(
    discovery_service: ToolDiscoveryService,
    context: ToolDiscoveryContext
) -> BaseTool:
    """
    Create a synchronous version of the tool search tool.

    For use in synchronous contexts.
    """

    @tool("search_available_tools", args_schema=ToolSearchInput)
    def search_available_tools(
        query: str,
        category: Optional[str] = None,
        max_results: int = 20
    ) -> str:
        """
        Search for available tools that can help with your task.

        Use this tool when you need to:
        - Find tools for a specific task (web search, file operations, maps, etc.)
        - Discover what capabilities are available
        - Get tool details and examples before using them

        After using this tool, you can directly call any discovered tools.

        Args:
            query: Description of what you need to do
            category: Optional filter (search, location, file_system, code)
            max_results: Maximum number of tools to return

        Returns:
            JSON with matching tools, their parameters, and usage examples
        """
        logger.info(f"[ToolSearch] Query: '{query}', category: {category}")

        # Parse category filter
        category_filter = None
        if category:
            try:
                category_filter = ToolCategory(category.lower())
            except ValueError:
                logger.warning(f"[ToolSearch] Invalid category: {category}")

        # Perform search
        results = discovery_service.search_tools(
            query=query,
            context=context,
            max_results=max_results,
            category_filter=category_filter
        )

        if not results:
            return json.dumps({
                "found": 0,
                "message": f"No tools found for '{query}'.",
                "available_categories": [
                    {"name": "search", "description": "Web search, news, images, videos"},
                    {"name": "location", "description": "Maps, directions, places"},
                    {"name": "file_system", "description": "Read, write, list files"},
                    {"name": "code", "description": "Execute code"},
                ]
            }, indent=2)

        formatted_tools = [result.to_search_result() for result in results]

        return json.dumps({
            "found": len(formatted_tools),
            "tools": formatted_tools,
            "note": "Call tools using the exact 'function_name' value shown above."
        }, indent=2)

    return search_available_tools


# ============================================================================
# Get Tool Details - Returns full schema for a specific tool
# ============================================================================

class GetToolDetailsInput(BaseModel):
    """Input schema for get_tool_details."""

    function_name: str = Field(
        ...,
        description="The exact function_name from search_available_tools results"
    )


def create_get_tool_details_tool(
    discovery_service: ToolDiscoveryService,
    context: ToolDiscoveryContext
) -> BaseTool:
    """
    Factory to create the Get Tool Details tool.

    Returns full parameter schema and examples for a specific tool.
    Use after search_available_tools when you need complete details.
    """

    @tool("get_tool_details", args_schema=GetToolDetailsInput)
    def get_tool_details(function_name: str) -> str:
        """
        {{ACTION: Getting tool details}}

        Get full details for a specific tool including complete parameter schema.

        Use this after search_available_tools when you need:
        - Complete parameter definitions with types and descriptions
        - Usage examples
        - Full documentation

        Args:
            function_name: The exact function_name from search results

        Returns:
            JSON with complete tool details
        """
        logger.info(f"[GetToolDetails] Requested: {function_name}")

        # Get catalog
        catalog = discovery_service.catalog
        user_id = context.user_id

        # Try to find the tool - support multiple naming formats
        tool_def = catalog.get_tool(function_name, user_id=user_id)

        if not tool_def:
            # Try various name transformations
            name_lower = function_name.lower().replace('-', '_').replace('.', '_')
            alt_names = [
                f"mcp_{name_lower}",  # mcp_notion_notion_create_pages
                function_name.replace(".", "_"),  # Notion_notion-create-pages
                function_name.replace("-", "_"),  # notion_create_pages
            ]
            # Handle sanitized MCP names: mcp_custom_463_name -> mcp_custom:463_name
            colon_match = re.match(r'^(mcp_[a-z]+)_(\d+)_(.+)$', function_name)
            if colon_match:
                unsanitized = f"{colon_match.group(1)}:{colon_match.group(2)}_{colon_match.group(3)}"
                alt_names.insert(0, unsanitized)  # Try this first
            for alt in alt_names:
                tool_def = catalog.get_tool(alt, user_id=user_id)
                if tool_def:
                    logger.info(f"[GetToolDetails] Found via alt name: {alt}")
                    break

        if not tool_def:
            # Try partial match - search all tools for one that ends with the name
            all_tools = catalog.list_tools(user_id=user_id)
            search_name = function_name.lower().replace('-', '_').replace('.', '_')
            for tid in all_tools:
                tid_normalized = tid.lower().replace('-', '_').replace('.', '_')
                if tid_normalized.endswith(search_name) or search_name in tid_normalized:
                    tool_def = catalog.get_tool(tid, user_id=user_id)
                    if tool_def:
                        logger.info(f"[GetToolDetails] Found via partial match: {tid}")
                        break

        if not tool_def:
            # List available tools to help user
            all_tool_ids = catalog.list_tools(user_id=context.user_id)[:10]  # Show first 10
            return json.dumps({
                "error": f"Tool '{function_name}' not found",
                "suggestion": "Use search_available_tools to find available tools first",
                "available_tools_sample": all_tool_ids
            }, indent=2)

        # Build full details response
        # Sanitize function_name for Anthropic compatibility (only [a-zA-Z0-9_-] allowed)
        sanitized_id = tool_def.id.replace(":", "_")
        result: Dict[str, Any] = {
            "function_name": sanitized_id,
            "name": tool_def.name,
            "description": tool_def.description,  # Full description
            "category": tool_def.category.value,
        }

        # Full parameter schema
        if tool_def.input_schema:
            result["parameters"] = tool_def.input_schema

        # Examples if available
        examples = tool_def.get_examples_for_prompt(max_examples=3)
        if examples:
            result["examples"] = examples

        # Additional metadata
        if tool_def.system_prompt_section:
            result["usage_notes"] = tool_def.system_prompt_section

        return json.dumps(result, indent=2)

    return get_tool_details


# Tool definition for the search tool itself (for catalog registration)
TOOL_SEARCH_DEFINITION = ToolDefinition(
    id="search_available_tools",
    name="Search Available Tools",
    description="Search for available tools that can help with your task. Use this to discover capabilities before attempting to use specific tools.",
    category=ToolCategory.DATA,  # Meta category
    provider=ToolProvider.CORE,
    tags=["meta", "search", "discovery", "tools", "capabilities"],
    loading_strategy=LoadingStrategy.ALWAYS,  # Always available
    priority=0,  # Highest priority
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Description of what you need to do"
            },
            "category": {
                "type": "string",
                "description": "Optional category filter",
                "enum": ["search", "location", "file_system", "code", "communication", "productivity", "data", "media"]
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum tools to return (1-50)",
                "default": 20,
                "minimum": 1,
                "maximum": 50
            }
        },
        "required": ["query"]
    },
    search_keywords=["find", "search", "discover", "available", "tools", "capabilities", "what can"],
    search_boost=2.0,  # High boost for meta-tool
)

GET_TOOL_DETAILS_DEFINITION = ToolDefinition(
    id="get_tool_details",
    name="Get Tool Details",
    description="Get full parameter schema and examples for a specific tool. Use after search_available_tools when you need complete details before calling a tool.",
    category=ToolCategory.DATA,
    provider=ToolProvider.CORE,
    tags=["meta", "tools", "schema", "details", "parameters"],
    loading_strategy=LoadingStrategy.ALWAYS,
    priority=1,
    input_schema={
        "type": "object",
        "properties": {
            "function_name": {
                "type": "string",
                "description": "The exact function_name from search_available_tools results"
            }
        },
        "required": ["function_name"]
    },
    search_keywords=["details", "schema", "parameters", "how to use", "tool info"],
    search_boost=1.5,
)
