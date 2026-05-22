"""Tests for regime-grounded signal degraded propagation — Chunk 2."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_macro_service, get_regime_service, get_signal_service
from apps.api.dto.builders import signal_output_to_dto
from apps.api.main import app
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.domain.signals.enums import SignalStrength, SignalType, TrendDirection
from src.domain.signals.models import SignalOutput, SignalResult
from src.pipelines.ingestion.models import FreshnessStatus
from src.services.signal_service import SignalService


def _regime(
    label: RegimeLabel,
    family: RegimeFamily,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
    metadata: dict[str, str] | None = None,
) -> MacroRegime:
    return MacroRegime(
        as_of_date=date(2026, 4, 1),
        regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-1",
        confidence=confidence,
        freshness_status=freshness,
        degraded_status=degraded,
        transition=RegimeTransition(
            transition_from_prior=None,
            transition_type=RegimeTransitionType.INITIAL,
            changed=False,
        ),
        metadata=metadata or {},
    )


@pytest.mark.asyncio
class TestSignalDegradedPropagation:
    async def test_healthy_regime_produces_non_degraded_signals(self) -> None:
        svc = SignalService()
        regime = _regime(RegimeLabel.GOLDILOCKS, RegimeFamily.EXPANSION)
        result = await svc.run_regime_grounded_engine(regime)

        assert result.success is True
        for sig in result.signals:
            assert sig.is_degraded is False, f"Signal {sig.signal_id} should not be degraded"
            assert sig.caveat is None

    async def test_stale_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.GOLDILOCKS,
            RegimeFamily.EXPANSION,
            freshness=FreshnessStatus.STALE,
            confidence=RegimeConfidence.LOW,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None
            assert "stale" in sig.caveat.lower()

    async def test_partial_degraded_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.SLOWDOWN,
            RegimeFamily.DOWNSHIFT,
            degraded=DegradedStatus.PARTIAL,
            confidence=RegimeConfidence.MEDIUM,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None
            assert "partial" in sig.caveat.lower()

    async def test_seeded_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.POLICY_TIGHTENING_DRAG,
            RegimeFamily.LATE_CYCLE,
            metadata={"seeded": "true", "source": "synthetic_seed"},
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None
            assert "bootstrap" in sig.caveat.lower() or "synthetic" in sig.caveat.lower()

    async def test_low_confidence_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.DISINFLATION,
            RegimeFamily.INFLATION_TRANSITION,
            confidence=RegimeConfidence.LOW,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None
            assert "low" in sig.caveat.lower() or "confidence" in sig.caveat.lower()

    async def test_unclear_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.UNCLEAR,
            RegimeFamily.UNCERTAIN,
            confidence=RegimeConfidence.LOW,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None
            assert "non-directional" in sig.caveat.lower() or "unclear" in sig.caveat.lower()

    async def test_mixed_regime_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.MIXED,
            RegimeFamily.UNCERTAIN,
            confidence=RegimeConfidence.LOW,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True

    async def test_missing_critical_data_marks_signals_degraded(self) -> None:
        svc = SignalService()
        regime = _regime(
            RegimeLabel.CONTRACTION,
            RegimeFamily.CONTRACTION,
            degraded=DegradedStatus.MISSING,
            confidence=RegimeConfidence.LOW,
        )
        result = await svc.run_regime_grounded_engine(regime)

        for sig in result.signals:
            assert sig.is_degraded is True
            assert sig.caveat is not None

    async def test_signals_all_have_non_empty_rationale(self) -> None:
        """Every regime-grounded signal must carry a non-empty rationale."""
        svc = SignalService()
        for label in RegimeLabel:
            family = {
                RegimeLabel.GOLDILOCKS: RegimeFamily.EXPANSION,
                RegimeLabel.DISINFLATION: RegimeFamily.INFLATION_TRANSITION,
                RegimeLabel.REFLATION: RegimeFamily.INFLATION_TRANSITION,
                RegimeLabel.SLOWDOWN: RegimeFamily.DOWNSHIFT,
                RegimeLabel.STAGFLATION_RISK: RegimeFamily.LATE_CYCLE,
                RegimeLabel.CONTRACTION: RegimeFamily.CONTRACTION,
                RegimeLabel.POLICY_TIGHTENING_DRAG: RegimeFamily.LATE_CYCLE,
                RegimeLabel.MIXED: RegimeFamily.UNCERTAIN,
                RegimeLabel.UNCLEAR: RegimeFamily.UNCERTAIN,
            }[label]
            regime = _regime(label, family)
            result = await svc.run_regime_grounded_engine(regime)
            for sig in result.signals:
                assert sig.rationale.strip(), (
                    f"Empty rationale for regime={label}, signal={sig.signal_id}"
                )

    async def test_result_has_correct_run_id_format(self) -> None:
        """run_id should be a UUID string."""
        svc = SignalService()
        regime = _regime(RegimeLabel.GOLDILOCKS, RegimeFamily.EXPANSION)
        result = await svc.run_regime_grounded_engine(regime)
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(result.run_id), f"run_id not a UUID: {result.run_id}"


class TestSignalOutputDegradedFields:
    """Unit tests for is_degraded/caveat fields on SignalOutput domain model."""

    def test_signal_output_defaults_is_degraded_false(self) -> None:
        sig = SignalOutput(
            signal_id="test_sig",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            score=0.8,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            trend=TrendDirection.UP,
        )
        assert sig.is_degraded is False
        assert sig.caveat is None

    def test_signal_output_accepts_degraded_flag(self) -> None:
        sig = SignalOutput(
            signal_id="test_sig_degraded",
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            score=0.2,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            trend=TrendDirection.NEUTRAL,
            is_degraded=True,
            caveat="Stale data — regime classification may be outdated.",
        )
        assert sig.is_degraded is True
        assert sig.caveat is not None
        assert "stale" in sig.caveat.lower()


class TestSignalSummaryDTODegradedFields:
    """Verify is_degraded and caveat are passed through the DTO builder."""

    def test_dto_builder_passes_through_degraded_fields(self) -> None:
        sig = SignalOutput(
            signal_id="degraded_sig",
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            score=0.2,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            trend=TrendDirection.NEUTRAL,
            is_degraded=True,
            caveat="Bootstrap data — synthetic signal only.",
        )
        dto = signal_output_to_dto(sig)
        assert dto.is_degraded is True
        assert dto.caveat == "Bootstrap data — synthetic signal only."

    def test_dto_builder_passes_through_non_degraded(self) -> None:
        sig = SignalOutput(
            signal_id="clean_sig",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            score=0.85,
            triggered_at=datetime(2026, 4, 1, tzinfo=UTC),
            trend=TrendDirection.UP,
        )
        dto = signal_output_to_dto(sig)
        assert dto.is_degraded is False
        assert dto.caveat is None


class TestSignalsLatestRouterDegradedPropagation:
    """Integration-level tests: signals router surfaces degraded state correctly."""

    def test_signals_response_has_regime_grounded_fields(self) -> None:
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

        real_signal_svc = SignalService()
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: real_signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["is_regime_grounded"] is True
            assert payload["regime_label"] == "goldilocks"
            assert payload["as_of_date"] == "2026-04-01"
            assert payload["status"] == "success"
            # Every signal should have is_degraded and caveat fields
            for sig in payload["signals"]:
                assert "is_degraded" in sig
                assert "caveat" in sig
        finally:
            app.dependency_overrides.clear()

    def test_signals_fallback_has_correct_status(self) -> None:
        now = datetime(2026, 4, 1, tzinfo=UTC)
        snapshot = MacroSnapshot(
            features=[
                MacroFeature(
                    indicator_type=MacroIndicatorType.PMI,
                    source=MacroSourceType.FRED,
                    value=51.0,
                    timestamp=now,
                    frequency=DataFrequency.MONTHLY,
                    country="US",
                )
            ],
            snapshot_time=now,
        )
        signal_result = SignalResult(
            run_id="run-fallback",
            timestamp=now,
            macro_snapshot=snapshot,
            signals=[
                SignalOutput(
                    signal_id="test_sig",
                    signal_type=SignalType.HOLD,
                    strength=SignalStrength.WEAK,
                    score=0.3,
                    triggered_at=now,
                )
            ],
            success=True,
        )

        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=None)
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=snapshot)
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=signal_result)

        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["is_regime_grounded"] is False
            assert payload["status"] == "fallback"
            assert payload["regime_label"] is None
        finally:
            app.dependency_overrides.clear()
