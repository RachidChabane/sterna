"""Tests for seed_all orchestrator (task 28)."""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _run(*args):
    out = StringIO()
    err = StringIO()
    call_command("seed_all", *args, stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


@pytest.mark.django_db
def test_seed_all_calls_each_required_step_in_order():
    with patch(
        "seed.management.commands.seed_all.call_command"
    ) as mock_call:
        _run()
        called_names = [c.args[0] for c in mock_call.call_args_list]
        assert called_names == [
            "sync_stripe_prices",
            "setup_usage_quota",
            "seed_preconfigured_servers",
            "seed_smoke_user",
        ]


@pytest.mark.django_db
def test_seed_all_continues_after_step_failure():
    def side_effect(name, *a, **kw):
        if name == "setup_usage_quota":
            raise CommandError("boom in usage quota")
        if name == "seed_smoke_user":
            raise CommandError("boom in smoke user")

    with patch(
        "seed.management.commands.seed_all.call_command",
        side_effect=side_effect,
    ) as mock_call:
        with pytest.raises(CommandError) as exc_info:
            _run()
        # All 4 should have been attempted even though setup_usage_quota
        # raised early.
        called_names = [c.args[0] for c in mock_call.call_args_list]
        assert called_names == [
            "sync_stripe_prices",
            "setup_usage_quota",
            "seed_preconfigured_servers",
            "seed_smoke_user",
        ]
        msg = str(exc_info.value)
        assert "setup_usage_quota" in msg
        assert "seed_smoke_user" in msg


@pytest.mark.django_db
def test_seed_all_dry_run_propagates_to_supporting_children():
    with patch(
        "seed.management.commands.seed_all.call_command"
    ) as mock_call:
        _run("--dry-run")
        per_call = {c.args[0]: list(c.args[1:]) for c in mock_call.call_args_list}
        assert per_call["sync_stripe_prices"] == ["--dry-run"]
        assert per_call["seed_preconfigured_servers"] == ["--dry-run"]
        # setup_usage_quota does not support --dry-run; must not receive it.
        assert per_call["setup_usage_quota"] == []
        # seed_smoke_user does not support --dry-run.
        assert per_call["seed_smoke_user"] == []


@pytest.mark.django_db
def test_seed_all_skip_smoke_user_flag():
    with patch(
        "seed.management.commands.seed_all.call_command"
    ) as mock_call:
        _run("--skip-smoke-user")
        called_names = [c.args[0] for c in mock_call.call_args_list]
        assert "seed_smoke_user" not in called_names
