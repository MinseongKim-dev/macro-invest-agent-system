"""Unit tests for the FRED normalizer.

Covers:
- Valid observation values
- FRED missing-value sentinel (".")
- Non-numeric / empty values
- Out-of-range values (outside MacroFeature bounds)
- Timezone handling on the returned timestamp
- Metadata fields on successful normalisation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agent.adapters.sources.fred.normalizer import normalize_fred_observation
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType

# Shared fixture timestamp
_TS = datetime(2026, 1, 1, tzinfo=UTC)


class TestNormalizeFredObservationValid:
    """Happy-path normalisation tests."""

    def test_returns_macro_feature_for_valid_value(self) -> None:
        feature = normalize_fred_observation("GDPC1", "25000.5", "US", _TS, MacroIndicatorType.GDP)
        assert feature is not None
        assert feature.value == 25000.5

    def test_source_is_fred(self) -> None:
        feature = normalize_fred_observation("GDPC1", "100.0", "US", _TS, MacroIndicatorType.GDP)
        assert feature is not None
        assert feature.source == MacroSourceType.FRED

    def test_frequency_is_monthly(self) -> None:
        feature = normalize_fred_observation("GDPC1", "100.0", "US", _TS, MacroIndicatorType.GDP)
        assert feature is not None
        assert feature.frequency == DataFrequency.MONTHLY

    def test_indicator_type_preserved(self) -> None:
        feature = normalize_fred_observation(
            "CPIAUCSL", "310.0", "US", _TS, MacroIndicatorType.INFLATION
        )
        assert feature is not None
        assert feature.indicator_type == MacroIndicatorType.INFLATION

    def test_country_preserved(self) -> None:
        feature = normalize_fred_observation("UNRATE", "4.1", "JP", _TS, MacroIndicatorType.UNEMPLOYMENT)
        assert feature is not None
        assert feature.country == "JP"

    def test_series_id_in_metadata(self) -> None:
        feature = normalize_fred_observation("FEDFUNDS", "5.25", "US", _TS, MacroIndicatorType.INTEREST_RATE)
        assert feature is not None
        assert feature.metadata["series_id"] == "FEDFUNDS"

    def test_source_in_metadata(self) -> None:
        feature = normalize_fred_observation("DGS10", "4.6", "US", _TS, MacroIndicatorType.BOND_YIELD)
        assert feature is not None
        assert feature.metadata["source"] == "fred"

    def test_timestamp_preserved(self) -> None:
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        feature = normalize_fred_observation("GDPC1", "26000.0", "US", ts, MacroIndicatorType.GDP)
        assert feature is not None
        assert feature.timestamp == ts

    def test_naive_timestamp_gets_utc(self) -> None:
        naive_ts = datetime(2025, 1, 1)  # no tzinfo
        feature = normalize_fred_observation("GDPC1", "100.0", "US", naive_ts, MacroIndicatorType.GDP)
        assert feature is not None
        assert feature.timestamp.tzinfo is not None

    def test_negative_value_within_range(self) -> None:
        feature = normalize_fred_observation("FEDFUNDS", "-0.5", "US", _TS, MacroIndicatorType.INTEREST_RATE)
        assert feature is not None
        assert feature.value == pytest.approx(-0.5)

    def test_integer_string_value(self) -> None:
        feature = normalize_fred_observation("UNRATE", "4", "US", _TS, MacroIndicatorType.UNEMPLOYMENT)
        assert feature is not None
        assert feature.value == 4.0


class TestNormalizeFredObservationMissing:
    """Tests for FRED sentinel and empty values."""

    def test_fred_dot_sentinel_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", ".", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "   ", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_none_value_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", None, "US", _TS, MacroIndicatorType.GDP)  # type: ignore[arg-type]
        assert result is None


class TestNormalizeFredObservationNonNumeric:
    """Tests for non-parseable value strings."""

    def test_alphabetic_string_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "N/A", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_mixed_string_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "25000a", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_special_chars_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "#ERROR", "US", _TS, MacroIndicatorType.GDP)
        assert result is None


class TestNormalizeFredObservationOutOfRange:
    """Tests for values outside the MacroFeature validator range (-1e10, 1e10)."""

    def test_value_at_upper_bound_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "1e10", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_value_above_upper_bound_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "1.5e10", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_value_at_lower_bound_returns_none(self) -> None:
        result = normalize_fred_observation("GDPC1", "-1e10", "US", _TS, MacroIndicatorType.GDP)
        assert result is None

    def test_value_just_inside_upper_bound(self) -> None:
        result = normalize_fred_observation("GDPC1", "9999999999.0", "US", _TS, MacroIndicatorType.GDP)
        assert result is not None
