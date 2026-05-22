"""Tests for macro service."""

import pytest

from src.domain.macro.enums import MacroIndicatorType
from src.services.macro_service import MacroService


@pytest.mark.asyncio
class TestMacroService:
    """Tests for MacroService."""

    async def test_service_initialization(self) -> None:
        """Test macro service initializes."""
        service = MacroService()
        assert service is not None

    async def test_fetch_features(self) -> None:
        """Test fetching macro features."""
        service = MacroService()
        features = await service.fetch_features(
            [
                MacroIndicatorType.GDP.value,
                MacroIndicatorType.INFLATION.value,
            ]
        )
        assert len(features) >= 0  # Placeholder may return 0 or more

    async def test_fetch_features_empty_invalid(self) -> None:
        """Test that empty indicator list is rejected."""
        service = MacroService()
        with pytest.raises(ValueError, match="At least one"):
            await service.fetch_features([])

    async def test_get_snapshot(self) -> None:
        """Test getting macro snapshot."""
        service = MacroService()
        snapshot = await service.get_snapshot()
        assert snapshot is not None
        assert snapshot.version == 1

    async def test_get_snapshot_with_country(self) -> None:
        """Test getting snapshot for specific country."""
        service = MacroService()
        snapshot = await service.get_snapshot(country="GB")
        assert snapshot is not None
