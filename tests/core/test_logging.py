"""Unit tests for core/logging/logger.py and core/logging/timing.py.

Covers:
- set_trace_id / get_trace_id
- set_session_id / get_session_id
- bind_request_context (sets ContextVars, binds structlog context)
- timed_operation (success path and exception path)
"""

from __future__ import annotations

import uuid

import pytest

from src.core.logging.logger import (
    bind_request_context,
    get_session_id,
    get_trace_id,
    set_session_id,
    set_trace_id,
)
from src.core.logging.timing import timed_operation

# ---------------------------------------------------------------------------
# Trace ID
# ---------------------------------------------------------------------------


class TestTraceId:
    """set_trace_id / get_trace_id behave correctly."""

    def test_set_returns_provided_value(self) -> None:
        tid = set_trace_id("my-trace-abc")
        assert tid == "my-trace-abc"

    def test_get_returns_set_value(self) -> None:
        set_trace_id("trace-xyz")
        assert get_trace_id() == "trace-xyz"

    def test_set_none_generates_uuid(self) -> None:
        tid = set_trace_id(None)
        uuid.UUID(tid)  # raises if not valid UUID

    def test_set_empty_generates_uuid(self) -> None:
        tid = set_trace_id("")
        uuid.UUID(tid)


# ---------------------------------------------------------------------------
# Session ID
# ---------------------------------------------------------------------------


class TestSessionId:
    """set_session_id / get_session_id behave correctly."""

    def test_set_returns_provided_value(self) -> None:
        sid = set_session_id("sess-001")
        assert sid == "sess-001"

    def test_get_returns_set_value(self) -> None:
        set_session_id("s-abc")
        assert get_session_id() == "s-abc"

    def test_set_none_clears_to_empty(self) -> None:
        set_session_id("existing")
        result = set_session_id(None)
        assert result == ""
        assert get_session_id() == ""

    def test_set_empty_clears(self) -> None:
        set_session_id("existing")
        result = set_session_id("")
        assert result == ""
        assert get_session_id() == ""


# ---------------------------------------------------------------------------
# bind_request_context
# ---------------------------------------------------------------------------


class TestBindRequestContext:
    """bind_request_context wires ContextVars and structlog context."""

    def test_returns_trace_id(self) -> None:
        tid = bind_request_context(request_id="req-001")
        uuid.UUID(tid)  # generated UUID

    def test_returns_provided_trace_id(self) -> None:
        tid = bind_request_context(request_id="r", trace_id="fixed-trace")
        assert tid == "fixed-trace"

    def test_sets_trace_id_contextvar(self) -> None:
        bind_request_context(request_id="r", trace_id="t-123")
        assert get_trace_id() == "t-123"

    def test_sets_session_id_contextvar_when_provided(self) -> None:
        bind_request_context(request_id="r", session_id="s-abc")
        assert get_session_id() == "s-abc"

    def test_clears_session_id_contextvar_when_none(self) -> None:
        set_session_id("old-session")
        bind_request_context(request_id="r", session_id=None)
        assert get_session_id() == ""

    def test_request_id_bound_in_structlog_context(self) -> None:
        """request_id should appear in the structlog bound contextvars."""
        import structlog.contextvars as sv
        bind_request_context(request_id="req-bound", trace_id="t-bound")
        ctx = sv.get_contextvars()
        assert ctx["request_id"] == "req-bound"

    def test_trace_id_bound_in_structlog_context(self) -> None:
        import structlog.contextvars as sv
        bind_request_context(request_id="r", trace_id="t-explicit")
        ctx = sv.get_contextvars()
        assert ctx["trace_id"] == "t-explicit"

    def test_session_id_bound_in_structlog_context_when_provided(self) -> None:
        import structlog.contextvars as sv
        bind_request_context(request_id="r", session_id="s-bound")
        ctx = sv.get_contextvars()
        assert ctx["session_id"] == "s-bound"

    def test_session_id_absent_when_not_provided(self) -> None:
        import structlog.contextvars as sv
        bind_request_context(request_id="r", session_id=None)
        ctx = sv.get_contextvars()
        assert "session_id" not in ctx


# ---------------------------------------------------------------------------
# timed_operation
# ---------------------------------------------------------------------------


class _MockLog:
    """Minimal stand-in logger for timed_operation tests."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def debug(self, event: str, **kw: object) -> None:
        self.records.append({"level": "debug", "event": event, **kw})

    def warning(self, event: str, **kw: object) -> None:
        self.records.append({"level": "warning", "event": event, **kw})

    info = debug  # capture all levels uniformly


class TestTimedOperation:
    """timed_operation emits structured logs and re-raises on failure."""

    @pytest.mark.asyncio
    async def test_success_emits_operation_complete(self) -> None:
        log = _MockLog()
        async with timed_operation("test_layer", "test_op", log):
            pass
        events = [r["event"] for r in log.records]
        assert "operation_complete" in events

    @pytest.mark.asyncio
    async def test_success_record_has_latency_ms(self) -> None:
        log = _MockLog()
        async with timed_operation("layer", "op", log):
            pass
        complete = next(r for r in log.records if r["event"] == "operation_complete")
        assert isinstance(complete["latency_ms"], float)
        assert complete["latency_ms"] >= 0.0

    @pytest.mark.asyncio
    async def test_success_record_has_layer_and_operation(self) -> None:
        log = _MockLog()
        async with timed_operation("svc", "do_thing", log):
            pass
        complete = next(r for r in log.records if r["event"] == "operation_complete")
        assert complete["layer"] == "svc"
        assert complete["operation"] == "do_thing"

    @pytest.mark.asyncio
    async def test_exception_is_reraised_unchanged(self) -> None:
        log = _MockLog()

        class _SentinelError(Exception):
            pass

        with pytest.raises(_SentinelError):
            async with timed_operation("layer", "op", log):
                raise _SentinelError("boom")

    @pytest.mark.asyncio
    async def test_exception_emits_operation_failed(self) -> None:
        log = _MockLog()
        with pytest.raises(ValueError):  # noqa: PT011
            async with timed_operation("layer", "op", log):
                raise ValueError("something broke")
        events = [r["event"] for r in log.records]
        assert "operation_failed" in events

    @pytest.mark.asyncio
    async def test_failed_record_has_error_type(self) -> None:
        log = _MockLog()
        with pytest.raises(RuntimeError):  # noqa: PT011
            async with timed_operation("l", "o", log):
                raise RuntimeError("rt-error")
        failed = next(r for r in log.records if r["event"] == "operation_failed")
        assert failed["error"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_operation_complete_not_emitted_on_failure(self) -> None:
        log = _MockLog()
        with pytest.raises(OSError):  # noqa: PT011
            async with timed_operation("l", "o", log):
                raise OSError("io error")
        events = [r["event"] for r in log.records]
        assert "operation_complete" not in events
