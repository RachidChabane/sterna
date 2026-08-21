import base64
import logging
import time
from typing import Optional

import requests
import resend
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
BACKOFF_SECONDS = (0.5, 1.0, 2.0)
MAX_ATTEMPTS = 4  # 1 initial + 3 retries


class ResendSendError(Exception):
    """Raised when Resend returns a non-retryable error or retries are exhausted."""


class ResendEmailBackend(BaseEmailBackend):
    """Django email backend that delivers via the Resend HTTP API.

    Retries 5xx responses 3 times (4 total attempts) with backoff
    [0.5s, 1.0s, 2.0s]. Raises ResendSendError on 4xx or after retry
    exhaustion. Network errors (Timeout, ConnectionError) are treated
    as retryable transient failures.
    """

    def __init__(self, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, "RESEND_API_KEY", "")
        if not self.api_key and not fail_silently:
            raise ImproperlyConfigured(
                "RESEND_API_KEY must be set to use ResendEmailBackend"
            )
        if self.api_key:
            resend.api_key = self.api_key

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
                logger.exception(
                    "Resend send failed (fail_silently=True)",
                    extra={"to": list(message.to)},
                )
        return sent

    def _send(self, message: EmailMessage) -> None:
        payload = self._build_payload(message)
        last_status: Optional[int] = None
        last_body: Optional[str] = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resend.Emails.send(payload)
                return
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_status = None
                last_body = str(exc)
                logger.warning(
                    "Resend transient network error (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_ATTEMPTS,
                    exc,
                )
            except Exception as exc:
                status = getattr(exc, "status_code", None) or getattr(
                    exc, "code", None
                )
                body = getattr(exc, "message", None) or str(exc)
                if status is None:
                    logger.error(
                        "Resend unexpected error (no status), aborting",
                        exc_info=True,
                        extra={"to": list(message.to)},
                    )
                    raise ResendSendError(
                        f"Resend unexpected error: {exc}"
                    ) from exc
                last_status = status
                last_body = body[:1000] if body else None
                if 400 <= int(status) < 500:
                    logger.error(
                        "Resend 4xx (no retry) status=%s body=%s",
                        status,
                        last_body,
                        extra={"to": list(message.to)},
                    )
                    raise ResendSendError(
                        f"Resend rejected request: {status} {last_body}"
                    ) from exc
                logger.warning(
                    "Resend 5xx transient (attempt %d/%d) status=%s body=%s",
                    attempt + 1,
                    MAX_ATTEMPTS,
                    status,
                    last_body,
                )

            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS[attempt])

        raise ResendSendError(
            f"Resend retries exhausted: last_status={last_status} body={last_body}"
        )

    def _build_payload(self, message: EmailMessage) -> dict:
        payload = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives or []:
                if mimetype == "text/html":
                    payload["html"] = content
                    break
        if message.attachments:
            payload["attachments"] = [
                self._encode_attachment(att) for att in message.attachments
            ]
        if message.extra_headers:
            payload["headers"] = dict(message.extra_headers)
        return payload

    @staticmethod
    def _encode_attachment(attachment) -> dict:
        if isinstance(attachment, tuple):
            filename, content, mimetype = (attachment + (None,) * 3)[:3]
        else:
            raise ValueError("MIMEBase attachments not supported")

        if isinstance(content, str):
            content = content.encode("utf-8")
        encoded = base64.b64encode(content).decode("ascii")
        result = {"filename": filename, "content": encoded}
        if mimetype:
            result["content_type"] = mimetype
        return result
