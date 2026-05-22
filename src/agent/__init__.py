"""Read-only agent layer for macro signal review and snapshot summarisation.

This package provides a thin, deterministic agent service that orchestrates
existing MCP tool calls to produce schema-validated summaries.

Public API
----------
* :class:`~agent.service.AgentService` — main entry point.
* :mod:`agent.schemas` — typed request/response models.
* :mod:`agent.mcp_adapter` — MCP tool invocation with error normalisation.

Constraints
-----------
* The agent layer is **read-only**.  It queries data; it never mutates state.
* Outputs are **deterministic** — no LLM calls, no randomness.
* The agent layer does not bypass the MCP boundary.
  All data access goes through the MCP adapter → MCP tool → service chain.
"""
