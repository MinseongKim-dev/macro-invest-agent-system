"""Unit tests for MacroService when a data source is injected."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agent.adapters.sources.fixture_macro_data_source import FixtureMacroDataSource
from src.core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.services.macro_service import MacroService


def _make_feature(indicator: MacroIndicatorType, value: float = 1.0) -> MacroFeature:
    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.MARKET_DATA,
        value=value,
        timestamp=datetime.now(UTC),
        frequency=DataFrequency.MONTHLY,
        country="US",
    )


class _StubSource(MacroDataSourceContract):
    """Minimal stub source that returns a fixed list of features."""

    def __init__(self, features: list[MacroFeature]) -> None:
        self._features = features
        self.fetch_raw_calls: list[tuple[str, list[str]]] = []

    @property
    def source_id(self) -> str:
        return "stub"

    @property
    def metadata(self) -> SourceMetadata:
        indicators = frozenset(f.indicator_type.value for f in self._features)
        return SourceMetadata(
            source_id="stub",
            priority=10,
            supported_indicators=indicators,
        )

    async def fetch_raw(self, country: str, indicators: list[str]) -> list[MacroFeature]:
        self.fetch_raw_calls.append((country, indicators))
        return [f for f in self._features if f.indicator_type.value in indicators]


@pytest.mark.asyncio
class TestMacroServiceWithSource:
    """MacroService delegates to the injected source when one is provided."""

    async def test_fetch_features_delegates_to_source(self) -> None:
        gdp_feature = _make_feature(MacroIndicatorType.GDP, value=25_000.0)
        stub = _StubSource([gdp_feature])
        svc = MacroService(source=stub)

        features = await svc.fetch_features(
            indicator_types=[MacroIndicatorType.GDP.value],
            country="US",
        )

        assert len(features) == 1
        assert features[0].indicator_type == MacroIndicatorType.GDP
        assert features[0].value == 25_000.0

    async def test_fetch_features_passes_country_to_source(self) -> None:
        stub = _StubSource([_make_feature(MacroIndicatorType.GDP)])
        svc = MacroService(source=stub)
        await svc.fetch_features(["GDP"], country="DE")
        assert stub.fetch_raw_calls[0][0] == "DE"

    async def test_fetch_features_raises_value_error_when_empty(self) -> None:
        svc = MacroService(source=_StubSource([]))
        with pytest.raises(ValueError, match="At least one"):
            await svc.fetch_features([], country="US")

    async def test_get_snapshot_delegates_to_source(self) -> None:
        gdp = _make_feature(MacroIndicatorType.GDP, 22_000.0)
        infl = _make_feature(MacroIndicatorType.INFLATION, 2.5)
        stub = _StubSource([gdp, infl])
        svc = MacroService(source=stub)

        snapshot = await svc.get_snapshot(country="US")
        assert isinstance(snapshot, MacroSnapshot)
        assert len(snapshot.features) > 0

    async def test_get_snapshot_raises_on_empty_features(self) -> None:
        """When source returns no features, get_snapshot raises RuntimeError."""
        stub = _StubSource([])
        svc = MacroService(source=stub)
        with pytest.raises(RuntimeError):
            await svc.get_snapshot(country="US")

    async def test_no_source_returns_synthetic_data(self) -> None:
        """Without a source, MacroService uses synthetic fallback (backward compat)."""
        svc = MacroService()  # no source
        features = await svc.fetch_features(
            indicator_types=[MacroIndicatorType.GDP.value],
            country="US",
        )
        assert len(features) == 1
        assert features[0].value == 50.0  # synthetic placeholder

    async def test_fixture_source_integration(self) -> None:
        """MacroService delegates to FixtureMacroDataSource correctly."""
        fixture = FixtureMacroDataSource()
        svc = MacroService(source=fixture)

        features = await svc.fetch_features(
            indicator_types=[MacroIndicatorType.GDP.value, MacroIndicatorType.INFLATION.value],
            country="US",
        )
        assert len(features) == 2
        indicators_returned = {f.indicator_type for f in features}
        assert MacroIndicatorType.GDP in indicators_returned
        assert MacroIndicatorType.INFLATION in indicators_returned

    async def test_source_id_is_logged(self) -> None:
        """MacroService correctly identifies the source in its internal state."""
        stub = _StubSource([_make_feature(MacroIndicatorType.GDP)])
        svc = MacroService(source=stub)
        assert svc._source is not None
        assert svc._source.source_id == "stub"
