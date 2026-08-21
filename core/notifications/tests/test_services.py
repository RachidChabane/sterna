from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import resend
import responses
from django.core import mail
from django.test import SimpleTestCase, override_settings

from notifications.email_backend import RESEND_API_URL
from notifications.services import (
    send_account_deleted_email,
    send_account_deletion_confirmation,
    send_data_export_ready_email,
    send_password_reset_email,
    send_subscription_canceled,
    send_subscription_receipt,
    send_verification_email,
)


def _make_user(email="alice@example.com", short_name="Alice"):
    user = SimpleNamespace(email=email)
    user.get_short_name = lambda: short_name
    user.full_name = short_name
    return user


@override_settings(
    DEFAULT_FROM_EMAIL="noreply@example.com",
    SUPPORT_EMAIL="support@example.com",
    BRAND_NAME="Sterna",
    FRONTEND_URL="http://testserver",
)
class NotificationServicesTests(SimpleTestCase):
    def setUp(self):
        self.user = _make_user()
        mail.outbox = []

    def tearDown(self):
        mail.outbox = []
        resend.api_key = None
        responses.reset()
        super().tearDown()

    def _html_alternative(self, message):
        for content, mimetype in message.alternatives or []:
            if mimetype == "text/html":
                return content
        return ""

    def test_send_verification_email_renders_template(self):
        send_verification_email(self.user, "tok_xyz")
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, [self.user.email])
        self.assertEqual(m.from_email, "noreply@example.com")
        self.assertIn("Verify", m.subject)
        self.assertIn("/verify-email?token=tok_xyz", m.body)
        html = self._html_alternative(m)
        self.assertIn("/verify-email?token=tok_xyz", html)

    def test_send_password_reset_email_renders_template(self):
        send_password_reset_email(self.user, "rst_abc")
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn("Reset", m.subject)
        self.assertIn("/reset-password?token=rst_abc", m.body)
        html = self._html_alternative(m)
        self.assertIn("/reset-password?token=rst_abc", html)

    def test_send_subscription_receipt_uses_invoice_data(self):
        invoice = {
            "amount_display": "$23.80 EUR",
            "subtotal_display": "$20.00 EUR",
            "tax_display": "$3.80 EUR",
            "tax_rate_display": "VAT 19%",
            "plan_name": "Plus Monthly",
            "period_start": "2026-05-01",
            "period_end": "2026-06-01",
            "date_paid_display": "2026-05-01",
            "next_renewal_display": "2026-06-01",
            "invoice_number": "INV-0042",
            "hosted_invoice_url": "https://invoice.stripe.com/i/test",
            "invoice_pdf": "https://invoice.stripe.com/p/test/pdf",
        }
        send_subscription_receipt(self.user, invoice)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn("receipt", m.subject.lower())
        self.assertEqual(m.to, [self.user.email])
        for key in ("amount_display", "subtotal_display", "tax_display",
                    "tax_rate_display", "plan_name", "period_start",
                    "period_end", "invoice_number"):
            self.assertIn(invoice[key], m.body)
        html = self._html_alternative(m)
        for key in ("amount_display", "subtotal_display", "tax_display",
                    "tax_rate_display", "plan_name", "invoice_number"):
            self.assertIn(invoice[key], html)
        self.assertIn(invoice["hosted_invoice_url"], html)
        self.assertIn(invoice["invoice_pdf"], html)

    def test_send_subscription_receipt_omits_vat_row_when_tax_empty(self):
        invoice = {
            "amount_display": "$20.00 EUR",
            "subtotal_display": "$20.00 EUR",
            "tax_display": "",  # B2B reverse-charge
            "tax_rate_display": "",
            "plan_name": "Plus Monthly",
            "period_start": "2026-05-01",
            "period_end": "2026-06-01",
            "date_paid_display": "2026-05-01",
            "next_renewal_display": "2026-06-01",
            "invoice_number": "INV-0042",
            "hosted_invoice_url": "https://invoice.stripe.com/i/test",
            "invoice_pdf": "https://invoice.stripe.com/p/test/pdf",
        }
        send_subscription_receipt(self.user, invoice)
        m = mail.outbox[0]
        html = self._html_alternative(m)
        # No VAT row label rendered when tax_display is empty.
        self.assertNotIn("VAT 19%", html)
        # Subtotal still present (rest of table still renders).
        self.assertIn("$20.00 EUR", html)
        # Both links still render.
        self.assertIn(invoice["hosted_invoice_url"], html)
        self.assertIn(invoice["invoice_pdf"], html)

    def test_send_subscription_canceled_uses_canceled_template(self):
        send_subscription_canceled(self.user)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn("canceled", m.subject.lower())
        html = self._html_alternative(m)
        self.assertIn("/billing", html)

    def test_send_account_deletion_confirmation_includes_request_id(self):
        send_account_deletion_confirmation(self.user, "req_123")
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn("req_123", m.body)
        html = self._html_alternative(m)
        self.assertIn("req_123", html)

    def test_send_account_deletion_confirmation_uses_cancel_token(self):
        # The view passes the one-shot cancel JWT (the user is logged
        # out + deactivated, so the link must carry its own auth).
        send_account_deletion_confirmation(
            self.user,
            request_id="req_456",
            cancel_token="tok_cancel_789",
            grace_days=7,
        )
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn(
            "/account/cancel-deletion?token=tok_cancel_789", m.body
        )
        self.assertIn("req_456", m.body)
        self.assertIn("7 days", m.body)
        html = self._html_alternative(m)
        self.assertIn(
            "/account/cancel-deletion?token=tok_cancel_789", html
        )

    def test_send_data_export_ready_email_renders_template(self):
        from datetime import datetime, timezone as dt_timezone

        url = "https://r2.example.com/user-exports/u1/req.zip?sig=abc"
        expires = datetime(2026, 7, 18, 12, 0, tzinfo=dt_timezone.utc)
        send_data_export_ready_email(self.user, url, expires)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, [self.user.email])
        self.assertIn("export", m.subject.lower())
        self.assertIn(url, m.body)
        self.assertIn("2026-07-18", m.body)
        html = self._html_alternative(m)
        self.assertIn(url, html)

    def test_send_account_deleted_email_takes_snapshot_strings(self):
        # The User row is already hard-deleted when this fires — the
        # task passes the email + name snapshots, not a user instance.
        send_account_deleted_email("gone@example.com", "Gone Person")
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ["gone@example.com"])
        self.assertIn("deleted", m.subject.lower())
        self.assertIn("Gone", m.body)
        self.assertIn("permanently deleted", m.body)
        html = self._html_alternative(m)
        self.assertIn("permanently deleted", html)

    def test_send_account_deleted_email_without_name_uses_local_part(self):
        send_account_deleted_email("solo@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("solo", mail.outbox[0].body)

    @patch("notifications.services.override")
    def test_default_language_is_english(self, mock_override):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=None)
        cm.__exit__ = MagicMock(return_value=False)
        mock_override.return_value = cm
        send_verification_email(self.user, "tok")
        mock_override.assert_called_with("en")

    @patch("notifications.services.override")
    def test_explicit_language_overrides_translation(self, mock_override):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=None)
        cm.__exit__ = MagicMock(return_value=False)
        mock_override.return_value = cm
        send_verification_email(self.user, "tok", language="fr")
        mock_override.assert_called_with("fr")

    @responses.activate
    @override_settings(
        EMAIL_BACKEND="notifications.email_backend.ResendEmailBackend",
        RESEND_API_KEY="re_test_xxx",
    )
    def test_send_uses_configured_backend(self):
        responses.add(
            responses.POST,
            RESEND_API_URL,
            status=200,
            json={"id": "abc"},
        )
        send_verification_email(self.user, "tok")
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(responses.calls[0].request.url, RESEND_API_URL)

    def test_reply_to_defaults_to_support_email(self):
        from django.conf import settings as dj_settings

        send_verification_email(self.user, "tok")
        m = mail.outbox[0]
        self.assertEqual(m.reply_to, [dj_settings.SUPPORT_EMAIL])
