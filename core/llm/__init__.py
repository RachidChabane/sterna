"""
LLM Module

This module provides the AI agent infrastructure for the application.

Quick Start:
    from llm.langchain_agent import LangChainStreamingAgent

    agent = LangChainStreamingAgent(...)

This is the live, production streaming agent, used directly by
llm/views.py. It is complemented by supporting subsystems also under
this package:

Tool Discovery:
    from llm.tool_catalog import get_tool_catalog
    from llm.tool_discovery import get_discovery_service

Optimized Prompts:
    from llm.prompts_v2 import get_prompt_builder

Note: Imports are done on-demand to avoid Django app loading issues.
Use direct module imports (from llm.module import Class) instead of
package-level imports (from llm import Class) where possible.
"""

# Only expose the most essential items at package level
# to avoid circular import issues with Django

__all__ = [
    # Available at package level (backward compatibility)
    "LangChainStreamingAgent",
    "build_system_prompt",
    # Utilities
    "CatalogService",
]


def __getattr__(name):
    """
    Lazy import handler for backward compatibility.

    This allows `from llm import X` to work without loading
    all modules at once, which would trigger Django model loading.
    """
    if name == "LangChainStreamingAgent":
        from .langchain_agent import LangChainStreamingAgent
        return LangChainStreamingAgent

    if name == "build_system_prompt":
        from .prompt_builder import build_system_prompt
        return build_system_prompt

    if name == "SystemPromptBuilder":
        from .prompt_builder import SystemPromptBuilder
        return SystemPromptBuilder

    if name == "CatalogService":
        from .catalog_service import CatalogService
        return CatalogService

    if name == "OpenRouterClient":
        from .client import OpenRouterClient
        return OpenRouterClient

    # V2 Tool Catalog
    if name in ("ToolCatalogRegistry", "get_tool_catalog", "ToolCategory",
                "ToolProvider", "LoadingStrategy", "ToolDefinition",
                "CORE_TOOL_DEFINITIONS", "ALWAYS_LOADED_TOOL_IDS"):
        from . import tool_catalog
        return getattr(tool_catalog, name)

    # V2 Tool Discovery
    if name in ("ToolDiscoveryService", "ToolDiscoveryContext",
                "create_tool_search_tool", "get_discovery_service"):
        from . import tool_discovery
        return getattr(tool_discovery, name)

    # V2 Prompts
    if name in ("OptimizedPromptBuilder", "get_prompt_builder",
                "PromptLayer", "PromptSection"):
        from . import prompts_v2
        return getattr(prompts_v2, name)

    # V2 PTC
    if name in ("PTCEngine", "PTCCodeGenerator", "PTCToolBinding",
                "PTCExecutionResult"):
        from . import ptc
        return getattr(ptc, name)

    raise AttributeError(f"module 'llm' has no attribute '{name}'")
