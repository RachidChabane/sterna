"""
Smart Context Truncation

Uses AST parsing and heuristics to extract only relevant code sections,
reducing token usage while preserving context needed for editing.
"""

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    AST_CONTEXT_LINES_AFTER,
    AST_CONTEXT_LINES_BEFORE,
    AST_SUPPORTED_EXTENSIONS,
    MAX_FILE_PREVIEW_CHARS,
)

logger = logging.getLogger(__name__)


@dataclass
class CodeBlock:
    """Represents a code block (function, class, etc.)."""
    name: str
    type: str  # "function", "class", "method"
    start_line: int
    end_line: int
    content: str
    docstring: Optional[str] = None


@dataclass
class FileStructure:
    """Represents the structure of a source file."""
    path: str
    language: str
    total_lines: int
    imports: List[str]
    blocks: List[CodeBlock]
    has_error: bool = False
    error_message: Optional[str] = None


class SmartTruncator:
    """Truncates file content intelligently using AST and heuristics."""

    def truncate_for_edit(
        self,
        file_content: str,
        file_path: str,
        edit_target: Optional[str] = None
    ) -> str:
        """
        Truncate file content to relevant sections for editing.

        Args:
            file_content: Full file content
            file_path: Path to determine language
            edit_target: Optional target identifier (function/class name, line number)

        Returns:
            Truncated content with context
        """
        language = self._detect_language(file_path)

        # For small files, return as-is
        if len(file_content) <= MAX_FILE_PREVIEW_CHARS:
            return file_content

        # Try language-specific truncation
        if language == "python":
            return self._truncate_python(file_content, edit_target)
        elif language in ("javascript", "typescript"):
            return self._truncate_js_ts(file_content, edit_target)
        else:
            return self._truncate_generic(file_content, edit_target)

    def get_file_summary(self, file_content: str, file_path: str) -> str:
        """
        Generate a structural summary of a file without full content.

        Args:
            file_content: Full file content
            file_path: Path for language detection

        Returns:
            Summary showing file structure (functions, classes, imports)
        """
        structure = self.analyze_structure(file_content, file_path)

        parts = [f"# File: {file_path}"]
        parts.append(f"# Lines: {structure.total_lines}")
        parts.append(f"# Language: {structure.language}")

        if structure.has_error:
            parts.append(f"# Parse error: {structure.error_message}")
            # Fall back to line-based summary
            lines = file_content.split("\n")
            parts.append(f"\n## First 30 lines:\n{chr(10).join(lines[:30])}")
            if len(lines) > 30:
                parts.append(f"\n... [{len(lines) - 30} more lines]")
            return "\n".join(parts)

        # Imports
        if structure.imports:
            parts.append("\n## Imports:")
            for imp in structure.imports[:10]:
                parts.append(f"  {imp}")
            if len(structure.imports) > 10:
                parts.append(f"  ... and {len(structure.imports) - 10} more")

        # Code structure
        if structure.blocks:
            parts.append("\n## Structure:")
            for block in structure.blocks:
                signature = f"  {block.type}: {block.name} (lines {block.start_line}-{block.end_line})"
                parts.append(signature)
                if block.docstring:
                    doc_preview = block.docstring[:80]
                    if len(block.docstring) > 80:
                        doc_preview += "..."
                    parts.append(f"    \"{doc_preview}\"")

        return "\n".join(parts)

    def analyze_structure(self, file_content: str, file_path: str) -> FileStructure:
        """
        Analyze the structure of a source file.

        Args:
            file_content: Full file content
            file_path: Path for language detection

        Returns:
            FileStructure with imports and code blocks
        """
        language = self._detect_language(file_path)
        lines = file_content.split("\n")

        if language == "python":
            return self._analyze_python(file_content, file_path, lines)
        elif language in ("javascript", "typescript"):
            return self._analyze_js_ts(file_content, file_path, lines)
        else:
            return self._analyze_generic(file_content, file_path, lines)

    def extract_context_around(
        self,
        file_content: str,
        target_line: int,
        lines_before: int = AST_CONTEXT_LINES_BEFORE,
        lines_after: int = AST_CONTEXT_LINES_AFTER
    ) -> Tuple[str, int, int]:
        """
        Extract content around a target line.

        Args:
            file_content: Full file content
            target_line: Line number to center on (1-indexed)
            lines_before: Lines to include before target
            lines_after: Lines to include after target

        Returns:
            Tuple of (content, start_line, end_line)
        """
        lines = file_content.split("\n")
        total = len(lines)

        start = max(0, target_line - 1 - lines_before)
        end = min(total, target_line + lines_after)

        content_lines = lines[start:end]
        content = "\n".join(content_lines)

        return content, start + 1, end

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        return AST_SUPPORTED_EXTENSIONS.get(ext, "unknown")

    def _truncate_python(
        self,
        file_content: str,
        edit_target: Optional[str]
    ) -> str:
        """Truncate Python file using AST."""
        try:
            tree = ast.parse(file_content)
            lines = file_content.split("\n")

            # Find imports section
            imports = []
            last_import_line = 0
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    line_num = getattr(node, "lineno", 0)
                    last_import_line = max(last_import_line, line_num)
                    imports.append(ast.unparse(node))

            # Find target block if specified
            target_block = None
            if edit_target:
                target_block = self._find_python_block(tree, edit_target, lines)

            parts = []

            # Include imports
            if imports:
                parts.append("# Imports:")
                parts.append("\n".join(imports))
                parts.append("")

            if target_block:
                # Include target block with context
                parts.append(f"# Target: {target_block.name}")
                parts.append(target_block.content)
            else:
                # Include first few functions/classes
                blocks = self._extract_python_blocks(tree, lines)
                if blocks:
                    parts.append("# Key definitions:")
                    for block in blocks[:5]:
                        # Show signature only for non-target blocks
                        signature = self._get_block_signature(block, lines)
                        parts.append(signature)

            # Add truncation notice
            total_lines = len(lines)
            shown_lines = sum(len(p.split("\n")) for p in parts)
            if shown_lines < total_lines:
                parts.append(f"\n# ... [{total_lines - shown_lines} lines not shown]")

            return "\n".join(parts)

        except SyntaxError as e:
            logger.warning(f"Python syntax error during truncation: {e}")
            return self._truncate_generic(file_content, edit_target)

    def _truncate_js_ts(
        self,
        file_content: str,
        edit_target: Optional[str]
    ) -> str:
        """Truncate JavaScript/TypeScript file using regex patterns."""
        lines = file_content.split("\n")
        total_lines = len(lines)

        parts = []

        # Extract imports (at top of file usually)
        import_lines = []
        for i, line in enumerate(lines[:50]):
            if re.match(r'^(import|export\s+\{|const\s+\{.*\}\s+=\s+require)', line):
                import_lines.append(line)
            elif line.strip() and not line.strip().startswith("//"):
                break

        if import_lines:
            parts.append("// Imports:")
            parts.extend(import_lines)
            parts.append("")

        # Find function/class definitions
        patterns = [
            (r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)', "function"),
            (r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(', "arrow function"),
            (r'^(?:export\s+)?class\s+(\w+)', "class"),
            (r'^(?:export\s+)?interface\s+(\w+)', "interface"),
            (r'^(?:export\s+)?type\s+(\w+)', "type"),
        ]

        definitions: List[Dict[str, Any]] = []
        for i, line in enumerate(lines):
            for pattern, def_type in patterns:
                match = re.match(pattern, line)
                if match:
                    name = match.group(1)
                    definitions.append({
                        "name": name,
                        "type": def_type,
                        "line": i + 1,
                        "content": line,
                    })

        if edit_target:
            # Find the target
            target_def = None
            for d in definitions:
                if d["name"] == edit_target or str(d["line"]) == edit_target:
                    target_def = d
                    break

            if target_def:
                # Extract block with context
                content, start, end = self.extract_context_around(
                    file_content, target_def["line"]
                )
                parts.append(f"// Target: {target_def['name']} (line {target_def['line']})")
                parts.append(content)
            else:
                # Target not found, show structure
                parts.append("// File structure:")
                for d in definitions[:10]:
                    parts.append(f"//   {d['type']}: {d['name']} (line {d['line']})")

        else:
            # No target, show structure
            parts.append("// File structure:")
            for d in definitions[:10]:
                parts.append(f"//   {d['type']}: {d['name']} (line {d['line']})")

        shown_lines = sum(len(p.split("\n")) for p in parts)
        if shown_lines < total_lines:
            parts.append(f"\n// ... [{total_lines - shown_lines} lines not shown]")

        return "\n".join(parts)

    def _truncate_generic(
        self,
        file_content: str,
        edit_target: Optional[str]
    ) -> str:
        """Generic truncation using line-based approach."""
        lines = file_content.split("\n")
        total_lines = len(lines)

        if edit_target and edit_target.isdigit():
            # Target is a line number
            target_line = int(edit_target)
            content, start, end = self.extract_context_around(file_content, target_line)
            return (
                f"# Lines {start}-{end} of {total_lines}:\n{content}\n"
                f"# ... [{total_lines - (end - start + 1)} lines not shown]"
            )

        # Default: show head + structure hints + tail
        head = "\n".join(lines[:50])
        tail = "\n".join(lines[-20:])

        return (
            f"# First 50 lines:\n{head}\n\n"
            f"# ... [{total_lines - 70} lines in middle] ...\n\n"
            f"# Last 20 lines:\n{tail}"
        )

    def _analyze_python(
        self,
        file_content: str,
        file_path: str,
        lines: List[str]
    ) -> FileStructure:
        """Analyze Python file structure using AST."""
        try:
            tree = ast.parse(file_content)

            imports = []
            blocks = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(ast.unparse(node))

                elif isinstance(node, ast.FunctionDef):
                    block = CodeBlock(
                        name=node.name,
                        type="function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content="",
                        docstring=ast.get_docstring(node),
                    )
                    blocks.append(block)

                elif isinstance(node, ast.AsyncFunctionDef):
                    block = CodeBlock(
                        name=node.name,
                        type="async function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content="",
                        docstring=ast.get_docstring(node),
                    )
                    blocks.append(block)

                elif isinstance(node, ast.ClassDef):
                    block = CodeBlock(
                        name=node.name,
                        type="class",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content="",
                        docstring=ast.get_docstring(node),
                    )
                    blocks.append(block)

            return FileStructure(
                path=file_path,
                language="python",
                total_lines=len(lines),
                imports=imports,
                blocks=sorted(blocks, key=lambda b: b.start_line),
            )

        except SyntaxError as e:
            return FileStructure(
                path=file_path,
                language="python",
                total_lines=len(lines),
                imports=[],
                blocks=[],
                has_error=True,
                error_message=str(e),
            )

    def _analyze_js_ts(
        self,
        file_content: str,
        file_path: str,
        lines: List[str]
    ) -> FileStructure:
        """Analyze JS/TS file structure using regex."""
        language = self._detect_language(file_path)
        imports = []
        blocks = []

        for i, line in enumerate(lines):
            # Imports
            if re.match(r'^import\s+', line):
                imports.append(line.strip())
            elif re.match(r'^const\s+\{.*\}\s+=\s+require', line):
                imports.append(line.strip())

            # Functions and classes
            func_match = re.match(
                r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)', line
            )
            if func_match:
                blocks.append(CodeBlock(
                    name=func_match.group(1),
                    type="function",
                    start_line=i + 1,
                    end_line=i + 1,  # Unknown without full parsing
                    content=line,
                ))

            arrow_match = re.match(
                r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(', line
            )
            if arrow_match:
                blocks.append(CodeBlock(
                    name=arrow_match.group(1),
                    type="arrow function",
                    start_line=i + 1,
                    end_line=i + 1,
                    content=line,
                ))

            class_match = re.match(r'^(?:export\s+)?class\s+(\w+)', line)
            if class_match:
                blocks.append(CodeBlock(
                    name=class_match.group(1),
                    type="class",
                    start_line=i + 1,
                    end_line=i + 1,
                    content=line,
                ))

        return FileStructure(
            path=file_path,
            language=language,
            total_lines=len(lines),
            imports=imports,
            blocks=blocks,
        )

    def _analyze_generic(
        self,
        file_content: str,
        file_path: str,
        lines: List[str]
    ) -> FileStructure:
        """Generic file structure analysis."""
        return FileStructure(
            path=file_path,
            language="unknown",
            total_lines=len(lines),
            imports=[],
            blocks=[],
        )

    def _find_python_block(
        self,
        tree: ast.AST,
        target: str,
        lines: List[str]
    ) -> Optional[CodeBlock]:
        """Find a specific block in Python AST by name or line."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Match by name
                if node.name == target:
                    start = node.lineno
                    end = node.end_lineno or start
                    content = "\n".join(lines[start - 1:end])
                    return CodeBlock(
                        name=node.name,
                        type="class" if isinstance(node, ast.ClassDef) else "function",
                        start_line=start,
                        end_line=end,
                        content=content,
                        docstring=ast.get_docstring(node),
                    )

                # Match by line number
                if target.isdigit():
                    line_num = int(target)
                    if node.lineno <= line_num <= (node.end_lineno or node.lineno):
                        start = node.lineno
                        end = node.end_lineno or start
                        content = "\n".join(lines[start - 1:end])
                        return CodeBlock(
                            name=node.name,
                            type="class" if isinstance(node, ast.ClassDef) else "function",
                            start_line=start,
                            end_line=end,
                            content=content,
                            docstring=ast.get_docstring(node),
                        )

        return None

    def _extract_python_blocks(
        self,
        tree: ast.AST,
        lines: List[str]
    ) -> List[CodeBlock]:
        """Extract all top-level blocks from Python AST."""
        blocks = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno or start
                blocks.append(CodeBlock(
                    name=node.name,
                    type="function",
                    start_line=start,
                    end_line=end,
                    content="\n".join(lines[start - 1:end]),
                    docstring=ast.get_docstring(node),
                ))
            elif isinstance(node, ast.ClassDef):
                start = node.lineno
                end = node.end_lineno or start
                blocks.append(CodeBlock(
                    name=node.name,
                    type="class",
                    start_line=start,
                    end_line=end,
                    content="\n".join(lines[start - 1:end]),
                    docstring=ast.get_docstring(node),
                ))

        return sorted(blocks, key=lambda b: b.start_line)

    def _get_block_signature(self, block: CodeBlock, lines: List[str]) -> str:
        """Get just the signature line(s) of a block."""
        start = block.start_line - 1
        signature_lines = []

        for i in range(start, min(start + 5, len(lines))):
            line = lines[i]
            signature_lines.append(line)
            if line.rstrip().endswith(":"):
                break

        signature = "\n".join(signature_lines)
        if block.docstring:
            signature += f'\n    """{block.docstring[:60]}..."""'

        return signature


# Singleton instance
_truncator_instance: Optional[SmartTruncator] = None


def get_truncator() -> SmartTruncator:
    """Get or create the singleton truncator instance."""
    global _truncator_instance
    if _truncator_instance is None:
        _truncator_instance = SmartTruncator()
    return _truncator_instance


def truncate_file_content(
    content: str,
    file_path: str,
    edit_target: Optional[str] = None
) -> str:
    """
    Convenience function to truncate file content.

    Args:
        content: Full file content
        file_path: Path for language detection
        edit_target: Optional target identifier

    Returns:
        Truncated content
    """
    return get_truncator().truncate_for_edit(content, file_path, edit_target)


def get_file_summary(content: str, file_path: str) -> str:
    """
    Convenience function to get file summary.

    Args:
        content: Full file content
        file_path: Path for language detection

    Returns:
        Structural summary of the file
    """
    return get_truncator().get_file_summary(content, file_path)
