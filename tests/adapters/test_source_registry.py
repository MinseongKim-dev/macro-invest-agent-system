"""Unit tests for SourceRegistry."""

from __future__ import annotations

from src.agent.adapters.sources.fixture_macro_data_source import FixtureMacroDataSource
from src.agent.adapters.sources.in_memory_macro_data_source import InMemoryMacroDataSource
from src.agent.adapters.sources.source_registry import SourceRegistry
from src.core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from src.domain.macro.enums import MacroIndicatorType
from src.domain.macro.models import MacroFeature


class _HighPrioritySource(MacroDataSourceContract):
    """Stub source with priority=20 supporting only 'GDP'."""

    @property
    def source_id(self) -> str:
        return "high_priority"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="high_priority",
            priority=20,
            supported_indicators=frozenset(["GDP"]),
        )

    async def fetch_raw(self, country: str, indicators: list[str]) -> list[MacroFeature]:
        return []


class _LowPrioritySource(MacroDataSourceContract):
    """Stub source with priority=1 supporting 'GDP' and 'INFLATION'."""

    @property
    def source_id(self) -> str:
        return "low_priority"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="low_priority",
            priority=1,
            supported_indicators=frozenset(["GDP", "INFLATION"]),
        )

    async def fetch_raw(self, country: str, indicators: list[str]) -> list[MacroFeature]:
        return []


class _NoMetadataSource(MacroDataSourceContract):
    """Stub source that does not implement metadata."""

    @property
    def source_id(self) -> str:
        return "no_metadata"

    async def fetch_raw(self, country: str, indicators: list[str]) -> list[MacroFeature]:
        return []


class TestSourceRegistrySelect:
    """SourceRegistry.select returns the correct source."""

    def test_select_returns_highest_priority_source(self) -> None:
        high = _HighPrioritySource()
        low = _LowPrioritySource()
        registry = SourceRegistry([low, high])
        selected = registry.select("GDP")
        assert selected is high

    def test_select_returns_only_supporting_source(self) -> None:
        high = _HighPrioritySource()
        low = _LowPrioritySource()
        registry = SourceRegistry([high, low])
        # Only low supports INFLATION
        selected = registry.select("INFLATION")
        assert selected is low

    def test_select_returns_none_when_no_source_supports_indicator(self) -> None:
        registry = SourceRegistry([_HighPrioritySource()])
        selected = registry.select("COMMODITY_PRICE")
        assert selected is None

    def test_select_returns_none_for_empty_registry(self) -> None:
        registry = SourceRegistry()
        assert registry.select("GDP") is None

    def test_select_skips_sources_without_metadata(self) -> None:
        """Sources with metadata=None should be skipped."""
        no_meta = _NoMetadataSource()
        low = _LowPrioritySource()
        registry = SourceRegistry([no_meta, low])
        selected = registry.select("GDP")
        # Should return low, not the no-metadata source
        assert selected is low

    def test_select_returns_none_when_only_no_metadata_sources(self) -> None:
        registry = SourceRegistry([_NoMetadataSource()])
        assert registry.select("GDP") is None


class TestSourceRegistryAllSources:
    """SourceRegistry.all_sources returns all registered sources."""

    def test_all_sources_returns_insertion_order(self) -> None:
        high = _HighPrioritySource()
        low = _LowPrioritySource()
        registry = SourceRegistry([high, low])
        assert registry.all_sources() == [high, low]

    def test_all_sources_returns_copy(self) -> None:
        high = _HighPrioritySource()
        registry = SourceRegistry([high])
        sources = registry.all_sources()
        sources.clear()
        assert len(registry.all_sources()) == 1

    def test_register_adds_source(self) -> None:
        registry = SourceRegistry()
        src = _LowPrioritySource()
        registry.register(src)
        assert src in registry.all_sources()

    def test_empty_registry_returns_empty_list(self) -> None:
        assert SourceRegistry().all_sources() == []


class TestConcreteAdapterMetadata:
    """FixtureMacroDataSource and InMemoryMacroDataSource expose correct metadata."""

    def test_fixture_source_metadata(self) -> None:
        src = FixtureMacroDataSource()
        meta = src.metadata
        assert meta is not None
        assert meta.source_id == "fixture"
        assert meta.priority == 5
        assert MacroIndicatorType.GDP.value in meta.supported_indicators

    def test_in_memory_source_metadata_empty_store(self) -> None:
        src = InMemoryMacroDataSource()
        meta = src.metadata
        assert meta is not None
        assert meta.source_id == "in_memory"
        assert meta.priority == 1
        assert len(meta.supported_indicators) == 0

    def test_in_memory_source_metadata_reflects_stored_indicators(self) -> None:
        from datetime import UTC, datetime

        from src.domain.macro.enums import DataFrequency, MacroSourceType

        src = InMemoryMacroDataSource()
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.MARKET_DATA,
            value=100.0,
            timestamp=datetime.now(UTC),
            frequency=DataFrequency.MONTHLY,
            country="US",
        )
        src.set_feature("US", MacroIndicatorType.GDP.value, feature)
        meta = src.metadata
        assert MacroIndicatorType.GDP.value in meta.supported_indicators
