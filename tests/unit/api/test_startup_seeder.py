"""Tests for the startup seeder — seed_regime_from_synthetic_observations."""

from __future__ import annotations

from datetime import date

import pytest

from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import InMemoryMacroSnapshotStore
from apps.api.startup_seeder import (
    SEEDER_METADATA,
    SeedStatus,
    seed_regime_from_synthetic_observations,
)
from src.domain.macro.regime import RegimeLabel
from src.services.macro_regime_service import MacroRegimeService
from src.services.macro_snapshot_service import MacroSnapshotService


@pytest.fixture()
def snapshot_store() -> InMemoryMacroSnapshotStore:
    return InMemoryMacroSnapshotStore()


@pytest.fixture()
def regime_store() -> InMemoryMacroRegimeStore:
    return InMemoryMacroRegimeStore()


@pytest.fixture()
def snapshot_service(snapshot_store: InMemoryMacroSnapshotStore) -> MacroSnapshotService:
    return MacroSnapshotService(repository=snapshot_store)


@pytest.fixture()
def regime_service(
    snapshot_store: InMemoryMacroSnapshotStore,
    regime_store: InMemoryMacroRegimeStore,
) -> MacroRegimeService:
    return MacroRegimeService(
        snapshot_repository=snapshot_store,
        regime_repository=regime_store,
    )


@pytest.mark.asyncio
async def test_seeder_populates_regime_store(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    regime_store: InMemoryMacroRegimeStore,
) -> None:
    """After seeding, the regime store contains exactly one regime."""
    assert regime_store.all_regimes() == []

    status = await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    assert status.success is True
    assert status.skipped is False
    regimes = regime_store.all_regimes()
    assert len(regimes) == 1


@pytest.mark.asyncio
async def test_seeder_regime_has_known_label(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    regime_store: InMemoryMacroRegimeStore,
) -> None:
    """The seeded regime label must be a valid, non-UNCLEAR label."""
    await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    regime = regime_store.all_regimes()[0]
    assert regime.regime_label in {
        RegimeLabel.SLOWDOWN,
        RegimeLabel.POLICY_TIGHTENING_DRAG,
        RegimeLabel.STAGFLATION_RISK,
        RegimeLabel.CONTRACTION,
    }


@pytest.mark.asyncio
async def test_seeder_regime_carries_synthetic_metadata(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    regime_store: InMemoryMacroRegimeStore,
) -> None:
    """Seeded regime must have metadata distinguishing it from production data."""
    await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    regime = regime_store.all_regimes()[0]
    assert regime.metadata.get("seeded") == "true"
    assert regime.metadata.get("source") == "synthetic_seed"
    assert regime.metadata.get("seed_version") is not None
    for key, value in SEEDER_METADATA.items():
        assert regime.metadata.get(key) == value


@pytest.mark.asyncio
async def test_seeder_is_idempotent(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    regime_store: InMemoryMacroRegimeStore,
) -> None:
    """Calling the seeder twice does not add a second regime (idempotent)."""
    target = date(2026, 4, 1)

    status1 = await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=target,
    )
    assert status1.success is True
    assert status1.skipped is False

    status2 = await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=target,
    )
    assert status2.success is True
    assert status2.skipped is True
    assert len(regime_store.all_regimes()) == 1


@pytest.mark.asyncio
async def test_seeder_regime_is_retrievable_via_service(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
) -> None:
    """After seeding, get_latest_regime returns the seeded regime."""
    target = date(2026, 4, 1)
    await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=target,
    )

    regime = await regime_service.get_latest_regime(as_of_date=target)
    assert regime is not None
    assert regime.as_of_date == target


@pytest.mark.asyncio
async def test_seeder_regime_transition_is_initial(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
) -> None:
    """The first seeded regime has transition_type=initial (no prior baseline)."""
    await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    regime = await regime_service.get_latest_regime(as_of_date=date(2026, 4, 1))
    assert regime is not None
    assert regime.transition.transition_type.value == "initial"


@pytest.mark.asyncio
async def test_seeder_snapshot_is_populated(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    snapshot_store: InMemoryMacroSnapshotStore,
) -> None:
    """After seeding, snapshot store contains one snapshot with derived state values."""
    await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    snapshots = snapshot_store.all_snapshots()
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.growth_state.value != "unknown"
    assert snap.inflation_state.value != "unknown"
    assert snap.labor_state.value != "unknown"
    assert snap.policy_state.value != "unknown"
    assert snap.financial_conditions_state.value != "unknown"


@pytest.mark.asyncio
async def test_seeder_returns_success_status(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
) -> None:
    """SeedStatus.success is True and regime_id is populated on a fresh store."""
    status = await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
        as_of_date=date(2026, 4, 1),
    )

    assert isinstance(status, SeedStatus)
    assert status.success is True
    assert status.error is None
    assert status.regime_id is not None
