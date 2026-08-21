"""Re-encrypt all stored BYOK OpenRouter keys with the current primary
encryption key.

See ``docs/operations/byok-key-rotation.md`` for the full procedure.

Behavior:
  * Reads raw ciphertext directly via SQL to bypass the field's silent
    ``InvalidToken`` fallback. Without this bypass, a row encrypted with
    a key not in either the primary or any legacy slot would be read as
    its raw ciphertext bytes, re-encrypted, and become double-encrypted
    garbage.
  * Decrypts via the current ``MultiFernet`` (primary + legacy).
  * Writes the plaintext back through the ORM so the field's
    ``get_prep_value`` re-encrypts using the current primary only.

Exit codes:
  * 0 = all rows rotated cleanly.
  * 1 = at least one row failed to decrypt. The user IDs are written to
    stderr; ops must trigger a "reset your key" email for those users.
"""

import sys

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand
from django.db import connection

from authentication.models import User
from mcp.fields import _build_cipher


class Command(BaseCommand):
    help = (
        "Re-encrypt User.openrouter_api_key rows with the current primary "
        "BYOK encryption key. See docs/operations/byok-key-rotation.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Decrypt-only pass. Reports failures but does not re-save.",
        )

    def handle(self, *args, dry_run: bool = False, **opts):
        cipher = _build_cipher()
        users = (
            User.objects
            .exclude(openrouter_api_key__isnull=True)
            .exclude(openrouter_api_key='')
        )

        ok = 0
        failed: list[str] = []

        for user in users.iterator():
            # Bypass from_db_value's silent InvalidToken-as-plaintext fallback.
            with connection.cursor() as cur:
                cur.execute(
                    'SELECT openrouter_api_key FROM auth_user WHERE email = %s',
                    [user.email],
                )
                row = cur.fetchone()
            raw = row[0] if row else None
            if not raw:
                continue

            try:
                payload = raw.encode() if isinstance(raw, str) else raw
                plaintext = cipher.decrypt(payload).decode()
            except InvalidToken:
                failed.append(str(user.id))
                self.stderr.write(self.style.ERROR(
                    f"FAIL user={user.id} ({user.email}): row decrypts under "
                    f"neither primary nor any legacy key — refusing to "
                    f"re-encrypt."
                ))
                continue

            if not dry_run:
                # Re-save via ORM so get_prep_value encrypts with current primary.
                user.openrouter_api_key = plaintext
                user.save(update_fields=['openrouter_api_key'])
            ok += 1

        mode = 'dry-run' if dry_run else 'rotated'
        self.stdout.write(self.style.SUCCESS(
            f"BYOK rotation {mode}: {ok} rows ok, {len(failed)} failures"
        ))
        if failed:
            sys.exit(1)
