"""Enumerations for the Catalyst Attribution domain (Chapter 8).

These enums define the controlled vocabularies used across:
* attribution confidence levels,
* attribution match status.

Design notes
------------
* All enums use ``StrEnum`` so that serialization (JSON, Pydantic) produces
  human-readable strings without extra conversion.
* ``AttributionConfidence`` is explicitly advisory — values reflect the
  quality of the match, not a calibrated probability.
"""

from __future__ import annotations

from enum import StrEnum


class AttributionConfidence(StrEnum):
    """Confidence level for a ``ChangeAttribution`` result.

    ``high``
        The event type and indicator type match a defined rule, and the
        observed delta falls within the expected lag window.  Advisory only —
        does not constitute a causal claim.
    ``medium``
        The event type and indicator type match a defined rule, but the lag
        is approaching the outer boundary or the delta is small.
    ``low``
        A partial or heuristic match — the event type is plausibly related
        to the indicator type but no explicit rule covers this combination.
    ``unattributed``
        No candidate event was identified as a plausible cause for this
        feature delta.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNATTRIBUTED = "unattributed"


class AttributionMatchStatus(StrEnum):
    """Match status for a single candidate attribution.

    ``matched``
        The candidate event satisfies the rule's event_type, indicator_type,
        and max_lag_days constraints.
    ``partial``
        The event type matches but the lag exceeds the strict window or the
        indicator type is only heuristically related.
    ``no_match``
        The candidate event does not satisfy the rule constraints.
    """

    MATCHED = "matched"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
