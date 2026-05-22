"""OpenTelemetry tracing utilities for the macro-invest-agent-platform.

Public API
----------
* :func:`get_tracer` — return a named OTel :class:`opentelemetry.trace.Tracer`.
* :func:`configure_tracing` — initialise the SDK once at application startup.
* :mod:`span_attributes` — canonical span attribute name constants.
"""

from core.tracing.tracer import configure_tracing, get_tracer

__all__ = ["configure_tracing", "get_tracer"]
