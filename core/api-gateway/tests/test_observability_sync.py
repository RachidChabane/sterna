"""Guards the intentional cross-service duplication of _observability.py.

Five FastAPI/Starlette microservices under core/ each build from an
isolated Docker context (`COPY . .` scoped to that service's own
directory — see each service's Dockerfile), so none of them can import
a shared package at image-build time without a larger change than the
duplication itself (an `additional_contexts` COPY step added to every
Dockerfile, or publishing this module as an installable wheel). The
five copies are kept byte-identical instead, and this test is what
turns drift between them into a CI failure rather than a runtime
surprise.

This test lives here (rather than once per service) because the
invariant it checks — "these five files are identical" — is a
repo-level fact, not a per-service one. It still runs on every
service's changes: CI's `microservice-tests` job triggers whenever any
file under core/** changes (see .github/workflows/ci.yml, `any-service`
filter), and this suite is part of the api-gateway matrix entry.

To change the shared behavior: edit CANONICAL_PATH's file first, then
copy its exact contents over the other four files below.
"""

from pathlib import Path

import pytest

_CORE_DIR = Path(__file__).resolve().parents[2]

CANONICAL_PATH = _CORE_DIR / "api-gateway" / "gateway" / "_observability.py"

DUPLICATE_PATHS = (
    _CORE_DIR / "brave-search" / "_observability.py",
    _CORE_DIR / "google-maps" / "_observability.py",
    _CORE_DIR / "sandbox" / "orchestrator" / "_observability.py",
    _CORE_DIR / "user-preferences-service" / "app" / "_observability.py",
)


def test_canonical_file_exists():
    assert CANONICAL_PATH.is_file(), f"canonical file missing: {CANONICAL_PATH}"


@pytest.mark.parametrize(
    "duplicate_path",
    DUPLICATE_PATHS,
    ids=lambda p: p.relative_to(_CORE_DIR).as_posix(),
)
def test_observability_copy_matches_canonical(duplicate_path: Path) -> None:
    assert duplicate_path.is_file(), f"expected duplicate missing: {duplicate_path}"

    canonical_bytes = CANONICAL_PATH.read_bytes()
    copy_bytes = duplicate_path.read_bytes()

    assert copy_bytes == canonical_bytes, (
        f"{duplicate_path} has drifted from the canonical copy at "
        f"{CANONICAL_PATH}. Sync the file contents exactly (see this "
        "test's module docstring for why the five copies must stay "
        "byte-identical)."
    )
