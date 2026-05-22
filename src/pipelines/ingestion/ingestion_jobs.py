"""Ingestion job definitions for Phase 1 macro data foundation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.macro.enums import DataFrequency, MacroIndicatorType
from pipelines.ingestion.indicator_catalog import PRIORITY_INDICATORS


class IngestionJob(BaseModel, extra="forbid"):
    """A scheduled ingestion job over a set of indicators."""

    job_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    frequency: DataFrequency
    indicators: list[MacroIndicatorType] = Field(default_factory=list)
    country: str = Field(default="US", min_length=2)


PHASE1_INGESTION_JOBS: tuple[IngestionJob, ...] = (
    IngestionJob(
        job_id="macro-daily-rates",
        description="Collect daily rates proxy for freshness",
        frequency=DataFrequency.DAILY,
        indicators=[MacroIndicatorType.YIELD_10Y],
    ),
    IngestionJob(
        job_id="macro-monthly-core",
        description="Collect monthly macro starter set",
        frequency=DataFrequency.MONTHLY,
        indicators=[i for i in PRIORITY_INDICATORS if i != MacroIndicatorType.YIELD_10Y],
    ),
)
