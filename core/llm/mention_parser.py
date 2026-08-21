"""
Parse @mentions from user messages.

Supports patterns:
- @server_name - Reference to an MCP server
- @server_name:tool_name - Reference to a specific tool on a server
"""

import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MentionedTool:
    """A tool mentioned in a user message."""
    server_name: str
    tool_name: Optional[str] = None

    @property
    def full_name(self) -> str:
        """Full reference like @Notion:create-comment or @Notion."""
        if self.tool_name:
            return f"@{self.server_name}:{self.tool_name}"
        return f"@{self.server_name}"


def parse_mentions(text: str) -> List[MentionedTool]:
    """
    Parse @mentions from text.

    Patterns:
    - @server_name - References a server
    - @server_name:tool_name - References a specific tool

    Args:
        text: User message text

    Returns:
        List of MentionedTool objects
    """
    mentions = []

    # Match @server_name or @server_name:tool_name
    # Server/tool names can contain letters, numbers, underscores, hyphens
    # Must be at start of text or preceded by whitespace/punctuation (not word char)
    # This prevents matching emails like user@example.com
    pattern = r'(?:^|(?<=[\s.,!?;:\'"()\[\]{}]))@([a-zA-Z0-9_-]+)(?::([a-zA-Z0-9_-]+))?'

    for match in re.finditer(pattern, text):
        server_name = match.group(1)
        tool_name = match.group(2)  # May be None

        mentions.append(MentionedTool(
            server_name=server_name,
            tool_name=tool_name
        ))

    return mentions


def extract_mentions_from_messages(messages: List[dict]) -> List[MentionedTool]:
    """
    Extract all @mentions from a list of messages.

    Only looks at user messages (role='user').

    Args:
        messages: List of message dicts with 'role' and 'content' keys

    Returns:
        List of unique MentionedTool objects
    """
    all_mentions = []
    seen = set()

    for msg in messages:
        if msg.get("role") != "user":
            continue

        content = msg.get("content", "")

        # Handle multimodal content (list of parts)
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    mentions = parse_mentions(text)
                    for m in mentions:
                        key = (m.server_name.lower(), m.tool_name.lower() if m.tool_name else None)
                        if key not in seen:
                            seen.add(key)
                            all_mentions.append(m)
        elif isinstance(content, str):
            mentions = parse_mentions(content)
            for m in mentions:
                key = (m.server_name.lower(), m.tool_name.lower() if m.tool_name else None)
                if key not in seen:
                    seen.add(key)
                    all_mentions.append(m)

    return all_mentions


def build_mention_priority_prompt(mentions: List[MentionedTool], available_tools: List = None) -> Optional[str]:
    """
    Build a system prompt section that instructs the model to prioritize mentioned tools.

    Args:
        mentions: List of MentionedTool objects parsed from user messages
        available_tools: List of available MCP tools (to validate mentions)

    Returns:
        Prompt string or None if no valid mentions
    """
    if not mentions:
        return None

    # Build a map of available tools for validation
    available_map = {}
    if available_tools:
        for tool in available_tools:
            server_name = getattr(tool, 'server_name', None) or getattr(getattr(tool, 'server', None), 'name', None)
            tool_name = getattr(tool, 'name', None)
            if server_name and tool_name:
                key = server_name.lower()
                if key not in available_map:
                    available_map[key] = []
                available_map[key].append(tool_name)

    # Filter mentions to only those that match available tools
    valid_mentions = []
    for mention in mentions:
        server_key = mention.server_name.lower()

        # Check if server exists
        if server_key in available_map:
            if mention.tool_name:
                # Check if specific tool exists
                if mention.tool_name in available_map[server_key] or mention.tool_name.lower() in [t.lower() for t in available_map[server_key]]:
                    valid_mentions.append(mention)
                else:
                    logger.debug(f"Mentioned tool not found: {mention.full_name}")
            else:
                # Server-only mention is valid
                valid_mentions.append(mention)
        else:
            logger.debug(f"Mentioned server not found: {mention.server_name}")

    if not valid_mentions:
        return None

    # Build the priority instruction
    lines = ["## Tool Priority Instructions"]
    lines.append("The user has explicitly mentioned the following tools/servers. Use these directly without needing to discover them:")
    lines.append("")

    for mention in valid_mentions:
        if mention.tool_name:
            lines.append(f"- **{mention.tool_name}** from {mention.server_name} server - Use this tool for the user's request")
        else:
            lines.append(f"- **{mention.server_name}** server - Prefer tools from this server")

    lines.append("")
    lines.append("Do NOT use tool_discovery to find these tools - call them directly.")

    return "\n".join(lines)


# Tools that should be force-called when explicitly @mentioned
FORCED_TOOL_NAMES = {
    "plan_implementation", "implement_plan", "edit_plan", "coding_agent",
    "generate_image", "generate_video",
    "animate_image", "upscale_video", "animate_character",
}

# Pattern for extracting [key:value ...] params from media tool mentions
MEDIA_PARAM_PATTERN = re.compile(
    r'@(generate_image|generate_video|animate_image|upscale_video|animate_character)\s+\[([^\]]*)\]'
)


def extract_media_params(text: str) -> Optional[Dict[str, str]]:
    """
    Extract [key:value ...] parameters from media tool mentions.

    Example: "@generate_image [model:gemini-2.5-flash-image ratio:16:9 res:2K]"
    Returns: {"model": "gemini-2.5-flash-image", "ratio": "16:9", "res": "2K"}
    """
    match = MEDIA_PARAM_PATTERN.search(text)
    if not match:
        return None
    params = {}
    for pair in match.group(2).split():
        if ':' in pair:
            key, _, value = pair.partition(':')
            params[key.strip()] = value.strip()
    return params


def get_forced_tool_choice(mentions: List[MentionedTool]) -> Optional[str]:
    """
    Check if any mention is a coding agent tool that should be force-called.

    When a user explicitly selects @plan_implementation, @implement_plan, etc.
    via the UI picker, the LLM should not decide whether to call it - it should
    be forced via tool_choice.

    Returns the tool name to force, or None.
    """
    for mention in mentions:
        name = mention.server_name.lower()
        if name in FORCED_TOOL_NAMES:
            return mention.server_name
    return None
