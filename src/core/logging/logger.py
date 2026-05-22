"""Structured logger factory for the macro-invest-agent-platform.

Provides a single :func:`get_logger` factory that returns a
:mod:`structlog` logger pre-configured for the current environment:

- **Local / pretty mode**: human-readable, colourised console output.
- **JSON mode**: one-line JSON records suitable for log aggregators.

Every log record includes ``trace_id`` and ``session_id`` fields so that
requests can be correlated across the domain, MCP, and agent layers.

When the OpenTelemetry SDK is active, each record also carries
``otel_trace_id`` and ``otel_span_id`` so that logs can be correlated with
spans in any observability backend.

Usage::

    from core.logging.logger import get_logger, bind_request_context

    log = get_logger(__name__)

    # At the request entry-point:
    bind_request_context(request_id="req-001", trace_id="…", session_id="…")

    log.info("signal_computed", strategy="base-macro-v1", direction="BULLISH")
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, cast

import structlog
from structlog.types import FilteringBoundLogger

from core.config.settings import get_settings

# ---------------------------------------------------------------------------
# Trace-ID context variable
# ---------------------------------------------------------------------------

#: Thread/async-safe storage for the current request's trace identifier.
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

#: Thread/async-safe storage for the current session identifier.
_session_id_var: ContextVar[str] = ContextVar("session_id", default="")


def set_trace_id(trace_id: str | None = None) -> str:
    """Set the trace ID for the current execution context.

    If *trace_id* is ``None`` or empty a new UUID4 is generated.
    Returns the trace ID that was set.
    """
    tid = trace_id or str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """Return the trace ID for the current execution context, or an empty string."""
    return _trace_id_var.get()


def set_session_id(session_id: str | None = None) -> str:
    """Set the session ID for the current execution context.

    If *session_id* is ``None`` or empty the context variable is cleared
    (set to empty string).  Returns the value that was set.
    """
    sid = session_id or ""
    _session_id_var.set(sid)
    return sid


def get_session_id() -> str:
    """Return the session ID for the current execution context, or an empty string."""
    return _session_id_var.get()


def bind_request_context(
    request_id: str,
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Bind request-level identifiers to the current execution context.

    Sets the trace ID and session ID context variables and also binds
    ``trace_id``, ``request_id``, and (when non-empty) ``session_id`` into
    the structlog context-vars so they appear on every subsequent log record
    in the same async task.

    Args:
        request_id: Unique identifier for the current request.
        trace_id: Optional trace ID.  A new UUID4 is generated when
            ``None`` or empty.
        session_id: Optional session ID.  Omitted from structlog context
            when ``None`` or empty.

    Returns:
        The trace ID that was set (generated or provided).
    """
    tid = set_trace_id(trace_id)
    sid = set_session_id(session_id)

    ctx: dict[str, str] = {"trace_id": tid, "request_id": request_id}
    if sid:
        ctx["session_id"] = sid

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**ctx)
    return tid


# ---------------------------------------------------------------------------
# Structlog processors that inject context variables into every log record
# ---------------------------------------------------------------------------


def _inject_trace_id(
    logger: Any,  # noqa: ANN401
    method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Structlog processor: add ``trace_id`` from the current context var."""
    tid = get_trace_id()
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def _inject_session_id(
    logger: Any,  # noqa: ANN401
    method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Structlog processor: add ``session_id`` from the current context var."""
    sid = get_session_id()
    if sid:
        event_dict["session_id"] = sid
    return event_dict


def _inject_otel_ids(
    logger: Any,  # noqa: ANN401
    method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Structlog processor: add OTel trace/span IDs when a recording span is active.

    Delegates to :func:`~core.tracing.tracer.inject_otel_context_into_structlog`
    which is kept in the tracing module to avoid a circular import.  When the
    OTel SDK is not active the call is a cheap no-op.
    """
    from core.tracing.tracer import inject_otel_context_into_structlog

    return inject_otel_context_into_structlog(logger, method, event_dict)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# One-time configuration (idempotent)
# ---------------------------------------------------------------------------

_configured = False


def _configure_structlog() -> None:
    """Configure structlog processors and output format.

    Called once per process.  Subsequent calls are no-ops.
    """
    global _configured  # noqa: PLW0603
    if _configured:
        return

    settings = get_settings()
    log_level = getattr(logging, settings.log_level.value, logging.INFO)

    # Configure stdlib logging as the backend
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_trace_id,
        _inject_session_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _inject_otel_ids,
    ]

    if settings.log_pretty:
        # Human-readable output for local development
        processors: list[Any] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production / log aggregators
        processors = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def get_logger(name: str) -> FilteringBoundLogger:
    """Return a configured structlog logger bound to *name*.

    Call once per module::

        log = get_logger(__name__)

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog ``BoundLogger`` ready to use.
    """
    _configure_structlog()
    return cast(FilteringBoundLogger, structlog.get_logger(name))
