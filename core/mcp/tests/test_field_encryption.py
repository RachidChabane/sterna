"""Round-trip + DB-bytes-differ + MultiFernet rotation tests for MCPServer's
encrypted fields (EncryptedTextField / EncryptedJSONField, mcp/fields.py).

Mirrors the pattern in authentication/tests/test_encrypted_field.py, which
covers the same primitives on User.openrouter_api_key.
"""

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from mcp.models import MCPServer

from .conftest import make_server


def _reset_field_cipher_cache(*field_names):
    for name in field_names:
        MCPServer._meta.get_field(name)._fernet = None


@pytest.mark.django_db
def test_oauth_access_token_encrypted_at_rest(user_a):
    """EncryptedTextField: DB bytes must never contain the plaintext token."""
    plaintext = "ya29.SUPER-SECRET-OAUTH-ACCESS-TOKEN"
    server = make_server(user_a, auth_type=MCPServer.AuthType.OAUTH)
    server.oauth_access_token = plaintext
    server.save()

    with connection.cursor() as cur:
        cur.execute(
            "SELECT oauth_access_token FROM mcp_mcpserver WHERE id = %s",
            [server.id],
        )
        raw = cur.fetchone()[0]

    assert raw is not None
    assert plaintext not in raw, "Plaintext OAuth token leaked into DB!"
    assert raw.startswith("gAAAAA"), "Not a Fernet ciphertext"

    server.refresh_from_db()
    assert server.oauth_access_token == plaintext


@pytest.mark.django_db
def test_auth_config_json_encrypted_at_rest(user_a):
    """EncryptedJSONField: ciphertext in DB, decrypted dict on ORM read."""
    secret_config = {"API_KEY": "sk-live-SUPER-SECRET-KEY"}
    server = make_server(user_a, auth_config=secret_config)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT auth_config FROM mcp_mcpserver WHERE id = %s",
            [server.id],
        )
        raw = cur.fetchone()[0]

    assert raw is not None
    assert "sk-live-SUPER-SECRET-KEY" not in raw, "Plaintext API key leaked into DB!"
    # SQLite's JSONField compatibility shim re-wraps get_prep_value's
    # output in a JSON string literal (surrounding quotes), so check
    # for the Fernet token as a substring rather than a strict prefix.
    assert "gAAAAA" in raw, "Not a Fernet ciphertext"

    server.refresh_from_db()
    assert server.auth_config == secret_config


@pytest.mark.django_db
def test_env_vars_json_encrypted_at_rest(user_a):
    """Second EncryptedJSONField on the model — same guarantee holds."""
    env_vars = {"GITHUB_TOKEN": "ghp_SUPER_SECRET_TOKEN"}
    server = make_server(user_a, env_vars=env_vars)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT env_vars FROM mcp_mcpserver WHERE id = %s",
            [server.id],
        )
        raw = cur.fetchone()[0]

    assert "ghp_SUPER_SECRET_TOKEN" not in raw
    assert "gAAAAA" in raw, "Not a Fernet ciphertext"
    server.refresh_from_db()
    assert server.env_vars == env_vars


@pytest.mark.django_db
def test_encrypted_text_field_empty_string_passthrough(user_a):
    """Empty string is the field's declared default — must not be encrypted."""
    server = make_server(user_a)
    assert server.oauth_access_token == ""
    server.refresh_from_db()
    assert server.oauth_access_token == ""


@pytest.mark.django_db
def test_encrypted_json_field_empty_dict_round_trips(user_a):
    server = make_server(user_a, auth_config={})
    server.refresh_from_db()
    assert server.auth_config == {}


@pytest.mark.django_db
def test_legacy_plaintext_oauth_token_falls_back_gracefully(user_a):
    """Pre-encryption rows (plain text) must not crash on decrypt.

    EncryptedTextField.from_db_value swallows InvalidToken and returns the
    raw value, so legacy unencrypted data degrades instead of 500ing.
    """
    server = make_server(user_a, auth_type=MCPServer.AuthType.OAUTH)
    server.oauth_access_token = "plaintext-legacy-token"
    server.save()

    # Overwrite the DB row directly with genuinely unencrypted text,
    # bypassing the ORM's encrypt-on-write.
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE mcp_mcpserver SET oauth_access_token = %s WHERE id = %s",
            ["legacy-plaintext-value", server.id],
        )

    server.refresh_from_db()
    assert server.oauth_access_token == "legacy-plaintext-value"


@pytest.mark.django_db
def test_legacy_plaintext_json_falls_back_to_plain_parse(user_a):
    """EncryptedJSONField.from_db_value falls back to json.loads on InvalidToken."""
    server = make_server(user_a)

    with connection.cursor() as cur:
        cur.execute(
            'UPDATE mcp_mcpserver SET auth_config = %s WHERE id = %s',
            ['{"legacy": "plain-json"}', server.id],
        )

    server.refresh_from_db()
    assert server.auth_config == {"legacy": "plain-json"}


@pytest.mark.django_db
def test_multifernet_key_rotation_round_trip(settings, user_a):
    """Encrypt with old key, rotate to new+legacy, decrypt still works,
    then dropping the legacy key after a re-save still round-trips."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    settings.BYOK_ENCRYPTION_KEY = old_key
    settings.BYOK_ENCRYPTION_KEY_LEGACY = []
    _reset_field_cipher_cache("oauth_access_token")

    server = make_server(user_a, auth_type=MCPServer.AuthType.OAUTH)
    server.oauth_access_token = "token-encrypted-with-old-key"
    server.save()

    # Rotate: new key primary, old key kept for decrypting existing rows.
    settings.BYOK_ENCRYPTION_KEY = new_key
    settings.BYOK_ENCRYPTION_KEY_LEGACY = [old_key]
    _reset_field_cipher_cache("oauth_access_token")

    reloaded = MCPServer.objects.get(id=server.id)
    assert reloaded.oauth_access_token == "token-encrypted-with-old-key"

    # Re-save now writes with the new primary key.
    reloaded.save()

    # Drop the legacy key entirely — value must still decrypt because the
    # re-save upgraded it to the new key.
    settings.BYOK_ENCRYPTION_KEY_LEGACY = []
    _reset_field_cipher_cache("oauth_access_token")

    final = MCPServer.objects.get(id=server.id)
    assert final.oauth_access_token == "token-encrypted-with-old-key"


@pytest.mark.django_db
def test_no_encryption_key_raises_improperly_configured(settings, user_a):
    """No BYOK_ENCRYPTION_KEY and no FIELD_ENCRYPTION_KEY fallback → hard fail
    on write, rather than silently persisting a secret in plain text."""
    settings.BYOK_ENCRYPTION_KEY = None
    settings.FIELD_ENCRYPTION_KEY = None
    _reset_field_cipher_cache("auth_config", "oauth_access_token")

    with pytest.raises(ImproperlyConfigured):
        make_server(user_a, auth_config={"API_KEY": "will-fail-to-encrypt"})
