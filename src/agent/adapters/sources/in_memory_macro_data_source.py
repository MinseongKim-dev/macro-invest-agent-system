"""In-memory macro data source adapter.

Stores macro features in a mutable in-memory dict so that tests can
pre-populate specific indicator values and verify ingestion behaviour without
touching the fixture or any external I/O.

Design notes
------------
* Data is stored per ``(country, indicator)`` key.  The store is mutable via
  :meth:`set_feature`, which allows tests to inject controlled values.
* If a requested indicator has no stored data the adapter returns an empty
  list entry for that indicator (omitting it from the result), matching the
  contract behaviour for unavailable data.
* This adapter is intended for use in tests and local development.  It is
  **not** thread-safe.
"""

from __future__ import annotations

from core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from domain.macro.models import MacroFeature


class InMemoryMacroDataSource(MacroDataSourceContract):
    """Mutable in-memory macro data source.

    Useful in tests that need precise control over which feature values are
    returned without relying on fixture defaults.

    Args:
        initial_features: Optional pre-populated store.  Keyed by
            ``(country, indicator_name)`` tuples.

    Example::

        source = InMemoryMacroDataSource()
        source.set_feature("US", "gdp", my_feature)
        features = await source.fetch_raw("US", ["gdp"])
    """

    def __init__(
        self,
        initial_features: dict[tuple[str, str], MacroFeature] | None = None,
    ) -> None:
        self._store: dict[tuple[str, str], MacroFeature] = dict(initial_features or {})

    @property
    def source_id(self) -> str:
        """Stable identifier for this adapter."""
        return "in_memory"

    @property
    def metadata(self) -> SourceMetadata:
        """Source metadata: all currently stored indicators are supported."""
        supported = frozenset(indicator for _, indicator in self._store)
        return SourceMetadata(
            source_id="in_memory",
            priority=1,
            supported_indicators=supported,
        )

    def set_feature(self, country: str, indicator: str, feature: MacroFeature) -> None:
        """Store a feature for a given country and indicator.

        Args:
            country: ISO 3166-1 alpha-2 country code.
            indicator: Indicator name (e.g. ``"gdp"``).
            feature: :class:`~domain.macro.models.MacroFeature` to store.
        """
        self._store[(country, indicator)] = feature

    def clear(self) -> None:
        """Remove all stored features."""
        self._store.clear()

    async def fetch_raw(
        self,
        country: str,
        indicators: list[str],
    ) -> list[MacroFeature]:
        """Return stored features for the requested indicators.

        Args:
            country: ISO 3166-1 alpha-2 country code.
            indicators: List of indicator names to return.  Names for which no
                data is stored are silently omitted.

        Returns:
            List of stored :class:`~domain.macro.models.MacroFeature` instances
            in the same order as ``indicators``.
        """
        features: list[MacroFeature] = []
        for indicator in indicators:
            feature = self._store.get((country, indicator))
            if feature is not None:
                features.append(feature)
        return features
