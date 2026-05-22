"""Fixture-backed macro data source adapter.

Returns deterministic, hard-coded macro features so that the ingestion
pipeline can be exercised without any external I/O.

Design notes
------------
* All returned features are fixed at construction time; no network calls are
  made.
* The fixture uses realistic-looking values for common indicators, but they
  are **not** real economic data.
* The fixture supports the full :class:`~core.contracts.macro_data_source.MacroDataSourceContract`
  interface, so it can be dropped into any code that depends on that contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature

# Fixed reference timestamp so fixture output is fully deterministic
_FIXTURE_TIMESTAMP = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

# Fixture values keyed by indicator type.  These are illustrative only.
_FIXTURE_VALUES: dict[MacroIndicatorType, float] = {
    MacroIndicatorType.GDP: 25_000.0,
    MacroIndicatorType.INFLATION: 3.2,
    MacroIndicatorType.UNEMPLOYMENT: 4.1,
    MacroIndicatorType.YIELD_10Y: 4.6,
    MacroIndicatorType.RETAIL_SALES: 720_000.0,
    MacroIndicatorType.INTEREST_RATE: 5.25,
    MacroIndicatorType.EXCHANGE_RATE: 1.0,
    MacroIndicatorType.STOCK_INDEX: 4_500.0,
    MacroIndicatorType.BOND_YIELD: 4.6,
    MacroIndicatorType.CREDIT_SPREAD: 1.2,
    MacroIndicatorType.COMMODITY_PRICE: 80.0,
    MacroIndicatorType.PMI: 52.3,
}


class FixtureMacroDataSource(MacroDataSourceContract):
    """Deterministic fixture adapter for macro data.

    Returns hard-coded :class:`~domain.macro.models.MacroFeature` objects
    with a fixed timestamp.  Useful in tests, CI, and early-stage development
    when real data sources are not yet connected.

    Args:
        country_override: Optional country to use regardless of the
            ``country`` argument passed to :meth:`fetch_raw`.  Defaults to
            ``None`` (use the argument as-is).
    """

    def __init__(self, country_override: str | None = None) -> None:
        self._country_override = country_override

    @property
    def source_id(self) -> str:
        """Stable identifier for this adapter."""
        return "fixture"

    @property
    def metadata(self) -> SourceMetadata:
        """Source metadata for SourceRegistry selection."""
        return SourceMetadata(
            source_id="fixture",
            priority=5,
            supported_indicators=frozenset(i.value for i in _FIXTURE_VALUES),
        )

    async def fetch_raw(
        self,
        country: str,
        indicators: list[str],
    ) -> list[MacroFeature]:
        """Return deterministic fixture features for the requested indicators.

        Args:
            country: ISO 3166-1 alpha-2 country code.  Overridden by
                ``country_override`` if set at construction.
            indicators: List of indicator names to return.  Unknown names are
                silently skipped (matching the behaviour expected by the
                ingestion service).

        Returns:
            List of :class:`~domain.macro.models.MacroFeature` instances with
            fixed values and the ``_FIXTURE_TIMESTAMP`` reference time.
        """
        effective_country = self._country_override if self._country_override else country
        features: list[MacroFeature] = []

        for indicator_name in indicators:
            try:
                indicator = MacroIndicatorType(indicator_name)
            except ValueError:
                continue  # unknown indicator — skip silently

            value = _FIXTURE_VALUES.get(indicator, 0.0)
            features.append(
                MacroFeature(
                    indicator_type=indicator,
                    source=MacroSourceType.CUSTOM,
                    value=value,
                    timestamp=_FIXTURE_TIMESTAMP,
                    frequency=DataFrequency.MONTHLY,
                    country=effective_country,
                    metadata={"source": "fixture", "status": "deterministic"},
                )
            )

        return features
