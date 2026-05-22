"""Unit tests for the data pipeline ingestion layer.

Covers:
- MacroIngestionService: happy path, empty-features error, custom indicators
- InMemoryFeatureStore: save/get_latest/list_snapshots behaviour
- FixtureMacroDataSource: deterministic output, unknown indicator skipping
- InMemoryMacroDataSource: set_feature / fetch_raw round-trip
- FeatureSnapshot model: field validation, features_count derivation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.agent.adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
from src.agent.adapters.sources.fixture_macro_data_source import FixtureMacroDataSource
from src.agent.adapters.sources.in_memory_macro_data_source import InMemoryMacroDataSource
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature
from src.pipelines.ingestion.macro_ingestion_service import DEFAULT_INDICATORS, MacroIngestionService
from src.pipelines.ingestion.models import FeatureSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(
    indicator: MacroIndicatorType = MacroIndicatorType.GDP,
    value: float = 100.0,
    country: str = "US",
) -> MacroFeature:
    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.CUSTOM,
        value=value,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        frequency=DataFrequency.MONTHLY,
        country=country,
    )


def _make_snapshot(country: str = "US", n_features: int = 2) -> FeatureSnapshot:
    features = [
        _make_feature(MacroIndicatorType.GDP, country=country),
        _make_feature(MacroIndicatorType.INFLATION, country=country),
    ][:n_features]
    return FeatureSnapshot(country=country, source_id="test", features=features)


# ---------------------------------------------------------------------------
# FeatureSnapshot model
# ---------------------------------------------------------------------------


class TestFeatureSnapshotModel:
    """Tests for FeatureSnapshot field validation."""

    def test_features_count_derived_from_features(self) -> None:
        features = [
            _make_feature(MacroIndicatorType.GDP),
            _make_feature(MacroIndicatorType.INFLATION),
            _make_feature(MacroIndicatorType.UNEMPLOYMENT),
        ]
        snapshot = FeatureSnapshot(country="US", source_id="x", features=features)
        assert snapshot.features_count == 3

    def test_snapshot_id_is_generated(self) -> None:
        snapshot = _make_snapshot()
        assert len(snapshot.snapshot_id) > 0

    def test_two_snapshots_have_different_ids(self) -> None:
        s1 = _make_snapshot()
        s2 = _make_snapshot()
        assert s1.snapshot_id != s2.snapshot_id

    def test_empty_features_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            FeatureSnapshot(country="US", source_id="x", features=[])

    def test_empty_country_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            FeatureSnapshot(country="", source_id="x", features=[_make_feature()])

    def test_ingested_at_defaults_to_utc_now(self) -> None:
        snapshot = _make_snapshot()
        assert snapshot.ingested_at.tzinfo is not None

    def test_round_trip(self) -> None:
        snapshot = _make_snapshot()
        reparsed = FeatureSnapshot.model_validate(snapshot.model_dump())
        assert reparsed.snapshot_id == snapshot.snapshot_id
        assert reparsed.features_count == snapshot.features_count


# ---------------------------------------------------------------------------
# FixtureMacroDataSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFixtureMacroDataSource:
    """Tests for FixtureMacroDataSource."""

    async def test_source_id_is_fixture(self) -> None:
        src = FixtureMacroDataSource()
        assert src.source_id == "fixture"

    async def test_returns_features_for_known_indicators(self) -> None:
        src = FixtureMacroDataSource()
        features = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert len(features) == 1
        assert features[0].indicator_type == MacroIndicatorType.GDP

    async def test_unknown_indicator_is_skipped(self) -> None:
        src = FixtureMacroDataSource()
        features = await src.fetch_raw("US", ["not_a_real_indicator"])
        assert features == []

    async def test_mixed_indicators_skips_unknown(self) -> None:
        src = FixtureMacroDataSource()
        features = await src.fetch_raw(
            "US", [MacroIndicatorType.GDP.value, "bad_indicator"]
        )
        assert len(features) == 1
        assert features[0].indicator_type == MacroIndicatorType.GDP

    async def test_empty_indicators_returns_empty(self) -> None:
        src = FixtureMacroDataSource()
        features = await src.fetch_raw("US", [])
        assert features == []

    async def test_output_is_deterministic(self) -> None:
        src = FixtureMacroDataSource()
        f1 = await src.fetch_raw("US", [MacroIndicatorType.INFLATION.value])
        f2 = await src.fetch_raw("US", [MacroIndicatorType.INFLATION.value])
        assert f1[0].value == f2[0].value
        assert f1[0].timestamp == f2[0].timestamp

    async def test_country_override_respected(self) -> None:
        src = FixtureMacroDataSource(country_override="GB")
        features = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert features[0].country == "GB"

    async def test_country_passed_through_without_override(self) -> None:
        src = FixtureMacroDataSource()
        features = await src.fetch_raw("JP", [MacroIndicatorType.GDP.value])
        assert features[0].country == "JP"

    async def test_returns_multiple_features(self) -> None:
        src = FixtureMacroDataSource()
        indicators = [MacroIndicatorType.GDP.value, MacroIndicatorType.INFLATION.value]
        features = await src.fetch_raw("US", indicators)
        assert len(features) == 2


# ---------------------------------------------------------------------------
# InMemoryMacroDataSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInMemoryMacroDataSource:
    """Tests for InMemoryMacroDataSource."""

    async def test_source_id_is_in_memory(self) -> None:
        src = InMemoryMacroDataSource()
        assert src.source_id == "in_memory"

    async def test_empty_store_returns_empty(self) -> None:
        src = InMemoryMacroDataSource()
        features = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert features == []

    async def test_set_and_fetch_feature(self) -> None:
        src = InMemoryMacroDataSource()
        feature = _make_feature(MacroIndicatorType.GDP, value=99.0)
        src.set_feature("US", MacroIndicatorType.GDP.value, feature)

        result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert len(result) == 1
        assert result[0].value == 99.0

    async def test_fetch_only_returns_stored_indicators(self) -> None:
        src = InMemoryMacroDataSource()
        src.set_feature("US", MacroIndicatorType.GDP.value, _make_feature(MacroIndicatorType.GDP))

        result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value, MacroIndicatorType.INFLATION.value])
        assert len(result) == 1
        assert result[0].indicator_type == MacroIndicatorType.GDP

    async def test_country_isolation(self) -> None:
        src = InMemoryMacroDataSource()
        src.set_feature("US", MacroIndicatorType.GDP.value, _make_feature(MacroIndicatorType.GDP, country="US"))
        src.set_feature("GB", MacroIndicatorType.GDP.value, _make_feature(MacroIndicatorType.GDP, country="GB"))

        us_result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        gb_result = await src.fetch_raw("GB", [MacroIndicatorType.GDP.value])
        assert us_result[0].country == "US"
        assert gb_result[0].country == "GB"

    async def test_clear_removes_all_features(self) -> None:
        src = InMemoryMacroDataSource()
        src.set_feature("US", MacroIndicatorType.GDP.value, _make_feature())
        src.clear()

        result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert result == []

    async def test_initial_features_accepted(self) -> None:
        feature = _make_feature(MacroIndicatorType.GDP)
        src = InMemoryMacroDataSource(
            initial_features={("US", MacroIndicatorType.GDP.value): feature}
        )
        result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# InMemoryFeatureStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInMemoryFeatureStore:
    """Tests for InMemoryFeatureStore."""

    async def test_empty_store_returns_none_for_latest(self) -> None:
        store = InMemoryFeatureStore()
        result = await store.get_latest_snapshot("US")
        assert result is None

    async def test_save_and_get_latest(self) -> None:
        store = InMemoryFeatureStore()
        snapshot = _make_snapshot()
        await store.save_snapshot(snapshot)

        latest = await store.get_latest_snapshot("US")
        assert latest is not None
        assert latest.snapshot_id == snapshot.snapshot_id

    async def test_get_latest_returns_most_recent(self) -> None:
        store = InMemoryFeatureStore()
        s1 = _make_snapshot()
        s2 = _make_snapshot()
        await store.save_snapshot(s1)
        await store.save_snapshot(s2)

        latest = await store.get_latest_snapshot("US")
        assert latest is not None
        assert latest.snapshot_id == s2.snapshot_id

    async def test_country_isolation(self) -> None:
        store = InMemoryFeatureStore()
        us_snapshot = _make_snapshot(country="US")
        gb_snapshot = _make_snapshot(country="GB")
        await store.save_snapshot(us_snapshot)
        await store.save_snapshot(gb_snapshot)

        assert (await store.get_latest_snapshot("US")).snapshot_id == us_snapshot.snapshot_id  # type: ignore[union-attr]
        assert (await store.get_latest_snapshot("GB")).snapshot_id == gb_snapshot.snapshot_id  # type: ignore[union-attr]

    async def test_list_snapshots_empty(self) -> None:
        store = InMemoryFeatureStore()
        result = await store.list_snapshots("US")
        assert result == []

    async def test_list_snapshots_ordered_newest_first(self) -> None:
        store = InMemoryFeatureStore()
        s1 = _make_snapshot()
        s2 = _make_snapshot()
        await store.save_snapshot(s1)
        await store.save_snapshot(s2)

        result = await store.list_snapshots("US")
        assert result[0].snapshot_id == s2.snapshot_id
        assert result[1].snapshot_id == s1.snapshot_id

    async def test_list_snapshots_respects_limit(self) -> None:
        store = InMemoryFeatureStore()
        for _ in range(5):
            await store.save_snapshot(_make_snapshot())

        result = await store.list_snapshots("US", limit=3)
        assert len(result) == 3

    async def test_save_wrong_type_raises_type_error(self) -> None:
        store = InMemoryFeatureStore()
        with pytest.raises(TypeError, match="Expected FeatureSnapshot"):
            await store.save_snapshot("not a snapshot")

    async def test_all_snapshots_returns_insertion_order(self) -> None:
        store = InMemoryFeatureStore()
        s1 = _make_snapshot(country="US")
        s2 = _make_snapshot(country="GB")
        await store.save_snapshot(s1)
        await store.save_snapshot(s2)

        all_snaps = store.all_snapshots()
        assert all_snaps[0].snapshot_id == s1.snapshot_id
        assert all_snaps[1].snapshot_id == s2.snapshot_id


# ---------------------------------------------------------------------------
# MacroIngestionService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMacroIngestionService:
    """Tests for MacroIngestionService."""

    def _make_service(
        self,
        source: FixtureMacroDataSource | InMemoryMacroDataSource | None = None,
        repository: InMemoryFeatureStore | None = None,
    ) -> tuple[MacroIngestionService, InMemoryFeatureStore]:
        store = repository or InMemoryFeatureStore()
        svc = MacroIngestionService(
            source=source or FixtureMacroDataSource(),
            repository=store,
        )
        return svc, store

    async def test_ingest_returns_feature_snapshot(self) -> None:
        svc, _ = self._make_service()
        snapshot = await svc.ingest("US")
        assert isinstance(snapshot, FeatureSnapshot)

    async def test_ingest_uses_default_indicators(self) -> None:
        svc, _ = self._make_service()
        snapshot = await svc.ingest("US")
        assert snapshot.features_count == len(DEFAULT_INDICATORS)

    async def test_ingest_uses_custom_indicators(self) -> None:
        svc, _ = self._make_service()
        snapshot = await svc.ingest("US", indicators=[MacroIndicatorType.GDP.value])
        assert snapshot.features_count == 1
        assert snapshot.features[0].indicator_type == MacroIndicatorType.GDP

    async def test_ingest_persists_snapshot(self) -> None:
        svc, store = self._make_service()
        snapshot = await svc.ingest("US")

        latest = await store.get_latest_snapshot("US")
        assert latest is not None
        assert latest.snapshot_id == snapshot.snapshot_id

    async def test_ingest_sets_correct_country(self) -> None:
        svc, _ = self._make_service()
        snapshot = await svc.ingest("JP")
        assert snapshot.country == "JP"

    async def test_ingest_sets_source_id(self) -> None:
        svc, _ = self._make_service(source=FixtureMacroDataSource())
        snapshot = await svc.ingest("US")
        assert snapshot.source_id == "fixture"

    async def test_ingest_raises_on_empty_features(self) -> None:
        empty_source = InMemoryMacroDataSource()  # no features stored
        svc, _ = self._make_service(source=empty_source)

        with pytest.raises(RuntimeError, match="No macro features returned"):
            await svc.ingest("US")

    async def test_multiple_ingestions_stack_in_store(self) -> None:
        svc, store = self._make_service()
        await svc.ingest("US")
        await svc.ingest("US")

        snapshots = await store.list_snapshots("US")
        assert len(snapshots) == 2

    async def test_ingestion_with_in_memory_source(self) -> None:
        source = InMemoryMacroDataSource()
        source.set_feature("DE", MacroIndicatorType.GDP.value, _make_feature(MacroIndicatorType.GDP, country="DE"))
        svc, _ = self._make_service(source=source)

        snapshot = await svc.ingest("DE", indicators=[MacroIndicatorType.GDP.value])
        assert snapshot.features_count == 1
        assert snapshot.features[0].country == "DE"
