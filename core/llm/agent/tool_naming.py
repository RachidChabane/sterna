"""Translation between catalog tool ids and provider-safe function names.

Anthropic's tool-name pattern (``^[a-zA-Z0-9_-]{1,128}$``) forbids the
colon used by MCP catalog ids, so ids are sanitized on the way out to the
model and restored on the way back in. Single responsibility: that one
mapping.
"""

import re

# ``mcp_{type}_{numeric_id}_{rest}`` -- the colon sits between type and id.
_SANITIZED_MCP_TOOL_ID = re.compile(r'^(mcp_[a-z]+)_(\d+)_(.+)$')


def unsanitize_tool_name(sanitized_name: str) -> str:
    """
    Convert a sanitized tool name back to the original format with colons.

    The sanitization replaces colons with underscores to comply with Anthropic's
    tool name pattern ^[a-zA-Z0-9_-]{1,128}$.

    Example:
        mcp_custom_463_notion-create-comment -> mcp_custom:463_notion-create-comment

    The pattern is: mcp_{type}_{id}_{name} where type is 'custom', 'stdio', 'http', etc.
    and id is a numeric server ID. We restore the colon between type and id.
    """
    match = _SANITIZED_MCP_TOOL_ID.match(sanitized_name)
    if match:
        return f"{match.group(1)}:{match.group(2)}_{match.group(3)}"
    return sanitized_name
