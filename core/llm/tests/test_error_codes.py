"""Machine-readable error codes for user-actionable failures.

The SSE error payload carries ``code`` when the user can fix the
problem directly (missing/invalid/underfunded API key) so the frontend
renders resolution actions instead of a generic dead-end message.
"""

from django.test import SimpleTestCase

from llm.error_messages import (
    ERROR_CODE_INSUFFICIENT_CREDITS,
    ERROR_CODE_INVALID_API_KEY,
    ERROR_CODE_NO_API_KEY,
    error_payload,
    get_error_code,
    get_user_friendly_error,
)
from llm.services.api_key_resolver import NoAPIKeyError


class GetErrorCodeTests(SimpleTestCase):
    def test_no_api_key_error_instance(self):
        self.assertEqual(
            get_error_code(NoAPIKeyError("No OpenRouter API key available")),
            ERROR_CODE_NO_API_KEY,
        )

    def test_no_api_key_message_pattern(self):
        self.assertEqual(
            get_error_code(ValueError("No API key available. Either authenticate...")),
            ERROR_CODE_NO_API_KEY,
        )

    def test_upstream_401_with_key_context(self):
        self.assertEqual(
            get_error_code(Exception("openrouter 401 Unauthorized: invalid key")),
            ERROR_CODE_INVALID_API_KEY,
        )

    def test_direct_provider_401(self):
        self.assertEqual(
            get_error_code(Exception("401 from https://api.anthropic.com/v1/chat/completions")),
            ERROR_CODE_INVALID_API_KEY,
        )

    def test_insufficient_credits_402(self):
        self.assertEqual(
            get_error_code(Exception("openrouter 402: insufficient credits")),
            ERROR_CODE_INSUFFICIENT_CREDITS,
        )

    def test_generic_errors_have_no_code(self):
        self.assertIsNone(get_error_code(Exception("connection timed out")))
        self.assertIsNone(get_error_code(Exception("500 internal server error")))
        # 401 without any key/provider context stays generic (e.g. session auth)
        self.assertIsNone(get_error_code(Exception("401 unauthorized")))


class ErrorPayloadTests(SimpleTestCase):
    def test_actionable_payload_has_code_and_message(self):
        payload = error_payload(NoAPIKeyError("No OpenRouter API key available"))
        self.assertEqual(payload["code"], ERROR_CODE_NO_API_KEY)
        self.assertIn("API key", payload["error"])
        self.assertIn("Settings", payload["error"])

    def test_generic_payload_has_no_code(self):
        payload = error_payload(Exception("connection refused"))
        self.assertNotIn("code", payload)
        self.assertTrue(payload["error"])

    def test_friendly_message_matches_actionable_text(self):
        exc = NoAPIKeyError("No OpenRouter API key available")
        self.assertEqual(get_user_friendly_error(exc), error_payload(exc)["error"])

    def test_no_key_material_in_actionable_messages(self):
        # Key material from the underlying exception must never surface.
        # (Naming OpenRouter as a user-facing BYOK option is fine.)
        for exc in (
            NoAPIKeyError("No OpenRouter API key available"),
            Exception("openrouter 401 unauthorized sk-or-v1-abcdef"),
            Exception("openrouter 402 insufficient credits sk-or-v1-abcdef"),
        ):
            message = error_payload(exc)["error"]
            self.assertNotIn("sk-or", message)
            self.assertNotIn("abcdef", message)
