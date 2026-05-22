"""Ingestion pipeline models.

Defines the :class:`FeatureSnapshot` — the unit of data that the ingestion
service produces and the feature-store repository persists.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature


class FeatureSnapshot(BaseModel):
    """A persisted snapshot of macro features produced by an ingestion run.

    A :class:`FeatureSnapshot` represents the output of one ingestion cycle:
    the raw features fetched from a data source, attached to a unique ID,
    a reference country, and an ingestion timestamp.

    Attributes:
        snapshot_id: UUID4 string that uniquely identifies this snapshot.
        country: ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
        source_id: Identifier of the :class:`~core.contracts.macro_data_source.MacroDataSourceContract`
            that provided the raw data.
        ingested_at: UTC timestamp when this snapshot was created.
        features: Non-empty list of :class:`~domain.macro.models.MacroFeature`
            instances included in the snapshot.
        features_count: Derived count of features; always equals
            ``len(features)``.
    """

    snapshot_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 string uniquely identifying this snapshot",
    )
    country: str = Field(..., min_length=1, description="Country code (ISO 3166-1 alpha-2)")
    source_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the data source that provided these features",
    )
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when this snapshot was ingested",
    )
    features: list[MacroFeature] = Field(
        ...,
        min_length=1,
        description="Macro features included in this snapshot (must be non-empty)",
    )
    features_count: int = Field(
        default=0,
        ge=0,
        description="Number of features in this snapshot (derived from len(features))",
    )

    @field_validator("features")
    @classmethod
    def features_must_be_non_empty(cls, v: list[MacroFeature]) -> list[MacroFeature]:
        """Ensure the snapshot contains at least one feature."""
        if not v:
            raise ValueError("FeatureSnapshot must contain at least one feature")
        return v

    def model_post_init(self, __context: object) -> None:
        """Synchronise features_count with the actual features list length."""
        object.__setattr__(self, "features_count", len(self.features))


class FreshnessStatus(StrEnum):
    """Freshness state for a normalized macro observation."""

    FRESH = "fresh"
    LATE = "late"
    STALE = "stale"
    UNKNOWN = "unknown"


class RevisionStatus(StrEnum):
    """Revision stage of a normalized macro observation."""

    INITIAL = "initial"
    REVISED = "revised"
    FINAL = "final"
    UNKNOWN = "unknown"


class FreshnessMetadata(BaseModel, extra="forbid"):
    """Freshness metadata attached to normalized observations."""

    expected_max_lag_hours: int = Field(
        ..., ge=1, description="Expected lag threshold by frequency"
    )
    observed_lag_hours: float = Field(..., ge=0.0)
    status: FreshnessStatus = Field(default=FreshnessStatus.FRESH)
    is_late: bool = Field(default=False)
    is_stale: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_flags(self) -> FreshnessMetadata:
        if self.status == FreshnessStatus.LATE and not self.is_late:
            raise ValueError("is_late must be true when status is 'late'")
        if self.status == FreshnessStatus.STALE and not self.is_stale:
            raise ValueError("is_stale must be true when status is 'stale'")
        return self


class RawFeatureRecord(BaseModel, extra="forbid"):
    """Raw source payload persisted separately from normalized observations."""

    snapshot_id: str = Field(..., min_length=1)
    indicator_type: MacroIndicatorType
    source_id: str = Field(..., min_length=1)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_payload: dict[str, str] = Field(default_factory=dict, description="Raw source payload")


class NormalizedMacroObservation(BaseModel, extra="forbid"):
    """Normalized macro observation schema for Phase 1 ingestion foundation."""

    snapshot_id: str = Field(..., min_length=1)
    indicator_id: MacroIndicatorType
    observation_date: datetime
    fetched_at: datetime
    source: MacroSourceType
    value: float | None = Field(default=None)
    release_date: datetime
    unit: str = Field(default="index")
    frequency: DataFrequency
    source_series_id: str | None = Field(default=None)
    region: str = Field(default="US")
    freshness: FreshnessMetadata
    revision_status: RevisionStatus = Field(default=RevisionStatus.UNKNOWN)
    revision_number: int = Field(default=0, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> NormalizedMacroObservation:
        if self.observation_date > self.fetched_at:
            raise ValueError("observation_date cannot be later than fetched_at")
        if self.release_date > self.fetched_at:
            raise ValueError("release_date cannot be later than fetched_at")
        return self


class IngestionRunRecord(BaseModel, extra="forbid"):
    """Operational ingestion-run metadata for run tracking and audits."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    country: str = Field(..., min_length=1)
    started_at: datetime
    finished_at: datetime
    requested_indicators: list[str] = Field(default_factory=list)
    fetched_count: int = Field(default=0, ge=0)
    normalized_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    success: bool = Field(default=True)
    error_summary: str | None = Field(default=None)


def build_normalized_observation(
    *,
    snapshot_id: str,
    feature: MacroFeature,
    fetched_at: datetime | None = None,
    release_date: datetime | None = None,
    expected_max_lag_hours: int = 24 * 45,
    revision_status: RevisionStatus = RevisionStatus.UNKNOWN,
    revision_number: int = 0,
) -> NormalizedMacroObservation:
    """Build a normalized observation from a domain MacroFeature."""
    effective_fetched_at = fetched_at or datetime.now(UTC)
    effective_release_date = release_date or feature.timestamp

    lag_hours = max((effective_fetched_at - feature.timestamp).total_seconds() / 3600.0, 0.0)
    status = FreshnessStatus.FRESH
    is_late = lag_hours > float(expected_max_lag_hours)
    is_stale = lag_hours > float(expected_max_lag_hours * 2)
    if is_stale:
        status = FreshnessStatus.STALE
    elif is_late:
        status = FreshnessStatus.LATE

    freshness = FreshnessMetadata(
        expected_max_lag_hours=expected_max_lag_hours,
        observed_lag_hours=lag_hours,
        status=status,
        is_late=is_late,
        is_stale=is_stale,
    )

    return NormalizedMacroObservation(
        snapshot_id=snapshot_id,
        indicator_id=feature.indicator_type,
        observation_date=feature.timestamp,
        fetched_at=effective_fetched_at,
        source=feature.source,
        value=feature.value,
        release_date=effective_release_date,
        unit=str(feature.metadata.get("unit", "index")),
        frequency=feature.frequency,
        source_series_id=feature.metadata.get("series_id"),
        region=feature.country or "US",
        freshness=freshness,
        revision_status=revision_status,
        revision_number=revision_number,
        metadata={k: str(v) for k, v in feature.metadata.items()},
    )
