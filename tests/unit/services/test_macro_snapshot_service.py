"""Tests for Phase 2 MacroSnapshotService."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.agent.adapters.repositories.in_memory_macro_snapshot_store import InMemoryMacroSnapshotStore
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.pipelines.ingestion.models import (
    FreshnessMetadata,
    FreshnessStatus,
    NormalizedMacroObservation,
)
from src.services.macro_snapshot_service import MacroSnapshotService


def _obs(
    indicator: MacroIndicatorType,
    value: float,
    ts: datetime,
) -> NormalizedMacroObservation:
    return NormalizedMacroObservation(
        snapshot_id="raw-snap",
        indicator_id=indicator,
        observation_date=ts,
        release_date=ts,
        fetched_at=ts + timedelta(hours=1),
        value=value,
        unit="index",
        frequency=DataFrequency.MONTHLY,
        source=MacroSourceType.FRED,
        source_series_id="SERIES",
        region="US",
        freshness=FreshnessMetadata(
            expected_max_lag_hours=48,
            observed_lag_hours=1.0,
            status=FreshnessStatus.FRESH,
            is_late=False,
            is_stale=False,
        ),
    )


@pytest.mark.asyncio
class TestMacroSnapshotService:
    async def test_build_and_save_snapshot(self) -> None:
        now = datetime(2026, 1, 10, tzinfo=UTC)
        observations = [
            _obs(MacroIndicatorType.INFLATION, 3.1, now),
            _obs(MacroIndicatorType.UNEMPLOYMENT, 4.0, now),
            _obs(MacroIndicatorType.YIELD_10Y, 4.7, now),
            _obs(MacroIndicatorType.PMI, 52.5, now),
            _obs(MacroIndicatorType.RETAIL_SALES, 700000.0, now),
        ]

        repo = InMemoryMacroSnapshotStore()
        svc = MacroSnapshotService(repository=repo)
        snapshot = await svc.build_and_save_snapshot(observations, as_of_date=date(2026, 1, 10))

        assert snapshot.as_of_date == date(2026, 1, 10)
        assert snapshot.degraded_status == "none"
        assert snapshot.growth_state == "accelerating"
        assert snapshot.comparison.baseline_available is False
        assert len(repo.all_snapshots()) == 1

    async def test_snapshot_comparison_with_previous(self) -> None:
        day1 = datetime(2026, 1, 9, tzinfo=UTC)
        day2 = datetime(2026, 1, 10, tzinfo=UTC)
        repo = InMemoryMacroSnapshotStore()
        svc = MacroSnapshotService(repository=repo)

        obs_day1 = [
            _obs(MacroIndicatorType.INFLATION, 2.9, day1),
            _obs(MacroIndicatorType.UNEMPLOYMENT, 4.2, day1),
            _obs(MacroIndicatorType.YIELD_10Y, 4.1, day1),
            _obs(MacroIndicatorType.PMI, 49.5, day1),
            _obs(MacroIndicatorType.RETAIL_SALES, 690000.0, day1),
        ]
        obs_day2 = [
            _obs(MacroIndicatorType.INFLATION, 3.4, day2),
            _obs(MacroIndicatorType.UNEMPLOYMENT, 3.9, day2),
            _obs(MacroIndicatorType.YIELD_10Y, 4.8, day2),
            _obs(MacroIndicatorType.PMI, 53.0, day2),
            _obs(MacroIndicatorType.RETAIL_SALES, 710000.0, day2),
        ]

        await svc.build_and_save_snapshot(obs_day1, as_of_date=date(2026, 1, 9))
        second = await svc.build_and_save_snapshot(obs_day2, as_of_date=date(2026, 1, 10))

        assert second.comparison.baseline_available is True
        assert len(second.comparison.changed_category_states) > 0
        assert len(second.comparison.changed_indicators) > 0
