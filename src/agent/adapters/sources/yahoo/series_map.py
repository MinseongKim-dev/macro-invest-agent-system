"""Yahoo Finance indicator-to-ticker mapping.

Maps MacroIndicatorType values to Yahoo Finance ticker symbols.
Yahoo Finance is best suited for market data (indices, rates, FX, commodities)
rather than economic indicators — it complements FRED and Alpha Vantage.

No API key required. Uses the public v8 chart/quote endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.macro.enums import DataFrequency, MacroIndicatorType


@dataclass(frozen=True)
class YFSeriesConfig:
    """Configuration for one Yahoo Finance data fetch."""

    ticker: str
    frequency: DataFrequency = DataFrequency.DAILY


YAHOO_FINANCE_SERIES_MAP: dict[MacroIndicatorType, YFSeriesConfig] = {
    # --- Rates / Yields ---
    MacroIndicatorType.YIELD_2Y: YFSeriesConfig(
        ticker="^IRX",
        frequency=DataFrequency.DAILY,
    ),
    MacroIndicatorType.YIELD_10Y: YFSeriesConfig(
        ticker="^TNX",
        frequency=DataFrequency.DAILY,
    ),
    # --- Dollar ---
    MacroIndicatorType.DOLLAR_STRENGTH: YFSeriesConfig(
        ticker="DX-Y.NYB",
        frequency=DataFrequency.DAILY,
    ),
    # --- Volatility ---
    MacroIndicatorType.VOLATILITY_PROXY: YFSeriesConfig(
        ticker="^VIX",
        frequency=DataFrequency.DAILY,
    ),
    # --- Stock Indices ---
    MacroIndicatorType.STOCK_INDEX: YFSeriesConfig(
        ticker="^GSPC",
        frequency=DataFrequency.DAILY,
    ),
    # --- Commodities ---
    MacroIndicatorType.COMMODITY_PRICE: YFSeriesConfig(
        ticker="GC=F",
        frequency=DataFrequency.DAILY,
    ),
    # --- Exchange Rate ---
    MacroIndicatorType.EXCHANGE_RATE: YFSeriesConfig(
        ticker="USDKRW=X",
        frequency=DataFrequency.DAILY,
    ),
}
