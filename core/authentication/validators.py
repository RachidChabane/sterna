"""Email validators for signup abuse prevention (task 19).

Used by ``RegisterSerializer.email`` to reject disposable-email domains.
The list is vendored at
``core/authentication/data/disposable_email_domains.txt``; see
``docs/operations/disposable-domains.md`` for the refresh cadence.

``settings.DISPOSABLE_EMAIL_ALLOWLIST`` is an operations escape hatch
for legitimate users hitting false positives. It accepts EMAIL
ADDRESSES, not domains — to deliberately allow an entire domain, edit
the blocklist file directly.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

_DATA_FILE = Path(__file__).parent / "data" / "disposable_email_domains.txt"


@lru_cache(maxsize=1)
def _load_disposable_domains() -> frozenset[str]:
    """Load the vendored blocklist once per process."""
    try:
        text = _DATA_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return frozenset()
    return frozenset(
        line.strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    )


def _is_allowlisted(email: str) -> bool:
    allowlist = getattr(settings, "DISPOSABLE_EMAIL_ALLOWLIST", []) or []
    normalized = email.strip().lower()
    return normalized in {e.strip().lower() for e in allowlist}


@deconstructible
class DisposableEmailValidator:
    """DRF-compatible callable validator.

    Raises ``ValidationError(code='disposable_email')`` for emails
    whose domain matches the vendored blocklist, unless the full email
    is in ``settings.DISPOSABLE_EMAIL_ALLOWLIST``.
    """

    message = (
        "Please use a real email address. Disposable email "
        "addresses are not accepted for signup."
    )
    code = "disposable_email"

    def __call__(self, value: str) -> None:
        if not value or "@" not in value:
            return
        email = value.strip().lower()
        if _is_allowlisted(email):
            return
        domain = email.rsplit("@", 1)[1]
        if domain in _load_disposable_domains():
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other) -> bool:
        return isinstance(other, DisposableEmailValidator)

    def __hash__(self) -> int:
        return hash(type(self))
