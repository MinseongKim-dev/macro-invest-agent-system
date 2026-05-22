"""Pure normalizer for raw FRED observation values.

Isolates the parsing / conversion logic from all network I/O so it can be
unit-tested independently of any HTTP fixtures.

Design notes
------------
* Returns ``None`` for non-numeric or out-of-range values rather than
  raising, so the adapter can silently skip bad observations rather than
  crashing the ingestion run.
* The ``"."`` string is the FRED sentinel for a missing value and is
  treated as non-numeric.
* The :class:`~domain.macro.models.MacroFeature` validator already rejects
  values outside ``(-1e10, 1e10)``, so we guard against that range here and
  return ``None`` rather than letting Pydantic raise.
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature


def normalize_fred_observation(
    series_id: str,
    raw_value_str: str,
    country: str,
    timestamp: datetime,
    indicator: MacroIndicatorType,
) -> MacroFeature | None:
    """Convert a raw FRED observation string into a :class:`~domain.macro.models.MacroFeature`.

    Args:
        series_id: FRED series identifier (e.g. ``"GDPC1"``).  Stored in
            the feature's ``metadata`` for traceability.
        raw_value_str: Raw string value returned by FRED (e.g. ``"25000.0"``).
            The special FRED sentinel ``"."`` is treated as a missing value.
        country: ISO 3166-1 alpha-2 country code to attach to the feature.
        timestamp: UTC observation date parsed from the FRED response.
        indicator: The :class:`~domain.macro.enums.MacroIndicatorType` enum
            value for this observation.

    Returns:
        A :class:`~domain.macro.models.MacroFeature` with
        ``source=MacroSourceType.FRED`` and ``frequency=DataFrequency.MONTHLY``,
        or ``None`` if the value string cannot be parsed as a finite float
        within the accepted range.
    """
    # FRED uses "." as a sentinel for missing / not-yet-released data.
    if raw_value_str is None or raw_value_str.strip() in ("", "."):
        return None

    try:
        value = float(raw_value_str)
    except (ValueError, TypeError):
        return None

    # Guard against values outside the MacroFeature validator range.
    if not (-1e10 < value < 1e10):
        return None

    # Ensure timestamp is timezone-aware.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.FRED,
        value=value,
        timestamp=timestamp,
        frequency=DataFrequency.MONTHLY,
        country=country,
        metadata={"series_id": series_id, "source": "fred"},
    )
