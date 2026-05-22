"""Mapping from :class:`~domain.macro.enums.MacroIndicatorType` values to FRED series IDs.

This module provides a Phase-1 foundation map for growth, inflation, labor,
policy/rates, and financial-condition indicators.

References
----------
* GDP (Real): https://fred.stlouisfed.org/series/GDPC1
* CPI (inflation proxy): https://fred.stlouisfed.org/series/CPIAUCSL
* Unemployment rate: https://fred.stlouisfed.org/series/UNRATE
* Federal Funds Rate: https://fred.stlouisfed.org/series/FEDFUNDS
* 10-Year Treasury yield: https://fred.stlouisfed.org/series/DGS10
"""

from __future__ import annotations

from domain.macro.enums import MacroIndicatorType

# Maps each supported MacroIndicatorType to the corresponding FRED series ID.
FRED_SERIES_MAP: dict[MacroIndicatorType, str] = {
    # Growth
    MacroIndicatorType.GDP: "GDPC1",
    MacroIndicatorType.PMI: "NAPM",
    MacroIndicatorType.INDUSTRIAL_PRODUCTION: "INDPRO",
    MacroIndicatorType.RETAIL_SALES: "RSAFS",
    MacroIndicatorType.PAYROLLS: "PAYEMS",
    # Inflation
    MacroIndicatorType.INFLATION: "CPIAUCSL",
    MacroIndicatorType.CORE_CPI: "CPILFESL",
    MacroIndicatorType.PCE: "PCEPI",
    MacroIndicatorType.WAGE_GROWTH: "CES0500000003",
    MacroIndicatorType.PPI: "PPIACO",
    # Labor
    MacroIndicatorType.UNEMPLOYMENT: "UNRATE",
    MacroIndicatorType.JOBLESS_CLAIMS: "ICSA",
    MacroIndicatorType.JOB_OPENINGS: "JTSJOL",
    MacroIndicatorType.PAYROLL_TREND: "PAYEMS",
    # Policy / rates
    MacroIndicatorType.INTEREST_RATE: "FEDFUNDS",
    MacroIndicatorType.POLICY_RATE: "FEDFUNDS",
    MacroIndicatorType.YIELD_2Y: "DGS2",
    MacroIndicatorType.YIELD_10Y: "DGS10",
    MacroIndicatorType.YIELD_CURVE_SLOPE: "T10Y2Y",
    MacroIndicatorType.REAL_YIELD: "DFII10",
    MacroIndicatorType.BOND_YIELD: "DGS10",
    # Financial conditions
    MacroIndicatorType.CREDIT_SPREAD: "BAA10Y",
    MacroIndicatorType.DOLLAR_STRENGTH: "DTWEXBGS",
    MacroIndicatorType.VOLATILITY_PROXY: "VIXCLS",
    MacroIndicatorType.LIQUIDITY_PROXY: "M2SL",
}
