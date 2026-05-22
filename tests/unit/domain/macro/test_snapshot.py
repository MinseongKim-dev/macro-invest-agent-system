"""Unit tests for Phase 2 snapshot derivation and comparison."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.snapshot import (
    DegradedStatus,
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    PolicyState,
    compare_snapshot_states,
    derive_degraded_status,
    derive_freshness_status,
    derive_growth_state,
    derive_inflation_state,
    derive_labor_state,
    derive_policy_state,
    select_latest_observations,
)
from src.pipelines.ingestion.models import (
    FreshnessMetadata,
    FreshnessStatus,
    NormalizedMacroObservation,
)


def _obs(
    indicator: MacroIndicatorType,
    value: float,
    observed_at: datetime,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
) -> NormalizedMacroObservation:
    return NormalizedMacroObservation(
        snapshot_id="snap-x",
        indicator_id=indicator,
        observation_date=observed_at,
        release_date=observed_at,
        fetched_at=observed_at + timedelta(hours=1),
        value=value,
        unit="index",
        frequency=DataFrequency.MONTHLY,
        source=MacroSourceType.FRED,
        source_series_id="X",
        region="US",
        freshness=FreshnessMetadata(
            expected_max_lag_hours=48,
            observed_lag_hours=1.0,
            status=freshness,
            is_late=freshness == FreshnessStatus.LATE,
            is_stale=freshness == FreshnessStatus.STALE,
        ),
    )


class TestSnapshotDerivation:
    def test_select_latest_observations_by_as_of(self) -> None:
        now = datetime(2026, 1, 10, tzinfo=UTC)
        older = _obs(MacroIndicatorType.PMI, 50.0, now - timedelta(days=10))
        newer = _obs(MacroIndicatorType.PMI, 53.0, now - timedelta(days=2))
        out_of_range = _obs(MacroIndicatorType.PMI, 60.0, now + timedelta(days=2))

        selected = select_latest_observations([older, newer, out_of_range], as_of_date=now.date())
        assert selected[MacroIndicatorType.PMI].value == 53.0

    def test_category_states(self) -> None:
        now = datetime(2026, 1, 10, tzinfo=UTC)
        selected = {
            MacroIndicatorType.PMI: _obs(MacroIndicatorType.PMI, 53.0, now),
            MacroIndicatorType.RETAIL_SALES: _obs(MacroIndicatorType.RETAIL_SALES, 700_000.0, now),
            MacroIndicatorType.INFLATION: _obs(MacroIndicatorType.INFLATION, 3.0, now),
            MacroIndicatorType.UNEMPLOYMENT: _obs(MacroIndicatorType.UNEMPLOYMENT, 3.8, now),
            MacroIndicatorType.YIELD_10Y: _obs(MacroIndicatorType.YIELD_10Y, 4.8, now),
        }
        assert derive_growth_state(selected) == GrowthState.ACCELERATING
        assert derive_inflation_state(selected) == InflationState.STICKY
        assert derive_labor_state(selected) == LaborState.TIGHT
        assert derive_policy_state(selected) == PolicyState.RESTRICTIVE

    def test_freshness_and_degraded(self) -> None:
        now = datetime(2026, 1, 10, tzinfo=UTC)
        selected = {
            MacroIndicatorType.PMI: _obs(
                MacroIndicatorType.PMI, 53.0, now, freshness=FreshnessStatus.LATE
            ),
            MacroIndicatorType.RETAIL_SALES: _obs(MacroIndicatorType.RETAIL_SALES, 700_000.0, now),
        }
        freshness = derive_freshness_status(selected)
        degraded, missing = derive_degraded_status(
            selected=selected,
            required_indicators=[MacroIndicatorType.PMI, MacroIndicatorType.RETAIL_SALES],
        )
        assert freshness == FreshnessStatus.LATE
        assert degraded == DegradedStatus.NONE
        assert missing == []


class TestSnapshotComparison:
    def test_comparison_detects_changed_states_and_indicators(self) -> None:
        now = datetime(2026, 1, 10, tzinfo=UTC)
        from src.domain.macro.snapshot import MacroSnapshotState

        previous = MacroSnapshotState(
            snapshot_id="prev",
            as_of_date=date(2026, 1, 9),
            snapshot_timestamp=now - timedelta(days=1),
            growth_state=GrowthState.SLOWING,
            inflation_state=InflationState.STICKY,
            labor_state=LaborState.SOFTENING,
            policy_state=PolicyState.NEUTRAL,
            financial_conditions_state=FinancialConditionsState.NEUTRAL,
            indicator_values={"pmi": 49.0},
        )
        current = MacroSnapshotState(
            snapshot_id="curr",
            as_of_date=date(2026, 1, 10),
            snapshot_timestamp=now,
            growth_state=GrowthState.ACCELERATING,
            inflation_state=InflationState.STICKY,
            labor_state=LaborState.SOFTENING,
            policy_state=PolicyState.RESTRICTIVE,
            financial_conditions_state=FinancialConditionsState.NEUTRAL,
            indicator_values={"pmi": 53.0},
        )
        cmp = compare_snapshot_states(current, previous)
        assert cmp.baseline_available is True
        assert "growth_state" in cmp.changed_category_states
        assert "policy_state" in cmp.changed_category_states
        assert "pmi" in cmp.changed_indicators
