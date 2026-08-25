"""System prompts for MCP tool integration."""

import logging

logger = logging.getLogger(__name__)

# Template for the MCP tools system prompt section. {tools_count},
# {servers_count}, and {tools_content} are filled in by
# build_mcp_system_prompt().
_MCP_TOOLS_PROMPT_TEMPLATE = (
    "# External Tools (MCP)\n\n"
    "You have access to {tools_count} tool(s) from {servers_count} MCP server(s):\n\n"
    "{tools_content}\n\n"
    "## Usage Guidelines:\n\n"
    "1. **Extract parameters intelligently**: Analyze the user's message and conversation "
    "context to determine parameter values. Only ask for clarification when genuinely ambiguous.\n\n"
    "2. **Be transparent**: Briefly explain what you'll do before calling a tool.\n\n"
    "3. **User approval**: Tool calls require user approval. Wait for execution results before continuing.\n\n"
    "4. **Handle errors**: If a tool fails or is rejected, adapt and explain alternatives.\n\n"
    "5. **Explain results**: Interpret tool outputs in plain language for the user."
)


def build_mcp_system_prompt(tools: list) -> str:
    """Build system prompt for MCP-enabled conversations.

    Called by llm.client's direct completion path when MCP tools are
    enabled and available, to describe the actual tool list by name.

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

    return _MCP_TOOLS_PROMPT_TEMPLATE.format(
        tools_count=len(tools),
        servers_count=len(servers_map),
        tools_content=tools_content
    )
