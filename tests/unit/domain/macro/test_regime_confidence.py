"""Tests for regime confidence and degraded-input handling rules."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.domain.macro.regime import RegimeConfidence, RegimeLabel
from src.domain.macro.regime_mapping import derive_regime_confidence, derive_regime_missing_inputs
from src.domain.macro.snapshot import (
    DegradedStatus,
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    MacroSnapshotState,
    PolicyState,
)
from src.pipelines.ingestion.models import FreshnessStatus


def _snapshot(
    *,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
    growth: GrowthState = GrowthState.ACCELERATING,
    inflation: InflationState = InflationState.COOLING,
    labor: LaborState = LaborState.TIGHT,
    policy: PolicyState = PolicyState.NEUTRAL,
    conditions: FinancialConditionsState = FinancialConditionsState.NEUTRAL,
    missing: list[str] | None = None,
) -> MacroSnapshotState:
    return MacroSnapshotState(
        as_of_date=date(2026, 2, 1),
        snapshot_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        freshness_status=freshness,
        degraded_status=degraded,
        growth_state=growth,
        inflation_state=inflation,
        labor_state=labor,
        policy_state=policy,
        financial_conditions_state=conditions,
        missing_indicators=missing or [],
    )


class TestRegimeConfidence:
    def test_high_when_fresh_complete_and_specific_label(self) -> None:
        snap = _snapshot()
        assert (
            derive_regime_confidence(snapshot=snap, label=RegimeLabel.GOLDILOCKS)
            == RegimeConfidence.HIGH
        )

    def test_partial_or_late_downgrades_to_medium(self) -> None:
        partial = _snapshot(degraded=DegradedStatus.PARTIAL)
        late = _snapshot(freshness=FreshnessStatus.LATE)
        assert (
            derive_regime_confidence(snapshot=partial, label=RegimeLabel.DISINFLATION)
            == RegimeConfidence.MEDIUM
        )
        assert (
            derive_regime_confidence(snapshot=late, label=RegimeLabel.DISINFLATION)
            == RegimeConfidence.MEDIUM
        )

    def test_missing_or_stale_or_unclear_downgrades_to_low(self) -> None:
        missing = _snapshot(degraded=DegradedStatus.MISSING)
        stale = _snapshot(freshness=FreshnessStatus.STALE)
        assert (
            derive_regime_confidence(snapshot=missing, label=RegimeLabel.CONTRACTION)
            == RegimeConfidence.LOW
        )
        assert (
            derive_regime_confidence(snapshot=stale, label=RegimeLabel.CONTRACTION)
            == RegimeConfidence.LOW
        )
        assert (
            derive_regime_confidence(snapshot=_snapshot(), label=RegimeLabel.UNCLEAR)
            == RegimeConfidence.LOW
        )

    def test_missing_inputs_forwarded_from_snapshot(self) -> None:
        snap = _snapshot(missing=["inflation", "pmi"])
        assert derive_regime_missing_inputs(snap) == ["inflation", "pmi"]
