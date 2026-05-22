"""External Event Impact Adapter v1 (Chapter 7, Chunk 2).

Translates :class:`~domain.events.models.NormalizedExternalEvent` records into
conservative, structured :class:`~domain.events.impact.ExternalEventImpact`
objects that downstream layers (explanation, conflict, confidence) can safely
consume.

Adapter design principles
--------------------------
* **Deterministic** — same normalized event always produces the same impact.
* **Conservative** — defaults are explanation evidence and caveats; confidence
  downgrades and conflict contributions are only triggered for specific
  high-impact event categories.
* **Heuristic** — all mappings are rules-based heuristics, explicitly labelled
  as such; no statistical calibration is claimed.
* **Non-overriding** — the adapter never directly rewrites regime labels or
  signal directions.
* **Bounded** — rules are keyed only on ``event_type``; fine-grained per-event
  interpretation is deferred to later phases.

Priority routing (from spec)
-----------------------------
1. explanation evidence
2. caveats / notes
3. conflict enrichment
4. confidence downgrade hint
5. (limited score/signal adjustment — deferred)
6. (direct signal override — deferred, requires explicit justification)

Impact mapping rules (v1 heuristic)
-------------------------------------
``central_bank_decision``
    • explanation evidence: describes the policy action context
    • caveat: policy uncertainty may affect current assessment
    • conflict contributor: policy_catalyst_active
    • confidence downgrade hint: True (policy decisions introduce uncertainty)
    • severity: high

``policy_announcement``
    • explanation evidence: notes the policy context
    • caveat: policy change may affect forward-looking signals
    • conflict contributor: policy_catalyst_active
    • confidence downgrade hint: True
    • severity: moderate

``geopolitical_development``
    • explanation evidence: notes the geopolitical context
    • caveat: geopolitical risk is elevated; interpretation should be conservative
    • conflict contributor: geopolitical_risk_elevated
    • confidence downgrade hint: True
    • severity: moderate

``macro_release``
    • explanation evidence: references the data release
    • severity: low (data releases are expected and already reflected in snapshots)

``earnings_event``
    • explanation evidence: notes the earnings context
    • severity: low

``market_catalyst``
    • explanation evidence: notes the market catalyst
    • caveat: market catalyst may not yet be reflected in macro data
    • severity: moderate

``other``
    • explanation evidence only
    • severity: low
"""

from __future__ import annotations

from collections.abc import Callable

from domain.events.enums import ExternalEventType, SourceReliabilityTier
from domain.events.impact import ExternalEventImpact, ExternalEventImpactRouting
from domain.events.models import NormalizedExternalEvent


def _build_impact(  # noqa: PLR0913
    event: NormalizedExternalEvent,
    *,
    explanation_evidence: list[str],
    caveat_notes: list[str],
    conflict_contributors: list[str],
    confidence_downgrade_hint: bool,
    confidence_downgrade_reason: str | None,
    change_context_annotation: str | None,
    impact_severity: str,
) -> ExternalEventImpact:
    """Construct an :class:`ExternalEventImpact` with routing flags computed."""
    routing = ExternalEventImpactRouting(
        has_explanation_evidence=bool(explanation_evidence),
        has_caveat_notes=bool(caveat_notes),
        has_conflict_contributors=bool(conflict_contributors),
        has_confidence_downgrade=confidence_downgrade_hint,
        has_change_context=change_context_annotation is not None,
    )
    return ExternalEventImpact(
        source_event_id=event.event_id,
        source_event_type=event.event_type,
        explanation_evidence=explanation_evidence,
        caveat_notes=caveat_notes,
        conflict_contributors=conflict_contributors,
        confidence_downgrade_hint=confidence_downgrade_hint,
        confidence_downgrade_reason=confidence_downgrade_reason,
        change_context_annotation=change_context_annotation,
        impact_severity=impact_severity,
        affected_domains=list(event.affected_domains),
        routing=routing,
        is_heuristic=True,
    )


def _reliability_caveat(event: NormalizedExternalEvent) -> list[str]:
    """Return a reliability caveat when the source is lower-tier."""
    if event.reliability_tier in {
        SourceReliabilityTier.TIER_3,
        SourceReliabilityTier.UNKNOWN,
    }:
        return [
            f"Event source '{event.source}' has heuristic reliability tier "
            f"'{event.reliability_tier.value}' — interpret with caution."
        ]
    return []


def _entity_fragment(event: NormalizedExternalEvent) -> str:
    """Return a short entity/region string for use in evidence text."""
    parts = []
    if event.entity:
        parts.append(event.entity)
    if event.region:
        parts.append(f"({event.region})")
    return " ".join(parts) if parts else ""


class EventImpactAdapter:
    """Deterministic adapter mapping normalized events to conservative impacts.

    Usage::

        adapter = EventImpactAdapter()
        impact = adapter.adapt(event)

    The adapter is stateless — it can be reused across calls.
    """

    def adapt(self, event: NormalizedExternalEvent) -> ExternalEventImpact:
        """Translate *event* into a conservative :class:`ExternalEventImpact`.

        Args:
            event: A normalized external event to adapt.

        Returns:
            Structured :class:`ExternalEventImpact` with conservative routing.
        """
        handler = _HANDLERS.get(event.event_type, _handle_other)
        return handler(event)

    def adapt_many(
        self, events: list[NormalizedExternalEvent]
    ) -> list[ExternalEventImpact]:
        """Adapt a list of events, skipping non-usable records.

        Events where :meth:`~domain.events.models.NormalizedExternalEvent.is_usable`
        returns ``False`` (duplicates, degraded-stale) are excluded.

        Args:
            events: List of normalized events to adapt.

        Returns:
            List of :class:`ExternalEventImpact` objects for usable events.
        """
        return [self.adapt(e) for e in events if e.is_usable()]


# ---------------------------------------------------------------------------
# Per-event-type handlers
# ---------------------------------------------------------------------------


def _handle_central_bank_decision(event: NormalizedExternalEvent) -> ExternalEventImpact:
    entity = _entity_fragment(event)
    evidence = [f"Central bank decision ({entity}): {event.title}" if entity else f"Central bank decision: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    caveats = [
        "A central bank decision is active — policy uncertainty may affect current regime assessment."
    ] + _reliability_caveat(event)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=caveats,
        conflict_contributors=["policy_catalyst_active"],
        confidence_downgrade_hint=True,
        confidence_downgrade_reason=(
            "Central bank decisions introduce forward-looking policy uncertainty "
            "not yet reflected in macro data."
        ),
        change_context_annotation=(
            f"Central bank action recorded: {event.title}. "
            "Policy-sensitive indicators may shift in subsequent snapshots."
        ),
        impact_severity="high",
    )


def _handle_policy_announcement(event: NormalizedExternalEvent) -> ExternalEventImpact:
    entity = _entity_fragment(event)
    evidence = [f"Policy announcement ({entity}): {event.title}" if entity else f"Policy announcement: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    caveats = [
        "A policy announcement is active — changes may affect forward-looking signals."
    ] + _reliability_caveat(event)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=caveats,
        conflict_contributors=["policy_catalyst_active"],
        confidence_downgrade_hint=True,
        confidence_downgrade_reason=(
            "Policy announcements may introduce uncertainty in macro signal interpretation."
        ),
        change_context_annotation=None,
        impact_severity="moderate",
    )


def _handle_geopolitical_development(event: NormalizedExternalEvent) -> ExternalEventImpact:
    entity = _entity_fragment(event)
    evidence = [f"Geopolitical development ({entity}): {event.title}" if entity else f"Geopolitical development: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    caveats = [
        "Geopolitical risk is elevated — macro interpretation should be conservative.",
        "Geopolitical causality is heuristic; direct regime impact is not statistically validated.",
    ] + _reliability_caveat(event)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=caveats,
        conflict_contributors=["geopolitical_risk_elevated"],
        confidence_downgrade_hint=True,
        confidence_downgrade_reason=(
            "Elevated geopolitical risk creates uncertainty not captured in current macro data."
        ),
        change_context_annotation=None,
        impact_severity="moderate",
    )


def _handle_macro_release(event: NormalizedExternalEvent) -> ExternalEventImpact:
    evidence = [f"Macro data release: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=_reliability_caveat(event),
        conflict_contributors=[],
        confidence_downgrade_hint=False,
        confidence_downgrade_reason=None,
        change_context_annotation=None,
        impact_severity="low",
    )


def _handle_earnings_event(event: NormalizedExternalEvent) -> ExternalEventImpact:
    entity = _entity_fragment(event)
    evidence = [f"Earnings event ({entity}): {event.title}" if entity else f"Earnings event: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=_reliability_caveat(event),
        conflict_contributors=[],
        confidence_downgrade_hint=False,
        confidence_downgrade_reason=None,
        change_context_annotation=None,
        impact_severity="low",
    )


def _handle_market_catalyst(event: NormalizedExternalEvent) -> ExternalEventImpact:
    evidence = [f"Market catalyst: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    caveats = [
        "Market catalyst detected — may not yet be reflected in macro data snapshots."
    ] + _reliability_caveat(event)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=caveats,
        conflict_contributors=[],
        confidence_downgrade_hint=False,
        confidence_downgrade_reason=None,
        change_context_annotation=None,
        impact_severity="moderate",
    )


def _handle_other(event: NormalizedExternalEvent) -> ExternalEventImpact:
    evidence = [f"External event: {event.title}"]
    if event.summary:
        evidence.append(event.summary)
    return _build_impact(
        event,
        explanation_evidence=evidence,
        caveat_notes=_reliability_caveat(event),
        conflict_contributors=[],
        confidence_downgrade_hint=False,
        confidence_downgrade_reason=None,
        change_context_annotation=None,
        impact_severity="low",
    )


_HANDLERS: dict[ExternalEventType, Callable[[NormalizedExternalEvent], ExternalEventImpact]] = {
    ExternalEventType.CENTRAL_BANK_DECISION: _handle_central_bank_decision,
    ExternalEventType.POLICY_ANNOUNCEMENT: _handle_policy_announcement,
    ExternalEventType.GEOPOLITICAL_DEVELOPMENT: _handle_geopolitical_development,
    ExternalEventType.MACRO_RELEASE: _handle_macro_release,
    ExternalEventType.EARNINGS_EVENT: _handle_earnings_event,
    ExternalEventType.MARKET_CATALYST: _handle_market_catalyst,
    ExternalEventType.OTHER: _handle_other,
}
