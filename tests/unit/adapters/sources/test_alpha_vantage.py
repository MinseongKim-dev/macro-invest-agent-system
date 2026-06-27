"""Unit tests for the Alpha Vantage adapter.

Covers:
- Series map: every mapped indicator has a valid AVSeriesConfig
- No-API-key guard: RuntimeError raised before any I/O
- Normalizer: valid values, missing sentinel, non-numeric, out-of-range
- Adapter construction and internal extraction helpers
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agent.adapters.sources.alpha_vantage.normalizer import normalize_av_observation
from src.agent.adapters.sources.alpha_vantage.series_map import ALPHA_VANTAGE_SERIES_MAP
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType

_TS = datetime(2026, 1, 1, tzinfo=UTC)


class TestNormalizeAVObservation:
    def test_valid_value(self) -> None:
        result = normalize_av_observation(
            function_name="REAL_GDP",
            raw_value_str="25000.0",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.GDP,
        )
        assert result is not None
        assert result.value == 25000.0
        assert result.indicator_type == MacroIndicatorType.GDP
        assert result.source == MacroSourceType.ALPHA_VANTAGE
        assert result.metadata["function"] == "REAL_GDP"
        assert result.metadata["source"] == "alpha_vantage"

    def test_missing_sentinel_dot(self) -> None:
        result = normalize_av_observation(
            function_name="CPI",
            raw_value_str=".",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.INFLATION,
        )
        assert result is None

    def test_empty_string(self) -> None:
        result = normalize_av_observation(
            function_name="CPI",
            raw_value_str="",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.INFLATION,
        )
        assert result is None

    def test_none_value(self) -> None:
        result = normalize_av_observation(
            function_name="CPI",
            raw_value_str=None,
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.INFLATION,
        )
        assert result is None

    def test_non_numeric(self) -> None:
        result = normalize_av_observation(
            function_name="CPI",
            raw_value_str="not_a_number",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.INFLATION,
        )
        assert result is None

    def test_out_of_range(self) -> None:
        result = normalize_av_observation(
            function_name="GDP",
            raw_value_str="99999999999",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.GDP,
        )
        assert result is None

    def test_timezone_naive_timestamp(self) -> None:
        naive_ts = datetime(2026, 1, 1)
        result = normalize_av_observation(
            function_name="CPI",
            raw_value_str="310.5",
            country="US",
            timestamp=naive_ts,
            indicator=MacroIndicatorType.INFLATION,
        )
        assert result is not None
        assert result.timestamp.tzinfo is not None

    def test_custom_frequency(self) -> None:
        result = normalize_av_observation(
            function_name="REAL_GDP",
            raw_value_str="25000.0",
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.GDP,
            frequency=DataFrequency.QUARTERLY,
        )
        assert result is not None
        assert result.frequency == DataFrequency.QUARTERLY


class TestAlphaVantageSeriesMap:
    def test_all_entries_have_function(self) -> None:
        for indicator, config in ALPHA_VANTAGE_SERIES_MAP.items():
            assert config.function, f"{indicator} has no function"

    def test_map_is_not_empty(self) -> None:
        assert len(ALPHA_VANTAGE_SERIES_MAP) > 0


class TestAlphaVantageDataSource:
    def test_no_api_key_raises(self) -> None:
        from src.agent.adapters.sources.alpha_vantage import AlphaVantageDataSource

        with pytest.raises(RuntimeError, match="requires a non-empty api_key"):
            AlphaVantageDataSource(api_key="")

    def test_none_api_key_raises(self) -> None:
        from src.agent.adapters.sources.alpha_vantage import AlphaVantageDataSource

        with pytest.raises(RuntimeError, match="requires a non-empty api_key"):
            AlphaVantageDataSource(api_key=None)

    def test_valid_api_key_constructs(self) -> None:
        from src.agent.adapters.sources.alpha_vantage import AlphaVantageDataSource

        source = AlphaVantageDataSource(api_key="test_key_123")
        assert source.source_id == "alpha_vantage"
        assert source.metadata.priority == 8

    def test_extract_latest_valid_data(self) -> None:
        from src.agent.adapters.sources.alpha_vantage.alpha_vantage_data_source import (
            AlphaVantageDataSource,
        )

        source = AlphaVantageDataSource(api_key="test")
        data = {
            "data": [
                {"date": "2026-01-01", "value": "310.5"},
                {"date": "2025-12-01", "value": "308.2"},
            ]
        }
        result = source._extract_latest(data)
        assert result == ("2026-01-01", "310.5")

    def test_extract_latest_rate_limit(self) -> None:
        from src.agent.adapters.sources.alpha_vantage.alpha_vantage_data_source import (
            AlphaVantageDataSource,
        )

        source = AlphaVantageDataSource(api_key="test")
        data = {"Note": "Thank you for using Alpha Vantage! Please visit..."}
        result = source._extract_latest(data)
        assert result is None

    def test_extract_latest_empty_data(self) -> None:
        from src.agent.adapters.sources.alpha_vantage.alpha_vantage_data_source import (
            AlphaVantageDataSource,
        )

        source = AlphaVantageDataSource(api_key="test")
        data: dict = {"data": []}
        result = source._extract_latest(data)
        assert result is None
