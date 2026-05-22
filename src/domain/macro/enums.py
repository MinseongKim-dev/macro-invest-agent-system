"""Enumerations for macro economic data types and sources."""

from enum import StrEnum


class MacroIndicatorType(StrEnum):
    """Types of macroeconomic indicators."""

    # Growth
    GDP = "gdp"
    PMI = "pmi"  # Purchasing Managers' Index
    INDUSTRIAL_PRODUCTION = "industrial_production"
    RETAIL_SALES = "retail_sales"
    PAYROLLS = "payrolls"

    # Inflation
    INFLATION = "inflation"
    CORE_CPI = "core_cpi"
    PCE = "pce"
    WAGE_GROWTH = "wage_growth"
    PPI = "ppi"

    # Labor
    UNEMPLOYMENT = "unemployment"
    JOBLESS_CLAIMS = "jobless_claims"
    JOB_OPENINGS = "job_openings"
    PAYROLL_TREND = "payroll_trend"

    # Policy / Rates
    INTEREST_RATE = "interest_rate"
    POLICY_RATE = "policy_rate"
    YIELD_2Y = "yield_2y"
    YIELD_10Y = "yield_10y"
    YIELD_CURVE_SLOPE = "yield_curve_slope"
    REAL_YIELD = "real_yield"

    # Financial conditions
    DOLLAR_STRENGTH = "dollar_strength"
    VOLATILITY_PROXY = "volatility_proxy"
    LIQUIDITY_PROXY = "liquidity_proxy"

    # Existing generic / legacy keys
    EXCHANGE_RATE = "exchange_rate"
    STOCK_INDEX = "stock_index"
    BOND_YIELD = "bond_yield"
    CREDIT_SPREAD = "credit_spread"
    COMMODITY_PRICE = "commodity_price"


class MacroSourceType(StrEnum):
    """Data sources for macroeconomic indicators."""

    FRED = "fred"  # Federal Reserve Economic Data
    WORLD_BANK = "world_bank"
    IMF = "imf"  # International Monetary Fund
    OECD = "oecd"
    ECB = "ecb"  # European Central Bank
    MARKET_DATA = "market_data"
    CUSTOM = "custom"


class DataFrequency(StrEnum):
    """Frequency of data observations."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
