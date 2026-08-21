import json
from unittest.mock import call, patch

import requests
import resend
import responses
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from notifications.email_backend import (
    RESEND_API_URL,
    ResendEmailBackend,
    ResendSendError,
)


@override_settings(
    EMAIL_BACKEND="notifications.email_backend.ResendEmailBackend",
    RESEND_API_KEY="re_test_xxx",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class ResendEmailBackendTests(SimpleTestCase):
    def tearDown(self):
        resend.api_key = None
        responses.reset()
        super().tearDown()

    def _make_message(self, **kwargs):
        defaults = {
            "subject": "Hello",
            "body": "Plain text",
            "from_email": "noreply@example.com",
            "to": ["alice@example.com"],
        }
        defaults.update(kwargs)
        return EmailMessage(**defaults)

    def _last_request_body(self):
        return json.loads(responses.calls[-1].request.body)

    @responses.activate
    def test_simple_text_email_payload(self):
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = self._make_message()
        backend = ResendEmailBackend()
        sent = backend.send_messages([msg])
        self.assertEqual(sent, 1)
        body = self._last_request_body()
        self.assertEqual(body["from"], "noreply@example.com")
        self.assertEqual(body["to"], ["alice@example.com"])
        self.assertEqual(body["subject"], "Hello")
        self.assertEqual(body["text"], "Plain text")
        self.assertNotIn("html", body)
        auth_header = responses.calls[-1].request.headers.get("Authorization")
        self.assertEqual(auth_header, "Bearer re_test_xxx")

    @responses.activate
    def test_multialternative_html_payload(self):
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = EmailMultiAlternatives(
            subject="Hello",
            body="Plain text",
            from_email="noreply@example.com",
            to=["alice@example.com"],
        )
        msg.attach_alternative("<p>Hi</p>", "text/html")
        ResendEmailBackend().send_messages([msg])
        body = self._last_request_body()
        self.assertEqual(body["text"], "Plain text")
        self.assertEqual(body["html"], "<p>Hi</p>")

    @responses.activate
    def test_cc_bcc_reply_to_headers(self):
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = self._make_message(
            cc=["c@example.com"],
            bcc=["b@example.com"],
            reply_to=["r@example.com"],
        )
        ResendEmailBackend().send_messages([msg])
        body = self._last_request_body()
        self.assertEqual(body["cc"], ["c@example.com"])
        self.assertEqual(body["bcc"], ["b@example.com"])
        self.assertEqual(body["reply_to"], ["r@example.com"])

        responses.reset()
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg2 = self._make_message()
        ResendEmailBackend().send_messages([msg2])
        body2 = self._last_request_body()
        self.assertNotIn("cc", body2)
        self.assertNotIn("bcc", body2)
        self.assertNotIn("reply_to", body2)

    @responses.activate
    def test_attachment_base64_encoded(self):
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = self._make_message()
        msg.attach("hello.txt", b"hi", "text/plain")
        ResendEmailBackend().send_messages([msg])
        body = self._last_request_body()
        self.assertEqual(
            body["attachments"][0],
            {"filename": "hello.txt", "content": "aGk=", "content_type": "text/plain"},
        )

        responses.reset()
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg2 = self._make_message()
        msg2.attach("readme.md", "hi", "text/markdown")
        ResendEmailBackend().send_messages([msg2])
        body2 = self._last_request_body()
        self.assertEqual(body2["attachments"][0]["content"], "aGk=")
        self.assertEqual(body2["attachments"][0]["content_type"], "text/markdown")

    @responses.activate
    def test_extra_headers_passthrough(self):
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = self._make_message()
        msg.extra_headers = {"X-Trace-Id": "abc"}
        ResendEmailBackend().send_messages([msg])
        body = self._last_request_body()
        self.assertEqual(body["headers"], {"X-Trace-Id": "abc"})

    @responses.activate
    @patch("notifications.email_backend.time.sleep")
    def test_5xx_retries_with_exponential_backoff(self, mock_sleep):
        for _ in range(4):
            responses.add(
                responses.POST,
                RESEND_API_URL,
                status=503,
                json={
                    "statusCode": 503,
                    "name": "application_error",
                    "message": "service unavailable",
                },
            )
        msg = self._make_message()
        with self.assertRaises(ResendSendError):
            ResendEmailBackend().send_messages([msg])
        self.assertEqual(len(responses.calls), 4)
        mock_sleep.assert_has_calls(
            [call(0.5), call(1.0), call(2.0)]
        )
        self.assertEqual(mock_sleep.call_count, 3)

    @responses.activate
    @patch("notifications.email_backend.time.sleep")
    def test_4xx_no_retry_logs_body(self, mock_sleep):
        responses.add(
            responses.POST,
            RESEND_API_URL,
            status=422,
            json={
                "statusCode": 422,
                "name": "validation_error",
                "message": "invalid recipient",
            },
        )
        msg = self._make_message()
        with self.assertLogs(
            "notifications.email_backend", level="ERROR"
        ) as log_cm:
            with self.assertRaises(ResendSendError):
                ResendEmailBackend().send_messages([msg])
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(mock_sleep.call_count, 0)
        combined = "\n".join(log_cm.output)
        self.assertIn("422", combined)
        self.assertIn("invalid recipient", combined)

    @responses.activate
    @patch("notifications.email_backend.time.sleep")
    def test_transient_network_error_retried(self, mock_sleep):
        responses.add(
            responses.POST,
            RESEND_API_URL,
            body=requests.ConnectionError("conn refused"),
        )
        responses.add(
            responses.POST, RESEND_API_URL, status=200, json={"id": "abc"}
        )
        msg = self._make_message()
        sent = ResendEmailBackend().send_messages([msg])
        self.assertEqual(sent, 1)
        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @responses.activate
    def test_fail_silently_swallows_errors(self):
        responses.add(
            responses.POST,
            RESEND_API_URL,
            status=422,
            json={
                "statusCode": 422,
                "name": "validation_error",
                "message": "bad request",
            },
        )
        msg = self._make_message()
        with self.assertLogs(
            "notifications.email_backend", level="ERROR"
        ):
            sent = ResendEmailBackend(fail_silently=True).send_messages([msg])
        self.assertEqual(sent, 0)

    def test_missing_api_key_raises_improperly_configured(self):
        with override_settings(RESEND_API_KEY=""):
            with self.assertRaises(ImproperlyConfigured):
                ResendEmailBackend(fail_silently=False)
            ResendEmailBackend(fail_silently=True)

    @responses.activate
    def test_send_messages_empty_list_returns_zero(self):
        backend = ResendEmailBackend()
        self.assertEqual(backend.send_messages([]), 0)
        self.assertEqual(len(responses.calls), 0)

    @patch("notifications.email_backend.time.sleep")
    @patch("notifications.email_backend.resend.Emails.send")
    def test_status_less_sdk_exception_is_fatal_not_retried(
        self, mock_send, mock_sleep
    ):
        mock_send.side_effect = RuntimeError("boom")
        msg = self._make_message()
        with self.assertLogs(
            "notifications.email_backend", level="ERROR"
        ) as log_cm:
            with self.assertRaises(ResendSendError) as raised:
                ResendEmailBackend().send_messages([msg])
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertEqual(mock_sleep.call_count, 0)
        self.assertTrue(
            any("aborting" in rec.lower() for rec in log_cm.output)
            or any("unexpected" in rec.lower() for rec in log_cm.output)
        )
