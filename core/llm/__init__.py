"""
LLM Module

This module provides the AI agent infrastructure for the application.

Quick Start:
    from llm.agent_service.endpoint import agent_core_streaming_response
    from llm.agent_service.v1_endpoint import v1_streaming_response

Both chat endpoints run their turn on `llm.agent_core`'s agent loop;
`llm.agent_service` is the Django-side glue each endpoint assembles it
through. It is complemented by supporting subsystems also under this
package:

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
    # Utilities
    "CatalogService",
]


def __getattr__(name):
    """
    Lazy import handler for backward compatibility.

    This allows `from llm import X` to work without loading
    all modules at once, which would trigger Django model loading.
    """
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
