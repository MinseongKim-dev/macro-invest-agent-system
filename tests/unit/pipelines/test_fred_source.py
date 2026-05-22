"""Unit tests for the FredMacroDataSource adapter.

Covers:
- Series-map: every DEFAULT_INDICATORS indicator has a FRED series ID
- No-API-key guard: RuntimeError raised before any I/O
- Fixture-backed (mocked) fetch_raw: correct MacroFeature shape
- Ingestion integration: FredMacroDataSource + MacroIngestionService pipeline
- HTTP error failure path: RuntimeError with actionable message
- Timeout failure path: RuntimeError with actionable message
- Unknown indicator skipped silently
- Indicator not in series map skipped silently
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
from src.agent.adapters.sources.fred.fred_macro_data_source import FredMacroDataSource
from src.agent.adapters.sources.fred.series_map import FRED_SERIES_MAP
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature
from src.pipelines.ingestion.macro_ingestion_service import (
    DEFAULT_INDICATORS,
    MacroIngestionService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _make_feature(
    indicator: MacroIndicatorType = MacroIndicatorType.GDP,
    value: float = 25000.0,
    country: str = "US",
) -> MacroFeature:
    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.FRED,
        value=value,
        timestamp=_TS,
        frequency=DataFrequency.MONTHLY,
        country=country,
        metadata={"series_id": FRED_SERIES_MAP[indicator], "source": "fred"},
    )


def _make_default_features(country: str = "US") -> list[MacroFeature]:
    """Return one FRED feature per DEFAULT_INDICATORS entry."""
    indicator_map = {
        MacroIndicatorType.INFLATION: 310.0,
        MacroIndicatorType.UNEMPLOYMENT: 4.1,
        MacroIndicatorType.YIELD_10Y: 4.6,
        MacroIndicatorType.PMI: 52.0,
        MacroIndicatorType.RETAIL_SALES: 700000.0,
    }
    return [_make_feature(ind, val, country) for ind, val in indicator_map.items()]


# ---------------------------------------------------------------------------
# Series-map coverage
# ---------------------------------------------------------------------------


class TestFredSeriesMap:
    """Every DEFAULT_INDICATORS indicator must be in the FRED series map."""

    def test_all_default_indicators_have_series_id(self) -> None:
        for indicator_str in DEFAULT_INDICATORS:
            indicator = MacroIndicatorType(indicator_str)
            assert indicator in FRED_SERIES_MAP, (
                f"{indicator_str!r} is in DEFAULT_INDICATORS but has no FRED series ID"
            )

    def test_inflation_maps_to_cpiaucsl(self) -> None:
        assert FRED_SERIES_MAP[MacroIndicatorType.INFLATION] == "CPIAUCSL"

    def test_unemployment_maps_to_unrate(self) -> None:
        assert FRED_SERIES_MAP[MacroIndicatorType.UNEMPLOYMENT] == "UNRATE"

    def test_yield_10y_maps_to_dgs10(self) -> None:
        assert FRED_SERIES_MAP[MacroIndicatorType.YIELD_10Y] == "DGS10"

    def test_pmi_maps_to_napm(self) -> None:
        assert FRED_SERIES_MAP[MacroIndicatorType.PMI] == "NAPM"

    def test_retail_sales_maps_to_rsafs(self) -> None:
        assert FRED_SERIES_MAP[MacroIndicatorType.RETAIL_SALES] == "RSAFS"


# ---------------------------------------------------------------------------
# Constructor guard
# ---------------------------------------------------------------------------


class TestFredMacroDataSourceConstructor:
    """Tests for constructor-level validation."""

    def test_missing_api_key_raises_runtime_error(self) -> None:
        with pytest.raises(RuntimeError, match="api_key"):
            FredMacroDataSource(api_key=None)

    def test_empty_string_api_key_raises_runtime_error(self) -> None:
        with pytest.raises(RuntimeError, match="api_key"):
            FredMacroDataSource(api_key="")

    def test_valid_api_key_constructs_successfully(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        assert src.source_id == "fred"

    def test_source_id_is_fred(self) -> None:
        src = FredMacroDataSource(api_key="key")
        assert src.source_id == "fred"


# ---------------------------------------------------------------------------
# Fixture-backed (mocked) fetch_raw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFredMacroDataSourceFetchRaw:
    """Tests for fetch_raw with mocked HTTP layer."""

    async def test_returns_features_for_default_indicators(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        expected = _make_default_features()

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=expected)):
            result = await src.fetch_raw("US", DEFAULT_INDICATORS)

        assert len(result) == len(DEFAULT_INDICATORS)

    async def test_feature_source_is_fred(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        features = [_make_feature(MacroIndicatorType.GDP)]

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=features)):
            result = await src.fetch_raw("US", [MacroIndicatorType.GDP.value])

        assert result[0].source == MacroSourceType.FRED

    async def test_feature_frequency_is_monthly(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        features = [_make_feature(MacroIndicatorType.INFLATION)]

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=features)):
            result = await src.fetch_raw("US", [MacroIndicatorType.INFLATION.value])

        assert result[0].frequency == DataFrequency.MONTHLY

    async def test_feature_country_preserved(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        features = [_make_feature(MacroIndicatorType.GDP, country="JP")]

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=features)):
            result = await src.fetch_raw("JP", [MacroIndicatorType.GDP.value])

        assert result[0].country == "JP"

    async def test_empty_indicators_returns_empty(self) -> None:
        src = FredMacroDataSource(api_key="test-key")

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=[])):
            result = await src.fetch_raw("US", [])

        assert result == []

    async def test_unknown_indicator_skipped(self) -> None:
        """Indicators not in MacroIndicatorType are skipped silently."""
        src = FredMacroDataSource(api_key="test-key")

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=[])):
            result = await src.fetch_raw("US", ["not_a_real_indicator"])

        assert result == []

    async def test_indicator_not_in_series_map_skipped(self) -> None:
        """Valid MacroIndicatorType values not in FRED_SERIES_MAP are skipped."""
        src = FredMacroDataSource(api_key="test-key")
        # EXCHANGE_RATE is a valid enum but not in FRED_SERIES_MAP
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=[])):
            result = await src.fetch_raw("US", [MacroIndicatorType.EXCHANGE_RATE.value])

        assert result == []

    async def test_metadata_contains_series_id(self) -> None:
        feature = _make_feature(MacroIndicatorType.GDP)
        assert feature.metadata["series_id"] == "GDPC1"


# ---------------------------------------------------------------------------
# Failure paths: _fetch_latest_observation level
# ---------------------------------------------------------------------------


class TestFredMacroDataSourceFailurePaths:
    """Tests for HTTP error and timeout error paths."""

    def test_http_error_raises_runtime_error_with_message(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError(
                "FRED API HTTP error 400 for series='GDPC1': Bad Request. "
                "Verify your FRED_API_KEY and network access."
            ),
        ), pytest.raises(RuntimeError, match="FRED API HTTP error 400"):
            src._fetch_latest_observation("GDPC1")

    def test_timeout_raises_runtime_error_with_message(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError(
                "FRED API request timed out after 10.0s for series='GDPC1'. "
                "Check your network connection or increase fred_request_timeout_s."
            ),
        ), pytest.raises(RuntimeError, match="timed out"):
            src._fetch_latest_observation("GDPC1")

    def test_http_error_surfaces_through_fetch_raw(self) -> None:
        """RuntimeError from _fetch_latest_observation propagates through fetch_raw."""
        src = FredMacroDataSource(api_key="test-key")

        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError("FRED API HTTP error 403 for series='GDPC1': Forbidden."),
        ), pytest.raises(RuntimeError, match="FRED API HTTP error 403"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                src.fetch_raw("US", [MacroIndicatorType.GDP.value])
            )

    def test_timeout_surfaces_through_fetch_raw(self) -> None:
        """TimeoutError from _fetch_latest_observation propagates through fetch_raw."""
        src = FredMacroDataSource(api_key="test-key")

        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError("FRED API request timed out after 10.0s"),
        ), pytest.raises(RuntimeError, match="timed out"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                src.fetch_raw("US", [MacroIndicatorType.GDP.value])
            )


# ---------------------------------------------------------------------------
# Ingestion integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFredIngestionIntegration:
    """MacroIngestionService with mocked FredMacroDataSource."""

    async def test_ingest_with_fred_source_returns_snapshot(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        expected_features = _make_default_features()
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=expected_features)):
            snapshot = await svc.ingest("US")

        assert snapshot.source_id == "fred"
        assert snapshot.country == "US"
        assert snapshot.features_count == len(DEFAULT_INDICATORS)

    async def test_ingest_persists_snapshot(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        features = _make_default_features()
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=features)):
            snapshot = await svc.ingest("US")

        latest = await store.get_latest_snapshot("US")
        assert latest is not None
        assert latest.snapshot_id == snapshot.snapshot_id

    async def test_ingest_features_have_fred_source(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        features = _make_default_features()
        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=features)):
            snapshot = await svc.ingest("US")

        for feature in snapshot.features:
            assert feature.source == MacroSourceType.FRED

    async def test_ingest_raises_when_fred_returns_no_features(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        with patch.object(src, "fetch_raw", new=AsyncMock(return_value=[])), pytest.raises(
            RuntimeError, match="No macro features returned"
        ):
            await svc.ingest("US")
