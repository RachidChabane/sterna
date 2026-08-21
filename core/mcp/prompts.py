"""System prompts for MCP tool integration."""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for template to avoid loading JSON on every call
_template_cache: Optional[str] = None


def _load_template() -> str:
    """Load MCP tools prompt template from JSON file."""
    global _template_cache

    if _template_cache is not None:
        return _template_cache

    try:
        template_path = Path(__file__).parent.parent / "llm" / "prompts" / "mcp_tools_template.json"
        with open(template_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            _template_cache = config["template"]
            return _template_cache
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load MCP tools template: {e}")
        # Fallback to a minimal template
        return "You have access to {tools_count} external tool(s) from {servers_count} MCP server(s).\n\n{tools_content}"


def build_mcp_system_prompt(tools: list) -> str:
    """Build system prompt for MCP-enabled conversations.

    This function is called dynamically by llm.prompt_builder when MCP tools are enabled.

    Args:
        tools: List of MCPTool instances available to the model

    Returns:
        System prompt string describing available tools and usage guidelines
    """
    if not tools:
        return ""

    # Group tools by server for better organization
    servers_map = {}
    for tool in tools:
        server_name = tool.server.name
        if server_name not in servers_map:
            servers_map[server_name] = {
                'server': tool.server,
                'tools': []
            }
        servers_map[server_name]['tools'].append(tool)

    # Build organized tools description
    sections = []
    for server_name, data in servers_map.items():
        server = data['server']
        tools_list = data['tools']

        # Server header with description if available
        server_desc = f"**{server_name}**"
        if server.description:
            server_desc += f" - {server.description}"

        # Tools list for this server
        tool_items = []
        for tool in tools_list:
            tool_items.append(f"  - `{tool.name}`: {tool.description}")

        section = f"{server_desc}\n" + "\n".join(tool_items)
        sections.append(section)

    tools_content = "\n\n".join(sections)

    # Load template and fill in variables
    template = _load_template()

    return template.format(
        tools_count=len(tools),
        servers_count=len(servers_map),
        tools_content=tools_content
    )
