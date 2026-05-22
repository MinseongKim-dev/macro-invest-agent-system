"""Tests for InMemoryMacroRegimeStore.list_recent and InMemoryMacroSnapshotStore.list_recent."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import InMemoryMacroSnapshotStore
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
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


def _regime(as_of_date: date) -> MacroRegime:
    return MacroRegime(
        as_of_date=as_of_date,
        regime_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        regime_label=RegimeLabel.GOLDILOCKS,
        regime_family=RegimeFamily.EXPANSION,
        supporting_snapshot_id="snap-1",
        confidence=RegimeConfidence.HIGH,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        transition=RegimeTransition(transition_type=RegimeTransitionType.INITIAL),
    )


def _snapshot(as_of_date: date) -> MacroSnapshotState:
    return MacroSnapshotState(
        as_of_date=as_of_date,
        snapshot_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        growth_state=GrowthState.ACCELERATING,
        inflation_state=InflationState.COOLING,
        labor_state=LaborState.TIGHT,
        policy_state=PolicyState.NEUTRAL,
        financial_conditions_state=FinancialConditionsState.NEUTRAL,
    )


class TestInMemoryMacroRegimeStoreListRecent:
    def _store_with_regimes(self, dates: list[date]) -> InMemoryMacroRegimeStore:
        store = InMemoryMacroRegimeStore()
        for d in dates:
            asyncio.get_event_loop().run_until_complete(store.save_regime(_regime(d)))
        return store

    def test_empty_store_returns_empty_list(self) -> None:
        store = InMemoryMacroRegimeStore()
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 3, 1))
        )
        assert result == []

    def test_returns_most_recent_first(self) -> None:
        dates = [date(2026, 1, d) for d in [1, 5, 3]]
        store = self._store_with_regimes(dates)
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 1, 10))
        )
        result_dates = [r.as_of_date for r in result]
        assert result_dates == sorted(dates, reverse=True)

    def test_limit_applied(self) -> None:
        dates = [date(2026, 1, d) for d in range(1, 11)]
        store = self._store_with_regimes(dates)
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 1, 31), limit=3)
        )
        assert len(result) == 3

    def test_excludes_future_regimes(self) -> None:
        store = self._store_with_regimes([date(2026, 6, 1), date(2026, 1, 1)])
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 3, 1))
        )
        assert len(result) == 1
        assert result[0].as_of_date == date(2026, 1, 1)

    def test_default_limit_is_10(self) -> None:
        dates = [date(2026, 1, d) for d in range(1, 16)]  # 15 regimes
        store = self._store_with_regimes(dates)
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 1, 31))
        )
        assert len(result) == 10

    def test_as_of_date_inclusive(self) -> None:
        store = self._store_with_regimes([date(2026, 2, 1)])
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 2, 1))
        )
        assert len(result) == 1


class TestInMemoryMacroSnapshotStoreListRecent:
    def _store_with_snapshots(self, dates: list[date]) -> InMemoryMacroSnapshotStore:
        store = InMemoryMacroSnapshotStore()
        for d in dates:
            asyncio.get_event_loop().run_until_complete(store.save_snapshot(_snapshot(d)))
        return store

    def test_empty_store_returns_empty(self) -> None:
        store = InMemoryMacroSnapshotStore()
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 3, 1))
        )
        assert result == []

    def test_returns_most_recent_first(self) -> None:
        dates = [date(2026, 1, d) for d in [1, 5, 3]]
        store = self._store_with_snapshots(dates)
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 1, 10))
        )
        result_dates = [s.as_of_date for s in result]
        assert result_dates == sorted(dates, reverse=True)

    def test_limit_applied(self) -> None:
        dates = [date(2026, 1, d) for d in range(1, 8)]
        store = self._store_with_snapshots(dates)
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 1, 31), limit=2)
        )
        assert len(result) == 2

    def test_excludes_future_snapshots(self) -> None:
        store = self._store_with_snapshots([date(2026, 6, 1), date(2026, 1, 1)])
        result = asyncio.get_event_loop().run_until_complete(
            store.list_recent(as_of_date=date(2026, 3, 1))
        )
        assert len(result) == 1
        assert result[0].as_of_date == date(2026, 1, 1)
