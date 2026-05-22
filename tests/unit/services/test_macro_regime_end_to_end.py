"""End-to-end Phase 3 regime flow tests (build -> persist -> compare)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import (
    InMemoryMacroSnapshotStore,
)
from src.domain.macro.snapshot import (
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
) -> MacroSnapshotState:
    return MacroSnapshotState(
        as_of_date=as_of_date,
        snapshot_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        freshness_status=FreshnessStatus.FRESH,
        growth_state=growth,
        inflation_state=inflation,
        labor_state=labor,
        policy_state=policy,
        financial_conditions_state=conditions,
    )


@pytest.mark.asyncio
async def test_phase3_regime_flow_build_save_and_compare() -> None:
    snapshot_repo = InMemoryMacroSnapshotStore()
    regime_repo = InMemoryMacroRegimeStore()
    service = MacroRegimeService(snapshot_repository=snapshot_repo, regime_repository=regime_repo)

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
    first = await service.build_and_save_regime(as_of_date=date(2026, 1, 31))
    assert first.regime_label.value in {"contraction", "policy_tightening_drag", "slowdown"}
    assert first.transition.transition_type.value == "initial"

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
    second = await service.build_and_save_regime(as_of_date=date(2026, 2, 1))
    assert second.regime_label.value == "goldilocks"
    assert second.transition.transition_type.value == "shift"

    current, previous = await service.compare_latest_with_prior(as_of_date=date(2026, 2, 1))
    assert current.regime_id == second.regime_id
    assert previous is not None
    assert previous.regime_id == first.regime_id
