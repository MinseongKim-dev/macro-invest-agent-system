"""Prometheus metric definitions for the macro-invest-agent-platform.

Design principles
-----------------
* **Actionable metrics only**: every metric here answers a concrete operational
  question (latency trend, failure rate, pipeline health).
* **Low label cardinality**: labels are bounded enumerable values such as
  operation names, provider IDs, or binary result flags — never per-request
  identifiers or free-form strings.
* **Stable names**: metric names follow the pattern
  ``<namespace>_<subsystem>_<name>_<unit>``.  The default namespace is
  ``macro_platform`` (overridable via ``Settings.metrics_namespace``).
* **No business logic**: this module only defines and exports metric objects.
  Instrumentation calls live in the application modules being measured.

Metric inventory
----------------
See ``docs/metrics.md`` for the full metric catalogue with meanings, labels,
and alert thresholds.
"""

from __future__ import annotations

import prometheus_client as prom

# ---------------------------------------------------------------------------
# Agent runtime metrics
# ---------------------------------------------------------------------------

AGENT_REQUESTS_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_agent_requests_total",
    documentation=(
        "Total number of agent invoke() calls, labelled by operation and result. "
        "Use to track request volume and success/failure rates per operation."
    ),
    labelnames=["operation", "result"],
)
"""Counter — agent request volume by operation and result (``success`` | ``failure``)."""

AGENT_REQUEST_DURATION: prom.Histogram = prom.Histogram(
    name="macro_platform_agent_request_duration_seconds",
    documentation=(
        "End-to-end agent invoke() wall-clock latency in seconds, "
        "labelled by operation.  Includes all downstream service and MCP calls."
    ),
    labelnames=["operation"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
"""Histogram — agent response latency per operation."""

SCHEMA_VALIDATION_FAILURES_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_schema_validation_failures_total",
    documentation=(
        "Total number of agent output schema validation failures, "
        "labelled by response_type.  Spikes indicate a regression in "
        "the deterministic formatter or a schema change."
    ),
    labelnames=["response_type"],
)
"""Counter — schema validation failures at the agent runtime boundary."""

DEGRADED_RESPONSES_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_degraded_responses_total",
    documentation=(
        "Total number of responses marked is_degraded=True or carrying "
        "partial/stale data warnings, labelled by operation. "
        "Sustained elevation indicates upstream data quality issues."
    ),
    labelnames=["operation"],
)
"""Counter — agent responses that completed in a degraded state."""

# ---------------------------------------------------------------------------
# MCP tool metrics
# ---------------------------------------------------------------------------

MCP_TOOL_CALLS_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_mcp_tool_calls_total",
    documentation=(
        "Total MCP tool invocations, labelled by tool name and result. "
        "Use to track individual tool failure rates and call volume."
    ),
    labelnames=["tool", "result"],
)
"""Counter — MCP tool call volume by tool and result (``success`` | ``failure``)."""

MCP_TOOL_DURATION: prom.Histogram = prom.Histogram(
    name="macro_platform_mcp_tool_duration_seconds",
    documentation=(
        "MCP tool invocation latency in seconds, labelled by tool name. "
        "Tracks latency trends for each individual tool."
    ),
    labelnames=["tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
"""Histogram — MCP tool call latency per tool."""

# ---------------------------------------------------------------------------
# Provider fetch metrics
# ---------------------------------------------------------------------------

PROVIDER_FETCH_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_provider_fetch_total",
    documentation=(
        "Total external provider fetch calls, labelled by provider and result. "
        "Repeated failures indicate a provider outage or misconfiguration."
    ),
    labelnames=["provider", "result"],
)
"""Counter — external provider fetch calls by provider and result."""

PROVIDER_FETCH_DURATION: prom.Histogram = prom.Histogram(
    name="macro_platform_provider_fetch_duration_seconds",
    documentation=(
        "External provider HTTP request latency in seconds, labelled by provider. "
        "Use to detect provider slowdowns and timeout threshold tuning."
    ),
    labelnames=["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
"""Histogram — provider fetch latency per provider."""

# ---------------------------------------------------------------------------
# Signal generation metrics
# ---------------------------------------------------------------------------

SIGNAL_GENERATION_DURATION: prom.Histogram = prom.Histogram(
    name="macro_platform_signal_generation_duration_seconds",
    documentation=(
        "Signal engine run() latency in seconds.  Tracks CPU cost of signal evaluation over time."
    ),
    labelnames=[],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)
"""Histogram — signal engine execution duration."""

# ---------------------------------------------------------------------------
# Ingestion pipeline metrics
# ---------------------------------------------------------------------------

PIPELINE_RUNS_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_pipeline_runs_total",
    documentation=(
        "Total ingestion pipeline runs, labelled by source and result. "
        "Use to monitor pipeline health and detect sustained failures."
    ),
    labelnames=["source", "result"],
)
"""Counter — ingestion pipeline runs by source and result."""

PIPELINE_RUN_DURATION: prom.Histogram = prom.Histogram(
    name="macro_platform_pipeline_run_duration_seconds",
    documentation=(
        "End-to-end ingestion pipeline latency in seconds, labelled by source. "
        "Tracks how long a full ingest cycle takes."
    ),
    labelnames=["source"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
"""Histogram — end-to-end pipeline run duration per source."""

INGESTION_OBSERVATIONS_TOTAL: prom.Counter = prom.Counter(
    name="macro_platform_ingestion_observations_total",
    documentation=(
        "Total number of ingestion-layer records processed, labelled by source and layer "
        "(raw|normalized). Useful for monitoring throughput and coverage."
    ),
    labelnames=["source", "layer"],
)
"""Counter — ingestion throughput for raw and normalized observation records."""
