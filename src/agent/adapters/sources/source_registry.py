"""Source registry for multi-provider data source selection.

:class:`SourceRegistry` maintains an ordered list of
:class:`~core.contracts.macro_data_source.MacroDataSourceContract` instances
and exposes a :meth:`~SourceRegistry.select` method that returns the
highest-priority source supporting a given indicator.

Design notes
------------
* Selection is based on the ``priority`` field of each source's
  :class:`~core.contracts.macro_data_source.SourceMetadata`.  Higher numbers
  take precedence (e.g. ``priority=10`` beats ``priority=5``).
* Sources without metadata (``metadata is None``) are excluded from selection
  but are still returned by :meth:`all_sources`.
* Source-selection logic is intentionally kept out of the service layer; the
  service layer accepts a ``MacroDataSourceContract`` directly.
* No cross-provider deduplication or async parallel fetching — each call
  selects a single source per indicator.

Usage::

    from adapters.sources.source_registry import SourceRegistry
    from adapters.sources.fred import FredMacroDataSource
    from adapters.sources.fixture_macro_data_source import FixtureMacroDataSource

    registry = SourceRegistry([
        FredMacroDataSource(api_key="..."),
        FixtureMacroDataSource(),
    ])

    source = registry.select("GDP")
    if source is not None:
        features = await source.fetch_raw("US", ["GDP"])
"""

from __future__ import annotations

from core.contracts.macro_data_source import MacroDataSourceContract


class SourceRegistry:
    """Registry of :class:`~core.contracts.macro_data_source.MacroDataSourceContract`
    instances ordered by priority.

    Args:
        sources: Initial list of data sources.  Order in the list does not
            matter — selection is always based on the priority encoded in each
            source's :class:`~core.contracts.macro_data_source.SourceMetadata`.
    """

    def __init__(self, sources: list[MacroDataSourceContract] | None = None) -> None:
        self._sources: list[MacroDataSourceContract] = list(sources or [])

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, source: MacroDataSourceContract) -> None:
        """Add a source to the registry.

        Args:
            source: The data source to register.  Duplicate registrations are
                allowed; the source will appear multiple times in
                :meth:`all_sources` but will only match once in
                :meth:`select`.
        """
        self._sources.append(source)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def select(self, indicator: str) -> MacroDataSourceContract | None:
        """Return the highest-priority source that supports *indicator*.

        Sources that have no :attr:`metadata` (i.e. return ``None``) are
        skipped.  Among eligible sources, the one with the highest
        ``priority`` integer wins.

        Args:
            indicator: A :class:`~domain.macro.enums.MacroIndicatorType`
                string value (e.g. ``"GDP"``).

        Returns:
            The best-matching :class:`MacroDataSourceContract`, or ``None``
            if no registered source supports the indicator.
        """
        best: MacroDataSourceContract | None = None
        best_priority: int = -1

        for source in self._sources:
            meta = source.metadata
            if meta is None:
                continue
            if indicator not in meta.supported_indicators:
                continue
            if meta.priority > best_priority:
                best = source
                best_priority = meta.priority

        return best

    def all_sources(self) -> list[MacroDataSourceContract]:
        """Return all registered sources in insertion order.

        Returns:
            Shallow copy of the internal source list.
        """
        return list(self._sources)
