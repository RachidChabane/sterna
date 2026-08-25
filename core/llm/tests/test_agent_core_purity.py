"""Characterization test: `llm.agent_core` never imports a web framework.

No module under the package may import `django`, `rest_framework`, or
`channels`, whether the import sits at the top of the module or is
reached only through a sibling module elsewhere in the package.
"""

import ast
import unittest
from pathlib import Path
from typing import Iterator, List

AGENT_CORE_ROOT = Path(__file__).resolve().parent.parent / "agent_core"

FORBIDDEN_ROOTS = frozenset({"django", "rest_framework", "channels"})


def _agent_core_modules() -> Iterator[Path]:
    return AGENT_CORE_ROOT.rglob("*.py")


def _import_roots(module_path: Path) -> Iterator[str]:
    """The top-level package name of every module-level or nested import.

    A relative import always resolves inside the current package
    tree, so it can never name a forbidden root; only absolute
    imports are yielded.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0]


class AgentCorePurityTests(unittest.TestCase):
    def test_package_exists_and_is_scanned(self):
        modules = list(_agent_core_modules())
        self.assertTrue(
            modules,
            f"expected at least one module under {AGENT_CORE_ROOT}; "
            "an empty scan would make the purity check vacuous.",
        )

    def test_no_module_imports_a_web_framework(self):
        violations: List[str] = []
        for module_path in _agent_core_modules():
            forbidden_hits = sorted(set(_import_roots(module_path)) & FORBIDDEN_ROOTS)
            if forbidden_hits:
                relative = module_path.relative_to(AGENT_CORE_ROOT)
                violations.append(f"{relative}: imports {', '.join(forbidden_hits)}")

        self.assertEqual(
            violations,
            [],
            "agent_core must stay framework-free; found:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
