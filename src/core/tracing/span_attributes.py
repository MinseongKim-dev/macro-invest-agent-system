"""Span attribute name constants for the macro-invest-agent-platform.

Centralising attribute names avoids typos and makes it easy to search for
attribute usage across the codebase.  Follow OpenTelemetry semantic convention
naming conventions (dot-separated, lowercase).

Never add secret values, API keys, or user-supplied free text as attributes.
"""

# ---- Request / correlation identifiers ----
REQUEST_ID = "request.id"
SESSION_ID = "session.id"
PIPELINE_RUN_ID = "pipeline.run_id"

# ---- Domain context ----
COUNTRY = "macro.country"
INDICATOR_COUNT = "macro.indicator_count"
FEATURES_COUNT = "macro.features_count"
SNAPSHOT_ID = "macro.snapshot_id"
SOURCE_ID = "macro.source_id"

# ---- MCP / agent ----
MCP_TOOL = "mcp.tool"
AGENT_OPERATION = "agent.operation"
SIGNAL_COUNT = "signal.count"
ENGINE_RUN_ID = "signal.engine_run_id"

# ---- Result ----
RESULT_SUCCESS = "result.success"
ERROR_TYPE = "error.type"
