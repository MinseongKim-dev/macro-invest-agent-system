"""MCP schemas for macro data retrieval."""

from datetime import datetime

from pydantic import Field

from mcp.schemas.common import MCPRequest, MCPResponse


class GetMacroFeaturesRequest(MCPRequest):
    """Request to fetch specific macro features.

    Used to retrieve specific indicators from the macro data system.
    """

    indicator_types: list[str] = Field(..., description="List of macro indicator types to fetch")
    country: str = Field(default="US", description="Country code (ISO 3166-1 alpha-2)")


class GetMacroFeaturesResponse(MCPResponse):
    """Response with fetched macro features.

    Contains the requested macro indicators.
    """

    features_count: int = Field(default=0, description="Number of features returned")
    # Note: actual feature data would be serialized via model_dump()
    # This response is a schema; implementation would populate features


class GetMacroSnapshotRequest(MCPRequest):
    """Request to get a complete macro snapshot.

    Retrieves all available macro indicators at a point in time.
    """

    country: str = Field(default="US", description="Country code (ISO 3166-1 alpha-2)")


class GetMacroSnapshotResponse(MCPResponse):
    """Response with a complete macro snapshot.

    Contains all available macro features at the requested time.
    """

    snapshot_timestamp: datetime | None = Field(
        default=None,
        description="Time of the macro snapshot; None on error",
    )
    features_count: int = Field(default=0, description="Number of features in snapshot")
    # Note: actual snapshot data would be nested; implementation would populate
