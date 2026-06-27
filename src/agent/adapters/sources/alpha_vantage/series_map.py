"""Alpha Vantage indicator-to-function mapping.

Each entry maps a MacroIndicatorType to an Alpha Vantage API function
and its corresponding symbol/parameter.

Alpha Vantage free tier: 25 requests/day, 5 requests/minute.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.macro.enums import MacroIndicatorType


@dataclass(frozen=True)
class AVSeriesConfig:
    """Configuration for one Alpha Vantage API call."""

    function: str
    symbol: str | None = None
    interval: str | None = None
    maturity: str | None = None


ALPHA_VANTAGE_SERIES_MAP: dict[MacroIndicatorType, AVSeriesConfig] = {
    # --- Growth ---
    MacroIndicatorType.GDP: AVSeriesConfig(
        function="REAL_GDP",
        interval="quarterly",
    ),
    MacroIndicatorType.RETAIL_SALES: AVSeriesConfig(
        function="RETAIL_SALES",
    ),
    # --- Inflation ---
    MacroIndicatorType.INFLATION: AVSeriesConfig(
        function="CPI",
        interval="monthly",
    ),
    # --- Labor ---
    MacroIndicatorType.UNEMPLOYMENT: AVSeriesConfig(
        function="UNEMPLOYMENT",
    ),
    # --- Rates ---
    MacroIndicatorType.INTEREST_RATE: AVSeriesConfig(
        function="FEDERAL_FUNDS_RATE",
        interval="monthly",
    ),
    MacroIndicatorType.YIELD_2Y: AVSeriesConfig(
        function="TREASURY_YIELD",
        interval="monthly",
        maturity="2year",
    ),
    MacroIndicatorType.YIELD_10Y: AVSeriesConfig(
        function="TREASURY_YIELD",
        interval="monthly",
        maturity="10year",
    ),
}
