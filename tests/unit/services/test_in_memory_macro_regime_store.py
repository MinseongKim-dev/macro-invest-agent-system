"""Tests for in-memory macro regime persistence adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.domain.macro.regime import MacroRegime, RegimeFamily, RegimeLabel


def _regime(as_of_date: date, snapshot_id: str) -> MacroRegime:
    return MacroRegime(
        as_of_date=as_of_date,
        regime_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        regime_label=RegimeLabel.GOLDILOCKS,
        regime_family=RegimeFamily.EXPANSION,
        supporting_snapshot_id=snapshot_id,
    )


@pytest.mark.asyncio
class TestInMemoryMacroRegimeStore:
    async def test_save_and_get_by_id(self) -> None:
        store = InMemoryMacroRegimeStore()
        regime = _regime(date(2026, 2, 1), "snap-1")
        await store.save_regime(regime)
        loaded = await store.get_regime_by_id(regime.regime_id)
        assert loaded is not None
        assert loaded.regime_id == regime.regime_id

    async def test_get_latest_on_or_before(self) -> None:
        store = InMemoryMacroRegimeStore()
        r1 = _regime(date(2026, 1, 30), "snap-1")
        r2 = _regime(date(2026, 2, 1), "snap-2")
        await store.save_regime(r1)
        await store.save_regime(r2)
        loaded = await store.get_latest_on_or_before(date(2026, 2, 2))
        assert loaded is not None
        assert loaded.supporting_snapshot_id == "snap-2"
