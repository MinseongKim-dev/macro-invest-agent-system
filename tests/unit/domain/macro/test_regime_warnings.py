"""Tests for derive_regime_warnings — Chunk 1: Regime Backbone Hardening."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.agent.adapters.repositories.in_memory_macro_snapshot_store import InMemoryMacroSnapshotStore
from apps.api.dependencies import get_regime_service
from apps.api.main import app
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.regime_mapping import derive_regime_warnings
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
from src.services.macro_regime_service import MacroRegimeService


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


class TestDeriveRegimeWarnings:
    def test_healthy_regime_has_no_warnings(self) -> None:
        snap = _snapshot()
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.HIGH,
            missing_inputs=[],
            is_seeded=False,
        )
        assert warnings == []

    def test_bootstrap_warning_when_seeded(self) -> None:
        snap = _snapshot()
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.HIGH,
            missing_inputs=[],
            is_seeded=True,
        )
        assert len(warnings) == 1
        assert "synthetic seed data" in warnings[0].lower() or "bootstrap" in warnings[0].lower()

    def test_stale_data_produces_warning(self) -> None:
        snap = _snapshot(freshness=FreshnessStatus.STALE)
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.LOW,
            missing_inputs=[],
            is_seeded=False,
        )
        stale_warnings = [w for w in warnings if "stale" in w.lower()]
        assert len(stale_warnings) >= 1

    def test_late_data_produces_warning(self) -> None:
        snap = _snapshot(freshness=FreshnessStatus.LATE)
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.MEDIUM,
            missing_inputs=[],
            is_seeded=False,
        )
        late_warnings = [w for w in warnings if "late" in w.lower()]
        assert len(late_warnings) >= 1

    def test_partial_degraded_status_produces_warning(self) -> None:
        snap = _snapshot(degraded=DegradedStatus.PARTIAL)
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.MEDIUM,
            missing_inputs=[],
            is_seeded=False,
        )
        partial_warnings = [w for w in warnings if "partial" in w.lower()]
        assert len(partial_warnings) >= 1

    def test_missing_inputs_produces_warning(self) -> None:
        snap = _snapshot(degraded=DegradedStatus.PARTIAL)
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.DISINFLATION,
            confidence=RegimeConfidence.MEDIUM,
            missing_inputs=["pmi", "retail_sales"],
            is_seeded=False,
        )
        missing_warnings = [w for w in warnings if "missing" in w.lower()]
        assert len(missing_warnings) >= 1

    def test_low_confidence_produces_warning(self) -> None:
        snap = _snapshot()
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.LOW,
            missing_inputs=[],
            is_seeded=False,
        )
        conf_warnings = [w for w in warnings if "low confidence" in w.lower()]
        assert len(conf_warnings) >= 1

    def test_unclear_regime_produces_non_directional_warning(self) -> None:
        snap = _snapshot()
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.UNCLEAR,
            confidence=RegimeConfidence.LOW,
            missing_inputs=[],
            is_seeded=False,
        )
        nd_warnings = [w for w in warnings if "non-directional" in w.lower()]
        assert len(nd_warnings) >= 1

    def test_mixed_regime_produces_non_directional_warning(self) -> None:
        snap = _snapshot()
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.MIXED,
            confidence=RegimeConfidence.LOW,
            missing_inputs=[],
            is_seeded=False,
        )
        nd_warnings = [w for w in warnings if "non-directional" in w.lower()]
        assert len(nd_warnings) >= 1

    def test_multiple_conditions_accumulate_warnings(self) -> None:
        snap = _snapshot(
            freshness=FreshnessStatus.STALE,
            degraded=DegradedStatus.PARTIAL,
        )
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.GOLDILOCKS,
            confidence=RegimeConfidence.LOW,
            missing_inputs=["pmi"],
            is_seeded=True,
        )
        # bootstrap + stale + partial + missing + low confidence
        assert len(warnings) >= 5

    def test_source_unavailable_produces_warning(self) -> None:
        snap = _snapshot(degraded=DegradedStatus.SOURCE_UNAVAILABLE)
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.UNCLEAR,
            confidence=RegimeConfidence.LOW,
            missing_inputs=[],
            is_seeded=False,
        )
        src_warnings = [w for w in warnings if "unavailable" in w.lower()]
        assert len(src_warnings) >= 1

    def test_missing_inputs_truncated_when_many(self) -> None:
        """Warning message should not list all indicators when there are many."""
        snap = _snapshot(degraded=DegradedStatus.PARTIAL)
        missing = ["pmi", "retail_sales", "inflation", "unemployment", "yield_10y"]
        warnings = derive_regime_warnings(
            snapshot=snap,
            label=RegimeLabel.UNCLEAR,
            confidence=RegimeConfidence.LOW,
            missing_inputs=missing,
            is_seeded=False,
        )
        # The per-indicator count warning starts with "Missing N indicator(s)"
        count_warnings = [w for w in warnings if w.startswith("Missing") and "indicator(s)" in w]
        assert len(count_warnings) >= 1
        # Should mention "and X more" for truncation when > 3 indicators
        assert "more" in count_warnings[0].lower()


class TestMacroRegimeWarningsField:
    """Verify warnings is stored on MacroRegime and accessible at runtime."""

    def test_regime_warnings_field_is_list(self) -> None:
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
        )
        assert isinstance(regime.warnings, list)
        assert regime.warnings == []

    def test_regime_accepts_warnings_at_construction(self) -> None:
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            warnings=["test warning"],
        )
        assert regime.warnings == ["test warning"]


@pytest.mark.asyncio
async def test_build_regime_populates_warnings_for_healthy_snapshot() -> None:
    """MacroRegimeService.build_regime populates warnings for a healthy snapshot."""
    repo = InMemoryMacroSnapshotStore()
    await repo.save_snapshot(
        _snapshot(
            freshness=FreshnessStatus.FRESH,
            degraded=DegradedStatus.NONE,
            growth=GrowthState.ACCELERATING,
            inflation=InflationState.COOLING,
            labor=LaborState.TIGHT,
            policy=PolicyState.NEUTRAL,
            conditions=FinancialConditionsState.NEUTRAL,
        )
    )
    svc = MacroRegimeService(snapshot_repository=repo)
    regime = await svc.build_regime(as_of_date=date(2026, 4, 1))
    assert isinstance(regime.warnings, list)
    # A healthy, non-seeded Goldilocks regime should have no warnings
    assert regime.warnings == []


@pytest.mark.asyncio
async def test_build_regime_populates_warnings_for_degraded_snapshot() -> None:
    """MacroRegimeService.build_regime surfaces warnings when snapshot is degraded."""
    repo = InMemoryMacroSnapshotStore()
    await repo.save_snapshot(
        _snapshot(
            freshness=FreshnessStatus.STALE,
            degraded=DegradedStatus.PARTIAL,
            growth=GrowthState.SLOWING,
            inflation=InflationState.STICKY,
            labor=LaborState.SOFTENING,
            policy=PolicyState.RESTRICTIVE,
            conditions=FinancialConditionsState.TIGHT,
        )
    )
    svc = MacroRegimeService(snapshot_repository=repo)
    regime = await svc.build_regime(as_of_date=date(2026, 4, 1))
    assert len(regime.warnings) >= 2  # at least stale + partial


class TestRegimeLatestResponseWarnings:
    """Test that the regime router surfaces warnings in the API response."""

    def test_latest_response_includes_warnings_field(self) -> None:
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
            warnings=[],
        )
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 200
            payload = resp.json()
            assert "warnings" in payload
            assert isinstance(payload["warnings"], list)
            assert payload["warnings"] == []
        finally:
            app.dependency_overrides.clear()

    def test_latest_response_status_success_for_healthy_regime(self) -> None:
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
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"
        finally:
            app.dependency_overrides.clear()

    def test_latest_response_status_bootstrap_for_seeded_regime(self) -> None:
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.POLICY_TIGHTENING_DRAG,
            regime_family=RegimeFamily.LATE_CYCLE,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.MEDIUM,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
            metadata={"seeded": "true", "source": "synthetic_seed"},
        )
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "bootstrap"
            assert payload["is_seeded"] is True
        finally:
            app.dependency_overrides.clear()

    def test_latest_response_status_stale(self) -> None:
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.SLOWDOWN,
            regime_family=RegimeFamily.DOWNSHIFT,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.LOW,
            freshness_status=FreshnessStatus.STALE,
            degraded_status=DegradedStatus.NONE,
        )
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 200
            assert resp.json()["status"] == "stale"
        finally:
            app.dependency_overrides.clear()

    def test_compare_response_includes_warnings_and_rationale(self) -> None:
        current = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.GOLDILOCKS,
            regime_family=RegimeFamily.EXPANSION,
            supporting_snapshot_id="snap-2",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
            transition=RegimeTransition(
                transition_from_prior="slowdown",
                transition_type=RegimeTransitionType.SHIFT,
                changed=True,
            ),
            rationale_summary="growth=accelerating, inflation=cooling",
            warnings=[],
        )
        previous = MacroRegime(
            as_of_date=date(2026, 3, 1),
            regime_timestamp=datetime(2026, 3, 1, tzinfo=UTC),
            regime_label=RegimeLabel.SLOWDOWN,
            regime_family=RegimeFamily.DOWNSHIFT,
            supporting_snapshot_id="snap-1",
            confidence=RegimeConfidence.MEDIUM,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
        )
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            assert resp.status_code == 200
            payload = resp.json()
            assert "warnings" in payload
            assert "current_rationale_summary" in payload
            assert "is_seeded" in payload
            assert payload["current_rationale_summary"] == "growth=accelerating, inflation=cooling"
            assert payload["is_seeded"] is False
        finally:
            app.dependency_overrides.clear()
