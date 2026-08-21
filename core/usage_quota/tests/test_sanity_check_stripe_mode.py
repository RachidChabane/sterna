"""Tests for sanity_check_stripe_mode management command.

Exits 0 on coherent env+key shape, 1 on drift.
"""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_test_env_with_no_key_passes(settings):
    settings.DJANGO_ENV = "test"
    settings.STRIPE_API_KEY = ""
    settings.STRIPE_LIVE_MODE = False
    call_command("sanity_check_stripe_mode")


@pytest.mark.django_db
def test_test_env_with_live_key_fails(settings):
    settings.DJANGO_ENV = "test"
    settings.STRIPE_API_KEY = "sk_live_BAD"
    settings.STRIPE_LIVE_MODE = True
    with pytest.raises(SystemExit) as exc:
        call_command("sanity_check_stripe_mode")
    assert exc.value.code == 1


@pytest.mark.django_db
def test_prod_env_with_test_key_fails(settings):
    settings.DJANGO_ENV = "prod"
    settings.STRIPE_API_KEY = "sk_test_NOT_PROD"
    settings.STRIPE_LIVE_MODE = False
    with pytest.raises(SystemExit) as exc:
        call_command("sanity_check_stripe_mode")
    assert exc.value.code == 1


@pytest.mark.django_db
def test_prod_env_with_live_key_passes(settings):
    settings.DJANGO_ENV = "prod"
    settings.STRIPE_API_KEY = "sk_live_REAL"
    settings.STRIPE_LIVE_MODE = True
    call_command("sanity_check_stripe_mode")


@pytest.mark.django_db
def test_staging_with_live_key_fails(settings):
    settings.DJANGO_ENV = "staging"
    settings.STRIPE_API_KEY = "sk_live_BAD"
    settings.STRIPE_LIVE_MODE = True
    with pytest.raises(SystemExit) as exc:
        call_command("sanity_check_stripe_mode")
    assert exc.value.code == 1


@pytest.mark.django_db
def test_staging_with_test_key_passes(settings):
    settings.DJANGO_ENV = "staging"
    settings.STRIPE_API_KEY = "sk_test_OK"
    settings.STRIPE_LIVE_MODE = False
    call_command("sanity_check_stripe_mode")


@pytest.mark.django_db
def test_prod_without_key_fails(settings):
    settings.DJANGO_ENV = "prod"
    settings.STRIPE_API_KEY = ""
    settings.STRIPE_LIVE_MODE = False
    with pytest.raises(SystemExit) as exc:
        call_command("sanity_check_stripe_mode")
    assert exc.value.code == 1
