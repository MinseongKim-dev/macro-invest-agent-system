"""Base MCP request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core.exceptions.failure_category import FailureCategory


class MCPRequest(BaseModel):
    """Base class for all MCP requests.

    MCP (Model Context Protocol) requests contain the input parameters
    and metadata for operations on macro data and signals.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "req-12345",
                "timestamp": "2026-04-11T12:00:00Z",
            }
        }
    )

    request_id: str = Field(..., description="Unique request identifier for tracing")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Request creation timestamp",
    )


class MCPResponse(BaseModel, extra="forbid"):
    """Base class for all MCP responses.

    MCP responses contain the result data and metadata for completed operations.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "req-12345",
                "timestamp": "2026-04-11T12:00:00Z",
                "success": True,
                "error_message": None,
                "failure_category": None,
                "is_degraded": False,
            }
        }
    )

    request_id: str = Field(..., description="Echo of the request ID that triggered this response")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response creation timestamp",
    )
    success: bool = Field(default=True, description="Whether the operation succeeded")
    error_message: str | None = Field(
        default=None,
        description="Error message if success is False",
    )
    failure_category: FailureCategory | None = Field(
        default=None,
        description=(
            "Machine-readable failure category when success=False or is_degraded=True. "
            "None when success=True and data is fresh."
        ),
    )
    is_degraded: bool = Field(
        default=False,
        description=(
            "True when the response is schema-valid but data is partial or stale. "
            "success may still be True for partial data (degraded but usable)."
        ),
    )
