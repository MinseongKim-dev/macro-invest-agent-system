"""Historical read models for macro regime and snapshot data.

These models provide first-class historical read paths so the platform can
retrieve prior regimes and snapshots in a structured, reusable way.

Design principles
-----------------
* **Explicit metadata**: every historical record carries ``as_of_date``,
  ``generated_at``, freshness, confidence, and degraded status so downstream
  compare/trend surfaces can render context without re-deriving it.
* **Read-only**: these are read models, not write models.  They are built
  from persisted :class:`~domain.macro.regime.MacroRegime` objects.
* **Reusable**: the same records power the history list, compare view,
  and future alerting / monitoring layers.
* **Semantics**: a historical record is not the same as a degraded state
  or a mixed/conflicted state.  It is simply a prior observation with its
  own quality metadata intact.

Retrieval semantics
-------------------
``HistoricalRegimeRecord``
    A flattened read model of a persisted regime.  Carries the minimum
    metadata required to render a compare/trend view or support change
    detection without loading the full domain object.

``RegimeHistoryBundle``
    An ordered list of historical records for a given ``as_of_date``,
    bounded by ``limit``.  Ordered by ``as_of_date`` descending (most
    recent first).  Includes a ``latest`` pointer to the most recent record
    and a ``previous`` pointer to the one before it.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.macro.regime import MacroRegime


class HistoricalRegimeRecord(BaseModel, extra="forbid"):
    """Flattened read model for a single persisted regime.

    Carries the metadata required for compare/trend surfaces without exposing
    full domain internals.

    Attributes:
        regime_id: Unique regime identifier.
        as_of_date: The date this regime was built for.
        generated_at: When this regime was created (``regime_timestamp``).
        regime_label: Regime label value (e.g. ``"goldilocks"``).
        regime_family: Regime family value (e.g. ``"expansion"``).
        confidence: Confidence level (``"high"`` / ``"medium"`` / ``"low"``).
        freshness_status: Freshness of the underlying snapshot data.
        degraded_status: Snapshot quality state.
        transition_type: How this regime relates to the prior one.
        transition_from_prior: Prior regime label, or ``None`` for the
            initial regime.
        changed: ``True`` when the regime label or confidence changed from
            the prior.
        warnings: Pre-computed analyst-facing warnings at the time of creation.
        is_seeded: ``True`` for bootstrap/synthetic regimes.
        missing_inputs: Indicators missing when this regime was built.
        supporting_snapshot_id: ID of the snapshot that grounded this regime.
    """

    regime_id: str = Field(..., description="Unique regime identifier")
    as_of_date: date = Field(..., description="Date this regime was built for")
    generated_at: datetime = Field(..., description="When this regime was created")
    regime_label: str = Field(..., description="Regime label value")
    regime_family: str = Field(..., description="Regime family value")
    confidence: str = Field(..., description="Confidence level: high / medium / low")
    freshness_status: str = Field(..., description="Freshness of the underlying snapshot data")
    degraded_status: str = Field(..., description="Snapshot quality state")
    transition_type: str = Field(..., description="Transition type vs prior regime")
    transition_from_prior: str | None = Field(
        default=None,
        description="Prior regime label; None for initial regimes",
    )
    changed: bool = Field(
        default=False,
        description="True when the regime label or confidence changed from the prior",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Analyst-facing warnings at creation time",
    )
    is_seeded: bool = Field(
        default=False,
        description="True for bootstrap/synthetic seed regimes",
    )
    missing_inputs: list[str] = Field(
        default_factory=list,
        description="Indicators that were missing when this regime was built",
    )
    supporting_snapshot_id: str = Field(
        default="",
        description="ID of the snapshot that grounded this regime",
    )


def regime_to_historical_record(regime: MacroRegime) -> HistoricalRegimeRecord:
    """Build a :class:`HistoricalRegimeRecord` from a domain :class:`MacroRegime`.

    Args:
        regime: The :class:`~domain.macro.regime.MacroRegime` to flatten.

    Returns:
        A :class:`HistoricalRegimeRecord` read model.
    """
    return HistoricalRegimeRecord(
        regime_id=regime.regime_id,
        as_of_date=regime.as_of_date,
        generated_at=regime.regime_timestamp,
        regime_label=regime.regime_label.value,
        regime_family=regime.regime_family.value,
        confidence=regime.confidence.value,
        freshness_status=regime.freshness_status.value,
        degraded_status=regime.degraded_status.value,
        transition_type=regime.transition.transition_type.value,
        transition_from_prior=regime.transition.transition_from_prior,
        changed=regime.transition.changed,
        warnings=list(regime.warnings),
        is_seeded=regime.metadata.get("seeded") == "true",
        missing_inputs=list(regime.missing_inputs),
        supporting_snapshot_id=regime.supporting_snapshot_id,
    )


class RegimeHistoryBundle(BaseModel, extra="forbid"):
    """Ordered history of regime records for a given as-of date.

    Attributes:
        as_of_date: The reference date the history was retrieved for.
        records: Ordered list of historical records, most recent first.
        total: Total number of records in this bundle (≤ the requested limit).
        latest: The most recent record; ``None`` when the store is empty.
        previous: The second-most-recent record; ``None`` when fewer than
            two records are available.  Used by compare/change logic.
    """

    as_of_date: date = Field(..., description="Reference date the history was retrieved for")
    records: list[HistoricalRegimeRecord] = Field(
        default_factory=list,
        description="Historical records, most recent first",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Number of records in this bundle",
    )
    latest: HistoricalRegimeRecord | None = Field(
        default=None,
        description="Most recent record; None when store is empty",
    )
    previous: HistoricalRegimeRecord | None = Field(
        default=None,
        description="Second-most-recent record; None when fewer than two records exist",
    )


def build_regime_history_bundle(
    regimes: list[MacroRegime],
    as_of_date: date,
) -> RegimeHistoryBundle:
    """Build a :class:`RegimeHistoryBundle` from a list of domain regimes.

    The list is expected to be ordered most-recent first (by ``as_of_date``).
    The caller is responsible for pre-filtering by date and applying the
    desired limit before calling this function.

    Args:
        regimes: List of :class:`~domain.macro.regime.MacroRegime` objects,
            most recent first.
        as_of_date: The reference date for this bundle.

    Returns:
        A :class:`RegimeHistoryBundle` with flattened records.
    """
    records = [regime_to_historical_record(r) for r in regimes]
    _min_for_previous = 2
    latest = records[0] if records else None
    previous = records[1] if len(records) >= _min_for_previous else None
    return RegimeHistoryBundle(
        as_of_date=as_of_date,
        records=records,
        total=len(records),
        latest=latest,
        previous=previous,
    )
