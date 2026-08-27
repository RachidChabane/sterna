"""Tests for ``usage_quota.billing.decorators``.

Covers ``@billable``/``@billable_async``'s user-extraction, execute+record
and swallowed-extractor-exception paths, ``_extract_user``'s argument
patterns, and the four service-specific convenience decorators. The billing
service itself is mocked at ``get_billing_service`` — the module's own
adapter seam — for every test.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from usage_quota.billing.decorators import (
    _extract_user,
    billable,
    billable_async,
    billable_llm,
    billable_search,
    billable_stt,
    billable_tts,
)
from usage_quota.models import FeatureType, ServiceType


def _patch_billing(fake_billing):
    return patch(
        "usage_quota.billing.decorators.get_billing_service",
        return_value=fake_billing,
    )


class BillableSyncNoUserTests(SimpleTestCase):
    """With no identifiable user, the wrapped function still runs, but
    billing is skipped entirely."""

    def test_calls_through_without_touching_billing_service(self):
        fake_billing = MagicMock()

        @billable(service=ServiceType.OPENROUTER, feature=FeatureType.CHAT)
        def do_call(payload):
            return {"echo": payload}

        with _patch_billing(fake_billing):
            result = do_call({"x": 1})

        self.assertEqual(result, {"echo": {"x": 1}})
        fake_billing.check_quota.assert_not_called()
        fake_billing.record_usage.assert_not_called()


class BillableAsyncNoUserTests(SimpleTestCase):
    def test_calls_through_without_touching_billing_service(self):
        fake_billing = MagicMock()

        @billable_async(service=ServiceType.OPENROUTER, feature=FeatureType.CHAT)
        async def do_call(payload):
            return {"echo": payload}

        with _patch_billing(fake_billing):
            result = async_to_sync(do_call)({"x": 1})

        self.assertEqual(result, {"echo": {"x": 1}})
        fake_billing.check_quota.assert_not_called()


class BillableSyncExecutionAndRecordingTests(SimpleTestCase):
    """Once a user is found and no pre-check is requested, the operation
    runs and, when an extractor is supplied, usage is recorded from its
    result."""

    def test_runs_operation_and_records_usage_via_extractor(self):
        fake_billing = MagicMock()
        user = MagicMock(id="user-1")
        recorded_operation = MagicMock()

        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            extract_operation=lambda result, **kw: recorded_operation,
        )
        def do_call(user, prompt):
            return {"cost": 0.01, "prompt": prompt}

        with _patch_billing(fake_billing):
            result = do_call(user=user, prompt="hello")

        self.assertEqual(result, {"cost": 0.01, "prompt": "hello"})
        fake_billing.record_usage.assert_called_once_with(user, recorded_operation)

    def test_extractor_exception_is_swallowed_and_result_still_returned(self):
        fake_billing = MagicMock()
        user = MagicMock(id="user-1")

        def _broken_extractor(result, **kw):
            raise ValueError("cannot extract")

        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            extract_operation=_broken_extractor,
        )
        def do_call(user):
            return "operation result"

        with _patch_billing(fake_billing):
            result = do_call(user=user)

        self.assertEqual(result, "operation result")
        fake_billing.record_usage.assert_not_called()

    def test_no_extractor_means_usage_is_never_recorded(self):
        fake_billing = MagicMock()
        user = MagicMock(id="user-1")

        @billable(service=ServiceType.OPENROUTER, feature=FeatureType.CHAT)
        def do_call(user):
            return "ok"

        with _patch_billing(fake_billing):
            do_call(user=user)

        fake_billing.record_usage.assert_not_called()


class BillableAsyncExecutionAndRecordingTests(SimpleTestCase):
    def test_runs_operation_and_records_usage_via_extractor(self):
        fake_billing = MagicMock()
        user = MagicMock(id="user-1")
        recorded_operation = MagicMock()

        @billable_async(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            extract_operation=lambda result, **kw: recorded_operation,
        )
        async def do_call(user):
            return "async result"

        with _patch_billing(fake_billing):
            result = async_to_sync(do_call)(user=user)

        self.assertEqual(result, "async result")
        fake_billing.record_usage.assert_called_once_with(user, recorded_operation)

    def test_extractor_exception_is_swallowed_and_result_still_returned(self):
        fake_billing = MagicMock()
        user = MagicMock(id="user-1")

        def _broken_extractor(result, **kw):
            raise ValueError("cannot extract")

        @billable_async(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            extract_operation=_broken_extractor,
        )
        async def do_call(user):
            return "async result"

        with _patch_billing(fake_billing):
            result = async_to_sync(do_call)(user=user)

        self.assertEqual(result, "async result")
        fake_billing.record_usage.assert_not_called()


class ExtractUserTests(SimpleTestCase):
    """``_extract_user`` walks kwargs, then positional args, in a fixed
    priority order."""

    def test_user_kwarg_wins_immediately(self):
        user = object()
        self.assertIs(_extract_user((), {"user": user}), user)

    def test_request_kwarg_with_authenticated_user_attribute(self):
        user = MagicMock(id="u1")
        request = MagicMock(user=user)
        self.assertIs(_extract_user((), {"request": request}), user)

    def test_request_kwarg_without_usable_user_falls_through_to_none(self):
        request = MagicMock(user=None)
        self.assertIsNone(_extract_user((), {"request": request}))

    def test_positional_request_like_object_with_user_attribute(self):
        user = MagicMock(id="u1")
        request = MagicMock(user=user)
        self.assertIs(_extract_user((request,), {}), user)

    def test_positional_object_that_looks_like_a_user_directly(self):
        user_like = MagicMock(id="u1", email="a@b.com")
        del user_like.user  # must not resemble a request object too
        self.assertIs(_extract_user((user_like,), {}), user_like)

    def test_none_positional_arg_is_skipped_without_raising(self):
        user = MagicMock(id="u1", email="a@b.com")
        del user.user
        self.assertIs(_extract_user((None, user), {}), user)

    def test_no_recognizable_user_returns_none(self):
        self.assertIsNone(_extract_user((object(), 42, "plain string"), {}))


class ConvenienceDecoratorServiceMappingTests(SimpleTestCase):
    """Each convenience decorator must pre-check against its dedicated
    ``ServiceType`` — verified by observing which service the pre-check
    call reaches ``check_quota`` with."""

    def _service_seen_by_precheck(self, decorator_factory, **decorator_kwargs):
        fake_billing = MagicMock()
        fake_billing.check_quota.return_value = MagicMock(allowed=True)
        user = MagicMock(id="user-1")

        @decorator_factory(pre_check=True, estimated_cost_usd=Decimal("0.01"), **decorator_kwargs)
        def do_call(user):
            return "ok"

        with _patch_billing(fake_billing):
            do_call(user=user)

        args, _kwargs = fake_billing.check_quota.call_args
        return args[1]  # (user, service, cost, feature)

    def test_billable_llm_targets_openrouter(self):
        self.assertEqual(self._service_seen_by_precheck(billable_llm), ServiceType.OPENROUTER)

    def test_billable_tts_defaults_to_elevenlabs(self):
        self.assertEqual(self._service_seen_by_precheck(billable_tts), ServiceType.ELEVENLABS_TTS)

    def test_billable_tts_openai_provider_targets_openai(self):
        self.assertEqual(
            self._service_seen_by_precheck(billable_tts, provider="openai"),
            ServiceType.OPENAI_TTS,
        )

    def test_billable_stt_targets_deepgram(self):
        self.assertEqual(self._service_seen_by_precheck(billable_stt), ServiceType.DEEPGRAM_STT)

    def test_billable_search_targets_brave_search(self):
        self.assertEqual(self._service_seen_by_precheck(billable_search), ServiceType.BRAVE_SEARCH)
