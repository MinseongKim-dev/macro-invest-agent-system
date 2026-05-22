"""Phase 1 macro data foundation tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.agent.adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
from src.agent.adapters.sources.fixture_macro_data_source import FixtureMacroDataSource
from src.domain.macro.enums import DataFrequency, MacroIndicatorType
from src.pipelines.ingestion.indicator_catalog import (
    INDICATOR_CATALOG,
    PRIORITY_INDICATORS,
    get_active_catalog_entries,
)
from src.pipelines.ingestion.macro_ingestion_service import MacroIngestionService
from src.pipelines.ingestion.models import (
    FeatureSnapshot,
    FreshnessStatus,
    RawFeatureRecord,
    RevisionStatus,
    build_normalized_observation,
)


class TestPhase1IndicatorCatalog:
    def test_priority_set_is_small_and_explicit(self) -> None:
        assert PRIORITY_INDICATORS == (
            MacroIndicatorType.INFLATION,
            MacroIndicatorType.UNEMPLOYMENT,
            MacroIndicatorType.YIELD_10Y,
            MacroIndicatorType.PMI,
            MacroIndicatorType.RETAIL_SALES,
        )

    def test_catalog_entries_have_source_and_frequency(self) -> None:
        for indicator in PRIORITY_INDICATORS:
            entry = INDICATOR_CATALOG[indicator]
            assert entry.source_id
            assert entry.source_series_id
            assert isinstance(entry.frequency, DataFrequency)

    def test_active_entries_deterministic_order(self) -> None:
        entries = get_active_catalog_entries()
        assert [e.indicator_id for e in entries] == list(PRIORITY_INDICATORS)


@pytest.mark.asyncio
class TestPhase1NormalizationSchema:
    async def test_observation_release_fetched_are_distinct(self) -> None:
        source = FixtureMacroDataSource()
        feature = (await source.fetch_raw("US", [MacroIndicatorType.INFLATION.value]))[0]

        fetched_at = feature.timestamp + timedelta(days=2)
        release_date = feature.timestamp + timedelta(days=1)
        normalized = build_normalized_observation(
            snapshot_id="snap-1",
            feature=feature,
            fetched_at=fetched_at,
            release_date=release_date,
            revision_status=RevisionStatus.INITIAL,
            revision_number=0,
        )

        assert normalized.observation_date == feature.timestamp
        assert normalized.release_date == release_date
        assert normalized.fetched_at == fetched_at

    async def test_freshness_late_and_stale_states(self) -> None:
        source = FixtureMacroDataSource()
        feature = (await source.fetch_raw("US", [MacroIndicatorType.PMI.value]))[0]

        late = build_normalized_observation(
            snapshot_id="snap-late",
            feature=feature,
            fetched_at=feature.timestamp + timedelta(hours=30),
            expected_max_lag_hours=24,
        )
        stale = build_normalized_observation(
            snapshot_id="snap-stale",
            feature=feature,
            fetched_at=feature.timestamp + timedelta(hours=80),
            expected_max_lag_hours=24,
        )

        assert late.freshness.status == FreshnessStatus.LATE
        assert stale.freshness.status == FreshnessStatus.STALE


@pytest.mark.asyncio
class TestPhase1RawNormalizedPersistence:
    async def test_ingestion_persists_raw_normalized_and_run(self) -> None:
        source = FixtureMacroDataSource()
        store = InMemoryFeatureStore()
        service = MacroIngestionService(source=source, repository=store)

        snapshot = await service.ingest("US")
        assert isinstance(snapshot, FeatureSnapshot)

        raw_records = store.raw_records(snapshot.snapshot_id)
        normalized_records = store.normalized_records(snapshot.snapshot_id)
        runs = store.ingestion_runs()

        assert len(raw_records) == snapshot.features_count
        assert all(isinstance(r, RawFeatureRecord) for r in raw_records)
        assert len(normalized_records) == snapshot.features_count
        assert runs[-1].snapshot_id == snapshot.snapshot_id
        assert runs[-1].requested_indicators
        assert runs[-1].success is True
