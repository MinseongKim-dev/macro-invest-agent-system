"""Normalized external event domain model (Chapter 7 — External Intelligence).

This module defines the canonical ``NormalizedExternalEvent`` — the first-class
representation of a real-world catalyst or fact after it has been ingested from
a raw source and passed through the normalization layer.

Architecture boundaries
-----------------------
* **Raw source payload** — provider-specific, unpredictable shape; stored
  by reference only (``raw_payload_ref``); never parsed here.
* **NormalizedExternalEvent** — this module; structured, provenance-explicit,
  freshness-tagged, deterministic.
* **ExternalEventImpact** — downstream interpreted effects; defined in
  ``domain.events.impact``; produced by the Event Impact Adapter.

Design notes
------------
* All timestamps are UTC-aware ``datetime`` objects.
* Provenance is always explicit: ``source``, ``provider``, ``reliability_tier``,
  ``ingested_at``.
* ``raw_payload_ref`` is an opaque reference string (e.g. a storage key) so
  that the raw blob can be retrieved without coupling this model to any
  specific storage backend.
* ``affected_domains`` uses free-form strings rather than an enum so that new
  macro domain tags can be added without a schema migration.  Canonical
  values documented in ``docs/external_intelligence_v1.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventStatus,
    ExternalEventType,
    SourceReliabilityTier,
)

# ---------------------------------------------------------------------------
# Freshness thresholds (heuristic defaults — may be overridden per event type)
# ---------------------------------------------------------------------------

_FRESHNESS_THRESHOLDS: dict[ExternalEventType, tuple[timedelta, timedelta]] = {
    # (fresh_threshold, recent_threshold)  — older than recent_threshold → stale
    ExternalEventType.MACRO_RELEASE: (timedelta(hours=24), timedelta(days=3)),
    ExternalEventType.CENTRAL_BANK_DECISION: (timedelta(hours=48), timedelta(days=7)),
    ExternalEventType.POLICY_ANNOUNCEMENT: (timedelta(hours=48), timedelta(days=7)),
    ExternalEventType.EARNINGS_EVENT: (timedelta(hours=24), timedelta(days=5)),
    ExternalEventType.GEOPOLITICAL_DEVELOPMENT: (timedelta(hours=72), timedelta(days=14)),
    ExternalEventType.MARKET_CATALYST: (timedelta(hours=24), timedelta(days=3)),
    ExternalEventType.OTHER: (timedelta(hours=48), timedelta(days=7)),
}


def compute_event_freshness(
    event_type: ExternalEventType,
    occurred_at: datetime,
    *,
    reference_time: datetime | None = None,
) -> ExternalEventFreshness:
    """Derive freshness status for an event based on its type and age.

    Args:
        event_type: Type of the external event (determines thresholds).
        occurred_at: UTC datetime when the event occurred.
        reference_time: Reference time for age computation; defaults to now.

    Returns:
        :class:`~domain.events.enums.ExternalEventFreshness` classification.
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)

    age = reference_time - occurred_at
    fresh_threshold, recent_threshold = _FRESHNESS_THRESHOLDS.get(
        event_type, (timedelta(hours=48), timedelta(days=7))
    )
    if age <= fresh_threshold:
        return ExternalEventFreshness.FRESH
    if age <= recent_threshold:
        return ExternalEventFreshness.RECENT
    return ExternalEventFreshness.STALE


# ---------------------------------------------------------------------------
# Normalized external event model
# ---------------------------------------------------------------------------


class NormalizedExternalEvent(BaseModel, extra="forbid"):
    """A normalized, provenance-explicit, freshness-tagged external event record.

    This is the canonical representation of a real-world catalyst or fact
    after ingestion and normalization.  It is deliberately separate from:

    * raw provider payloads (referenced by ``raw_payload_ref`` only),
    * interpreted downstream effects (see :mod:`domain.events.impact`).

    Attributes:
        event_id: Unique identifier for this event record (UUID).
        event_type: Analyst-meaningful category (see :class:`ExternalEventType`).
        title: Short, scannable human-readable title (≤200 chars).
        summary: Longer analyst-facing description; ``None`` when unavailable.
        entity: Named entity associated with the event (e.g. "Federal Reserve",
            "Apple Inc.", "Russia").  ``None`` when not applicable.
        region: Geographic region scope (e.g. "US", "EU", "GLOBAL").
            ``None`` when not region-specific.
        market_scope: Asset classes or markets affected (e.g.
            ``["equities", "bonds", "fx"]``).  Empty when unknown.
        occurred_at: UTC datetime when the event actually occurred.
        published_at: UTC datetime when the event was published/announced.
            ``None`` when not separately tracked.
        ingested_at: UTC datetime when this record was created in the platform.
        source: Human-readable source name (e.g. ``"Federal Reserve"``,
            ``"BLS"``, ``"Reuters"``, ``"manual_entry"``).
        source_url: URL linking to the original source; ``None`` when unavailable.
        provider: Internal provider/connector identifier that ingested the
            event (e.g. ``"fred_release_calendar"``, ``"manual"``).
            ``None`` when ingested ad-hoc.
        freshness: Staleness classification derived from ``occurred_at`` age.
        provenance: Machine-readable provenance note describing how this
            record was created (e.g. ``"fred_release_calendar_v1"``,
            ``"manual_analyst_entry"``).
        reliability_tier: Heuristic source reliability classification.
            **Explicitly heuristic** — see :class:`SourceReliabilityTier`.
        tags: Normalized taxonomy tags for filtering/grouping
            (e.g. ``["inflation", "monetary_policy", "rate_decision"]``).
        affected_domains: Macro domains this event may affect
            (e.g. ``["inflation", "growth", "policy"]``).
            Canonical values: ``inflation``, ``growth``, ``employment``,
            ``policy``, ``credit``, ``fx``, ``commodities``, ``geopolitical``.
        status: Lifecycle/quality status of this record.
        raw_payload_ref: Opaque reference to the original raw source payload
            in the storage backend; ``None`` when not stored.
        metadata: Arbitrary supplemental key/value pairs.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: ExternalEventType
    title: str = Field(..., min_length=1, max_length=500)
    summary: str | None = Field(default=None)
    entity: str | None = Field(default=None)
    region: str | None = Field(default=None)
    market_scope: list[str] = Field(default_factory=list)
    occurred_at: datetime
    published_at: datetime | None = Field(default=None)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = Field(..., min_length=1)
    source_url: str | None = Field(default=None)
    provider: str | None = Field(default=None)
    freshness: ExternalEventFreshness = Field(default=ExternalEventFreshness.UNKNOWN)
    provenance: str = Field(
        ...,
        min_length=1,
        description="Machine-readable provenance note (e.g. 'fred_release_calendar_v1')",
    )
    reliability_tier: SourceReliabilityTier = Field(
        default=SourceReliabilityTier.UNKNOWN,
        description=(
            "Heuristic source reliability tier. "
            "Not statistically calibrated — reflects source category intent."
        ),
    )
    tags: list[str] = Field(default_factory=list)
    affected_domains: list[str] = Field(default_factory=list)
    status: ExternalEventStatus = Field(default=ExternalEventStatus.ACTIVE)
    raw_payload_ref: str | None = Field(
        default=None,
        description="Opaque reference to the raw source payload; None when not stored",
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_freshness_if_unknown(self) -> NormalizedExternalEvent:
        """Compute freshness from occurred_at if not explicitly set."""
        if self.freshness == ExternalEventFreshness.UNKNOWN:
            computed = compute_event_freshness(self.event_type, self.occurred_at)
            object.__setattr__(self, "freshness", computed)
        return self

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_stale(self) -> bool:
        """Return True when freshness is STALE or UNKNOWN."""
        return self.freshness in {ExternalEventFreshness.STALE, ExternalEventFreshness.UNKNOWN}

    def is_partial(self) -> bool:
        """Return True when status is PARTIAL."""
        return self.status == ExternalEventStatus.PARTIAL

    def is_duplicate(self) -> bool:
        """Return True when status is DUPLICATE."""
        return self.status == ExternalEventStatus.DUPLICATE

    def is_usable(self) -> bool:
        """Return True when the event record is usable by downstream adapters.

        An event is not usable if it is a duplicate or if freshness is stale
        and status is degraded.
        """
        if self.status == ExternalEventStatus.DUPLICATE:
            return False
        return not (self.status == ExternalEventStatus.DEGRADED and self.is_stale())
