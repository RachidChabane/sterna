"""Characterization test: the agent loop loads in a process with no web framework.

`test_agent_core_purity` reads every module's import statements and
fails on a forbidden name. This test answers the question that reading
cannot: whether importing the loop actually pulls a web framework in,
through a dependency of a dependency or an import performed at
runtime. It imports the package in a fresh interpreter with no Django
settings configured and inspects what ended up loaded.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

CORE_ROOT = Path(__file__).resolve().parent.parent.parent

FORBIDDEN_MODULE_ROOTS = ("django", "rest_framework", "channels")

_PROBE = """
import json
import sys

import llm.agent_core.graph as graph

loaded = sorted({name.split(".")[0] for name in sys.modules})
print(json.dumps({"loaded": loaded, "loop": graph.AgentLoop.__name__}))
"""


def _import_in_a_fresh_interpreter() -> Dict[str, Any]:
    """Import the loop with no Django settings set, and report what loaded."""

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=CORE_ROOT,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(CORE_ROOT)},
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"importing llm.agent_core.graph failed:\n{completed.stderr}"
        )
    return json.loads(completed.stdout.strip().splitlines()[-1])


class AgentCoreGraphImportPurityTests(unittest.TestCase):
    def test_importing_the_loop_loads_no_web_framework(self):
        loaded = set(_import_in_a_fresh_interpreter()["loaded"])

        self.assertEqual(
            sorted(loaded.intersection(FORBIDDEN_MODULE_ROOTS)),
            [],
            "the agent loop must load without a web framework",
        )

    def test_the_probe_actually_imported_the_loop(self):
        payload = _import_in_a_fresh_interpreter()

        self.assertEqual(payload["loop"], "AgentLoop")
        self.assertIn("langgraph", payload["loaded"])


if __name__ == "__main__":
    unittest.main()
