"""Unit tests for core/tracing/tracer.py and core/tracing/span_attributes.py.

Covers:
- configure_tracing() is idempotent and safe when tracing is disabled
- get_tracer() returns a valid OTel Tracer
- inject_otel_context_into_structlog() injects IDs when a span is active
- inject_otel_context_into_structlog() is a no-op with no active span
- span_attributes constants are non-empty strings
"""

from __future__ import annotations

from typing import cast

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

import src.core.tracing.tracer as tracer_mod
from src.core.config.settings import Settings
from src.core.tracing import span_attributes
from src.core.tracing.tracer import (
    configure_tracing,
    get_tracer,
    inject_otel_context_into_structlog,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal stand-in for Settings, used to control configure_tracing()."""

    def __init__(
        self,
        *,
        tracing_enabled: bool = False,
        otlp_endpoint: str = "http://localhost:4318",
        otel_service_name: str = "test-service",
        otel_sample_rate: float = 1.0,
        app_env: object = None,
    ) -> None:
        self.tracing_enabled = tracing_enabled
        self.otlp_endpoint = otlp_endpoint
        self.otel_service_name = otel_service_name
        self.otel_sample_rate = otel_sample_rate

        class _Env:
            value = "test"

        self.app_env = app_env or _Env()


def _reset_tracer_module() -> None:
    """Reset configure_tracing idempotency guard between tests."""
    tracer_mod._configured = False


# ---------------------------------------------------------------------------
# configure_tracing
# ---------------------------------------------------------------------------


class TestConfigureTracing:
    """configure_tracing() behaves safely in disabled and idempotent cases."""

    def setup_method(self) -> None:
        _reset_tracer_module()

    def test_disabled_does_not_raise(self) -> None:
        configure_tracing(cast(Settings, _FakeSettings(tracing_enabled=False)))

    def test_disabled_marks_configured(self) -> None:
        configure_tracing(cast(Settings, _FakeSettings(tracing_enabled=False)))
        assert tracer_mod._configured is True

    def test_idempotent_second_call_is_noop(self) -> None:
        configure_tracing(cast(Settings, _FakeSettings(tracing_enabled=False)))
        # Second call must not raise even though _configured is True.
        configure_tracing(cast(Settings, _FakeSettings(tracing_enabled=False)))
        assert tracer_mod._configured is True

    def test_enabled_initialises_sdk_provider(self) -> None:
        """When enabled, configure_tracing() should install a TracerProvider.

        We test with a very short endpoint timeout so the batch processor
        errors quickly during teardown.  The test itself just verifies that
        a TracerProvider (not the default ProxyTracerProvider) is installed.
        """
        configure_tracing(
            cast(
                Settings,
                _FakeSettings(
                    tracing_enabled=True,
                    otlp_endpoint="http://localhost:4318",
                    otel_service_name="test-svc",
                    otel_sample_rate=1.0,
                ),
            )
        )
        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)
        # Restore no-op provider so other tests are not affected and the
        # batch-export background thread does not produce noise.
        provider.shutdown()
        trace.set_tracer_provider(trace.ProxyTracerProvider())
        _reset_tracer_module()


# ---------------------------------------------------------------------------
# get_tracer
# ---------------------------------------------------------------------------


class TestGetTracer:
    """get_tracer() returns a usable Tracer regardless of SDK state."""

    def test_returns_tracer_object(self) -> None:
        t = get_tracer(__name__)
        assert t is not None
        assert hasattr(t, "start_as_current_span")

    def test_tracer_start_span_does_not_raise(self) -> None:
        t = get_tracer("test_scope")
        with t.start_as_current_span("test.span"):
            pass  # No error expected


# ---------------------------------------------------------------------------
# inject_otel_context_into_structlog
# ---------------------------------------------------------------------------


class TestInjectOtelContextIntoStructlog:
    """The structlog processor bridges OTel span context into log records."""

    def test_no_active_span_leaves_event_dict_unchanged(self) -> None:
        # With only the no-op provider, no valid span is active.
        event: dict[str, object] = {"event": "something"}
        result = inject_otel_context_into_structlog(None, "info", event)
        assert "otel_trace_id" not in result
        assert "otel_span_id" not in result

    def test_active_recording_span_injects_ids(self) -> None:
        """With a real SDK TracerProvider, span IDs should appear in the dict."""
        provider = TracerProvider()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test.span"):
            event: dict[str, object] = {"event": "check_ids"}
            result = inject_otel_context_into_structlog(None, "debug", event)
            assert "otel_trace_id" in result
            assert "otel_span_id" in result
            assert isinstance(result["otel_trace_id"], str)
            assert len(result["otel_trace_id"]) == 32  # 128-bit trace ID as hex
            assert isinstance(result["otel_span_id"], str)
            assert len(result["otel_span_id"]) == 16  # 64-bit span ID as hex

    def test_active_recording_span_ids_are_hex_strings(self) -> None:
        provider = TracerProvider()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test.hex"):
            event: dict[str, object] = {}
            result = inject_otel_context_into_structlog(None, "info", event)
            if "otel_trace_id" in result:
                int(str(result["otel_trace_id"]), 16)  # must be valid hex


# ---------------------------------------------------------------------------
# span_attributes constants
# ---------------------------------------------------------------------------


class TestSpanAttributeConstants:
    """Span attribute constants are non-empty dot-separated strings."""

    _CONSTANTS = [
        span_attributes.REQUEST_ID,
        span_attributes.SESSION_ID,
        span_attributes.PIPELINE_RUN_ID,
        span_attributes.COUNTRY,
        span_attributes.INDICATOR_COUNT,
        span_attributes.FEATURES_COUNT,
        span_attributes.SNAPSHOT_ID,
        span_attributes.SOURCE_ID,
        span_attributes.MCP_TOOL,
        span_attributes.AGENT_OPERATION,
        span_attributes.SIGNAL_COUNT,
        span_attributes.ENGINE_RUN_ID,
        span_attributes.RESULT_SUCCESS,
        span_attributes.ERROR_TYPE,
    ]

    def test_all_constants_are_non_empty_strings(self) -> None:
        for const in self._CONSTANTS:
            assert isinstance(const, str), f"Expected str, got {type(const)} for {const!r}"
            assert const, "Constant must not be empty"

    def test_all_constants_contain_a_dot(self) -> None:
        for const in self._CONSTANTS:
            assert "." in const, f"Constant {const!r} should be dot-separated"
