"""Which streaming stack a V2 chat request is answered by.

The decision is made per request: the header wins over the setting,
and the setting answers a request that carries no header.
"""

import unittest

from django.test import RequestFactory, override_settings

from llm.agent_service.flag import (
    DEFAULT_ENABLED,
    HEADER_META_KEY,
    SETTING_NAME,
    configured_default,
    serves_agent_core,
)

PATH = "/api/llm/completions/stream-complete-v2/"


def _request(header_value=None):
    extra = {HEADER_META_KEY: header_value} if header_value is not None else {}
    return RequestFactory().post(PATH, **extra)


class AgentCoreFlagTests(unittest.TestCase):
    """What decides the stack for one request."""

    def test_a_request_naming_no_stack_takes_the_configured_default(self):
        with override_settings(**{SETTING_NAME: True}):
            self.assertTrue(serves_agent_core(_request()))
        with override_settings(**{SETTING_NAME: False}):
            self.assertFalse(serves_agent_core(_request()))

    def test_the_header_overrides_the_setting_in_both_directions(self):
        with override_settings(**{SETTING_NAME: False}):
            self.assertTrue(serves_agent_core(_request("on")))
        with override_settings(**{SETTING_NAME: True}):
            self.assertFalse(serves_agent_core(_request("off")))

    def test_a_header_naming_no_stack_leaves_the_setting_in_charge(self):
        with override_settings(**{SETTING_NAME: True}):
            self.assertTrue(serves_agent_core(_request("maybe")))

    def test_the_setting_answers_when_the_project_does_not_define_it(self):
        self.assertEqual(configured_default(), DEFAULT_ENABLED)


if __name__ == "__main__":
    unittest.main()
