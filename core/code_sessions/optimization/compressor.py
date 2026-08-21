"""
Tool Result Compression

Compresses tool results to reduce token usage while preserving essential information.
Different strategies are applied based on tool type.
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import (
    BASH_ERROR_MAX_LINES,
    BASH_OUTPUT_MAX_LINES,
    FILE_CONTENT_MAX_LINES,
    FILE_HEAD_LINES,
    FILE_TAIL_LINES,
    LIST_FILES_GROUP_BY_DIR,
    LIST_FILES_MAX_ITEMS,
    MAX_TOOL_RESULT_CHARS,
    PROGRAMMING_TASK_OUTPUT_MAX_CHARS,
)

logger = logging.getLogger(__name__)


class ToolResultCompressor:
    """Compresses tool results to reduce token consumption."""

    def compress(
        self,
        tool_name: str,
        result: str,
        args: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Compress a tool result based on the tool type.

        Args:
            tool_name: Name of the tool
            result: Raw tool result string
            args: Tool arguments (for context)

        Returns:
            Compressed result string
        """
        if not result:
            return result

        # Get tool-specific compressor
        compressor_method = getattr(
            self, f"_compress_{tool_name}", self._compress_default
        )

        try:
            compressed = compressor_method(result, args or {})

            # Log compression ratio
            original_len = len(result)
            compressed_len = len(compressed)
            if original_len > 0:
                ratio = compressed_len / original_len
                saved = original_len - compressed_len
                if ratio < 0.95:  # Log if any significant compression
                    logger.info(
                        f"[Compressor] {tool_name}: {original_len:,} → {compressed_len:,} chars "
                        f"({ratio:.0%}, saved {saved:,} chars)"
                    )
                else:
                    logger.debug(f"[Compressor] {tool_name}: {original_len:,} chars (no compression needed)")

            return compressed

        except Exception as e:
            logger.warning(f"[Compressor] Compression failed for {tool_name}: {e}")
            return self._compress_default(result, args or {})

    def _compress_default(self, result: str, args: Dict[str, Any]) -> str:
        """Default compression: simple truncation with ellipsis."""
        if len(result) <= MAX_TOOL_RESULT_CHARS:
            return result

        half = MAX_TOOL_RESULT_CHARS // 2
        return (
            f"{result[:half]}\n\n"
            f"... [TRUNCATED {len(result) - MAX_TOOL_RESULT_CHARS} chars] ...\n\n"
            f"{result[-half:]}"
        )

    def _compress_list_files(self, result: str, args: Dict[str, Any]) -> str:
        """
        Compress file listing by grouping by directory and limiting count.

        Example output:
        ```
        📁 src/ (23 files)
           ├── components/ (12 files: *.tsx, *.css)
           ├── utils/ (5 files: *.ts)
           └── main.tsx, index.ts, App.tsx
        📁 tests/ (8 files: *.test.ts)
        ```
        """
        try:
            # Try to parse as JSON first
            data = json.loads(result)
            if isinstance(data, dict) and "data" in data:
                files = data.get("data", {}).get("files", [])
            elif isinstance(data, list):
                files = data
            else:
                files = []

            if not files:
                return result

            # Extract file paths
            paths = []
            for f in files:
                if isinstance(f, dict):
                    paths.append(f.get("name", f.get("path", "")))
                elif isinstance(f, str):
                    paths.append(f)

            if not paths:
                return result

            # Apply limit
            total_files = len(paths)
            if total_files > LIST_FILES_MAX_ITEMS:
                paths = paths[:LIST_FILES_MAX_ITEMS]

            if LIST_FILES_GROUP_BY_DIR:
                return self._group_files_by_directory(paths, total_files)
            else:
                # Simple list with truncation
                output = "\n".join(paths)
                if total_files > LIST_FILES_MAX_ITEMS:
                    output += f"\n... and {total_files - LIST_FILES_MAX_ITEMS} more files"
                return output

        except json.JSONDecodeError:
            # Not JSON, apply default compression
            return self._compress_default(result, args)

    def _group_files_by_directory(self, paths: list, total_files: int) -> str:
        """Group files by directory for compact display."""
        # Group by parent directory
        dir_files: Dict[str, list] = defaultdict(list)
        for path in paths:
            parts = Path(path).parts
            if len(parts) > 1:
                parent = parts[0]
                dir_files[parent].append(path)
            else:
                dir_files["."].append(path)

        # Build compact output
        lines = []
        for dir_name, files in sorted(dir_files.items()):
            if dir_name == ".":
                # Root files
                if len(files) <= 5:
                    lines.extend(files)
                else:
                    exts = self._get_common_extensions(files)
                    lines.append(f"(root): {len(files)} files ({exts})")
            else:
                # Subdirectory
                exts = self._get_common_extensions(files)
                if len(files) <= 3:
                    for f in files:
                        lines.append(f)
                else:
                    lines.append(f"{dir_name}/ ({len(files)} files: {exts})")

        output = "\n".join(lines)
        if total_files > LIST_FILES_MAX_ITEMS:
            output += f"\n... and {total_files - LIST_FILES_MAX_ITEMS} more files"

        return output

    def _get_common_extensions(self, files: list) -> str:
        """Get common file extensions from a list of files."""
        ext_counts: Dict[str, int] = defaultdict(int)
        for f in files:
            ext = Path(f).suffix
            if ext:
                ext_counts[ext] += 1

        # Sort by count and take top 3
        sorted_exts = sorted(ext_counts.items(), key=lambda x: -x[1])
        top_exts = [f"*{ext}" for ext, _ in sorted_exts[:3]]
        return ", ".join(top_exts) if top_exts else "various"

    def _compress_read_file(self, result: str, args: Dict[str, Any]) -> str:
        """
        Compress file contents with smart truncation.

        For large files, shows:
        - File metadata (lines, size)
        - First N lines (head)
        - Last M lines (tail)
        - Middle truncation indicator
        """
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                content = data.get("data", {}).get("content", "")
                path = args.get("path", "file")
                success = data.get("success", True)

                if not success:
                    return result  # Keep error messages intact

                if not content:
                    return result

                lines = content.split("\n")
                total_lines = len(lines)

                if total_lines <= FILE_CONTENT_MAX_LINES:
                    return result  # No truncation needed

                # Smart truncation: head + tail
                head = lines[:FILE_HEAD_LINES]
                tail = lines[-FILE_TAIL_LINES:]
                omitted = total_lines - FILE_HEAD_LINES - FILE_TAIL_LINES

                truncated_content = (
                    "\n".join(head)
                    + f"\n\n... [{omitted} lines omitted] ...\n\n"
                    + "\n".join(tail)
                )

                # Rebuild JSON response
                compressed_data = {
                    "success": True,
                    "data": {
                        "path": path,
                        "content": truncated_content,
                        "_meta": {
                            "total_lines": total_lines,
                            "truncated": True,
                            "shown_lines": FILE_HEAD_LINES + FILE_TAIL_LINES,
                        }
                    }
                }
                return json.dumps(compressed_data, ensure_ascii=False)

        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: line-based truncation
        lines = result.split("\n")
        if len(lines) <= FILE_CONTENT_MAX_LINES:
            return result

        head = lines[:FILE_HEAD_LINES]
        tail = lines[-FILE_TAIL_LINES:]
        omitted = len(lines) - FILE_HEAD_LINES - FILE_TAIL_LINES

        return (
            "\n".join(head)
            + f"\n\n... [{omitted} lines omitted] ...\n\n"
            + "\n".join(tail)
        )

    def _compress_run_bash(self, result: str, args: Dict[str, Any]) -> str:
        """
        Compress bash output, keeping errors intact but truncating success output.
        """
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                success = data.get("success", True)
                output = data.get("data", {}).get("output", "")
                error = data.get("data", {}).get("error", "")
                exit_code = data.get("data", {}).get("exit_code", 0)

                # Keep errors mostly intact (important for debugging)
                if error:
                    error_lines = error.split("\n")
                    if len(error_lines) > BASH_ERROR_MAX_LINES:
                        error = (
                            "\n".join(error_lines[:BASH_ERROR_MAX_LINES])
                            + f"\n... [{len(error_lines) - BASH_ERROR_MAX_LINES} more error lines]"
                        )

                # Truncate success output more aggressively
                if output:
                    output_lines = output.split("\n")
                    if len(output_lines) > BASH_OUTPUT_MAX_LINES:
                        # Keep head and tail
                        head_lines = BASH_OUTPUT_MAX_LINES // 2
                        tail_lines = BASH_OUTPUT_MAX_LINES - head_lines
                        omitted = len(output_lines) - head_lines - tail_lines
                        output = (
                            "\n".join(output_lines[:head_lines])
                            + f"\n... [{omitted} lines omitted] ...\n"
                            + "\n".join(output_lines[-tail_lines:])
                        )

                compressed_data = {
                    "success": success,
                    "data": {
                        "command": args.get("command", ""),
                        "output": output,
                        "error": error,
                        "exit_code": exit_code,
                    }
                }
                return json.dumps(compressed_data, ensure_ascii=False)

        except (json.JSONDecodeError, KeyError):
            pass

        return self._compress_default(result, args)

    def _compress_execute_programming_task(
        self, result: str, args: Dict[str, Any]
    ) -> str:
        """
        Compress programming task output, preserving JSON summaries.
        """
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                output = data.get("data", {}).get("output", "")

                # Try to find JSON in output (common pattern)
                json_match = re.search(r'\{[\s\S]*\}', output)
                if json_match:
                    try:
                        # Try to parse and keep just the JSON
                        json_data = json.loads(json_match.group())
                        data["data"]["output"] = json.dumps(
                            json_data, indent=2, ensure_ascii=False
                        )
                        return json.dumps(data, ensure_ascii=False)
                    except json.JSONDecodeError:
                        pass

                # Truncate raw output
                if len(output) > PROGRAMMING_TASK_OUTPUT_MAX_CHARS:
                    output = (
                        output[:PROGRAMMING_TASK_OUTPUT_MAX_CHARS]
                        + f"\n... [truncated {len(output) - PROGRAMMING_TASK_OUTPUT_MAX_CHARS} chars]"
                    )
                    data["data"]["output"] = output

                return json.dumps(data, ensure_ascii=False)

        except (json.JSONDecodeError, KeyError):
            pass

        return self._compress_default(result, args)

    def _compress_edit_file(self, result: str, args: Dict[str, Any]) -> str:
        """Edit file results are usually small, minimal compression needed."""
        # These are typically confirmations, keep them short
        if len(result) <= 500:
            return result
        return self._compress_default(result, args)

    def _compress_write_file(self, result: str, args: Dict[str, Any]) -> str:
        """Write file results are confirmations, keep them brief."""
        if len(result) <= 500:
            return result
        return self._compress_default(result, args)

    def _compress_update_todos(self, result: str, args: Dict[str, Any]) -> str:
        """Todo updates are small, no compression needed."""
        return result

    def _compress_prepare_pull_request(
        self, result: str, args: Dict[str, Any]
    ) -> str:
        """PR preparation results should be kept intact."""
        return result


# Singleton instance for convenience
_compressor_instance: Optional[ToolResultCompressor] = None


def get_compressor() -> ToolResultCompressor:
    """Get or create the singleton compressor instance."""
    global _compressor_instance
    if _compressor_instance is None:
        _compressor_instance = ToolResultCompressor()
    return _compressor_instance


def compress_tool_result(
    tool_name: str,
    result: str,
    args: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to compress a tool result.

    Args:
        tool_name: Name of the tool
        result: Raw tool result
        args: Tool arguments

    Returns:
        Compressed result
    """
    return get_compressor().compress(tool_name, result, args)
