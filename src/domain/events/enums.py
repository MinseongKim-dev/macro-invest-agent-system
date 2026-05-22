"""Enumerations for the External Intelligence domain (Chapter 7).

These enums define the controlled vocabularies used across:
* normalized external event classification,
* source freshness and reliability tiers,
* event lifecycle / quality status.

Design notes
------------
* All enums use ``StrEnum`` so that serialization (JSON, Pydantic) produces
  human-readable strings without extra conversion.
* ``SourceReliabilityTier`` is explicitly heuristic — values reflect source
  category intent, not statistically validated accuracy scores.
"""

from __future__ import annotations

from enum import StrEnum


class ExternalEventType(StrEnum):
    """Analyst-meaningful category of a normalized external event.

    ``macro_release``
        Scheduled economic data releases (CPI, GDP, jobs report, etc.).
    ``central_bank_decision``
        Central bank meeting outcomes, rate decisions, or forward guidance.
    ``policy_announcement``
        Government / fiscal / regulatory policy announcements.
    ``earnings_event``
        Corporate earnings releases or guidance events.
    ``geopolitical_development``
        Significant geopolitical events (sanctions, conflicts, elections).
    ``market_catalyst``
        Market-moving catalyst not covered by other types (e.g. index
        rebalancing, commodity supply shock, systemic stress event).
    ``other``
        External events that do not fit the above categories.
    """

    MACRO_RELEASE = "macro_release"
    CENTRAL_BANK_DECISION = "central_bank_decision"
    POLICY_ANNOUNCEMENT = "policy_announcement"
    EARNINGS_EVENT = "earnings_event"
    GEOPOLITICAL_DEVELOPMENT = "geopolitical_development"
    MARKET_CATALYST = "market_catalyst"
    OTHER = "other"


class ExternalEventFreshness(StrEnum):
    """Staleness classification for a normalized external event.

    ``fresh``
        Event occurred within the platform's expected freshness window
        (heuristic; configurable per event type).
    ``recent``
        Event occurred recently but is approaching the staleness threshold.
    ``stale``
        Event is older than the freshness window; downstream consumers should
        treat it with reduced weight.
    ``unknown``
        Freshness cannot be determined (e.g., ``occurred_at`` is absent).
    """

    FRESH = "fresh"
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


class SourceReliabilityTier(StrEnum):
    """Heuristic reliability classification for an external event source.

    This is an *explicitly heuristic* classification.  Values reflect source
    category expectations — they are not statistically calibrated accuracy
    scores.  Downstream consumers must not treat ``tier_1`` as a guarantee of
    factual correctness.

    ``tier_1``
        High-reliability official or institutional sources (e.g. Federal
        Reserve, BLS, BEA, official government releases).
    ``tier_2``
        Known / established data providers with structured output (e.g.
        licensed financial data vendors, major financial news services with
        structured event feeds).
    ``tier_3``
        Lower-reliability or unverified sources (e.g. social media, informal
        aggregators, manually entered events).
    ``unknown``
        Reliability tier could not be determined for this source.
    """

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    UNKNOWN = "unknown"


class ExternalEventStatus(StrEnum):
    """Lifecycle / quality status of a normalized external event record.

    ``active``
        Event is current and has not been superseded or invalidated.
    ``stale``
        Event data is older than the expected freshness window.
    ``partial``
        The event record is incomplete — some expected fields are missing.
    ``duplicate``
        This event is a detected duplicate of an existing record (deduplication).
    ``degraded``
        The event record has quality issues but is still usable with caveats.
    """

    ACTIVE = "active"
    STALE = "stale"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    DEGRADED = "degraded"
