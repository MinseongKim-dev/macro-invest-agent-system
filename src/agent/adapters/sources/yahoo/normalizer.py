"""Pure normalizer for raw Yahoo Finance quote values.

Isolates parsing/conversion logic from network I/O for independent testing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature


def normalize_yf_quote(
    ticker: str,
    value: float | None,
    country: str,
    timestamp: datetime,
    indicator: MacroIndicatorType,
    frequency: DataFrequency = DataFrequency.DAILY,
) -> MacroFeature | None:
    """Convert a Yahoo Finance quote value into a MacroFeature.

    Args:
        ticker: Yahoo Finance ticker symbol (e.g. "^TNX").
        value: Numeric value from the quote response.
        country: ISO 3166-1 alpha-2 country code.
        timestamp: UTC timestamp of the quote.
        indicator: The MacroIndicatorType for this observation.
        frequency: Data frequency.

    Returns:
        A MacroFeature with source=YAHOO_FINANCE, or None if the value is invalid.
    """
    if value is None:
        return None

    try:
        value = float(value)
    except (ValueError, TypeError):
        return None

    if not (-1e10 < value < 1e10):
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.YAHOO_FINANCE,
        value=value,
        timestamp=timestamp,
        frequency=frequency,
        country=country,
        metadata={
            "ticker": ticker,
            "source": "yahoo_finance",
        },
    )
