"""Coverage for the Celery-unavailable Redis fallback queue in
usage_quota.tasks.

``queue_failed_deduction()``'s Redis fallback, ``process_failed_deductions_queue()``,
and ``get_failed_deductions_count()`` had no test coverage before this file:
they called ``cache.lpop``/``cache.rpush``/``cache.llen`` directly, methods
Django's cache API does not expose (only a Redis client obtained through
``_redis_list_client()`` does), so every call silently raised and was
swallowed by the surrounding ``except Exception`` — the fallback queue never
actually stored or drained anything. This file mocks the ``_redis_list_client``
seam directly since the test settings' cache backend (LocMemCache) doesn't
provide native Redis list commands either.
"""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from usage_quota import tasks


class QueueFailedDeductionRedisFallbackTest(TestCase):
    @patch("usage_quota.tasks._redis_list_client")
    @patch(
        "usage_quota.tasks.retry_failed_deduction.delay",
        side_effect=RuntimeError("celery unavailable"),
    )
    def test_falls_back_to_redis_when_celery_unavailable(
        self, mock_delay, mock_client_factory
    ):
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client

        result = tasks.queue_failed_deduction(
            user_id="u1", service="openrouter", cost_usd="0.05", feature="chat",
        )

        self.assertTrue(result)
        mock_client.rpush.assert_called_once()
        key, payload = mock_client.rpush.call_args[0]
        self.assertEqual(key, tasks.FAILED_DEDUCTIONS_KEY)
        stored = json.loads(payload)
        self.assertEqual(stored["user_id"], "u1")
        self.assertEqual(stored["service"], "openrouter")
        self.assertEqual(stored["cost_usd"], "0.05")
        self.assertEqual(stored["feature"], "chat")

    @patch("usage_quota.tasks._redis_list_client")
    @patch(
        "usage_quota.tasks.retry_failed_deduction.delay",
        side_effect=RuntimeError("celery unavailable"),
    )
    def test_returns_false_when_redis_also_unavailable(
        self, mock_delay, mock_client_factory
    ):
        mock_client_factory.side_effect = RuntimeError("no redis client")

        result = tasks.queue_failed_deduction(
            user_id="u1", service="openrouter", cost_usd="0.05", feature="chat",
        )

        self.assertFalse(result)


class ProcessFailedDeductionsQueueTest(TestCase):
    @patch("usage_quota.tasks._redis_list_client")
    @patch("usage_quota.tasks.retry_failed_deduction.delay")
    def test_drains_queue_and_dispatches_each_entry(
        self, mock_delay, mock_client_factory
    ):
        entries = [
            json.dumps({"user_id": "u1", "service": "openrouter",
                        "cost_usd": "0.01", "feature": "chat"}),
            json.dumps({"user_id": "u2", "service": "openrouter",
                        "cost_usd": "0.02", "feature": "chat"}),
        ]
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [*entries, None]
        mock_client_factory.return_value = mock_client

        processed = tasks.process_failed_deductions_queue()

        self.assertEqual(processed, 2)
        self.assertEqual(mock_delay.call_count, 2)

    @patch("usage_quota.tasks._redis_list_client")
    def test_requeues_entry_when_dispatch_fails(self, mock_client_factory):
        # redis-py returns bytes (no decode_responses=True configured),
        # matching what the production Redis backend actually hands back.
        raw = json.dumps({"user_id": "u1", "service": "openrouter",
                           "cost_usd": "0.01", "feature": "chat"}).encode()
        mock_client = MagicMock()
        mock_client.lpop.return_value = raw
        mock_client_factory.return_value = mock_client

        with patch(
            "usage_quota.tasks.retry_failed_deduction.delay",
            side_effect=RuntimeError("dispatch failed"),
        ):
            processed = tasks.process_failed_deductions_queue()

        self.assertEqual(processed, 0)
        mock_client.rpush.assert_called_once_with(
            tasks.FAILED_DEDUCTIONS_KEY, raw
        )

    @patch("usage_quota.tasks._redis_list_client")
    def test_invalid_json_bytes_are_logged_and_skipped(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [b"not valid json", None]
        mock_client_factory.return_value = mock_client

        with patch("usage_quota.tasks.retry_failed_deduction.delay") as mock_delay:
            processed = tasks.process_failed_deductions_queue()

        self.assertEqual(processed, 0)
        mock_delay.assert_not_called()
        # The invalid entry is dropped, not requeued.
        mock_client.rpush.assert_not_called()


class GetFailedDeductionsCountTest(TestCase):
    @patch("usage_quota.tasks._redis_list_client")
    def test_returns_queue_length(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.llen.return_value = 3
        mock_client_factory.return_value = mock_client

        self.assertEqual(tasks.get_failed_deductions_count(), 3)

    @patch(
        "usage_quota.tasks._redis_list_client",
        side_effect=RuntimeError("no redis"),
    )
    def test_returns_zero_when_client_unavailable(self, mock_client_factory):
        self.assertEqual(tasks.get_failed_deductions_count(), 0)
