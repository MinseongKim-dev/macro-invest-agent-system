"""Unit tests for deterministic snapshot-to-regime mapping rules."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.domain.macro.regime import RegimeLabel
from src.domain.macro.regime_mapping import map_snapshot_to_regime_label
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
    growth: GrowthState,
    inflation: InflationState,
    labor: LaborState,
    policy: PolicyState,
    conditions: FinancialConditionsState,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
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
    )


class TestSnapshotToRegimeMapping:
    def test_maps_goldilocks(self) -> None:
        snap = _snapshot(
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.COOLING,
            labor=LaborState.TIGHT,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
        assert map_snapshot_to_regime_label(snap) == RegimeLabel.GOLDILOCKS

    def test_maps_contraction(self) -> None:
        snap = _snapshot(
            growth=GrowthState.SLOWING,
            inflation=InflationState.STICKY,
            labor=LaborState.WEAK,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
        )
        assert map_snapshot_to_regime_label(snap) == RegimeLabel.CONTRACTION

    def test_stale_or_missing_input_becomes_unclear(self) -> None:
        stale = _snapshot(
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.COOLING,
            labor=LaborState.TIGHT,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
            freshness=FreshnessStatus.STALE,
        )
        missing = _snapshot(
            growth=GrowthState.SLOWING,
            inflation=InflationState.REACCELERATING,
            labor=LaborState.WEAK,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
            degraded=DegradedStatus.MISSING,
        )
        assert map_snapshot_to_regime_label(stale) == RegimeLabel.UNCLEAR
        assert map_snapshot_to_regime_label(missing) == RegimeLabel.UNCLEAR

    def test_unknown_category_state_becomes_mixed(self) -> None:
        snap = _snapshot(
            growth=GrowthState.UNKNOWN,
            inflation=InflationState.COOLING,
            labor=LaborState.SOFTENING,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
        assert map_snapshot_to_regime_label(snap) == RegimeLabel.MIXED
