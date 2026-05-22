"""Tests for Confidence Refactor — Chunk 2.

Verifies that:
- derive_regime_confidence() is backward compatible (existing cases still pass)
- quant_scores parameter correctly adjusts confidence
- MacroRegime carries quant_scores when built by the service
- signal score adjustment function behaves correctly
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.domain.macro.regime import MacroRegime, RegimeConfidence, RegimeFamily, RegimeLabel
from src.domain.macro.regime_mapping import derive_regime_confidence
from src.domain.macro.snapshot import (
    DegradedStatus,
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    MacroSnapshotState,
    PolicyState,
)
from src.domain.quant.models import QuantScoreBundle
from src.domain.quant.scoring import score_snapshot
from src.pipelines.ingestion.models import FreshnessStatus
from src.services.signal_service import _adjust_signal_score


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
        as_of_date=date(2026, 4, 1),
        snapshot_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
        freshness_status=freshness,
        degraded_status=degraded,
        growth_state=growth,
        inflation_state=inflation,
        labor_state=labor,
        policy_state=policy,
        financial_conditions_state=conditions,
        missing_indicators=missing or [],
    )


# ---------------------------------------------------------------------------
# Backward-compatibility: existing confidence rules still hold
# ---------------------------------------------------------------------------


class TestConfidenceBackwardCompatibility:
    """Existing confidence rules must not break with the quant_scores parameter."""

    def test_high_when_fresh_complete_no_quant(self) -> None:
        snap = _snapshot()
        result = derive_regime_confidence(snap, RegimeLabel.GOLDILOCKS, quant_scores=None)
        assert result == RegimeConfidence.HIGH

    def test_partial_downgrades_to_medium_no_quant(self) -> None:
        snap = _snapshot(degraded=DegradedStatus.PARTIAL)
        result = derive_regime_confidence(snap, RegimeLabel.DISINFLATION, quant_scores=None)
        assert result == RegimeConfidence.MEDIUM

    def test_missing_downgrades_to_low_no_quant(self) -> None:
        snap = _snapshot(degraded=DegradedStatus.MISSING)
        result = derive_regime_confidence(snap, RegimeLabel.CONTRACTION, quant_scores=None)
        assert result == RegimeConfidence.LOW

    def test_stale_downgrades_to_low_no_quant(self) -> None:
        snap = _snapshot(freshness=FreshnessStatus.STALE)
        result = derive_regime_confidence(snap, RegimeLabel.CONTRACTION, quant_scores=None)
        assert result == RegimeConfidence.LOW

    def test_mixed_label_always_low(self) -> None:
        snap = _snapshot()
        result = derive_regime_confidence(snap, RegimeLabel.MIXED, quant_scores=None)
        assert result == RegimeConfidence.LOW

    def test_unclear_label_always_low(self) -> None:
        snap = _snapshot()
        result = derive_regime_confidence(snap, RegimeLabel.UNCLEAR, quant_scores=None)
        assert result == RegimeConfidence.LOW


# ---------------------------------------------------------------------------
# Quant score adjustment to confidence
# ---------------------------------------------------------------------------


class TestQuantConfidenceAdjustment:
    """Quant scores can further adjust confidence (never inflate it)."""

    def _goldilocks_quant(self) -> QuantScoreBundle:
        snap = _snapshot(
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.COOLING,
            labor=LaborState.TIGHT,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
        return score_snapshot(snap)

    def _contraction_quant(self) -> QuantScoreBundle:
        snap = _snapshot(
            growth=GrowthState.SLOWING,
            inflation=InflationState.REACCELERATING,
            labor=LaborState.WEAK,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
        )
        return score_snapshot(snap)

    def test_strong_quant_support_keeps_high_confidence(self) -> None:
        snap = _snapshot()
        quant = self._goldilocks_quant()
        result = derive_regime_confidence(snap, RegimeLabel.GOLDILOCKS, quant_scores=quant)
        assert result == RegimeConfidence.HIGH

    def test_weak_quant_support_downgrades_high_to_medium(self) -> None:
        """When overall_support < 0.40, HIGH should downgrade to MEDIUM."""
        snap = _snapshot()
        quant = self._contraction_quant()
        # Contraction quant has very low overall_support
        assert quant.overall_support < 0.40
        result = derive_regime_confidence(snap, RegimeLabel.GOLDILOCKS, quant_scores=quant)
        assert result == RegimeConfidence.MEDIUM

    def test_weak_quant_support_downgrades_medium_to_low(self) -> None:
        """When overall_support < 0.40 and preliminary is MEDIUM, downgrade to LOW."""
        snap = _snapshot(degraded=DegradedStatus.PARTIAL)  # already MEDIUM
        quant = self._contraction_quant()
        assert quant.overall_support < 0.40
        result = derive_regime_confidence(snap, RegimeLabel.DISINFLATION, quant_scores=quant)
        assert result == RegimeConfidence.LOW

    def test_low_breadth_caps_high_at_medium(self) -> None:
        """breadth < 0.60 should prevent HIGH confidence."""
        snap = _snapshot()
        quant = score_snapshot(
            _snapshot(
                growth=GrowthState.UNKNOWN,
                inflation=InflationState.UNKNOWN,
                labor=LaborState.UNKNOWN,
            )
        )
        assert quant.breadth < 0.60
        result = derive_regime_confidence(snap, RegimeLabel.GOLDILOCKS, quant_scores=quant)
        assert result in {RegimeConfidence.MEDIUM, RegimeConfidence.LOW}

    def test_hard_floor_not_overridden_by_good_quant(self) -> None:
        """Good quant scores must not lift a hard-floor (MISSING/STALE) to HIGH."""
        snap = _snapshot(degraded=DegradedStatus.MISSING)
        quant = self._goldilocks_quant()
        result = derive_regime_confidence(snap, RegimeLabel.GOLDILOCKS, quant_scores=quant)
        assert result == RegimeConfidence.LOW

    def test_mixed_label_not_overridden_by_good_quant(self) -> None:
        """MIXED label always returns LOW regardless of quant scores."""
        snap = _snapshot()
        quant = self._goldilocks_quant()
        result = derive_regime_confidence(snap, RegimeLabel.MIXED, quant_scores=quant)
        assert result == RegimeConfidence.LOW


# ---------------------------------------------------------------------------
# MacroRegime quant_scores field
# ---------------------------------------------------------------------------


class TestMacroRegimeQuantScoresField:
    def test_regime_accepts_none_quant_scores(self) -> None:
        r = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
        )
        assert r.quant_scores is None

    def test_regime_accepts_quant_scores(self) -> None:
        snap = _snapshot()
        quant = score_snapshot(snap)
        r = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            quant_scores=quant,
        )
        assert r.quant_scores is not None
        assert r.quant_scores.breadth == 1.0


# ---------------------------------------------------------------------------
# Signal score adjustment function
# ---------------------------------------------------------------------------


class TestSignalScoreAdjustment:
    """Unit tests for _adjust_signal_score helper."""

    def test_high_confidence_no_quant_unchanged(self) -> None:
        result = _adjust_signal_score(0.80, RegimeConfidence.HIGH, None)
        assert result == pytest.approx(0.80, abs=0.001)

    def test_medium_confidence_reduces_score(self) -> None:
        result = _adjust_signal_score(0.80, RegimeConfidence.MEDIUM, None)
        assert result == pytest.approx(0.80 * 0.85, abs=0.001)

    def test_low_confidence_significantly_reduces_score(self) -> None:
        result = _adjust_signal_score(0.80, RegimeConfidence.LOW, None)
        assert result == pytest.approx(0.80 * 0.65, abs=0.001)

    def test_weak_quant_adds_extra_reduction(self) -> None:
        high_result = _adjust_signal_score(0.80, RegimeConfidence.HIGH, 0.30)
        assert high_result == pytest.approx(0.80 * 0.85, abs=0.001)

    def test_normal_quant_does_not_add_extra_reduction(self) -> None:
        high_result = _adjust_signal_score(0.80, RegimeConfidence.HIGH, 0.60)
        assert high_result == pytest.approx(0.80, abs=0.001)

    def test_result_clamped_to_valid_range(self) -> None:
        result = _adjust_signal_score(1.0, RegimeConfidence.LOW, 0.10)
        assert 0.0 <= result <= 1.0

    def test_score_never_exceeds_base(self) -> None:
        """Adjustment must never inflate the score above the base value."""
        for confidence in RegimeConfidence:
            result = _adjust_signal_score(0.75, confidence, 0.80)
            assert result <= 0.75 + 1e-9


# ---------------------------------------------------------------------------
# Signal service integration: score adjustment applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSignalScoreAdjustmentInService:
    """Verify that adjusted scores are lower for degraded/low-confidence regimes."""

    async def test_low_confidence_regime_lowers_signal_scores(self) -> None:
        from src.domain.macro.snapshot import DegradedStatus
        from src.pipelines.ingestion.models import FreshnessStatus
        from src.services.signal_service import SignalService

        svc = SignalService()

        healthy_regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
        )

        low_regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.LOW,
            freshness_status=FreshnessStatus.STALE,
            degraded_status=DegradedStatus.NONE,
        )

        healthy_result = await svc.run_regime_grounded_engine(healthy_regime)
        low_result = await svc.run_regime_grounded_engine(low_regime)

        healthy_scores = [s.score for s in healthy_result.signals]
        low_scores = [s.score for s in low_result.signals]

        assert len(healthy_scores) > 0
        assert len(low_scores) > 0
        # Average low-confidence scores should be below healthy
        avg_healthy = sum(healthy_scores) / len(healthy_scores)
        avg_low = sum(low_scores) / len(low_scores)
        assert avg_low < avg_healthy
