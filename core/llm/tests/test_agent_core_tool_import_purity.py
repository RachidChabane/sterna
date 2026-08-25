"""Characterization test: a tool wrapped into `llm.agent_core.tools` never
drags Django or LangChain in through what it imports.

`test_agent_core_purity.py` and `test_agent_core_no_langchain_import.py`
check only the import statements written directly in an `agent_core`
file. That is enough while every import in the package resolves inside
`agent_core` itself or into a third-party library, but a tool module is
allowed to import a first-party sibling package for its schema (e.g.
`llm.tool_catalog.core_tools`) — and that sibling's own imports are
invisible to a same-file check. This test resolves the *transitive*
closure of every absolute and relative import reachable from
`agent_core`, following first-party imports into their source files, and
checks the whole closure against the same forbidden roots.
"""

import ast
import unittest
from pathlib import Path
from typing import Iterator, List, Optional, Set

CORE_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_CORE_ROOT = CORE_ROOT / "llm" / "agent_core"

FORBIDDEN_ROOTS = frozenset(
    {"django", "rest_framework", "channels", "langchain", "langchain_core", "langchain_openai"}
)


def _package_of(path: Path) -> List[str]:
    """The dotted package a module at `path` belongs to, for resolving its relative imports."""

    parts = list(path.relative_to(CORE_ROOT).with_suffix("").parts)
    return parts[:-1]


def _resolve_dotted(path: Path, module: Optional[str], level: int) -> Optional[str]:
    """The absolute dotted name an import statement in `path` refers to."""

    if level == 0:
        return module
    package = _package_of(path)
    if level - 1 > len(package):
        return None
    base = package[: len(package) - (level - 1)]
    if module:
        base = base + module.split(".")
    return ".".join(base) if base else None


def _module_file(dotted: str) -> Optional[Path]:
    """The source file `dotted` resolves to under `CORE_ROOT`, if it is first-party."""

    rel = Path(*dotted.split("."))
    as_module = CORE_ROOT / rel.with_suffix(".py")
    if as_module.is_file():
        return as_module
    as_package = CORE_ROOT / rel / "__init__.py"
    if as_package.is_file():
        return as_package
    return None


def _dotted_imports(path: Path) -> Iterator[str]:
    """Every absolute dotted module name a statement in `path` imports."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_dotted(path, node.module, node.level)
            if resolved:
                yield resolved


def _transitive_roots(start_files: List[Path]) -> Set[str]:
    """Every top-level import root reachable from `start_files`, following first-party imports."""

    roots: Set[str] = set()
    visited: Set[Path] = set()
    stack = list(start_files)
    while stack:
        path = stack.pop()
        if path in visited:
            continue
        visited.add(path)
        for dotted in _dotted_imports(path):
            roots.add(dotted.split(".")[0])
            resolved = _module_file(dotted)
            if resolved is not None and resolved not in visited:
                stack.append(resolved)
    return roots


class AgentCoreTransitiveImportPurityTests(unittest.TestCase):
    def test_package_exists_and_is_scanned(self):
        modules = list(AGENT_CORE_ROOT.rglob("*.py"))
        self.assertTrue(
            modules,
            f"expected at least one module under {AGENT_CORE_ROOT}; "
            "an empty scan would make this check vacuous.",
        )

    def test_transitive_imports_never_reach_a_forbidden_root(self):
        roots = _transitive_roots(list(AGENT_CORE_ROOT.rglob("*.py")))
        hits = sorted(roots & FORBIDDEN_ROOTS)
        self.assertEqual(
            hits,
            [],
            "agent_core must stay Django- and LangChain-free even through a "
            f"first-party import it follows to a legacy module; found: {hits}",
        )


if __name__ == "__main__":
    unittest.main()
