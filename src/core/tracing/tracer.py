"""OpenTelemetry tracer factory and SDK configuration.

Design principles
-----------------
* **Safe by default**: when tracing is disabled (``TRACING_ENABLED=false``, the
  default), the OTel *no-op* tracer is used.  All ``start_as_current_span``
  calls are zero-overhead no-ops and the SDK is never initialised.
* **Explicit configuration**: the SDK is initialised only when
  :func:`configure_tracing` is called at application startup.  Modules that
  just call :func:`get_tracer` always get a working tracer without importing
  SDK internals.
* **No secret leakage**: attribute helpers in :mod:`core.tracing.span_attributes`
  define the safe set of span attributes.  Raw payloads, API keys, and
  exception messages must **never** appear as span attributes.
* **Context bridging**: :func:`inject_otel_context_into_structlog` reads the
  current OTel span context and injects ``otel_trace_id`` / ``otel_span_id``
  into structlog so that logs and traces can be correlated in any backend.

Usage
-----
Application startup (e.g. ``apps/api/main.py`` or ``apps/cli/main.py``)::

    from core.tracing.tracer import configure_tracing
    configure_tracing()  # reads Settings automatically

Any module::

    from core.tracing.tracer import get_tracer

    _tracer = get_tracer(__name__)

    async def my_fn() -> None:
        with _tracer.start_as_current_span("my.operation") as span:
            span.set_attribute("country", "US")
            ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, Tracer

if TYPE_CHECKING:
    from core.config.settings import Settings

_log = logging.getLogger(__name__)

# Module-level tracer registry — one tracer per instrumentation scope name.
# Tracers are lightweight proxies; creating many is fine.
_INSTRUMENTATION_SCOPE = "macro-invest-agent-platform"

_configured = False


def get_tracer(name: str) -> Tracer:
    """Return an OTel :class:`~opentelemetry.trace.Tracer` for *name*.

    Safe to call before :func:`configure_tracing` — returns the no-op tracer
    until the SDK has been initialised.

    Args:
        name: Instrumentation scope name (typically ``__name__`` of the
            calling module).

    Returns:
        A :class:`~opentelemetry.trace.Tracer` instance.
    """
    return trace.get_tracer(name, schema_url="https://opentelemetry.io/schemas/1.21.0")


def configure_tracing(settings: Settings | None = None) -> None:
    """Initialise the OpenTelemetry SDK if tracing is enabled.

    Reads configuration from *settings* (or calls
    :func:`~core.config.settings.get_settings` when ``None``).  The function
    is idempotent — subsequent calls after the first are no-ops.

    When ``settings.tracing_enabled`` is ``False`` (the default), this
    function returns immediately without touching the OTel SDK.  The no-op
    global tracer provider is used automatically, so spans created via
    :func:`get_tracer` cost essentially nothing.

    When tracing is enabled the function configures:

    * ``BatchSpanProcessor`` → ``OTLPSpanExporter`` sending to
      ``settings.otlp_endpoint``
    * ``TraceIdRatioBased`` sampler at ``settings.otel_sample_rate``
    * ``service.name``, ``service.version``, and ``deployment.environment``
      resource attributes

    Args:
        settings: Application settings.  Loaded from environment when ``None``.
    """
    global _configured  # noqa: PLW0603

    if _configured:
        return

    if settings is None:
        from core.config.settings import get_settings

        settings = get_settings()

    if not settings.tracing_enabled:
        _configured = True
        return

    # Lazy imports — only needed when SDK is actually in use.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.app_env.value,
        }
    )

    sampler = ParentBased(root=TraceIdRatioBased(rate=settings.otel_sample_rate))
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _log.info(
        "OpenTelemetry tracing configured: service=%s endpoint=%s sample_rate=%.2f",
        settings.otel_service_name,
        settings.otlp_endpoint,
        settings.otel_sample_rate,
    )
    _configured = True


def current_span() -> Span:
    """Return the currently active OTel span (may be a :class:`~opentelemetry.trace.NonRecordingSpan`)."""
    return trace.get_current_span()


def inject_otel_context_into_structlog(
    _logger: object,
    _method: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Structlog processor: add OTel trace/span IDs to every log record.

    When a recording span is active the processor adds:

    * ``otel_trace_id`` — 32-hex-character trace ID
    * ``otel_span_id`` — 16-hex-character span ID

    When no span is active (or the span is non-recording) the fields are
    omitted so logs remain clean in non-traced contexts.

    This bridges OpenTelemetry traces and structured logs so that log records
    can be correlated with spans in any observability backend.

    Args:
        _logger: Unused structlog parameter.
        _method: Unused structlog parameter.
        event_dict: The log record being assembled.

    Returns:
        The *event_dict* — possibly augmented with OTel IDs.
    """
    span = current_span()
    ctx = span.get_span_context()
    if ctx is not None and ctx.is_valid and not isinstance(span, NonRecordingSpan):
        event_dict["otel_trace_id"] = format(ctx.trace_id, "032x")
        event_dict["otel_span_id"] = format(ctx.span_id, "016x")
    return event_dict
