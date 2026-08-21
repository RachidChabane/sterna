"""
Smart History Pruning

Reduces token usage by intelligently pruning redundant content
from conversation history within a session.

Rules:
1. Deduplicate file reads: If same file read multiple times, summarize older reads
2. Collapse read+edit sequences: If file was read then edited, collapse the read
3. Age-based summarization: Large tool results from many turns ago get summarized
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Configuration
MAX_TOOL_RESULT_AGE = 8  # Turns before tool results get summarized (increased from 4)
MAX_TOOL_RESULT_CHARS = 3000  # Threshold for summarization (increased from 2000)
MIN_MESSAGES_FOR_PRUNING = 10  # Don't prune short conversations (increased from 6)


def prune_conversation_history(messages: List[Dict[str, Any]], user=None) -> List[Dict[str, Any]]:
    """
    Prune redundant content from conversation history.

    Args:
        messages: List of message dicts with role, content, tool_calls, etc.
        user: User instance for API key resolution (optional)

    Returns:
        Pruned list of messages with reduced token usage.
    """
    if len(messages) < MIN_MESSAGES_FOR_PRUNING:
        return messages

    # Don't modify the original list
    messages = [_deep_copy_message(m) for m in messages]

    # Track file operations
    file_reads: Dict[str, List[int]] = {}  # path -> list of message indices
    file_edits: Set[str] = set()  # paths that were edited

    # First pass: identify file operations
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tool_info = _extract_tool_info(msg)
            if tool_info:
                tool_name, path = tool_info
                if tool_name == "read_file" and path:
                    if path not in file_reads:
                        file_reads[path] = []
                    file_reads[path].append(i)
                elif tool_name in ("edit_file", "write_file") and path:
                    file_edits.add(path)

    # Second pass: prune based on rules
    total_messages = len(messages)
    pruned_count = 0

    # Rule 1: Deduplicate file reads - keep only the latest read for each file
    # BUT preserve useful structure information from earlier reads
    for path, indices in file_reads.items():
        if len(indices) > 1:
            # Keep the last read, extract useful summary from earlier ones
            for idx in indices[:-1]:
                msg = messages[idx]
                original_content = msg.get("content", "")
                if len(original_content) > 500:  # Only summarize if significant
                    # Use LLM to create useful summary
                    summary = _summarize_file_content_with_llm(original_content, path, user=user)
                    messages[idx]["content"] = json.dumps({
                        "success": True,
                        "data": {
                            "path": path,
                            "note": f"[Earlier read of {path} - latest version available below]",
                            "summary": summary,  # LLM-generated summary!
                            "original_size": len(original_content),
                        }
                    })
                    pruned_count += 1
                    logger.debug(f"[HistoryPruner] Deduplicated read of {path} at index {idx}")

    # Rule 2: Collapse read+edit sequences
    for path in file_edits:
        if path in file_reads:
            # Find reads that happened before any edit
            for idx in file_reads[path]:
                # Check if there's an edit after this read
                has_edit_after = _has_edit_after(messages, idx, path)
                if has_edit_after:
                    msg = messages[idx]
                    original_content = msg.get("content", "")
                    if len(original_content) > 200:
                        # Extract line count if available
                        try:
                            data = json.loads(original_content)
                            lines = data.get("data", {}).get("lines", "unknown")
                            total_lines = data.get("data", {}).get("total_lines", lines)
                        except (json.JSONDecodeError, TypeError):
                            total_lines = "unknown"

                        messages[idx]["content"] = json.dumps({
                            "success": True,
                            "data": {
                                "path": path,
                                "note": f"[File was read ({total_lines} lines) and subsequently edited]",
                                "original_size": len(original_content),
                            }
                        })
                        pruned_count += 1
                        logger.debug(f"[HistoryPruner] Collapsed read+edit for {path} at index {idx}")

    # Rule 3: Age-based summarization for large tool results
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            age = total_messages - i
            content = msg.get("content", "")

            if age > MAX_TOOL_RESULT_AGE and len(content) > MAX_TOOL_RESULT_CHARS:
                # Already pruned by rules 1 or 2
                if "[Earlier read" in content or "[File was read" in content:
                    continue

                tool_info = _extract_tool_info(msg)
                tool_name = tool_info[0] if tool_info else "unknown"

                # Summarize based on tool type
                summary = _summarize_tool_result(tool_name, content, user=user)
                if summary and len(summary) < len(content):
                    messages[i]["content"] = summary
                    pruned_count += 1
                    logger.debug(f"[HistoryPruner] Age-summarized {tool_name} result at index {i}")

    if pruned_count > 0:
        logger.info(f"[HistoryPruner] Pruned {pruned_count} tool results")

    return messages


def _deep_copy_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy a message dict."""
    return json.loads(json.dumps(msg))


def _extract_tool_info(msg: Dict[str, Any]) -> Optional[Tuple[str, Optional[str]]]:
    """Extract tool name and path from a tool result message."""
    content = msg.get("content", "")
    try:
        data = json.loads(content)
        # Try to get path from various locations
        path = None
        if isinstance(data, dict):
            path = data.get("data", {}).get("path")
            if not path:
                path = data.get("path")

        # Try to infer tool name from content
        tool_name = None
        if "files" in str(data) and "count" in str(data):
            tool_name = "list_files"
        elif path and "content" in str(data):
            tool_name = "read_file"
        elif "diff" in str(data) or "edited" in str(data).lower():
            tool_name = "edit_file"
        elif path and "message" in str(data) and "Success" in str(data):
            tool_name = "write_file"

        return (tool_name, path) if tool_name else None
    except (json.JSONDecodeError, TypeError):
        return None


def _has_edit_after(messages: List[Dict[str, Any]], read_idx: int, path: str) -> bool:
    """Check if there's an edit to the file after the given read index."""
    for i in range(read_idx + 1, len(messages)):
        msg = messages[i]
        if msg.get("role") == "assistant":
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                if func.get("name") in ("edit_file", "write_file"):
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                        if args.get("path") == path or path in args.get("path", ""):
                            return True
                    except json.JSONDecodeError:
                        pass
    return False


def _summarize_tool_result(tool_name: str, content: str, user=None) -> Optional[str]:
    """Create a summary of a tool result."""
    try:
        data = json.loads(content)

        if tool_name == "list_files":
            # Summarize file listing
            files = data.get("data", {}).get("files", [])
            count = len(files) if isinstance(files, list) else data.get("data", {}).get("count", 0)
            path = data.get("data", {}).get("path", "/")
            return json.dumps({
                "success": True,
                "data": {
                    "path": path,
                    "note": f"[Listed {count} items - details omitted for brevity]",
                    "count": count,
                }
            })

        elif tool_name == "read_file":
            # Summarize file read with LLM
            path = data.get("data", {}).get("path", "unknown")
            lines = data.get("data", {}).get("lines", 0)
            total_lines = data.get("data", {}).get("total_lines", lines)
            # Use LLM to create useful summary
            summary = _summarize_file_content_with_llm(content, path, user=user)
            return json.dumps({
                "success": True,
                "data": {
                    "path": path,
                    "note": f"[File content ({total_lines} lines) - summary below]",
                    "total_lines": total_lines,
                    "summary": summary,  # LLM-generated summary!
                }
            })

        elif tool_name in ("run_bash", "execute_programming_task"):
            # Summarize command output
            output = data.get("data", {}).get("output", "")
            exit_code = data.get("data", {}).get("exit_code", 0)
            lines = output.count('\n') + 1 if output else 0
            return json.dumps({
                "success": data.get("success", True),
                "data": {
                    "note": f"[Command output ({lines} lines, exit_code={exit_code}) - truncated for brevity]",
                    "exit_code": exit_code,
                    "output_preview": output[:200] + "..." if len(output) > 200 else output,
                }
            })

        # Default: just indicate it was truncated
        return json.dumps({
            "success": data.get("success", True),
            "data": {
                "note": f"[Tool result truncated for brevity - original size: {len(content)} chars]",
            }
        })

    except (json.JSONDecodeError, TypeError):
        # If we can't parse, just truncate
        return json.dumps({
            "note": f"[Tool result truncated - original size: {len(content)} chars]",
            "preview": content[:200] + "..." if len(content) > 200 else content,
        })


def _summarize_file_content_with_llm(content: str, path: str, user=None) -> str:
    """Use a cheap LLM to summarize file content.

    This is language-agnostic and works with any file type.

    Args:
        content: File content to summarize
        path: File path for context
        user: User instance for API key resolution (optional)
    """
    try:
        data = json.loads(content)
        file_content = data.get("data", {}).get("content", "")
        if not file_content:
            file_content = data.get("content", "")
        if not file_content:
            return "Empty file"
    except (json.JSONDecodeError, TypeError):
        file_content = content

    # Truncate to reasonable size for summarization
    if len(file_content) > 8000:
        file_content = file_content[:4000] + "\n...[truncated]...\n" + file_content[-2000:]

    try:
        from llm.client import OpenRouterClient
        from code_sessions.optimization.constants import SCOUT_MODEL_ID

        client = OpenRouterClient(user=user, request_source='history_pruner')
        result = client.complete(
            model=SCOUT_MODEL_ID,  # Use cheap model
            messages=[
                {
                    "role": "system",
                    "content": "Summarize this file in 2-3 sentences. Include: main purpose, key functions/classes/exports, and important dependencies. Be concise."
                },
                {
                    "role": "user",
                    "content": f"File: {path}\n\n```\n{file_content}\n```"
                }
            ],
            max_tokens=150,
            temperature=0.3,
        )
        summary = result.get("content", "").strip()
        if summary:
            return summary
    except Exception as e:
        logger.warning(f"[HistoryPruner] LLM summarization failed: {e}")

    # Fallback: just return first 500 chars as preview
    return f"Preview: {file_content[:500]}..."
