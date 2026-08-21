"""Refresh-token hardening: hashed storage + rotation families.

1. Adds ``family`` (rotation-chain id used for reuse detection).
2. Alters ``token`` help_text (now stores the SHA-256 hex digest of
   the raw JWT instead of the plaintext).
3. Data migration: hashes every existing plaintext token in place and
   gives each pre-existing row its own family (AddField would stamp
   one shared default UUID on all existing rows, which would make a
   single reuse event revoke every legacy session).

Reverse: the hash cannot be reversed to plaintext, so the data step
is a no-op on unapply; the schema steps reverse normally. Existing
sessions keep working — the client presents the raw JWT and lookups
hash it before comparing.
"""

import hashlib
import uuid

from django.db import migrations, models


def hash_existing_tokens(apps, schema_editor):
    """Hash plaintext tokens and assign a unique family per row."""
    RefreshToken = apps.get_model("authentication", "RefreshToken")
    batch = []
    for row in RefreshToken.objects.all().iterator(chunk_size=500):
        row.token = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
        row.family = uuid.uuid4()
        batch.append(row)
        if len(batch) >= 500:
            RefreshToken.objects.bulk_update(batch, ["token", "family"])
            batch = []
    if batch:
        RefreshToken.objects.bulk_update(batch, ["token", "family"])


def noop_reverse(apps, schema_editor):
    """No-op: SHA-256 digests cannot be reversed to the plaintext tokens.

    Unapplying leaves hashed values in ``token``; affected sessions
    simply fail refresh and users re-authenticate.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0012_gdpr_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="refreshtoken",
            name="family",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text="Rotation-chain id; reuse detection revokes the whole family",
            ),
        ),
        migrations.AlterField(
            model_name="refreshtoken",
            name="token",
            field=models.TextField(
                help_text="SHA-256 hex digest of the raw refresh JWT", unique=True
            ),
        ),
        migrations.RunPython(hash_existing_tokens, noop_reverse),
    ]
