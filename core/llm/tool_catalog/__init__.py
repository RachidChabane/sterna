"""
Tool Catalog Module

Provides centralized tool definitions, categorization, and registry for on-demand tool discovery.
Based on Anthropic's Advanced Tool Use patterns.
"""

from .models import (
    ToolCategory,
    ToolProvider,
    LoadingStrategy,
    ToolDefinition,
    ToolCatalogEntry,
)
from .registry import ToolCatalogRegistry, get_tool_catalog
from .core_tools import CORE_TOOL_DEFINITIONS, ALWAYS_LOADED_TOOL_IDS

__all__ = [
    "ToolCategory",
    "ToolProvider",
    "LoadingStrategy",
    "ToolDefinition",
    "ToolCatalogEntry",
    "ToolCatalogRegistry",
    "get_tool_catalog",
    "CORE_TOOL_DEFINITIONS",
    "ALWAYS_LOADED_TOOL_IDS",
]
