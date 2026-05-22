"""MCP schemas for signal engine execution."""

from pydantic import Field

from mcp.schemas.common import MCPRequest, MCPResponse


class RunSignalEngineRequest(MCPRequest):
    """Request to run the signal engine.

    Triggers signal evaluation against current or provided macro data.
    """

    signal_ids: list[str] = Field(..., description="List of signal definition IDs to evaluate")
    country: str = Field(default="US", description="Country code for macro data")
    use_latest_snapshot: bool = Field(
        default=True,
        description="Whether to fetch latest macro data or use provided snapshot",
    )


class RunSignalEngineResponse(MCPResponse):
    """Response with signal engine execution results.

    Contains all generated signals and evaluation metadata.
    """

    engine_run_id: str = Field(..., description="Unique ID for this engine execution")
    signals_generated: int = Field(default=0, description="Number of signals generated")
    buy_signals: int = Field(default=0, description="Count of buy signals")
    sell_signals: int = Field(default=0, description="Count of sell signals")
    hold_signals: int = Field(default=0, description="Count of hold signals")
    execution_time_ms: float = Field(
        default=0.0, description="Time taken to execute engine (milliseconds)"
    )
    # Note: actual signal data would be nested in implementation
