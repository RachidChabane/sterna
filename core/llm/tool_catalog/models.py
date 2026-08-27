"""
Tool Catalog Data Models

Defines the data structures for tool definitions, categories, and catalog entries.
Based on Anthropic's Advanced Tool Use patterns for on-demand tool discovery.
"""

import re
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class ToolCategory(str, Enum):
    """
    Tool categories for discovery and organization.

    Categories help the Tool Search find relevant tools
    and enable feature-based filtering.
    """
    SEARCH = "search"               # Brave Search, Web Search
    LOCATION = "location"           # Google Maps, Places
    FILE_SYSTEM = "file_system"     # File operations (read, write, list)
    CODE_EXECUTION = "code"         # Execute Python/Bash code
    COMMUNICATION = "communication" # Slack, Email (future MCP)
    PRODUCTIVITY = "productivity"   # Notion, Jira, Asana (future MCP)
    DATA = "data"                   # Database, API queries (future MCP)
    MEDIA = "media"                 # Image/Video processing
    CUSTOM = "custom"               # User-defined MCP tools


class ToolProvider(str, Enum):
    """
    Tool provider/source classification.

    Determines how tools are loaded and isolated.
    """
    CORE = "core"               # Built-in tools (Brave, Maps, File Tools)
    MCP_SYSTEM = "mcp_system"   # System-level MCP servers (managed by platform)
    MCP_USER = "mcp_user"       # User-specific MCP servers (per-user sandbox)


class LoadingStrategy(str, Enum):
    """
    Tool loading strategy for optimization.

    Controls when tool definitions are sent to the LLM.
    """
    ALWAYS = "always"           # Always loaded (essential core tools)
    ON_DEMAND = "on_demand"     # Discovered via Tool Search (default)
    EXPLICIT = "explicit"       # Only if explicitly requested by user


@dataclass
class ToolInputExample:
    """
    Example input for a tool.

    Used to improve tool selection accuracy (Anthropic's Tool Use Examples).
    """
    description: str                    # What this example demonstrates
    inputs: Dict[str, Any]              # Example input parameters
    expected_output_summary: Optional[str] = None  # Brief description of output


@dataclass
class ToolDefinition:
    """
    Complete definition of a tool.

    Contains all metadata needed for:
    - Tool discovery and search
    - LLM tool binding
    - Execution routing
    - Prompt generation
    """

    # ===== Identity =====
    id: str                             # Unique ID: "brave_web_search", "notion.create_page"
    name: str                           # Display name: "Web Search"
    description: str                    # Description for LLM: "Search the web for..."

    # ===== Classification =====
    category: ToolCategory              # Primary category
    provider: ToolProvider              # Source/provider
    tags: List[str] = field(default_factory=list)  # ["real-time", "news", "web"]

    # ===== Loading Configuration =====
    loading_strategy: LoadingStrategy = LoadingStrategy.ON_DEMAND
    priority: int = 50                  # 1-100, lower = higher priority for loading

    # ===== Schema =====
    input_schema: Dict[str, Any] = field(default_factory=dict)   # JSON Schema
    output_schema: Optional[Dict[str, Any]] = None               # Optional output schema

    # ===== Examples (for Tool Use Examples pattern) =====
    input_examples: List[ToolInputExample] = field(default_factory=list)

    # ===== Execution Configuration =====
    allowed_callers: Optional[List[str]] = None  # ["code_execution"] for PTC
    is_idempotent: bool = False                  # Safe for retry/parallel execution
    is_async: bool = True                        # Async execution supported
    estimated_latency_ms: int = 1000             # Expected latency
    timeout_seconds: int = 30                    # Execution timeout

    # ===== Context & Security =====
    requires_auth: bool = False                  # Requires authentication
    sandbox_isolated: bool = False               # Executed in user sandbox
    feature_flag: Optional[str] = None           # Required feature flag

    # ===== Associated Prompts =====
    system_prompt_section: Optional[str] = None  # Specific instructions for LLM

    # ===== Search Metadata =====
    search_keywords: List[str] = field(default_factory=list)  # Additional search terms
    search_boost: float = 1.0                    # Boost factor for search ranking

    # ===== MCP-specific (for MCP tools) =====
    mcp_server_id: Optional[str] = None          # Source MCP server ID for execution routing
    mcp_tool_name: Optional[str] = None          # Raw MCP tool name for execution

    def to_openai_function(self) -> Dict[str, Any]:
        """
        Convert to OpenAI function calling format.

        Returns:
            Dict compatible with OpenAI's tools parameter
        """
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": self.input_schema
            }
        }

    def to_langchain_tool_schema(self) -> Dict[str, Any]:
        """
        Convert to LangChain tool schema format.

        Returns:
            Dict for LangChain tool binding
        """
        return {
            "name": self.id,
            "description": self.description,
            "args_schema": self.input_schema,
        }

    def get_examples_for_prompt(self, max_examples: int = 2) -> List[Dict[str, Any]]:
        """
        Get formatted examples for inclusion in prompts.

        Args:
            max_examples: Maximum number of examples to return

        Returns:
            List of example dicts
        """
        return [
            {"inputs": ex.inputs, "description": ex.description}
            for ex in self.input_examples[:max_examples]
        ]


@dataclass
class ToolCatalogEntry:
    """
    Runtime catalog entry with metrics and state.

    Wraps a ToolDefinition with runtime information
    for monitoring and optimization.
    """

    definition: ToolDefinition

    # ===== Availability =====
    is_available: bool = True           # Currently available
    is_deprecated: bool = False         # Marked for removal
    deprecation_message: Optional[str] = None

    # ===== Usage Metrics =====
    usage_count: int = 0                # Total usage count
    usage_frequency: float = 0.0        # Usage frequency score (0-1)
    last_used: Optional[datetime] = None

    # ===== Performance Metrics =====
    success_rate: float = 1.0           # Success rate (0-1)
    avg_latency_ms: float = 0.0         # Average latency
    error_count: int = 0                # Total error count

    # ===== User-specific (for MCP_USER) =====
    user_id: Optional[str] = None       # Owner user ID
    mcp_server_id: Optional[str] = None # Source MCP server ID (for catalog entry)
    mcp_server_name: Optional[str] = None  # Server display name
    mcp_server_icon: Optional[str] = None  # Server icon URL
    mcp_server_icon_invert: bool = False   # Invert icon in dark mode

    # ===== Session State =====
    discovered_in_session: bool = False # Discovered in current session
    session_usage_count: int = 0        # Usage in current session

    def update_usage(self, success: bool, latency_ms: float):
        """
        Update usage metrics after a tool call.

        Args:
            success: Whether the call succeeded
            latency_ms: Call latency in milliseconds
        """
        self.usage_count += 1
        self.session_usage_count += 1
        self.last_used = datetime.utcnow()

        # Update rolling average latency
        if self.avg_latency_ms == 0:
            self.avg_latency_ms = latency_ms
        else:
            # Exponential moving average
            self.avg_latency_ms = 0.9 * self.avg_latency_ms + 0.1 * latency_ms

        if not success:
            self.error_count += 1

        # Update success rate
        self.success_rate = (self.usage_count - self.error_count) / self.usage_count

    def calculate_relevance_boost(self) -> float:
        """
        Calculate a boost factor based on usage and performance.

        Returns:
            Boost factor (0.5 - 2.0)
        """
        # Boost based on usage frequency
        usage_boost = min(1.0 + self.usage_frequency, 1.5)

        # Penalty for low success rate
        success_penalty = max(self.success_rate, 0.5)

        # Combine with definition's search_boost
        return self.definition.search_boost * usage_boost * success_penalty


# Mapping from feature flags to user-friendly names
# These MUST match the toggle names in the Features menu (frontend)
FEATURE_FLAG_DISPLAY_NAMES = {
    "brave_search": "Web Search",
    "web_search": "Web Search",
    "google_maps": "Web Search",
    "file_tools": "File Tools",
    "coding_agent": "File Tools",  # Coding Agent is enabled via File Tools
    "reasoning": "Reasoning",
    "mcp_tools": "Connectors",
    "knowledge_base": "Knowledge Base",
    "image_generation": "Image Generation",
    "video_generation": "Video Generation",
    "sparks": "Sparks",
}


@dataclass
class DiscoveredTool:
    """
    Result of a tool search/discovery.

    Contains the tool definition with relevance scoring.
    """
    definition: ToolDefinition
    relevance_score: float              # 0-1 relevance score
    match_reason: str                   # Why this tool was matched
    catalog_entry: Optional[ToolCatalogEntry] = None  # Full catalog entry if available
    is_enabled: bool = True             # Whether the required feature is enabled
    required_feature: Optional[str] = None  # Human-readable feature name if disabled
    # Connection status for MCP tools
    is_connected: bool = True           # Whether user has connected to the MCP server
    mcp_server_name: Optional[str] = None  # Server name for connection hint
    mcp_server_icon: Optional[str] = None  # Server icon URL (for frontend display only)
    mcp_server_icon_invert: bool = False   # Whether to invert icon in dark mode

    def to_search_result(self) -> Dict[str, Any]:
        """
        Format for Tool Search response.

        Optimized for minimal token usage - just enough info to select a tool.
        Full details (schema, examples) are available when tool is actually bound.

        Returns:
            Dict with tool info for LLM
        """
        # Truncate and clean description (strip markdown headers, limit length)
        desc = self._truncate_description(self.definition.description, max_length=120)

        # Sanitize function_name for Anthropic compatibility (only [a-zA-Z0-9_-] allowed)
        # e.g., mcp_custom:463_notion-create-comment -> mcp_custom_463_notion-create-comment
        sanitized_id = self.definition.id.replace(":", "_")

        result: Dict[str, Any] = {
            "function_name": sanitized_id,  # The exact name to use when calling this tool
            "name": self.definition.name,
            "description": desc,
        }

        # Add availability status (only if disabled)
        if not self.is_enabled:
            result["status"] = "disabled"
            result["requires"] = self.required_feature or "Unknown feature"
        # Add connection status for MCP tools (not connected)
        elif not self.is_connected:
            result["status"] = "not_connected"
            result["requires_connection"] = self.mcp_server_name or "MCP Server"
            result["setup_hint"] = f"Connect '{self.mcp_server_name}' in Connectors to use this tool"

        # Add server icon for MCP tools (frontend display only)
        if self.mcp_server_icon:
            result["server_icon"] = self.mcp_server_icon
            if self.mcp_server_icon_invert:
                result["server_icon_invert"] = True

        # Only show required parameter names (not full schema - saves tokens)
        if self.definition.input_schema:
            required_params = self._get_required_param_names(self.definition.input_schema)
            if required_params:
                result["required_params"] = required_params

        # Skip examples in search results - too verbose, full schema available when bound

        return result

    @staticmethod
    def _truncate_description(description: str, max_length: int = 120) -> str:
        """Truncate description and strip markdown formatting."""
        if not description:
            return ""

        # Strip markdown headers (## Overview, etc.)
        cleaned = re.sub(r'^#+\s*\w+\s*\n', '', description.strip())
        cleaned = re.sub(r'\n+', ' ', cleaned)  # Replace newlines with spaces
        cleaned = cleaned.strip()

        if len(cleaned) <= max_length:
            return cleaned

        # Truncate at word boundary
        truncated = cleaned[:max_length].rsplit(' ', 1)[0]
        return truncated + "..."

    @staticmethod
    def _get_required_param_names(schema: Dict[str, Any]) -> List[str]:
        """Get just the names of required parameters."""
        if not schema:
            return []
        return schema.get("required", [])

    @staticmethod
    def _simplify_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Simplify JSON Schema for display."""
        if not schema or "properties" not in schema:
            return {}

        simplified = {}
        required = schema.get("required", [])

        for name, prop in schema.get("properties", {}).items():
            prop_info = {
                "type": prop.get("type", "any"),
                "required": name in required,
            }

            desc = prop.get("description", "")
            if desc:
                prop_info["description"] = desc[:100]  # Truncate

            if "default" in prop:
                prop_info["default"] = prop["default"]

            if "enum" in prop:
                prop_info["allowed_values"] = prop["enum"]

            simplified[name] = prop_info

        return simplified
