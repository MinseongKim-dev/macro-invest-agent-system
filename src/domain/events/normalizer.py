"""Normalization helpers for external event ingestion (Chapter 7).

This module provides deterministic, testable helpers for constructing
:class:`~domain.events.models.NormalizedExternalEvent` objects from common
input patterns used in the platform.

Design notes
------------
* Normalization is strictly a transformation concern — it produces a
  ``NormalizedExternalEvent`` but applies **no interpretation or impact
  assessment**.  Impact is the responsibility of the Event Impact Adapter
  (see :mod:`services.event_impact_adapter`).
* All helpers are pure functions — same inputs always produce the same output.
* Raw source payloads are referenced by an opaque ``raw_payload_ref`` string;
  they are never parsed or stored in the normalized model.
* Deduplication is a separate concern handled by the repository layer.

Quality semantics
-----------------
* **missing** — required field absent; the record should be rejected before
  persisting or marked with ``status=PARTIAL``.
* **stale** — ``occurred_at`` age exceeds the freshness threshold for the type.
* **partial** — some optional but normally-expected fields are absent.
* **duplicate** — a record with the same (event_type, source, occurred_at)
  already exists.
* **degraded** — the record has quality issues but can still be used with caveats.
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventStatus,
    ExternalEventType,
    SourceReliabilityTier,
)
from domain.events.models import NormalizedExternalEvent, compute_event_freshness

# ---------------------------------------------------------------------------
# Source → reliability tier mapping
# ---------------------------------------------------------------------------

_SOURCE_RELIABILITY_MAP: dict[str, SourceReliabilityTier] = {
    # Tier 1 — official/institutional sources
    "federal_reserve": SourceReliabilityTier.TIER_1,
    "fed": SourceReliabilityTier.TIER_1,
    "bls": SourceReliabilityTier.TIER_1,
    "bea": SourceReliabilityTier.TIER_1,
    "treasury": SourceReliabilityTier.TIER_1,
    "ecb": SourceReliabilityTier.TIER_1,
    "bank_of_england": SourceReliabilityTier.TIER_1,
    "bank_of_japan": SourceReliabilityTier.TIER_1,
    "imf": SourceReliabilityTier.TIER_1,
    "world_bank": SourceReliabilityTier.TIER_1,
    "fred": SourceReliabilityTier.TIER_1,
    # Tier 2 — established data providers
    "reuters": SourceReliabilityTier.TIER_2,
    "bloomberg": SourceReliabilityTier.TIER_2,
    "wsj": SourceReliabilityTier.TIER_2,
    "financial_times": SourceReliabilityTier.TIER_2,
    # Tier 3 or manual
    "manual_entry": SourceReliabilityTier.TIER_3,
    "manual_analyst_entry": SourceReliabilityTier.TIER_3,
}


def infer_reliability_tier(source: str) -> SourceReliabilityTier:
    """Infer a heuristic reliability tier from a source identifier.

    Looks up ``source.lower()`` in the built-in map.  Returns
    :attr:`SourceReliabilityTier.UNKNOWN` when the source is not recognized.

    Args:
        source: Raw source identifier string.

    Returns:
        Heuristic :class:`~domain.events.enums.SourceReliabilityTier`.
    """
    return _SOURCE_RELIABILITY_MAP.get(source.lower().strip(), SourceReliabilityTier.UNKNOWN)


# ---------------------------------------------------------------------------
# Normalization entry point
# ---------------------------------------------------------------------------


def normalize_external_event(
    *,
    event_type: ExternalEventType,
    title: str,
    occurred_at: datetime,
    source: str,
    provenance: str,
    summary: str | None = None,
    entity: str | None = None,
    region: str | None = None,
    market_scope: list[str] | None = None,
    published_at: datetime | None = None,
    source_url: str | None = None,
    provider: str | None = None,
    reliability_tier: SourceReliabilityTier | None = None,
    tags: list[str] | None = None,
    affected_domains: list[str] | None = None,
    raw_payload_ref: str | None = None,
    metadata: dict[str, str] | None = None,
    reference_time: datetime | None = None,
) -> NormalizedExternalEvent:
    """Build a :class:`~domain.events.models.NormalizedExternalEvent` from keyword inputs.

    This is the primary normalization entry point.  It:

    1. Derives ``freshness`` from ``occurred_at`` age.
    2. Infers ``reliability_tier`` from ``source`` when not provided.
    3. Sets ``status`` to ``PARTIAL`` when ``summary`` is missing (partial record).
    4. Sets ``status`` to ``STALE`` when freshness is stale and no explicit status.

    Args:
        event_type: Category of the external event.
        title: Short scannable title (required).
        occurred_at: UTC datetime when the event occurred (required).
        source: Human-readable source name (required).
        provenance: Machine-readable provenance note (required).
        summary: Longer analyst-facing description; ``None`` → partial record.
        entity: Named entity (institution, company, country).
        region: Geographic region scope.
        market_scope: Affected asset classes / markets.
        published_at: Separate publication timestamp.
        source_url: URL to original source.
        provider: Internal provider/connector identifier.
        reliability_tier: Explicit reliability tier; inferred from source when
            ``None``.
        tags: Normalized taxonomy tags.
        affected_domains: Macro domains this event may affect.
        raw_payload_ref: Opaque reference to the raw source payload.
        metadata: Supplemental key/value metadata.
        reference_time: Reference time for freshness computation; defaults to now.

    Returns:
        A fully populated :class:`~domain.events.models.NormalizedExternalEvent`.
    """
    ref_time = reference_time or datetime.now(UTC)

    freshness = compute_event_freshness(event_type, occurred_at, reference_time=ref_time)

    tier = reliability_tier if reliability_tier is not None else infer_reliability_tier(source)

    # Determine status
    status = ExternalEventStatus.ACTIVE
    if not summary:
        status = ExternalEventStatus.PARTIAL
    elif freshness == ExternalEventFreshness.STALE:
        status = ExternalEventStatus.STALE

    return NormalizedExternalEvent(
        event_type=event_type,
        title=title.strip(),
        summary=summary,
        entity=entity,
        region=region,
        market_scope=market_scope or [],
        occurred_at=occurred_at,
        published_at=published_at,
        source=source,
        source_url=source_url,
        provider=provider,
        freshness=freshness,
        provenance=provenance,
        reliability_tier=tier,
        tags=tags or [],
        affected_domains=affected_domains or [],
        status=status,
        raw_payload_ref=raw_payload_ref,
        metadata=metadata or {},
    )


def assess_event_quality(event: NormalizedExternalEvent) -> list[str]:
    """Return a list of human-readable quality notes for a normalized event.

    Used to populate analyst-facing data quality surfaces.  Returns an empty
    list when the event has no quality concerns.

    Args:
        event: Normalized external event to assess.

    Returns:
        Ordered list of quality note strings.  Empty when no issues exist.
    """
    notes: list[str] = []
    if event.is_stale():
        notes.append(f"Event data is {event.freshness.value} (occurred_at: {event.occurred_at.date()})")
    if event.is_partial():
        notes.append("Event record is partial — some expected fields are missing")
    if event.status == ExternalEventStatus.DEGRADED:
        notes.append("Event has quality issues and should be interpreted with caution")
    if event.status == ExternalEventStatus.DUPLICATE:
        notes.append("Event is a suspected duplicate of an existing record")
    if event.reliability_tier == SourceReliabilityTier.TIER_3:
        notes.append(
            f"Source '{event.source}' is lower-reliability (heuristic tier 3) — "
            "interpret with caution"
        )
    if event.reliability_tier == SourceReliabilityTier.UNKNOWN:
        notes.append(f"Source '{event.source}' reliability is unknown")
    return notes
