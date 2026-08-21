"""Tests for StartProcessRequest cwd validation and workspace cwd resolution.

Plain pytest — no Django or pydantic dependencies.
Tests the validation and resolution logic as extracted functions that mirror main.py.
"""
import os
import pytest


# --- Extracted cwd validator (mirrors StartProcessRequest.validate_cwd) ---

def validate_cwd(v):
    """Validate cwd field. Returns normalized value or raises ValueError."""
    if v is None:
        return v
    v = v.strip()
    if not v:
        return None
    if '..' in v:
        raise ValueError('cwd must not contain ".."')
    if v.startswith('/') and not v.startswith('/workspace'):
        raise ValueError('cwd must be relative or under /workspace')
    if any(c in v for c in '\n\r\x00'):
        raise ValueError('cwd contains disallowed control characters')
    return v


class TestValidateCwd:
    def test_validate_cwd_none(self):
        assert validate_cwd(None) is None

    def test_validate_cwd_empty_string(self):
        assert validate_cwd("") is None

    def test_validate_cwd_whitespace_only(self):
        assert validate_cwd("   ") is None

    def test_validate_cwd_valid_relative(self):
        assert validate_cwd("spark-app-xxx") == "spark-app-xxx"

    def test_validate_cwd_dotdot_blocked(self):
        with pytest.raises(ValueError, match="must not contain"):
            validate_cwd("../escape")

    def test_validate_cwd_dotdot_in_middle_blocked(self):
        with pytest.raises(ValueError, match="must not contain"):
            validate_cwd("foo/../bar")

    def test_validate_cwd_absolute_outside(self):
        with pytest.raises(ValueError, match="must be relative or under /workspace"):
            validate_cwd("/etc/passwd")

    def test_validate_cwd_absolute_workspace(self):
        assert validate_cwd("/workspace/sub") == "/workspace/sub"

    def test_validate_cwd_control_chars(self):
        with pytest.raises(ValueError, match="control characters"):
            validate_cwd("path\x00evil")

    def test_validate_cwd_newline_blocked(self):
        with pytest.raises(ValueError, match="control characters"):
            validate_cwd("path\nevil")


# --- Extracted cwd resolution logic (mirrors start_process endpoint) ---

def resolve_cwd(chat_workspace, cwd):
    """Resolve effective cwd from chat_workspace and user-provided cwd.

    Returns effective_cwd or raises ValueError if cwd escapes workspace.
    """
    effective_cwd = chat_workspace
    if cwd:
        relative_cwd = cwd
        if relative_cwd.startswith("/workspace/"):
            relative_cwd = relative_cwd.replace("/workspace/", "", 1)
        elif relative_cwd.startswith("/workspace"):
            relative_cwd = relative_cwd.replace("/workspace", "", 1).lstrip("/")
        relative_cwd = relative_cwd.lstrip("/")
        candidate = os.path.normpath(f"{chat_workspace}/{relative_cwd}")
        if not candidate.startswith(chat_workspace):
            raise ValueError("cwd escapes workspace")
        effective_cwd = candidate
    return effective_cwd


class TestResolveCwd:
    CHAT_WS = "/workspace/chat-abc123"

    def test_resolve_cwd_within_workspace(self):
        result = resolve_cwd(self.CHAT_WS, "spark-app-xxx")
        assert result == f"{self.CHAT_WS}/spark-app-xxx"

    def test_resolve_cwd_escapes_workspace(self):
        with pytest.raises(ValueError, match="escapes workspace"):
            resolve_cwd(self.CHAT_WS, "../../etc")

    def test_resolve_cwd_none_defaults(self):
        result = resolve_cwd(self.CHAT_WS, None)
        assert result == self.CHAT_WS

    def test_resolve_cwd_workspace_prefix(self):
        result = resolve_cwd(self.CHAT_WS, "/workspace/spark-app-xxx")
        assert result == f"{self.CHAT_WS}/spark-app-xxx"

    def test_resolve_cwd_nested_path(self):
        result = resolve_cwd(self.CHAT_WS, "spark-app-xxx/src")
        assert result == f"{self.CHAT_WS}/spark-app-xxx/src"

    def test_resolve_cwd_empty_string_defaults(self):
        """Empty string is falsy, so resolve should use default."""
        result = resolve_cwd(self.CHAT_WS, "")
        assert result == self.CHAT_WS
