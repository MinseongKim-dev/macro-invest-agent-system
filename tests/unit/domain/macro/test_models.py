"""Tests for macro domain models."""

from datetime import datetime

import pytest

from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot


class TestMacroFeature:
    """Tests for MacroFeature model."""

    def test_create_valid_feature(self) -> None:
        """Test creating a valid macro feature."""
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.FRED,
            value=5.2,
            timestamp=datetime.utcnow(),
        )
        assert feature.indicator_type == MacroIndicatorType.GDP
        assert feature.source == MacroSourceType.FRED
        assert feature.value == 5.2

    def test_feature_default_frequency(self) -> None:
        """Test that frequency defaults to DAILY."""
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.INFLATION,
            source=MacroSourceType.MARKET_DATA,
            value=3.5,
            timestamp=datetime.utcnow(),
        )
        assert feature.frequency == DataFrequency.DAILY

    def test_feature_with_metadata(self) -> None:
        """Test creating feature with metadata."""
        metadata = {"unit": "percent", "source_id": "CPIAUCSL"}
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.INFLATION,
            source=MacroSourceType.FRED,
            value=3.5,
            timestamp=datetime.utcnow(),
            metadata=metadata,
        )
        assert feature.metadata == metadata

    def test_feature_with_country(self) -> None:
        """Test creating feature with country."""
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.WORLD_BANK,
            value=2500.0,
            timestamp=datetime.utcnow(),
            country="GB",
        )
        assert feature.country == "GB"

    def test_invalid_feature_nan(self) -> None:
        """Test that NaN values are rejected."""
        with pytest.raises(ValueError, match="finite number"):
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=float("nan"),
                timestamp=datetime.utcnow(),
            )

    def test_invalid_feature_infinity(self) -> None:
        """Test that infinity values are rejected."""
        with pytest.raises(ValueError, match="finite number"):
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=float("inf"),
                timestamp=datetime.utcnow(),
            )


class TestMacroSnapshot:
    """Tests for MacroSnapshot model."""

    def test_create_valid_snapshot(self) -> None:
        """Test creating a valid snapshot."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            ),
            MacroFeature(
                indicator_type=MacroIndicatorType.INFLATION,
                source=MacroSourceType.FRED,
                value=3.5,
                timestamp=datetime.utcnow(),
            ),
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        assert len(snapshot.features) == 2
        assert snapshot.version == 1

    def test_snapshot_empty_features_invalid(self) -> None:
        """Test that empty snapshots are rejected."""
        with pytest.raises(ValueError, match="at least one feature"):
            MacroSnapshot(
                features=[],
                snapshot_time=datetime.utcnow(),
            )

    def test_get_feature_by_indicator(self) -> None:
        """Test retrieving feature by indicator type."""
        gdp_feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.FRED,
            value=5.2,
            timestamp=datetime.utcnow(),
        )
        snapshot = MacroSnapshot(
            features=[gdp_feature],
            snapshot_time=datetime.utcnow(),
        )
        found = snapshot.get_feature_by_indicator(MacroIndicatorType.GDP)
        assert found is not None
        assert found.value == 5.2

    def test_get_feature_not_found(self) -> None:
        """Test retrieving non-existent feature returns None."""
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.FRED,
            value=5.2,
            timestamp=datetime.utcnow(),
        )
        snapshot = MacroSnapshot(
            features=[feature],
            snapshot_time=datetime.utcnow(),
        )
        found = snapshot.get_feature_by_indicator(MacroIndicatorType.INFLATION)
        assert found is None

    def test_snapshot_with_multiple_same_indicator(self) -> None:
        """Test snapshot can contain multiple instances of same indicator."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
                country="US",
            ),
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.WORLD_BANK,
                value=5.1,
                timestamp=datetime.utcnow(),
                country="GB",
            ),
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        assert len(snapshot.features) == 2
