"""Tests for Conflict Surface v1 — Chunk 3."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.domain.signals.conflict import (
    ConflictStatus,
    ConflictSurface,
    _quant_support_label,
    derive_conflict,
)
from src.domain.signals.enums import SignalStrength, SignalType
from src.domain.signals.models import SignalOutput

# ---------------------------------------------------------------------------
# ConflictSurface model
# ---------------------------------------------------------------------------


class TestConflictSurfaceModel:
    def test_default_is_clean(self) -> None:
        c = ConflictSurface()
        assert c.conflict_status == ConflictStatus.CLEAN
        assert c.is_mixed is False
        assert c.conflict_note is None
        assert c.quant_support_level == "unknown"

    def test_mixed_status_sets_is_mixed(self) -> None:
        c = ConflictSurface(
            conflict_status=ConflictStatus.MIXED,
            is_mixed=True,
        )
        assert c.is_mixed is True

    def test_low_conviction_sets_is_mixed(self) -> None:
        c = ConflictSurface(
            conflict_status=ConflictStatus.LOW_CONVICTION,
            is_mixed=True,
        )
        assert c.is_mixed is True

    def test_tension_does_not_set_is_mixed(self) -> None:
        c = ConflictSurface(
            conflict_status=ConflictStatus.TENSION,
            is_mixed=False,
        )
        assert c.is_mixed is False


# ---------------------------------------------------------------------------
# _quant_support_label helper
# ---------------------------------------------------------------------------


class TestQuantSupportLabel:
    def test_none_returns_unknown(self) -> None:
        assert _quant_support_label(None) == "unknown"

    def test_high_returns_strong(self) -> None:
        assert _quant_support_label(0.80) == "strong"

    def test_moderate_range(self) -> None:
        assert _quant_support_label(0.50) == "moderate"

    def test_weak_range(self) -> None:
        assert _quant_support_label(0.20) == "weak"

    def test_boundary_at_065(self) -> None:
        assert _quant_support_label(0.65) == "strong"

    def test_boundary_just_below_065(self) -> None:
        assert _quant_support_label(0.64) == "moderate"

    def test_boundary_at_040(self) -> None:
        assert _quant_support_label(0.40) == "moderate"

    def test_boundary_just_below_040(self) -> None:
        assert _quant_support_label(0.39) == "weak"


# ---------------------------------------------------------------------------
# derive_conflict — status classification
# ---------------------------------------------------------------------------


class TestDeriveConflictStatus:
    def test_clean_when_no_conflicting_drivers(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating", "inflation_cooling"],
            conflicting_drivers=[],
            quant_overall_support=0.75,
        )
        assert c.conflict_status == ConflictStatus.CLEAN
        assert c.is_mixed is False
        assert c.conflict_note is None

    def test_tension_when_few_conflicting_drivers(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating", "inflation_cooling", "policy_neutral"],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.70,
        )
        assert c.conflict_status == ConflictStatus.TENSION
        assert c.is_mixed is False
        assert c.conflict_note is not None
        assert "tension" in c.conflict_note.lower() or "conflicting" in c.conflict_note.lower()

    def test_mixed_when_equal_drivers(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.55,
        )
        assert c.conflict_status == ConflictStatus.MIXED
        assert c.is_mixed is True

    def test_mixed_when_more_conflicting_than_supporting(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=["policy_restrictive", "labor_weakening"],
            quant_overall_support=0.55,
        )
        assert c.conflict_status == ConflictStatus.MIXED
        assert c.is_mixed is True

    def test_low_conviction_when_no_supporting_drivers(self) -> None:
        c = derive_conflict(
            supporting_drivers=[],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.70,
        )
        assert c.conflict_status == ConflictStatus.LOW_CONVICTION
        assert c.is_mixed is True

    def test_low_conviction_when_quant_very_weak(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.25,  # < 0.35 threshold
        )
        assert c.conflict_status == ConflictStatus.LOW_CONVICTION
        assert c.is_mixed is True

    def test_low_conviction_no_drivers_and_weak_quant(self) -> None:
        c = derive_conflict(
            supporting_drivers=[],
            conflicting_drivers=[],
            quant_overall_support=0.20,
        )
        assert c.conflict_status == ConflictStatus.LOW_CONVICTION

    def test_clean_with_no_conflicting_and_strong_quant(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating", "inflation_cooling"],
            conflicting_drivers=[],
            quant_overall_support=0.80,
        )
        assert c.conflict_status == ConflictStatus.CLEAN

    def test_is_degraded_does_not_affect_conflict_status(self) -> None:
        """is_degraded is orthogonal to conflict logic."""
        c_clean = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=[],
            quant_overall_support=0.75,
            is_degraded=False,
        )
        c_degraded = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=[],
            quant_overall_support=0.75,
            is_degraded=True,
        )
        assert c_clean.conflict_status == c_degraded.conflict_status

    def test_quant_support_level_propagated(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=[],
            quant_overall_support=0.80,
        )
        assert c.quant_support_level == "strong"

    def test_quant_support_unknown_when_none(self) -> None:
        c = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=[],
            quant_overall_support=None,
        )
        assert c.quant_support_level == "unknown"

    def test_drivers_propagated_correctly(self) -> None:
        sup = ["growth_accelerating", "inflation_cooling"]
        con = ["policy_restrictive"]
        c = derive_conflict(supporting_drivers=sup, conflicting_drivers=con)
        assert c.supporting_drivers == sup
        assert c.conflicting_drivers == con


# ---------------------------------------------------------------------------
# SignalOutput conflict field
# ---------------------------------------------------------------------------


class TestSignalOutputConflictField:
    def test_conflict_defaults_to_none(self) -> None:
        sig = SignalOutput(
            signal_id="test",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            score=0.80,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
        assert sig.conflict is None

    def test_conflict_surface_attached_to_signal(self) -> None:
        conflict = derive_conflict(
            supporting_drivers=["growth_accelerating", "inflation_cooling", "policy_neutral"],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.70,
        )
        sig = SignalOutput(
            signal_id="test",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            score=0.65,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            conflict=conflict,
        )
        assert sig.conflict is not None
        assert sig.conflict.conflict_status == ConflictStatus.TENSION


# ---------------------------------------------------------------------------
# DTO builder passes through conflict fields
# ---------------------------------------------------------------------------


class TestDTOBuilderConflictFields:
    def test_dto_builder_maps_conflict_fields_from_conflict_surface(self) -> None:
        from apps.api.dto.builders import signal_output_to_dto

        conflict = derive_conflict(
            supporting_drivers=["growth_accelerating", "inflation_cooling", "policy_neutral"],
            conflicting_drivers=["policy_restrictive"],
            quant_overall_support=0.70,
        )
        sig = SignalOutput(
            signal_id="test_conflict",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            score=0.65,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            conflict=conflict,
        )
        dto = signal_output_to_dto(sig)
        assert dto.conflict_status == "tension"
        assert dto.is_mixed is False
        assert dto.conflict_note is not None
        assert dto.quant_support_level == "strong"

    def test_dto_builder_defaults_when_no_conflict_surface(self) -> None:
        from apps.api.dto.builders import signal_output_to_dto

        sig = SignalOutput(
            signal_id="no_conflict",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            score=0.80,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
        dto = signal_output_to_dto(sig)
        assert dto.conflict_status == "clean"
        assert dto.is_mixed is False
        assert dto.conflict_note is None
        assert dto.quant_support_level == "unknown"

    def test_dto_builder_mixed_signal(self) -> None:
        from apps.api.dto.builders import signal_output_to_dto

        conflict = derive_conflict(
            supporting_drivers=["growth_accelerating"],
            conflicting_drivers=["policy_restrictive", "labor_weakening"],
            quant_overall_support=0.50,
        )
        sig = SignalOutput(
            signal_id="mixed_sig",
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            score=0.35,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            conflict=conflict,
        )
        dto = signal_output_to_dto(sig)
        assert dto.is_mixed is True
        assert dto.conflict_status == "mixed"


# ---------------------------------------------------------------------------
# Integration: regime-grounded engine populates conflict surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConflictSurfaceInRegimeEngine:
    async def test_goldilocks_signals_have_conflict_populated(self) -> None:
        from src.domain.macro.regime import MacroRegime, RegimeConfidence, RegimeFamily, RegimeLabel
        from src.domain.macro.snapshot import DegradedStatus
        from src.pipelines.ingestion.models import FreshnessStatus
        from src.services.signal_service import SignalService

        svc = SignalService()
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
        )
        result = await svc.run_regime_grounded_engine(regime)
        assert result.success is True
        for sig in result.signals:
            assert sig.conflict is not None, f"Signal {sig.signal_id} missing conflict surface"
            assert isinstance(sig.conflict, ConflictSurface)

    async def test_goldilocks_signals_are_mostly_clean_or_tension(self) -> None:
        """Goldilocks is a coherent regime — most signals should not be 'mixed'."""
        from src.domain.macro.regime import MacroRegime, RegimeConfidence, RegimeFamily, RegimeLabel
        from src.domain.macro.snapshot import DegradedStatus
        from src.pipelines.ingestion.models import FreshnessStatus
        from src.services.signal_service import SignalService

        svc = SignalService()
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
        )
        result = await svc.run_regime_grounded_engine(regime)
        for sig in result.signals:
            assert sig.conflict is not None
            assert sig.conflict.conflict_status in {
                ConflictStatus.CLEAN,
                ConflictStatus.TENSION,
                ConflictStatus.MIXED,
                ConflictStatus.LOW_CONVICTION,
            }

    async def test_conflict_is_none_in_fallback_engine_path(self) -> None:
        """Legacy snapshot-based engine does not produce conflict surface."""
        from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
        from src.domain.macro.models import MacroFeature, MacroSnapshot
        from src.domain.signals.models import SignalDefinition, SignalRule
        from src.services.signal_service import SignalService

        svc = SignalService()
        snap = MacroSnapshot(
            features=[
                MacroFeature(
                    indicator_type=MacroIndicatorType.PMI,
                    source=MacroSourceType.FRED,
                    value=52.0,
                    timestamp=datetime(2026, 4, 1, tzinfo=UTC),
                    frequency=DataFrequency.MONTHLY,
                )
            ],
            snapshot_time=datetime(2026, 4, 1, tzinfo=UTC),
        )
        definition = SignalDefinition(
            signal_id="test_sig",
            name="Test",
            signal_type=SignalType.BUY,
            description="Test signal",
            rules=[SignalRule(name="rule1", description="r", condition="pmi > 50")],
        )
        result = await svc.run_engine(
            signal_definitions=[definition],
            snapshot=snap,
        )
        # Fallback engine does not attach conflict surface
        for sig in result.signals:
            assert sig.conflict is None


# ---------------------------------------------------------------------------
# API response includes conflict fields
# ---------------------------------------------------------------------------


class TestSignalsAPIConflictFields:
    def test_regime_grounded_response_has_conflict_fields(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from fastapi.testclient import TestClient

        from apps.api.dependencies import get_regime_service, get_signal_service
        from apps.api.main import app
        from src.domain.macro.regime import MacroRegime, RegimeConfidence, RegimeFamily, RegimeLabel
        from src.domain.macro.snapshot import DegradedStatus
        from src.pipelines.ingestion.models import FreshnessStatus
        from src.services.signal_service import SignalService

        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
        )
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)

        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            payload = resp.json()
            for sig in payload["signals"]:
                assert "conflict_status" in sig
                assert "is_mixed" in sig
                assert "conflict_note" in sig
                assert "quant_support_level" in sig
                assert sig["conflict_status"] in {
                    "clean", "tension", "mixed", "low_conviction"
                }
        finally:
            app.dependency_overrides.clear()
