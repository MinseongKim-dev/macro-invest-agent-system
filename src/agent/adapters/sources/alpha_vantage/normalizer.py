"""Pure normalizer for raw Alpha Vantage observation values.

Isolates parsing/conversion logic from network I/O for independent testing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature


def normalize_av_observation(
    function_name: str,
    raw_value_str: str,
    country: str,
    timestamp: datetime,
    indicator: MacroIndicatorType,
    frequency: DataFrequency = DataFrequency.MONTHLY,
) -> MacroFeature | None:
    """Convert a raw Alpha Vantage observation into a MacroFeature.

    Args:
        function_name: AV API function used (e.g. "REAL_GDP"). Stored in
            metadata for traceability.
        raw_value_str: Raw string value from the AV response (e.g. "3.2").
            The sentinel "." is treated as missing data.
        country: ISO 3166-1 alpha-2 country code.
        timestamp: UTC observation date parsed from the response.
        indicator: The MacroIndicatorType for this observation.
        frequency: Data frequency (defaults to MONTHLY).

    Returns:
        A MacroFeature with source=ALPHA_VANTAGE, or None if the value
        cannot be parsed as a finite float within accepted range.
    """
    if raw_value_str is None or raw_value_str.strip() in ("", "."):
        return None

    try:
        value = float(raw_value_str)
    except (ValueError, TypeError):
        return None

    if not (-1e10 < value < 1e10):
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.ALPHA_VANTAGE,
        value=value,
        timestamp=timestamp,
        frequency=frequency,
        country=country,
        metadata={
            "function": function_name,
            "source": "alpha_vantage",
        },
    )
