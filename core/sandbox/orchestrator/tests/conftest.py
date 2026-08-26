"""Test bootstrap for the orchestrator suite.

The orchestrator imports its own modules by bare name
(``from workspace_client import ...``), so the service directory must
be on ``sys.path`` regardless of where pytest is invoked from.

NOTE: no global dependency stubbing here — ``test_request_id_middleware``
relies on ``pytest.importorskip("fastapi")`` to skip in the Django venv,
and a sys.modules stub would defeat that.
"""

import sys
from pathlib import Path

ORCHESTRATOR_DIR = Path(__file__).resolve().parent.parent
if str(ORCHESTRATOR_DIR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_DIR))
