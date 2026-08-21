"""Round-trip + DB-bytes-differ + MultiFernet rotation tests for BYOK keys."""

import pytest
from django.db import connection
from cryptography.fernet import Fernet

from authentication.models import User


def _reset_field_cipher_cache():
    """Clear the cached cipher on the openrouter_api_key field so the
    next access re-reads settings (used by rotation tests).
    """
    User._meta.get_field('openrouter_api_key')._fernet = None


@pytest.mark.django_db
def test_byok_key_encrypted_at_rest():
    plaintext = 'sk-or-v1-MY-SECRET-KEY-DO-NOT-LEAK'
    u = User.objects.create_user(email='enc@test.com', password='x')
    u.openrouter_api_key = plaintext
    u.save()

    # Read raw bytes from DB — bypass ORM decryption. UUID handling
    # differs across vendors, so query by email (unique on the model).
    with connection.cursor() as cur:
        cur.execute(
            'SELECT openrouter_api_key FROM auth_user WHERE email = %s',
            [u.email],
        )
        row = cur.fetchone()
    assert row is not None, "Row not found in DB"
    raw = row[0]

    assert raw is not None
    assert plaintext not in raw, "Plaintext leaked into DB!"
    assert raw.startswith('gAAAAA'), "Not a Fernet ciphertext"

    # ORM read must return plaintext.
    u2 = User.objects.get(id=u.id)
    assert u2.openrouter_api_key == plaintext


@pytest.mark.django_db
def test_byok_key_none_passthrough():
    u = User.objects.create_user(email='none@test.com', password='x')
    u.openrouter_api_key = None
    u.save()
    u2 = User.objects.get(id=u.id)
    assert u2.openrouter_api_key is None


@pytest.mark.django_db
def test_multifernet_rotation(settings):
    """Encrypt with old key, rotate to new + legacy, decrypt round-trip."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Phase 1: only old key
    settings.BYOK_ENCRYPTION_KEY = old_key
    settings.BYOK_ENCRYPTION_KEY_LEGACY = []
    _reset_field_cipher_cache()

    u = User.objects.create_user(email='rot@test.com', password='x')
    u.openrouter_api_key = 'sk-or-old-encrypted'
    u.save()

    # Phase 2: rotate — new primary, old in legacy
    settings.BYOK_ENCRYPTION_KEY = new_key
    settings.BYOK_ENCRYPTION_KEY_LEGACY = [old_key]
    _reset_field_cipher_cache()

    u2 = User.objects.get(id=u.id)
    assert u2.openrouter_api_key == 'sk-or-old-encrypted'  # still decrypts via legacy

    # Re-save: row is now encrypted with new key.
    u2.save()

    # Phase 3: drop legacy — decryption still works because re-save used new key.
    settings.BYOK_ENCRYPTION_KEY_LEGACY = []
    _reset_field_cipher_cache()
    u3 = User.objects.get(id=u.id)
    assert u3.openrouter_api_key == 'sk-or-old-encrypted'


@pytest.mark.django_db
def test_no_encryption_key_raises(settings):
    """No primary AND no fallback → ImproperlyConfigured on encrypt path."""
    from django.core.exceptions import ImproperlyConfigured

    settings.BYOK_ENCRYPTION_KEY = None
    settings.FIELD_ENCRYPTION_KEY = None
    _reset_field_cipher_cache()

    u = User.objects.create_user(email='nokey@test.com', password='x')
    with pytest.raises(ImproperlyConfigured):
        u.openrouter_api_key = 'will-fail-encrypt'
        u.save()
