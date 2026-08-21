"""Encrypted field types for the authentication app.

Re-exports `EncryptedTextField` from `core.mcp.fields` for a stable import
location per the task-8 spec. The field uses MultiFernet with primary key
from `settings.BYOK_ENCRYPTION_KEY` (falling back to FIELD_ENCRYPTION_KEY)
and legacy-key rotation support via BYOK_ENCRYPTION_KEY_LEGACY.

See `docs/operations/byok-key-rotation.md` for the rotation procedure.
"""

from mcp.fields import EncryptedTextField, EncryptedJSONField

__all__ = ['EncryptedTextField', 'EncryptedJSONField']
