"""Tests for seed_smoke_user (task 28)."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from authentication.models import User

VALID_PW = "smoke-test-pw-min-20chars"  # >= 16 chars


def _run_command(monkeypatch, env_pw=VALID_PW, **kwargs):
    if env_pw is None:
        monkeypatch.delenv("SMOKE_TEST_USER_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SMOKE_TEST_USER_PASSWORD", env_pw)
    out = StringIO()
    call_command("seed_smoke_user", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_creates_user_with_env_password(monkeypatch):
    _run_command(monkeypatch)
    user = User.objects.get(email="smoke@sterna-internal.test")
    assert user.is_active
    assert user.is_verified
    assert not user.is_staff
    assert not user.is_superuser
    assert user.check_password(VALID_PW)


@pytest.mark.django_db
def test_idempotent_updates_password(monkeypatch):
    first_pw = "first-password-very-long"
    second_pw = "second-password-also-long"
    _run_command(monkeypatch, env_pw=first_pw)
    _run_command(monkeypatch, env_pw=second_pw)
    user = User.objects.get(email="smoke@sterna-internal.test")
    assert not user.check_password(first_pw)
    assert user.check_password(second_pw)
    # Confirm exactly one user exists.
    assert User.objects.filter(email="smoke@sterna-internal.test").count() == 1


@pytest.mark.django_db
def test_refuses_missing_password(monkeypatch):
    with pytest.raises(CommandError) as exc_info:
        _run_command(monkeypatch, env_pw=None)
    assert "SMOKE_TEST_USER_PASSWORD" in str(exc_info.value)


@pytest.mark.django_db
def test_refuses_short_password(monkeypatch):
    with pytest.raises(CommandError) as exc_info:
        _run_command(monkeypatch, env_pw="short-pw")  # 8 chars
    assert "16" in str(exc_info.value)
