"""Prometheus metrics for the macro-invest-agent-platform.

Usage
-----
Application startup::

    from core.metrics import configure_metrics
    configure_metrics()  # reads Settings automatically

Any instrumented module::

    from core.metrics.registry import AGENT_REQUEST_DURATION, AGENT_REQUESTS_TOTAL
    # record observations via the metric objects directly
"""

from core.metrics.registry import (
    AGENT_REQUEST_DURATION,
    AGENT_REQUESTS_TOTAL,
    DEGRADED_RESPONSES_TOTAL,
    INGESTION_OBSERVATIONS_TOTAL,
    MCP_TOOL_CALLS_TOTAL,
    MCP_TOOL_DURATION,
    PIPELINE_RUN_DURATION,
    PIPELINE_RUNS_TOTAL,
    PROVIDER_FETCH_DURATION,
    PROVIDER_FETCH_TOTAL,
    SCHEMA_VALIDATION_FAILURES_TOTAL,
    SIGNAL_GENERATION_DURATION,
)

__all__ = [
    "AGENT_REQUEST_DURATION",
    "AGENT_REQUESTS_TOTAL",
    "DEGRADED_RESPONSES_TOTAL",
    "INGESTION_OBSERVATIONS_TOTAL",
    "MCP_TOOL_CALLS_TOTAL",
    "MCP_TOOL_DURATION",
    "PIPELINE_RUN_DURATION",
    "PIPELINE_RUNS_TOTAL",
    "PROVIDER_FETCH_DURATION",
    "PROVIDER_FETCH_TOTAL",
    "SCHEMA_VALIDATION_FAILURES_TOTAL",
    "SIGNAL_GENERATION_DURATION",
]
