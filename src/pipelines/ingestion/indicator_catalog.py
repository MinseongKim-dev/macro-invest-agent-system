"""Phase 1 indicator catalog and source mapping table."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from domain.macro.enums import DataFrequency, MacroIndicatorType


class IndicatorCategory(StrEnum):
    """Top-level macro indicator categories used in Phase 1."""

    INFLATION = "inflation"
    LABOR = "labor"
    POLICY_RATES = "policy_rates"
    GROWTH = "growth"


class IndicatorCatalogEntry(BaseModel, extra="forbid"):
    """Catalog definition for one indicator in the ingestion foundation."""

    indicator_id: MacroIndicatorType
    label: str = Field(..., min_length=1)
    category: IndicatorCategory
    unit: str = Field(..., min_length=1)
    frequency: DataFrequency
    region: str = Field(default="US", min_length=2)
    source_id: str = Field(default="fred", min_length=1)
    source_series_id: str = Field(..., min_length=1)
    active: bool = Field(default=True)


# Priority starter set for Phase 1 (small, reliable, high-signal indicators)
PRIORITY_INDICATORS: tuple[MacroIndicatorType, ...] = (
    MacroIndicatorType.INFLATION,
    MacroIndicatorType.UNEMPLOYMENT,
    MacroIndicatorType.YIELD_10Y,
    MacroIndicatorType.PMI,
    MacroIndicatorType.RETAIL_SALES,
)


INDICATOR_CATALOG: dict[MacroIndicatorType, IndicatorCatalogEntry] = {
    MacroIndicatorType.INFLATION: IndicatorCatalogEntry(
        indicator_id=MacroIndicatorType.INFLATION,
        label="CPI (All Items)",
        category=IndicatorCategory.INFLATION,
        unit="index",
        frequency=DataFrequency.MONTHLY,
        source_id="fred",
        source_series_id="CPIAUCSL",
    ),
    MacroIndicatorType.UNEMPLOYMENT: IndicatorCatalogEntry(
        indicator_id=MacroIndicatorType.UNEMPLOYMENT,
        label="Unemployment Rate",
        category=IndicatorCategory.LABOR,
        unit="percent",
        frequency=DataFrequency.MONTHLY,
        source_id="fred",
        source_series_id="UNRATE",
    ),
    MacroIndicatorType.YIELD_10Y: IndicatorCatalogEntry(
        indicator_id=MacroIndicatorType.YIELD_10Y,
        label="10Y Treasury Yield",
        category=IndicatorCategory.POLICY_RATES,
        unit="percent",
        frequency=DataFrequency.DAILY,
        source_id="fred",
        source_series_id="DGS10",
    ),
    MacroIndicatorType.PMI: IndicatorCatalogEntry(
        indicator_id=MacroIndicatorType.PMI,
        label="ISM Manufacturing PMI",
        category=IndicatorCategory.GROWTH,
        unit="index",
        frequency=DataFrequency.MONTHLY,
        source_id="fred",
        source_series_id="NAPM",
    ),
    MacroIndicatorType.RETAIL_SALES: IndicatorCatalogEntry(
        indicator_id=MacroIndicatorType.RETAIL_SALES,
        label="Retail Sales",
        category=IndicatorCategory.GROWTH,
        unit="usd_millions",
        frequency=DataFrequency.MONTHLY,
        source_id="fred",
        source_series_id="RSAFS",
    ),
}


def get_active_catalog_entries() -> list[IndicatorCatalogEntry]:
    """Return active catalog entries in deterministic order."""
    return [
        INDICATOR_CATALOG[indicator]
        for indicator in PRIORITY_INDICATORS
        if INDICATOR_CATALOG[indicator].active
    ]
