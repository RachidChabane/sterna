"""Tests for the structured logging stack."""

import io
import json
import logging
import uuid

import pytest

from sterna.logging import (
    RedactSensitiveKeysFilter,
    RequestIDFilter,
    ServiceTagFilter,
    UserIDFilter,
    _make_json_formatter,
    build_logging_config,
)


def _capture(logger_name: str = "sterna.test"):
    """Build a logger with the JSON formatter writing to a StringIO."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_make_json_formatter())
    handler.addFilter(RequestIDFilter())
    handler.addFilter(UserIDFilter())
    handler.addFilter(RedactSensitiveKeysFilter())
    logger = logging.getLogger(f"{logger_name}.{uuid.uuid4().hex}")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return logger, buf


def _read_last(buf: io.StringIO) -> dict:
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert lines, "no log records emitted"
    return json.loads(lines[-1])


class TestJsonFormatterEmitsRequiredFields:
    def test_all_required_fields_present(self):
        logger, buf = _capture()
        logger.info(
            "billing.usage_recorded",
            extra={"cost_usd": "0.01", "feature": "chat"},
        )
        record = _read_last(buf)
        for key in ("timestamp", "level", "logger",
                    "request_id", "user_id", "msg"):
            assert key in record, f"missing {key}: {record}"
        assert record["level"] == "INFO"
        assert record["msg"] == "billing.usage_recorded"
        assert record["cost_usd"] == "0.01"
        assert record["feature"] == "chat"

    def test_exception_emits_exc_info(self):
        logger, buf = _capture()
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("orchestrator.execute_failed")
        record = _read_last(buf)
        body = json.dumps(record)
        assert "ValueError" in body
        assert "boom" in body


class TestRequestIDFilter:
    def test_request_id_is_dash_when_unset(self):
        logger, buf = _capture()
        logger.info("no-request-context")
        record = _read_last(buf)
        assert record["request_id"] == "-"

    def test_request_id_propagates_from_contextvar(self):
        from sterna.middleware.request_id import current_request_id
        token = current_request_id.set("abc-123")
        try:
            logger, buf = _capture()
            logger.info("with-context")
            record = _read_last(buf)
            assert record["request_id"] == "abc-123"
        finally:
            current_request_id.reset(token)

    def test_user_id_propagates_from_contextvar(self):
        from sterna.middleware.request_id import current_user_id
        token = current_user_id.set("user-42")
        try:
            logger, buf = _capture()
            logger.info("with-user")
            record = _read_last(buf)
            assert record["user_id"] == "user-42"
        finally:
            current_user_id.reset(token)


class TestSensitiveKeyFilterRedacts:
    @pytest.mark.parametrize("key,value", [
        ("api_key", "sk-or-v1-realsecret"),
        ("password", "hunter2"),
        ("openrouter_api_key", "sk-or-v1-x"),
        ("stripe_webhook_secret", "whsec_x"),
        ("refresh_token", "eyJxxx.yyy.zzz"),
        ("authorization", "Bearer eyJabc.def.ghi"),
        ("byok_api_key", "ak-x"),
        ("field_encryption_key", "fernet-key"),
        ("client_secret", "abc123"),
        ("id_token", "eyJ..."),
    ])
    def test_redacts_known_keys(self, key, value):
        logger, buf = _capture()
        logger.info("event", extra={key: value})
        record = _read_last(buf)
        assert record[key] == "***REDACTED***"

    def test_does_not_redact_innocuous_keys(self):
        logger, buf = _capture()
        logger.info(
            "event",
            extra={"user_id": "u-123", "cost_usd": "0.05", "service": "web"},
        )
        record = _read_last(buf)
        assert record["user_id"] == "u-123"
        assert record["cost_usd"] == "0.05"
        assert record["service"] == "web"

    def test_redacts_nested_dict_keys(self):
        logger, buf = _capture()
        logger.info(
            "event",
            extra={"operation": {"model_id": "gpt-4", "api_key": "leaked"}},
        )
        record = _read_last(buf)
        assert record["operation"]["api_key"] == "***REDACTED***"
        assert record["operation"]["model_id"] == "gpt-4"

    def test_redacts_secret_patterns_in_message_body(self):
        logger, buf = _capture()
        logger.error("Failed call: Authorization: Bearer eyJabc.def.ghi")
        record = _read_last(buf)
        assert "eyJabc.def.ghi" not in record["msg"]
        assert "***REDACTED***" in record["msg"]

    def test_redacts_stripe_key_in_message(self):
        logger, buf = _capture()
        logger.error("stripe call failed with sk_live_abc123xyz")
        record = _read_last(buf)
        assert "sk_live_abc123xyz" not in record["msg"]
        assert "***REDACTED***" in record["msg"]

    def test_redacts_openrouter_key_in_message(self):
        logger, buf = _capture()
        logger.error("openrouter call: sk-or-v1-abcDEF123")
        record = _read_last(buf)
        assert "sk-or-v1-abcDEF123" not in record["msg"]


class TestRequestIDMiddleware:
    """Exercise the middleware via RequestFactory so the test does not
    require the full URL resolver or the migrations stack."""

    def _build_middleware(self):
        from sterna.middleware.request_id import RequestIDMiddleware
        from django.http import HttpResponse

        captured = {}

        def get_response(request):
            from sterna.middleware.request_id import current_request_id
            captured["request_id_during_request"] = current_request_id.get()
            return HttpResponse("ok")

        return RequestIDMiddleware(get_response), captured

    def test_request_id_generated_when_missing(self):
        from django.test import RequestFactory
        mw, _ = self._build_middleware()
        req = RequestFactory().get("/livez")
        resp = mw(req)
        assert resp["X-Request-ID"]
        uuid.UUID(resp["X-Request-ID"])

    def test_request_id_preserved_when_provided(self):
        from django.test import RequestFactory
        mw, _ = self._build_middleware()
        rid = "cafef00d-cafe-cafe-cafe-cafef00dcafe"
        req = RequestFactory().get("/livez", HTTP_X_REQUEST_ID=rid)
        resp = mw(req)
        assert resp["X-Request-ID"] == rid

    def test_request_id_contextvar_set_during_request(self):
        from django.test import RequestFactory
        mw, captured = self._build_middleware()
        rid = "ddddeeee-aaaa-bbbb-cccc-111122223333"
        req = RequestFactory().get("/", HTTP_X_REQUEST_ID=rid)
        mw(req)
        assert captured["request_id_during_request"] == rid

    def test_request_id_contextvar_reset_after_response(self):
        from django.test import RequestFactory
        from sterna.middleware.request_id import current_request_id
        mw, _ = self._build_middleware()
        req = RequestFactory().get("/", HTTP_X_REQUEST_ID="abc")
        mw(req)
        # Token reset means the var goes back to its prior value (None
        # in tests). Without proper reset, this would still read "abc".
        assert current_request_id.get() is None

    def test_request_id_contextvar_reset_after_exception(self):
        from django.test import RequestFactory
        from sterna.middleware.request_id import (
            RequestIDMiddleware, current_request_id,
        )

        class _Boom(Exception):
            pass

        def get_response(request):
            raise _Boom()

        mw = RequestIDMiddleware(get_response)
        req = RequestFactory().get("/", HTTP_X_REQUEST_ID="rid-boom")
        try:
            mw(req)
        except _Boom:
            mw.process_exception(req, _Boom())
        assert current_request_id.get() is None

    def test_process_exception_then_process_response_does_not_raise(self):
        """Regression: when a view raises, Django runs BOTH
        process_exception and process_response. The second
        ``Token.reset`` used to raise RuntimeError ('Token has already
        been used once'), which the old ``except ValueError`` guard did
        not swallow."""
        from django.http import HttpResponse
        from django.test import RequestFactory
        from sterna.middleware.request_id import (
            RequestIDMiddleware, current_request_id,
        )

        mw = RequestIDMiddleware(lambda request: HttpResponse("ok"))
        req = RequestFactory().get("/", HTTP_X_REQUEST_ID="rid-double")
        mw.process_request(req)
        mw.process_exception(req, ValueError("view exploded"))
        # Must not raise RuntimeError on the second reset attempt.
        resp = mw.process_response(req, HttpResponse(status=500))
        assert resp["X-Request-ID"] == "rid-double"
        assert current_request_id.get() is None


class TestRequestIDHeadersHelper:
    """request_id_headers() injects X-Request-ID into outbound
    Django -> service HTTP calls (orchestrator et al.)."""

    def test_injects_current_request_id(self):
        from sterna.middleware.request_id import (
            current_request_id, request_id_headers,
        )
        token = current_request_id.set("rid-outbound-1")
        try:
            headers = request_id_headers({"Authorization": "Bearer t"})
            assert headers["X-Request-ID"] == "rid-outbound-1"
            assert headers["Authorization"] == "Bearer t"
        finally:
            current_request_id.reset(token)

    def test_noop_without_active_request_id(self):
        from sterna.middleware.request_id import request_id_headers
        headers = request_id_headers({"Authorization": "Bearer t"})
        assert "X-Request-ID" not in headers

    def test_does_not_mutate_input_and_keeps_explicit_header(self):
        from sterna.middleware.request_id import (
            current_request_id, request_id_headers,
        )
        token = current_request_id.set("rid-outbound-2")
        try:
            original = {"X-Request-ID": "explicit-rid"}
            headers = request_id_headers(original)
            assert headers["X-Request-ID"] == "explicit-rid"
            headers["extra"] = "x"
            assert "extra" not in original
        finally:
            current_request_id.reset(token)

    def test_none_input_returns_dict(self):
        from sterna.middleware.request_id import (
            current_request_id, request_id_headers,
        )
        token = current_request_id.set("rid-outbound-3")
        try:
            assert request_id_headers() == {"X-Request-ID": "rid-outbound-3"}
        finally:
            current_request_id.reset(token)


class TestServiceTagFilter:
    def test_service_field_stamped(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(_make_json_formatter())
        handler.addFilter(ServiceTagFilter("orchestrator"))
        handler.addFilter(RequestIDFilter())
        handler.addFilter(UserIDFilter())
        handler.addFilter(RedactSensitiveKeysFilter())
        logger = logging.getLogger(f"svc.{uuid.uuid4().hex}")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.propagate = False
        logger.info("ev")
        record = _read_last(buf)
        assert record.get("service") == "orchestrator"


class TestBuildLoggingConfig:
    def test_prod_uses_json_formatter(self):
        cfg = build_logging_config(env="prod", service="web")
        assert cfg["handlers"]["console"]["formatter"] == "json"

    def test_staging_uses_json_formatter(self):
        cfg = build_logging_config(env="staging", service="web")
        assert cfg["handlers"]["console"]["formatter"] == "json"

    def test_dev_uses_human_formatter(self):
        cfg = build_logging_config(env="dev", service="web")
        assert cfg["handlers"]["console"]["formatter"] == "human"

    def test_test_env_is_null(self):
        cfg = build_logging_config(env="test", service="web")
        assert "null" in cfg["handlers"]
        assert "console" not in cfg["handlers"]

    def test_service_logger_registered(self):
        cfg = build_logging_config(env="prod", service="orchestrator")
        assert "orchestrator" in cfg["loggers"]

    def test_console_handler_is_debug_so_logger_levels_govern(self):
        """Regression: a WARNING console handler silently dropped every
        app INFO event (billing.usage_recorded, billing.quota_exceeded)
        in prod/staging even though the app loggers were INFO."""
        for env in ("prod", "staging", "dev"):
            cfg = build_logging_config(env=env, service="web")
            assert cfg["handlers"]["console"]["level"] == "DEBUG", env

    def test_app_loggers_registered_at_info_in_prod(self):
        cfg = build_logging_config(env="prod", service="web")
        for name in ("usage_quota", "authentication", "llm",
                     "audit_logging", "conversations", "notifications",
                     "sterna"):
            assert name in cfg["loggers"], f"missing app logger {name}"
            assert cfg["loggers"][name]["level"] == "INFO"

    def test_root_stays_warning_in_prod(self):
        cfg = build_logging_config(env="prod", service="web")
        assert cfg["root"]["level"] == "WARNING"


class TestProdConfigEmitsAppInfoEvents:
    """Apply the real prod dictConfig and prove that an INFO event from
    an app logger is emitted while DEBUG stays suppressed. This is the
    exact path that dropped billing.usage_recorded in prod/staging."""

    _CONFIGURED_LOGGERS = (
        "django", "usage_quota", "authentication", "llm",
        "audit_logging", "conversations", "notifications",
        "sterna", "web",
    )

    def _cleanup(self):
        import logging.config
        for name in self._CONFIGURED_LOGGERS:
            lg = logging.getLogger(name)
            lg.handlers.clear()
            lg.setLevel(logging.NOTSET)
            lg.propagate = True
        # Restore the test-env null config for the root logger.
        logging.config.dictConfig(
            build_logging_config(env="test", service="web")
        )

    def test_info_emitted_and_debug_suppressed_under_prod(self):
        import logging.config

        logging.config.dictConfig(
            build_logging_config(env="prod", service="web")
        )
        try:
            app_logger = logging.getLogger("usage_quota.billing.service")
            handler = logging.getLogger("usage_quota").handlers[0]

            buf = io.StringIO()
            handler.setStream(buf)
            app_logger.info(
                "billing.usage_recorded",
                extra={"cost_usd": "0.01", "feature": "chat"},
            )
            record = _read_last(buf)
            assert record["msg"] == "billing.usage_recorded"
            assert record["level"] == "INFO"
            assert record["cost_usd"] == "0.01"

            buf2 = io.StringIO()
            handler.setStream(buf2)
            app_logger.debug("billing.debug_noise")
            assert buf2.getvalue() == "", (
                "DEBUG must stay suppressed under prod config"
            )
        finally:
            self._cleanup()

    def test_third_party_info_still_suppressed_under_prod(self):
        """Root stays WARNING: chatty third-party INFO must not leak."""
        import logging.config

        logging.config.dictConfig(
            build_logging_config(env="prod", service="web")
        )
        try:
            root_handler = logging.getLogger().handlers[0]
            buf = io.StringIO()
            root_handler.setStream(buf)
            logging.getLogger(f"urllib3.{uuid.uuid4().hex}").info("noise")
            assert buf.getvalue() == ""
        finally:
            self._cleanup()
