"""LangChain tool wrappers for MCP adapter methods.

Each function in this module creates a :class:`~langchain_core.tools.StructuredTool`
that delegates to the corresponding :class:`~agent.mcp_adapter.MCPAdapter` method.

The tools are **read-only** and honour the existing MCP boundary — they call
the adapter, which calls the MCP tool handler, which calls the service layer.
No business logic is added or bypassed.

These tools are intended for binding to a LangChain runtime so that a future
LLM-backed agent can select and invoke them.  In the current (Phase 2)
implementation, the runtime dispatches to them deterministically.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agent.mcp_adapter import MCPAdapter

# ---------------------------------------------------------------------------
# Tool input schemas
# ---------------------------------------------------------------------------


class RunSignalEngineInput(BaseModel):
    """Input schema for the ``run_signal_engine`` tool."""

    request_id: str = Field(..., description="Unique request identifier for tracing")
    signal_ids: list[str] = Field(
        ..., min_length=1, description="Signal definition IDs to evaluate"
    )
    country: str = Field(default="US", description="ISO 3166-1 alpha-2 country code")


class GetMacroSnapshotInput(BaseModel):
    """Input schema for the ``get_macro_snapshot`` tool."""

    request_id: str = Field(..., description="Unique request identifier for tracing")
    country: str = Field(default="US", description="ISO 3166-1 alpha-2 country code")


# ---------------------------------------------------------------------------
# Tool factories
# ---------------------------------------------------------------------------


def create_signal_engine_tool(adapter: MCPAdapter) -> StructuredTool:
    """Create a LangChain tool that wraps ``MCPAdapter.run_signal_engine``.

    The returned tool is read-only and raises :class:`~agent.mcp_adapter.MCPToolError`
    on MCP failures (matching the adapter contract).

    Args:
        adapter: The MCP adapter instance to delegate to.

    Returns:
        A :class:`~langchain_core.tools.StructuredTool` bound to the adapter.
    """

    async def _run(
        request_id: str,
        signal_ids: list[str],
        country: str = "US",
    ) -> dict[str, Any]:
        response = await adapter.run_signal_engine(
            request_id=request_id,
            signal_ids=signal_ids,
            country=country,
        )
        return response.model_dump()

    return StructuredTool.from_function(
        coroutine=_run,
        name="run_signal_engine",
        description=(
            "Run the deterministic signal engine against the current macro snapshot. "
            "Returns signal counts (BUY, SELL, HOLD), engine run ID, and execution time. "
            "Read-only — does not modify any state."
        ),
        args_schema=RunSignalEngineInput,
    )


def create_macro_snapshot_tool(adapter: MCPAdapter) -> StructuredTool:
    """Create a LangChain tool that wraps ``MCPAdapter.get_macro_snapshot``.

    The returned tool is read-only and raises :class:`~agent.mcp_adapter.MCPToolError`
    on MCP failures.

    Args:
        adapter: The MCP adapter instance to delegate to.

    Returns:
        A :class:`~langchain_core.tools.StructuredTool` bound to the adapter.
    """

    async def _run(
        request_id: str,
        country: str = "US",
    ) -> dict[str, Any]:
        response = await adapter.get_macro_snapshot(
            request_id=request_id,
            country=country,
        )
        return response.model_dump()

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_macro_snapshot",
        description=(
            "Fetch the current macro-economic snapshot for a given country. "
            "Returns feature count and snapshot timestamp. "
            "Read-only — does not modify any state."
        ),
        args_schema=GetMacroSnapshotInput,
    )
