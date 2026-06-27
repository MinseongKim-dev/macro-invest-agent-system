"""Unit tests for the Yahoo Finance adapter.

Covers:
- Series map: every mapped indicator has a valid ticker
- Normalizer: valid values, None, out-of-range
- Adapter construction (no API key needed)
- Response parsing: v8 chart response extraction
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.agent.adapters.sources.yahoo.normalizer import normalize_yf_quote
from src.agent.adapters.sources.yahoo.series_map import YAHOO_FINANCE_SERIES_MAP
from src.domain.macro.enums import MacroIndicatorType, MacroSourceType

_TS = datetime(2026, 1, 1, tzinfo=UTC)


class TestNormalizeYFQuote:
    def test_valid_value(self) -> None:
        result = normalize_yf_quote(
            ticker="^TNX",
            value=4.5,
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.YIELD_10Y,
        )
        assert result is not None
        assert result.value == 4.5
        assert result.indicator_type == MacroIndicatorType.YIELD_10Y
        assert result.source == MacroSourceType.YAHOO_FINANCE
        assert result.metadata["ticker"] == "^TNX"
        assert result.metadata["source"] == "yahoo_finance"

    def test_none_value(self) -> None:
        result = normalize_yf_quote(
            ticker="^VIX",
            value=None,
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.VOLATILITY_PROXY,
        )
        assert result is None

    def test_out_of_range(self) -> None:
        result = normalize_yf_quote(
            ticker="^GSPC",
            value=99999999999,
            country="US",
            timestamp=_TS,
            indicator=MacroIndicatorType.STOCK_INDEX,
        )
        assert result is None

    def test_timezone_naive(self) -> None:
        naive_ts = datetime(2026, 1, 1)
        result = normalize_yf_quote(
            ticker="^TNX",
            value=4.5,
            country="US",
            timestamp=naive_ts,
            indicator=MacroIndicatorType.YIELD_10Y,
        )
        assert result is not None
        assert result.timestamp.tzinfo is not None


class TestYahooFinanceSeriesMap:
    def test_all_entries_have_ticker(self) -> None:
        for indicator, config in YAHOO_FINANCE_SERIES_MAP.items():
            assert config.ticker, f"{indicator} has no ticker"

    def test_map_is_not_empty(self) -> None:
        assert len(YAHOO_FINANCE_SERIES_MAP) > 0

    def test_exchange_rate_mapped(self) -> None:
        assert MacroIndicatorType.EXCHANGE_RATE in YAHOO_FINANCE_SERIES_MAP
        assert "KRW" in YAHOO_FINANCE_SERIES_MAP[MacroIndicatorType.EXCHANGE_RATE].ticker


class TestYahooFinanceDataSource:
    def test_constructs_without_api_key(self) -> None:
        from src.agent.adapters.sources.yahoo import YahooFinanceDataSource

        source = YahooFinanceDataSource()
        assert source.source_id == "yahoo_finance"
        assert source.metadata.priority == 7

    def test_extract_latest_valid_response(self) -> None:
        from src.agent.adapters.sources.yahoo.yahoo_data_source import YahooFinanceDataSource

        source = YahooFinanceDataSource()
        data = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 4.52,
                            "regularMarketTime": 1735689600,
                        },
                        "indicators": {"quote": [{"close": [4.5, 4.52]}]},
                    }
                ]
            }
        }
        result = source._extract_latest(data)
        assert result is not None
        value, ts = result
        assert value == 4.52

    def test_extract_latest_fallback_to_close(self) -> None:
        from src.agent.adapters.sources.yahoo.yahoo_data_source import YahooFinanceDataSource

        source = YahooFinanceDataSource()
        data = {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketTime": 1735689600},
                        "indicators": {"quote": [{"close": [4.5, None, 4.55]}]},
                    }
                ]
            }
        }
        result = source._extract_latest(data)
        assert result is not None
        value, _ = result
        assert value == 4.55

    def test_extract_latest_empty_response(self) -> None:
        from src.agent.adapters.sources.yahoo.yahoo_data_source import YahooFinanceDataSource

        source = YahooFinanceDataSource()
        data: dict[str, object] = {"chart": {"result": [{"meta": {}, "indicators": {"quote": [{"close": []}]}}]}}
        result = source._extract_latest(data)
        assert result is None

    def test_extract_latest_malformed_response(self) -> None:
        from src.agent.adapters.sources.yahoo.yahoo_data_source import YahooFinanceDataSource

        source = YahooFinanceDataSource()
        result = source._extract_latest({"unexpected": "format"})
        assert result is None
