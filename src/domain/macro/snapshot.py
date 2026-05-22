"""Phase 2 macro snapshot contract, derivation rules, and comparison logic."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.macro.enums import MacroIndicatorType
from pipelines.ingestion.models import FreshnessStatus, NormalizedMacroObservation


class GrowthState(StrEnum):
    ACCELERATING = "accelerating"
    SLOWING = "slowing"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class InflationState(StrEnum):
    COOLING = "cooling"
    STICKY = "sticky"
    REACCELERATING = "reaccelerating"
    UNKNOWN = "unknown"


class LaborState(StrEnum):
    TIGHT = "tight"
    SOFTENING = "softening"
    WEAK = "weak"
    UNKNOWN = "unknown"


class PolicyState(StrEnum):
    RESTRICTIVE = "restrictive"
    NEUTRAL = "neutral"
    EASING_BIAS = "easing_bias"
    UNKNOWN = "unknown"


class FinancialConditionsState(StrEnum):
    TIGHT = "tight"
    NEUTRAL = "neutral"
    LOOSE = "loose"
    UNKNOWN = "unknown"


class DegradedStatus(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    MISSING = "missing"
    SOURCE_UNAVAILABLE = "source_unavailable"
    UNKNOWN = "unknown"


class SnapshotComparisonMetadata(BaseModel, extra="forbid"):
    baseline_available: bool = Field(default=False)
    previous_snapshot_id: str | None = Field(default=None)
    changed_category_states: list[str] = Field(default_factory=list)
    changed_indicators: list[str] = Field(default_factory=list)


class MacroSnapshotState(BaseModel, extra="forbid"):
    """Structured macro snapshot representation for a given as-of date."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    as_of_date: date
    snapshot_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_status: FreshnessStatus = Field(default=FreshnessStatus.UNKNOWN)
    degraded_status: DegradedStatus = Field(default=DegradedStatus.UNKNOWN)

    growth_state: GrowthState = Field(default=GrowthState.UNKNOWN)
    inflation_state: InflationState = Field(default=InflationState.UNKNOWN)
    labor_state: LaborState = Field(default=LaborState.UNKNOWN)
    policy_state: PolicyState = Field(default=PolicyState.UNKNOWN)
    financial_conditions_state: FinancialConditionsState = Field(
        default=FinancialConditionsState.UNKNOWN
    )

    key_indicator_changes: list[str] = Field(default_factory=list)
    missing_indicators: list[str] = Field(default_factory=list)
    source_summary: dict[str, int] = Field(default_factory=dict)
    indicator_values: dict[str, float] = Field(default_factory=dict)
    comparison: SnapshotComparisonMetadata = Field(default_factory=SnapshotComparisonMetadata)


def select_latest_observations(
    observations: list[NormalizedMacroObservation],
    as_of_date: date,
) -> dict[MacroIndicatorType, NormalizedMacroObservation]:
    """Select the latest observation per indicator up to a target as-of date."""
    selected: dict[MacroIndicatorType, NormalizedMacroObservation] = {}
    for obs in observations:
        if obs.observation_date.date() > as_of_date:
            continue
        existing = selected.get(obs.indicator_id)
        if existing is None or obs.observation_date > existing.observation_date:
            selected[obs.indicator_id] = obs
    return selected


def derive_growth_state(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> GrowthState:
    pmi = selected.get(MacroIndicatorType.PMI)
    retail = selected.get(MacroIndicatorType.RETAIL_SALES)
    if pmi is None or retail is None:
        return GrowthState.UNKNOWN
    if pmi.value is None or retail.value is None:
        return GrowthState.UNKNOWN
    if pmi.value >= 52.0 and retail.value >= 0.0:
        return GrowthState.ACCELERATING
    if pmi.value < 50.0:
        return GrowthState.SLOWING
    return GrowthState.MIXED


def derive_inflation_state(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> InflationState:
    cpi = selected.get(MacroIndicatorType.INFLATION)
    if cpi is None or cpi.value is None:
        return InflationState.UNKNOWN
    if cpi.value <= 2.5:
        return InflationState.COOLING
    if cpi.value <= 3.5:
        return InflationState.STICKY
    return InflationState.REACCELERATING


def derive_labor_state(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> LaborState:
    unemployment = selected.get(MacroIndicatorType.UNEMPLOYMENT)
    if unemployment is None or unemployment.value is None:
        return LaborState.UNKNOWN
    if unemployment.value < 4.0:
        return LaborState.TIGHT
    if unemployment.value <= 5.5:
        return LaborState.SOFTENING
    return LaborState.WEAK


def derive_policy_state(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> PolicyState:
    yield_10y = selected.get(MacroIndicatorType.YIELD_10Y)
    if yield_10y is None or yield_10y.value is None:
        return PolicyState.UNKNOWN
    if yield_10y.value >= 4.5:
        return PolicyState.RESTRICTIVE
    if yield_10y.value >= 3.0:
        return PolicyState.NEUTRAL
    return PolicyState.EASING_BIAS


def derive_financial_conditions_state(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> FinancialConditionsState:
    yield_10y = selected.get(MacroIndicatorType.YIELD_10Y)
    credit_spread = selected.get(MacroIndicatorType.CREDIT_SPREAD)

    if yield_10y is None or yield_10y.value is None:
        return FinancialConditionsState.UNKNOWN

    spread = credit_spread.value if credit_spread is not None else None
    if yield_10y.value >= 4.5 or (spread is not None and spread >= 2.0):
        return FinancialConditionsState.TIGHT
    if yield_10y.value < 3.0 and (spread is None or spread < 1.0):
        return FinancialConditionsState.LOOSE
    return FinancialConditionsState.NEUTRAL


def derive_freshness_status(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
) -> FreshnessStatus:
    if not selected:
        return FreshnessStatus.UNKNOWN
    states = {obs.freshness.status for obs in selected.values()}
    if FreshnessStatus.STALE in states:
        return FreshnessStatus.STALE
    if FreshnessStatus.LATE in states:
        return FreshnessStatus.LATE
    if FreshnessStatus.UNKNOWN in states:
        return FreshnessStatus.UNKNOWN
    return FreshnessStatus.FRESH


def derive_degraded_status(
    selected: dict[MacroIndicatorType, NormalizedMacroObservation],
    required_indicators: list[MacroIndicatorType],
) -> tuple[DegradedStatus, list[str]]:
    missing = [i.value for i in required_indicators if i not in selected]
    if not selected:
        return DegradedStatus.MISSING, [i.value for i in required_indicators]
    if missing:
        return DegradedStatus.PARTIAL, missing
    return DegradedStatus.NONE, []


def compare_snapshot_states(
    current: MacroSnapshotState,
    previous: MacroSnapshotState | None,
) -> SnapshotComparisonMetadata:
    """Compare current and previous snapshots by category state and indicator values."""
    if previous is None:
        return SnapshotComparisonMetadata(baseline_available=False, previous_snapshot_id=None)

    changed_categories: list[str] = []
    category_pairs = [
        ("growth_state", current.growth_state, previous.growth_state),
        ("inflation_state", current.inflation_state, previous.inflation_state),
        ("labor_state", current.labor_state, previous.labor_state),
        ("policy_state", current.policy_state, previous.policy_state),
        (
            "financial_conditions_state",
            current.financial_conditions_state,
            previous.financial_conditions_state,
        ),
    ]
    for name, curr, prev in category_pairs:
        if curr != prev:
            changed_categories.append(name)

    changed_indicators: list[str] = []
    for ind, curr_val in current.indicator_values.items():
        prev_val = previous.indicator_values.get(ind)
        if prev_val is None:
            changed_indicators.append(ind)
            continue
        if abs(curr_val - prev_val) > 1e-9:
            changed_indicators.append(ind)

    return SnapshotComparisonMetadata(
        baseline_available=True,
        previous_snapshot_id=previous.snapshot_id,
        changed_category_states=changed_categories,
        changed_indicators=changed_indicators,
    )
