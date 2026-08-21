"""
Tool Discovery Module

Provides on-demand tool discovery following Anthropic's Tool Search Tool pattern.
Enables efficient tool loading and reduced token consumption.
"""

from .service import (
    ToolDiscoveryService,
    ToolDiscoveryContext,
    get_discovery_service,
)
from .tool_search import (
    create_tool_search_tool,
    create_get_tool_details_tool,
    ToolSearchInput,
    GetToolDetailsInput,
)

__all__ = [
    "ToolDiscoveryService",
    "ToolDiscoveryContext",
    "get_discovery_service",
    "create_tool_search_tool",
    "create_get_tool_details_tool",
    "ToolSearchInput",
    "GetToolDetailsInput",
]
