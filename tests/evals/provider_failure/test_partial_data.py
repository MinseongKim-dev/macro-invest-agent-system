"""Eval: FRED returns partial data (3 of 5 indicators).

Verifies that when FRED returns only 3 of the 5 DEFAULT_INDICATORS, the
FeatureSnapshot.features_count reflects the actual partial count (3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
from adapters.sources.fred import FredMacroDataSource
from adapters.sources.fred.series_map import FRED_SERIES_MAP
from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature
from pipelines.ingestion.macro_ingestion_service import MacroIngestionService


def _make_partial_features(count: int = 3) -> list[MacroFeature]:
    """Return a list of *count* valid FRED features."""
    indicators = [
        MacroIndicatorType.GDP,
        MacroIndicatorType.INFLATION,
        MacroIndicatorType.UNEMPLOYMENT,
    ][:count]
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        MacroFeature(
            indicator_type=ind,
            source=MacroSourceType.FRED,
            value=50.0,
            timestamp=ts,
            frequency=DataFrequency.MONTHLY,
            country="US",
            metadata={"series_id": FRED_SERIES_MAP[ind], "source": "fred"},
        )
        for ind in indicators
    ]


@pytest.mark.asyncio
class TestPartialDataEval:
    """Partial FRED data flows through the ingestion pipeline correctly."""

    async def test_features_count_equals_partial_count(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        partial = _make_partial_features(3)
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=partial)):
            snapshot = await svc.ingest("US")

        assert snapshot.features_count == 3

    async def test_partial_snapshot_is_persisted(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        partial = _make_partial_features(3)
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=partial)):
            snapshot = await svc.ingest("US")

        latest = await store.get_latest_snapshot("US")
        assert latest is not None
        assert latest.snapshot_id == snapshot.snapshot_id

    async def test_partial_features_have_correct_source(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        partial = _make_partial_features(3)
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=partial)):
            snapshot = await svc.ingest("US")

        for feature in snapshot.features:
            assert feature.source == MacroSourceType.FRED

    async def test_single_feature_is_sufficient(self) -> None:
        """Even 1 feature from FRED should succeed the ingestion run."""
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        partial = _make_partial_features(1)
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=partial)):
            snapshot = await svc.ingest("US")

        assert snapshot.features_count == 1
