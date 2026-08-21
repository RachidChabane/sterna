"""Tests for the Celery observability wiring in sterna/celery.py.

Covers:
- setup_logging receiver re-applies the Django LOGGING dictConfig so
  workers keep JSON structure + redaction (root logger not hijacked).
- request-id propagation: publisher copies the ContextVar into task
  headers; worker restores it and clears it afterwards.

The signal handlers are invoked directly — no broker/worker needed.
"""

import logging

from sterna.celery import (
    REQUEST_ID_HEADER,
    app,
    clear_request_id_in_worker,
    configure_structured_logging,
    propagate_request_id_to_task,
    restore_request_id_in_worker,
)
from sterna.middleware.request_id import current_request_id


class _FakeTaskRequest(dict):
    """Mimics celery.app.task.Context: supports .get(key)."""


class _FakeTask:
    def __init__(self, request):
        self.request = request


class TestWorkerLoggingNotHijacked:
    def test_worker_hijack_root_logger_disabled(self):
        assert app.conf.worker_hijack_root_logger is False

    def test_setup_logging_receiver_connected(self):
        from celery.signals import setup_logging

        receivers = [
            getattr(r, "__name__", None)
            for r in setup_logging._live_receivers(None)
        ]
        assert "configure_structured_logging" in receivers

    def test_configure_structured_logging_applies_dictconfig(self):
        # Under the test settings, LOGGING is the null config: the
        # handler re-applies it without error and the root logger ends
        # up matching settings.LOGGING (CRITICAL + null handler).
        configure_structured_logging()
        root = logging.getLogger()
        assert root.level == logging.CRITICAL
        assert any(
            isinstance(h, logging.NullHandler) for h in root.handlers
        )


class TestRequestIDPropagation:
    def test_publish_copies_request_id_into_headers(self):
        token = current_request_id.set("rid-celery-1")
        try:
            headers = {}
            propagate_request_id_to_task(headers=headers)
            assert headers[REQUEST_ID_HEADER] == "rid-celery-1"
        finally:
            current_request_id.reset(token)

    def test_publish_noop_without_request_id(self):
        headers = {}
        propagate_request_id_to_task(headers=headers)
        assert REQUEST_ID_HEADER not in headers

    def test_publish_keeps_existing_header(self):
        token = current_request_id.set("rid-celery-2")
        try:
            headers = {REQUEST_ID_HEADER: "already-set"}
            propagate_request_id_to_task(headers=headers)
            assert headers[REQUEST_ID_HEADER] == "already-set"
        finally:
            current_request_id.reset(token)

    def test_publish_tolerates_non_dict_headers(self):
        # Celery may hand over None in edge cases — must not raise.
        propagate_request_id_to_task(headers=None)

    def test_prerun_restores_request_id_from_task_request(self):
        task = _FakeTask(_FakeTaskRequest({REQUEST_ID_HEADER: "rid-worker-1"}))
        try:
            restore_request_id_in_worker(task=task)
            assert current_request_id.get() == "rid-worker-1"
        finally:
            current_request_id.set(None)

    def test_prerun_falls_back_to_headers_dict(self):
        class _Ctx:
            headers = {REQUEST_ID_HEADER: "rid-worker-2"}

        try:
            restore_request_id_in_worker(task=_FakeTask(_Ctx()))
            assert current_request_id.get() == "rid-worker-2"
        finally:
            current_request_id.set(None)

    def test_prerun_sets_none_when_absent(self):
        current_request_id.set("stale-rid")
        restore_request_id_in_worker(task=_FakeTask(_FakeTaskRequest()))
        assert current_request_id.get() is None

    def test_postrun_clears_request_id(self):
        current_request_id.set("rid-worker-3")
        clear_request_id_in_worker(task=None)
        assert current_request_id.get() is None

    def test_round_trip_publish_to_worker(self):
        token = current_request_id.set("rid-round-trip")
        try:
            headers = {}
            propagate_request_id_to_task(headers=headers)
        finally:
            current_request_id.reset(token)

        # Simulate the worker side in a clean context.
        assert current_request_id.get() is None
        task = _FakeTask(_FakeTaskRequest(headers))
        restore_request_id_in_worker(task=task)
        assert current_request_id.get() == "rid-round-trip"
        clear_request_id_in_worker(task=task)
        assert current_request_id.get() is None
