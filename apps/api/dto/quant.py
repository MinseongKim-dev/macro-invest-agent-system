"""Quant Score DTOs for analyst-facing read API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class DimensionScoreDTO(BaseModel, extra="forbid"):
    dimension: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    level: str
    contributing_states: list[str] = Field(default_factory=list)


class QuantScoreLatestResponse(BaseModel, extra="forbid"):
    as_of_date: date
    regime_id: str
    regime_label: str
    growth: DimensionScoreDTO
    inflation: DimensionScoreDTO
    labor: DimensionScoreDTO
    policy: DimensionScoreDTO
    financial_conditions: DimensionScoreDTO
    momentum: float = Field(ge=0.0, le=1.0)
    breadth: float = Field(ge=0.0, le=1.0)
    change_intensity: float = Field(ge=0.0, le=1.0)
    overall_support: float = Field(ge=0.0, le=1.0)
    status: str = Field(
        default="success",
        description=(
            "Product-surface state inherited from the source regime. "
            "One of: 'success', 'degraded', 'stale', 'bootstrap'."
        ),
    )
