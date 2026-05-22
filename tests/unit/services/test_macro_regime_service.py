"""Tests for building deterministic macro regimes from snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import InMemoryMacroSnapshotStore
from src.domain.macro.regime import RegimeConfidence, RegimeLabel, RegimeTransitionType
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
    as_of_date: date,
    growth: GrowthState,
    inflation: InflationState,
    labor: LaborState,
    policy: PolicyState,
    conditions: FinancialConditionsState,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
) -> MacroSnapshotState:
    return MacroSnapshotState(
        as_of_date=as_of_date,
        snapshot_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        freshness_status=freshness,
        degraded_status=degraded,
        growth_state=growth,
        inflation_state=inflation,
        labor_state=labor,
        policy_state=policy,
        financial_conditions_state=conditions,
        indicator_values={"inflation": 2.2},
    )


@pytest.mark.asyncio
class TestMacroRegimeService:
    async def test_build_regime_from_latest_snapshot(self) -> None:
        repo = InMemoryMacroSnapshotStore()
        await repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 2, 1),
                growth=GrowthState.ACCELERATING,
                inflation=InflationState.COOLING,
                labor=LaborState.TIGHT,
                policy=PolicyState.NEUTRAL,
                conditions=FinancialConditionsState.NEUTRAL,
            )
        )

        svc = MacroRegimeService(snapshot_repository=repo)
        regime = await svc.build_regime(as_of_date=date(2026, 2, 1))

        assert regime.as_of_date == date(2026, 2, 1)
        assert regime.regime_label == RegimeLabel.GOLDILOCKS
        assert regime.confidence == RegimeConfidence.HIGH
        assert regime.supporting_states["growth_state"] == "accelerating"

    async def test_build_regime_uses_latest_on_or_before(self) -> None:
        repo = InMemoryMacroSnapshotStore()
        await repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 1, 31),
                growth=GrowthState.SLOWING,
                inflation=InflationState.STICKY,
                labor=LaborState.WEAK,
                policy=PolicyState.RESTRICTIVE,
                conditions=FinancialConditionsState.TIGHT,
            )
        )
        svc = MacroRegimeService(snapshot_repository=repo)
        regime = await svc.build_regime(as_of_date=date(2026, 2, 2))
        assert regime.as_of_date == date(2026, 1, 31)

    async def test_build_regime_raises_without_snapshot(self) -> None:
        svc = MacroRegimeService(snapshot_repository=InMemoryMacroSnapshotStore())
        with pytest.raises(ValueError, match="No snapshot available"):
            await svc.build_regime(as_of_date=date(2026, 2, 1))

    async def test_build_and_save_persists_regime(self) -> None:
        snapshot_repo = InMemoryMacroSnapshotStore()
        regime_repo = InMemoryMacroRegimeStore()
        await snapshot_repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 2, 1),
                growth=GrowthState.ACCELERATING,
                inflation=InflationState.COOLING,
                labor=LaborState.TIGHT,
                policy=PolicyState.NEUTRAL,
                conditions=FinancialConditionsState.NEUTRAL,
            )
        )
        svc = MacroRegimeService(snapshot_repository=snapshot_repo, regime_repository=regime_repo)
        saved = await svc.build_and_save_regime(as_of_date=date(2026, 2, 1))
        latest = await svc.get_latest_regime(as_of_date=date(2026, 2, 1))
        assert latest is not None
        assert latest.regime_id == saved.regime_id
        assert saved.transition.transition_type == RegimeTransitionType.INITIAL

    async def test_build_and_save_requires_regime_repository(self) -> None:
        snapshot_repo = InMemoryMacroSnapshotStore()
        await snapshot_repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 2, 1),
                growth=GrowthState.ACCELERATING,
                inflation=InflationState.COOLING,
                labor=LaborState.TIGHT,
                policy=PolicyState.NEUTRAL,
                conditions=FinancialConditionsState.NEUTRAL,
            )
        )
        svc = MacroRegimeService(snapshot_repository=snapshot_repo)
        with pytest.raises(ValueError, match="Regime repository is not configured"):
            await svc.build_and_save_regime(as_of_date=date(2026, 2, 1))

    async def test_build_and_save_sets_shift_transition_with_prior(self) -> None:
        snapshot_repo = InMemoryMacroSnapshotStore()
        regime_repo = InMemoryMacroRegimeStore()
        svc = MacroRegimeService(snapshot_repository=snapshot_repo, regime_repository=regime_repo)

        await snapshot_repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 1, 31),
                growth=GrowthState.SLOWING,
                inflation=InflationState.STICKY,
                labor=LaborState.WEAK,
                policy=PolicyState.RESTRICTIVE,
                conditions=FinancialConditionsState.TIGHT,
            )
        )
        first = await svc.build_and_save_regime(as_of_date=date(2026, 1, 31))
        assert first.transition.transition_type == RegimeTransitionType.INITIAL

        await snapshot_repo.save_snapshot(
            _snapshot(
                as_of_date=date(2026, 2, 1),
                growth=GrowthState.ACCELERATING,
                inflation=InflationState.COOLING,
                labor=LaborState.TIGHT,
                policy=PolicyState.NEUTRAL,
                conditions=FinancialConditionsState.NEUTRAL,
            )
        )
        second = await svc.build_and_save_regime(as_of_date=date(2026, 2, 1))
        assert second.transition.transition_type == RegimeTransitionType.SHIFT
        assert second.transition.changed is True
