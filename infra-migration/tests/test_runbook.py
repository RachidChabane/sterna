"""Lint the cold bring-up runbook to guarantee every numbered step
carries a verification check.

Parses docs/migration/cold-bring-up-runbook.md by regex. The intent
is to keep the runbook usable as a *checklist*, not a wall of text —
operators MUST be able to confirm each step's success before
proceeding to the next.

Triggered by .github/workflows/ci.yml's `runbook-lint` job; runs on
every push/PR that touches `docs/migration/**` or
`infra-migration/**`.
"""
import re
from pathlib import Path

# A "step" is a level-3 heading "### Step N — <title>".
STEP_PATTERN = re.compile(r"^### Step (\d+) — (.+)$", re.MULTILINE)

# A "verify" line is "**Verify:**" (bold marker) anywhere inside the
# step's body.
VERIFY_TOKEN = "**Verify:**"

RUNBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "migration"
    / "cold-bring-up-runbook.md"
)


def _runbook_text() -> str:
    assert RUNBOOK.exists(), f"Runbook missing at {RUNBOOK}"
    return RUNBOOK.read_text()


def _split_into_steps(text):
    """Yield (step_number, step_title, body_text) tuples."""
    matches = list(STEP_PATTERN.finditer(text))
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = (
            matches[i + 1].start() if i + 1 < len(matches) else len(text)
        )
        yield int(m.group(1)), m.group(2).strip(), text[body_start:body_end]


def test_runbook_exists():
    assert RUNBOOK.exists(), f"Runbook missing at {RUNBOOK}"


def test_runbook_has_at_least_one_step():
    text = _runbook_text()
    steps = list(_split_into_steps(text))
    assert len(steps) >= 1, "Runbook has no `### Step N — …` headings."


def test_every_step_has_a_verify_line():
    text = _runbook_text()
    failures = []
    for step_num, step_title, body in _split_into_steps(text):
        if VERIFY_TOKEN not in body:
            failures.append(
                f"  Step {step_num} ({step_title}): missing {VERIFY_TOKEN}"
            )
    assert not failures, (
        "Steps without **Verify:** line:\n" + "\n".join(failures)
    )


def test_step_numbering_is_contiguous_within_a_section():
    """Allow the staging section (1..N) and production section (1..M)
    to each start at 1, but disallow gaps within either."""
    text = _runbook_text()
    # Each section starts with a level-2 heading. Split by them.
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    for section in sections:
        nums = [int(m.group(1)) for m in STEP_PATTERN.finditer(section)]
        if not nums:
            continue
        expected = list(range(min(nums), max(nums) + 1))
        assert nums == expected, (
            f"Step numbers not contiguous in a section: {nums}"
        )


def test_no_todo_or_fixme_in_runbook():
    """Operators run this thing during incidents. TODO/FIXME means it's
    not finished — block the PR."""
    text = _runbook_text()
    bad_markers = re.findall(r"\b(TODO|FIXME|XXX)\b", text)
    assert not bad_markers, (
        f"Runbook contains incomplete markers: {bad_markers}"
    )
