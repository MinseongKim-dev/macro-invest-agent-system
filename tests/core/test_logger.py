"""Unit tests for core/logging/logger.py."""

import os
from unittest.mock import patch

from src.core.config.settings import get_settings
from src.core.logging.logger import get_logger, get_trace_id, set_trace_id


class TestTraceId:
    """Trace ID context variable behaves correctly."""

    def test_set_trace_id_returns_provided_value(self) -> None:
        tid = set_trace_id("my-trace-abc")
        assert tid == "my-trace-abc"

    def test_get_trace_id_returns_set_value(self) -> None:
        set_trace_id("trace-xyz")
        assert get_trace_id() == "trace-xyz"

    def test_set_trace_id_none_generates_uuid(self) -> None:
        tid = set_trace_id(None)
        import uuid

        uuid.UUID(tid)  # should not raise — confirms it's a valid UUID

    def test_set_trace_id_empty_generates_uuid(self) -> None:
        tid = set_trace_id("")
        import uuid

        uuid.UUID(tid)


class TestGetLogger:
    """get_logger returns a working logger instance."""

    def setup_method(self) -> None:
        get_settings.cache_clear()
        # Reset structlog configuration state for isolated tests
        import src.core.logging.logger as logger_mod

        logger_mod._configured = False

    def teardown_method(self) -> None:
        get_settings.cache_clear()
        import src.core.logging.logger as logger_mod

        logger_mod._configured = False

    def test_returns_logger_instance(self) -> None:

        log = get_logger(__name__)
        assert log is not None
        # structlog bound loggers expose a bind method
        assert hasattr(log, "bind")

    def test_calling_twice_returns_same_type(self) -> None:
        log1 = get_logger("module.a")
        log2 = get_logger("module.b")
        assert type(log1) is type(log2)

    def test_logger_info_does_not_raise(self) -> None:
        log = get_logger(__name__)
        log.info("test_event", extra_field="value")

    def test_logger_warning_does_not_raise(self) -> None:
        log = get_logger(__name__)
        log.warning("test_warning")

    def test_logger_error_does_not_raise(self) -> None:
        log = get_logger(__name__)
        log.error("test_error", code="SOME_CODE")

    def test_pretty_mode_configures_without_error(self) -> None:
        with patch.dict(os.environ, {"LOG_PRETTY": "true", "APP_ENV": "local"}):
            import src.core.logging.logger as logger_mod

            logger_mod._configured = False
            log = get_logger("pretty_test")
            log.info("pretty_event")
