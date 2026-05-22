"""Tests for Quant Scoring Engine v1 — Chunk 1."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.domain.macro.snapshot import (
    DegradedStatus,
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    MacroSnapshotState,
    PolicyState,
)
from src.domain.quant.models import QuantScoreBundle, ScoreDimension, ScoreLevel
from src.domain.quant.scoring import (
    score_financial_conditions,
    score_growth,
    score_inflation,
    score_labor,
    score_policy,
    score_snapshot,
)
from src.pipelines.ingestion.models import FreshnessStatus
from src.services.quant_scoring_service import QuantScoringService


def _snapshot(
    *,
    growth: GrowthState = GrowthState.ACCELERATING,
    inflation: InflationState = InflationState.COOLING,
    labor: LaborState = LaborState.TIGHT,
    policy: PolicyState = PolicyState.NEUTRAL,
    conditions: FinancialConditionsState = FinancialConditionsState.NEUTRAL,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
) -> MacroSnapshotState:
    return MacroSnapshotState(
        as_of_date=date(2026, 4, 1),
        snapshot_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
        freshness_status=freshness,
        degraded_status=degraded,
        growth_state=growth,
        inflation_state=inflation,
        labor_state=labor,
        policy_state=policy,
        financial_conditions_state=conditions,
    )


# ---------------------------------------------------------------------------
# Dimension scoring — growth
# ---------------------------------------------------------------------------


class TestGrowthScoring:
    def test_accelerating_returns_high_score(self) -> None:
        snap = _snapshot(growth=GrowthState.ACCELERATING)
        d = score_growth(snap)
        assert d.score is not None
        assert d.score >= 0.80
        assert d.level == ScoreLevel.STRONG

    def test_slowing_returns_low_score(self) -> None:
        snap = _snapshot(growth=GrowthState.SLOWING)
        d = score_growth(snap)
        assert d.score is not None
        assert d.score < 0.40
        assert d.level == ScoreLevel.WEAK

    def test_mixed_returns_moderate_score(self) -> None:
        snap = _snapshot(growth=GrowthState.MIXED)
        d = score_growth(snap)
        assert d.score is not None
        assert 0.40 <= d.score < 0.70
        assert d.level == ScoreLevel.MODERATE

    def test_unknown_returns_none_score(self) -> None:
        snap = _snapshot(growth=GrowthState.UNKNOWN)
        d = score_growth(snap)
        assert d.score is None
        assert d.level == ScoreLevel.UNKNOWN

    def test_contributing_states_populated(self) -> None:
        snap = _snapshot(growth=GrowthState.ACCELERATING)
        d = score_growth(snap)
        assert "accelerating" in d.contributing_states


# ---------------------------------------------------------------------------
# Dimension scoring — inflation
# ---------------------------------------------------------------------------


class TestInflationScoring:
    def test_cooling_returns_high_score(self) -> None:
        snap = _snapshot(inflation=InflationState.COOLING)
        d = score_inflation(snap)
        assert d.score is not None and d.score >= 0.70
        assert d.level == ScoreLevel.STRONG

    def test_reaccelerating_returns_low_score(self) -> None:
        snap = _snapshot(inflation=InflationState.REACCELERATING)
        d = score_inflation(snap)
        assert d.score is not None and d.score < 0.40
        assert d.level == ScoreLevel.WEAK

    def test_sticky_returns_moderate_score(self) -> None:
        snap = _snapshot(inflation=InflationState.STICKY)
        d = score_inflation(snap)
        assert d.score is not None
        assert 0.40 <= d.score < 0.70

    def test_unknown_returns_none_score(self) -> None:
        snap = _snapshot(inflation=InflationState.UNKNOWN)
        d = score_inflation(snap)
        assert d.score is None


# ---------------------------------------------------------------------------
# Dimension scoring — labor
# ---------------------------------------------------------------------------


class TestLaborScoring:
    def test_tight_returns_high_score(self) -> None:
        snap = _snapshot(labor=LaborState.TIGHT)
        d = score_labor(snap)
        assert d.score is not None and d.score >= 0.70

    def test_weak_returns_low_score(self) -> None:
        snap = _snapshot(labor=LaborState.WEAK)
        d = score_labor(snap)
        assert d.score is not None and d.score < 0.40

    def test_softening_returns_moderate_score(self) -> None:
        snap = _snapshot(labor=LaborState.SOFTENING)
        d = score_labor(snap)
        assert d.score is not None
        assert 0.40 <= d.score < 0.70


# ---------------------------------------------------------------------------
# Dimension scoring — policy
# ---------------------------------------------------------------------------


class TestPolicyScoring:
    def test_easing_bias_returns_high_score(self) -> None:
        snap = _snapshot(policy=PolicyState.EASING_BIAS)
        d = score_policy(snap)
        assert d.score is not None and d.score >= 0.70

    def test_restrictive_returns_low_score(self) -> None:
        snap = _snapshot(policy=PolicyState.RESTRICTIVE)
        d = score_policy(snap)
        assert d.score is not None and d.score < 0.40

    def test_neutral_returns_moderate_score(self) -> None:
        snap = _snapshot(policy=PolicyState.NEUTRAL)
        d = score_policy(snap)
        assert d.score is not None
        assert 0.40 <= d.score < 0.80


# ---------------------------------------------------------------------------
# Dimension scoring — financial conditions
# ---------------------------------------------------------------------------


class TestFinancialConditionsScoring:
    def test_loose_returns_high_score(self) -> None:
        snap = _snapshot(conditions=FinancialConditionsState.LOOSE)
        d = score_financial_conditions(snap)
        assert d.score is not None and d.score >= 0.70

    def test_tight_returns_low_score(self) -> None:
        snap = _snapshot(conditions=FinancialConditionsState.TIGHT)
        d = score_financial_conditions(snap)
        assert d.score is not None and d.score < 0.40

    def test_neutral_returns_moderate_score(self) -> None:
        snap = _snapshot(conditions=FinancialConditionsState.NEUTRAL)
        d = score_financial_conditions(snap)
        assert d.score is not None
        assert 0.40 <= d.score < 0.80


# ---------------------------------------------------------------------------
# Secondary measures
# ---------------------------------------------------------------------------


class TestSecondaryMeasures:
    def test_breadth_all_known(self) -> None:
        snap = _snapshot()
        bundle = score_snapshot(snap)
        assert bundle.breadth == 1.0

    def test_breadth_with_unknowns(self) -> None:
        snap = _snapshot(growth=GrowthState.UNKNOWN, inflation=InflationState.UNKNOWN)
        bundle = score_snapshot(snap)
        assert bundle.breadth == pytest.approx(0.60, abs=0.01)

    def test_breadth_all_unknown(self) -> None:
        snap = _snapshot(
            growth=GrowthState.UNKNOWN,
            inflation=InflationState.UNKNOWN,
            labor=LaborState.UNKNOWN,
            policy=PolicyState.UNKNOWN,
            conditions=FinancialConditionsState.UNKNOWN,
        )
        bundle = score_snapshot(snap)
        assert bundle.breadth == 0.0
        assert bundle.overall_support == 0.0

    def test_overall_support_goldilocks_is_high(self) -> None:
        """Goldilocks state: growth accelerating, inflation cooling, labor tight,
        policy neutral, conditions neutral — expect high overall_support."""
        snap = _snapshot(
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.COOLING,
            labor=LaborState.TIGHT,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
        bundle = score_snapshot(snap)
        assert bundle.overall_support >= 0.65

    def test_overall_support_contraction_is_low(self) -> None:
        """Contraction state: slowing, reaccelerating inflation, weak labor,
        restrictive policy, tight conditions — expect low overall_support."""
        snap = _snapshot(
            growth=GrowthState.SLOWING,
            inflation=InflationState.REACCELERATING,
            labor=LaborState.WEAK,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
        )
        bundle = score_snapshot(snap)
        assert bundle.overall_support < 0.40

    def test_change_intensity_high_dispersion(self) -> None:
        """Mixed snapshot with high-scoring and low-scoring dimensions
        should produce a non-trivial change_intensity."""
        snap = _snapshot(
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.REACCELERATING,
            labor=LaborState.TIGHT,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
        )
        bundle = score_snapshot(snap)
        assert bundle.change_intensity > 0.0

    def test_change_intensity_uniform_is_low(self) -> None:
        """All moderate/uniform dimensions → low dispersion → low change_intensity."""
        snap = _snapshot(
            growth=GrowthState.MIXED,
            inflation=InflationState.STICKY,
            labor=LaborState.SOFTENING,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
        bundle = score_snapshot(snap)
        # Dispersion should be relatively small for a uniform mixed scenario
        assert bundle.change_intensity < 0.60


# ---------------------------------------------------------------------------
# QuantScoreBundle helpers
# ---------------------------------------------------------------------------


class TestQuantScoreBundleHelpers:
    def test_dimensions_returns_five_items(self) -> None:
        snap = _snapshot()
        bundle = score_snapshot(snap)
        assert len(bundle.dimensions) == 5

    def test_known_dimensions_filters_unknowns(self) -> None:
        snap = _snapshot(growth=GrowthState.UNKNOWN)
        bundle = score_snapshot(snap)
        assert len(bundle.known_dimensions) == 4

    def test_get_dimension_lookup(self) -> None:
        snap = _snapshot()
        bundle = score_snapshot(snap)
        growth_dim = bundle.get_dimension(ScoreDimension.GROWTH)
        assert growth_dim.dimension == ScoreDimension.GROWTH

    def test_bundle_is_pydantic_model(self) -> None:
        snap = _snapshot()
        bundle = score_snapshot(snap)
        assert isinstance(bundle, QuantScoreBundle)

    def test_scores_in_valid_range(self) -> None:
        snap = _snapshot()
        bundle = score_snapshot(snap)
        for dim in bundle.dimensions:
            if dim.score is not None:
                assert 0.0 <= dim.score <= 1.0
        assert 0.0 <= bundle.overall_support <= 1.0
        assert 0.0 <= bundle.breadth <= 1.0
        assert 0.0 <= bundle.momentum <= 1.0
        assert 0.0 <= bundle.change_intensity <= 1.0


# ---------------------------------------------------------------------------
# QuantScoringService
# ---------------------------------------------------------------------------


class TestQuantScoringService:
    def test_service_compute_returns_bundle(self) -> None:
        svc = QuantScoringService()
        snap = _snapshot()
        result = svc.compute(snap)
        assert isinstance(result, QuantScoreBundle)

    def test_service_is_deterministic(self) -> None:
        svc = QuantScoringService()
        snap = _snapshot()
        r1 = svc.compute(snap)
        r2 = svc.compute(snap)
        assert r1.overall_support == r2.overall_support
        assert r1.breadth == r2.breadth

    def test_service_stateless(self) -> None:
        """Multiple calls with different snapshots do not contaminate each other."""
        svc = QuantScoringService()
        goldilocks = _snapshot(
            growth=GrowthState.ACCELERATING, inflation=InflationState.COOLING
        )
        contraction = _snapshot(
            growth=GrowthState.SLOWING, inflation=InflationState.REACCELERATING
        )
        r_gold = svc.compute(goldilocks)
        r_cont = svc.compute(contraction)
        assert r_gold.overall_support > r_cont.overall_support
