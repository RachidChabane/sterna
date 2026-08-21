"""Tests for zombie agent exit code handling and success override logic."""
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- Exit code extraction helper (mirrors coding_agent_runner.py logic) ---

def extract_exit_code(exec_run_result) -> int:
    """Extract exit code from container exec_run result.

    Mirrors the logic in _execute_with_file_streaming.
    """
    exit_code = 0
    if exec_run_result.exit_code == 0 and exec_run_result.output:
        try:
            exit_code = int(exec_run_result.output.decode().strip())
        except ValueError:
            exit_code = 1
    else:
        # Exit code file missing — process was likely killed by signal
        exit_code = 137
    return exit_code


@dataclass
class MockExecResult:
    exit_code: int
    output: bytes = b""


class TestExitCodeExtraction:
    def test_exit_code_file_missing(self):
        """exec_run returns exit_code!=0 (file not found) -> exit_code=137."""
        result = MockExecResult(exit_code=1, output=b"")
        assert extract_exit_code(result) == 137

    def test_exit_code_file_valid_zero(self):
        """exec_run returns '0\\n' -> exit_code=0."""
        result = MockExecResult(exit_code=0, output=b"0\n")
        assert extract_exit_code(result) == 0

    def test_exit_code_file_nonzero(self):
        """exec_run returns '1\\n' -> exit_code=1."""
        result = MockExecResult(exit_code=0, output=b"1\n")
        assert extract_exit_code(result) == 1

    def test_exit_code_file_non_numeric(self):
        """exec_run returns 'garbage' -> exit_code=1."""
        result = MockExecResult(exit_code=0, output=b"garbage")
        assert extract_exit_code(result) == 1


# --- Success override logic (mirrors _run_agent post-parse logic) ---

@dataclass
class MockParsedResult:
    success: bool
    error: Optional[str] = None
    steps: list = field(default_factory=list)


def apply_exit_code_override(parsed: MockParsedResult, exit_code: int) -> MockParsedResult:
    """Apply exit code override to parsed result.

    Mirrors the logic added to _run_agent after parse_claude_output.
    """
    if exit_code != 0 and parsed.success:
        parsed.success = False
        parsed.error = parsed.error or f"Agent process exited with code {exit_code} (likely killed by signal)"
    return parsed


class TestSuccessOverride:
    def test_override_success_when_killed(self):
        """parsed.success=True + exit_code=137 -> success=False, error message set."""
        parsed = MockParsedResult(success=True)
        result = apply_exit_code_override(parsed, 137)
        assert result.success is False
        assert "137" in result.error
        assert "killed" in result.error.lower()

    def test_no_override_on_normal_exit(self):
        """parsed.success=True + exit_code=0 -> success=True unchanged."""
        parsed = MockParsedResult(success=True)
        result = apply_exit_code_override(parsed, 0)
        assert result.success is True
        assert result.error is None

    def test_no_override_when_already_failed(self):
        """parsed.success=False + exit_code=137 -> stays False, original error kept."""
        parsed = MockParsedResult(success=False, error="Original error")
        result = apply_exit_code_override(parsed, 137)
        assert result.success is False
        assert result.error == "Original error"
