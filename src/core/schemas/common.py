"""Shared Pydantic schemas used across all application layers.

These base models standardise the shapes of API responses, error payloads,
freshness metadata, and audit metadata so that every domain boundary speaks
the same vocabulary.

Design rules:
- Models are immutable by default (``frozen=True`` where appropriate).
- Every model uses ``model_config = ConfigDict(...)`` for explicit settings.
- No business logic lives in this module — only data shape definitions.
- All fields carry descriptions for self-documenting OpenAPI output.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Generic type parameter for paginated / wrapped responses
# ---------------------------------------------------------------------------

DataT = TypeVar("DataT")


# ---------------------------------------------------------------------------
# Freshness metadata
# ---------------------------------------------------------------------------


class FreshnessMetadata(BaseModel):
    """Describes how recent a piece of data is.

    Attached to any response that wraps cached or pre-computed data to allow
    consumers to decide whether the data is stale.
    """

    model_config = ConfigDict(frozen=True)

    computed_at: datetime = Field(
        ...,
        description="UTC timestamp when this data was last computed or fetched.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="UTC timestamp after which this data should be considered stale. "
        "``None`` means the data does not expire.",
    )
    is_stale: bool = Field(
        default=False,
        description="True if ``expires_at`` is in the past at the time of serialisation.",
    )

    @classmethod
    def now(cls, expires_at: datetime | None = None) -> FreshnessMetadata:
        """Construct a :class:`FreshnessMetadata` stamped with the current UTC time.

        Args:
            expires_at: Optional expiry timestamp (UTC).

        Returns:
            A new :class:`FreshnessMetadata` instance.
        """
        now_utc = datetime.now(tz=UTC)
        stale = expires_at is not None and now_utc >= expires_at
        return cls(computed_at=now_utc, expires_at=expires_at, is_stale=stale)


# ---------------------------------------------------------------------------
# Audit metadata
# ---------------------------------------------------------------------------


class AuditMetadata(BaseModel):
    """Lightweight audit trail attached to created or updated records.

    Not a replacement for a full audit log — use a dedicated audit table for
    compliance-grade event sourcing.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the request that produced this record.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Distributed trace identifier, if available.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp when this record was created.",
    )

    @classmethod
    def new(cls, trace_id: str | None = None) -> AuditMetadata:
        """Create a fresh :class:`AuditMetadata` instance.

        Args:
            trace_id: Optional trace identifier from the current context.

        Returns:
            A new :class:`AuditMetadata` instance.
        """
        return cls(trace_id=trace_id)


# ---------------------------------------------------------------------------
# Error response
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Structured error payload returned to API consumers on failure.

    Maps directly to the JSON body of 4xx and 5xx HTTP responses.
    """

    model_config = ConfigDict(frozen=True)

    error_code: str = Field(
        ...,
        description="Machine-readable error identifier, e.g. ``NOT_FOUND``.",
        examples=["VALIDATION_ERROR", "NOT_FOUND", "INTERNAL_ERROR"],
    )
    message: str = Field(
        ...,
        description="Human-readable description of the error.",
    )
    detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured context for debugging. Must not contain secrets.",
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the failed request.",
    )

    @classmethod
    def from_app_error(cls, exc: Exception, request_id: str | None = None) -> ErrorDetail:
        """Construct an :class:`ErrorDetail` from an :class:`~core.exceptions.base.AppError`.

        Falls back to generic values for non-AppError exceptions to avoid
        leaking internal implementation details.

        Args:
            exc: The exception to convert.
            request_id: Optional request identifier to include.

        Returns:
            A new :class:`ErrorDetail` instance.
        """
        # Import here to avoid a circular dependency at module load time.
        from core.exceptions.base import AppError  # noqa: PLC0415

        if isinstance(exc, AppError):
            return cls(
                error_code=exc.error_code,
                message=exc.message,
                detail=exc.detail,
                request_id=request_id or str(uuid.uuid4()),
            )
        return cls(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            request_id=request_id or str(uuid.uuid4()),
        )


# ---------------------------------------------------------------------------
# Base response wrapper
# ---------------------------------------------------------------------------


class BaseResponse[T](BaseModel):
    """Generic response envelope used by all API endpoints.

    Wraps a typed ``data`` payload with a ``success`` flag and optional
    ``audit`` metadata so that callers can always expect a consistent shape.

    Example::

        response = BaseResponse[SignalResult](
            data=signal_result,
            audit=AuditMetadata.new(trace_id="abc-123"),
        )
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(default=True, description="True when the request succeeded.")
    data: T = Field(..., description="The response payload.")
    audit: AuditMetadata | None = Field(
        default=None,
        description="Optional audit metadata for tracing and debugging.",
    )
