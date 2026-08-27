"""
File Tools Integration for LLM

Provides file system tools to AI assistants through the LLM completion endpoints.
Simplified integration that executes tools immediately (no approval needed since sandboxed).
Also supports MCP-based tools (GitHub, etc.) when configured.
"""

import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Store for GitHub token per request (thread-local would be better in production)
_github_token_store: Dict[str, str] = {}

# Global instances (initialized on first use)
_tool_executor = None


def get_tool_executor():
    """Get or create HTTPToolExecutor instance."""
    global _tool_executor
    if _tool_executor is None:
        from llm.sandbox_tool_executor import HTTPToolExecutor
        # Use container name for orchestrator service
        _tool_executor = HTTPToolExecutor(orchestrator_url="http://sterna-orchestrator:8003")
        logger.info("Initialized HTTPToolExecutor for file tools")
    return _tool_executor


def get_file_tools() -> List[Dict[str, Any]]:
    """
    Get file system tools in OpenAI format.

    Returns:
        List of tool definitions
    """
    from sandbox.orchestrator.file_tools import get_file_tools as get_tools_defs
    return get_tools_defs()


def _simplify_coding_agent_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplify coding agent result for LLM consumption.

    Only passes the summary and file lists to the LLM, not the full execution logs.
    This keeps the LLM context clean and focused on what was accomplished.

    Args:
        result: Full coding agent result with steps, tokens, etc.

    Returns:
        Simplified result with only summary and file information
    """
    if not result.get("success"):
        # For errors, return the error message
        return {
            "success": False,
            "error": result.get("error", "Coding Agent execution failed")
        }

    data = result.get("data", {})

    # Build a concise summary for the LLM
    summary = data.get("summary", "Task completed")
    files_created = data.get("files_created", [])
    files_modified = data.get("files_modified", [])

    simplified = {
        "success": True,
        "summary": summary,
    }

    # Only include file lists if they have content
    if files_created:
        simplified["files_created"] = files_created
    if files_modified:
        simplified["files_modified"] = files_modified

    return simplified


def execute_file_tool_call(
    tool_call_id: str,
    tool_name: str,
    tool_arguments: Dict[str, Any],
    user_id: str,
    conversation_id: str,
    chat_id: Optional[str] = None,
    sync_mode: bool = True,
    auth_token: Optional[str] = None,
    github_token: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute a file tool call immediately.

    Args:
        tool_call_id: ID of the tool call
        tool_name: Name of the tool to execute
        tool_arguments: Arguments for the tool
        user_id: User ID for sandbox isolation
        conversation_id: Conversation ID
        chat_id: Optional chat ID
        sync_mode: Whether to use synced sandbox mode
        auth_token: JWT auth token from request
        github_token: Optional GitHub OAuth token for GitHub MCP tools
        model_metadata: Model metadata for file attribution (model_name, model_id, provider, icons)

    Returns:
        Dict with tool result message in format:
        {
            "role": "tool",
            "tool_call_id": str,
            "content": str (JSON serialized result)
        }
    """
    logger.info(f"Executing file tool: {tool_name} (tool_call_id={tool_call_id})")
    logger.debug(f"Tool arguments: {tool_arguments}")

    try:
        # Create a new tool executor with the auth token for this request
        from llm.sandbox_tool_executor import HTTPToolExecutor
        tool_executor = HTTPToolExecutor(
            orchestrator_url="http://sterna-orchestrator:8003",
            auth_token=auth_token,
            github_token=github_token
        )

        # Set model metadata for file attribution and model selection
        if model_metadata:
            tool_executor.set_model_metadata(model_metadata)
            # Also set the current model so coding agent handlers use the
            # chat's selected model instead of defaulting to Sonnet
            if model_metadata.get("model_id"):
                tool_executor.set_current_model(model_metadata["model_id"])

        result = tool_executor.execute_tool_call(
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            sync_mode=sync_mode
        )

        logger.info(f"Tool {tool_name} executed successfully: {result.get('success')}")

        # For coding agent tools, simplify the result for the LLM (don't send full execution logs)
        # But include full data for frontend display/persistence
        from .agent_tool_handlers import CODING_AGENT_TOOL_NAMES
        if tool_name in CODING_AGENT_TOOL_NAMES:
            llm_result = _simplify_coding_agent_result(result)
            # Include full result data for frontend (steps, duration, tokens, etc.)
            data = result.get("data", {})
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(llm_result, ensure_ascii=False),
                # Frontend-specific data (not sent to LLM)
                "coding_agent_data": {
                    "job_id": data.get("job_id"),
                    "steps": data.get("steps", []),
                    "duration_ms": data.get("duration_ms", 0),
                    "total_tokens": data.get("total_tokens", 0),
                    "cost_usd": data.get("cost_usd", 0),
                    "files_created": data.get("files_created", []),
                    "files_modified": data.get("files_modified", []),
                    "summary": data.get("summary"),
                    "success": result.get("success", False),
                }
            }
        else:
            llm_result = result

        # Return as tool message
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(llm_result, ensure_ascii=False)
        }

    except Exception as e:
        logger.error(f"Error executing file tool {tool_name}: {e}", exc_info=True)

        # Return error as tool message
        error_result = {
            "success": False,
            "error": f"Failed to execute tool: {str(e)}"
        }

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(error_result, ensure_ascii=False)
        }


def handle_file_tool_calls(
    tool_calls: List[Dict[str, Any]],
    user_id: str,
    conversation_id: str,
    chat_id: Optional[str] = None,
    sync_mode: bool = True,
    auth_token: Optional[str] = None,
    github_token: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Handle multiple file tool calls.

    Args:
        tool_calls: List of tool calls from LLM response
        user_id: User ID
        conversation_id: Conversation ID
        chat_id: Optional chat ID
        sync_mode: Sandbox sync mode
        auth_token: JWT auth token from request
        github_token: Optional GitHub OAuth token for GitHub MCP tools
        model_metadata: Model metadata for file attribution

    Returns:
        List of tool result messages
    """
    tool_messages = []

    for tool_call in tool_calls:
        tool_call_id = tool_call.get("id") or ""
        function = tool_call.get("function", {})
        tool_name = function.get("name")
        arguments_str = function.get("arguments", "{}")

        # Parse arguments
        try:
            tool_arguments = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool arguments: {e}")
            tool_arguments = {}

        # Execute tool and collect result
        tool_message = execute_file_tool_call(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            sync_mode=sync_mode,
            auth_token=auth_token,
            github_token=github_token,
            model_metadata=model_metadata
        )

        tool_messages.append(tool_message)

    return tool_messages


def should_enable_file_tools(request_data: Dict[str, Any], user) -> bool:
    """
    Determine if file tools should be enabled for this request.

    Args:
        request_data: Request data dict
        user: Django user object

    Returns:
        True if file tools should be enabled
    """
    # Check explicit flag in request
    enable_file_tools = request_data.get("enable_file_tools", False)

    if not enable_file_tools:
        return False

    # Additional checks can be added here
    # For example: user permissions, feature flags, etc.

    return True
