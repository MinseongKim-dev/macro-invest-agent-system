"""Deterministic rule-based attribution engine (Chapter 8).

Matches observed :class:`~domain.macro.comparison.FeatureDelta` records to
candidate :class:`~domain.events.models.NormalizedExternalEvent` records using
the configured :class:`~domain.attribution.models.AttributionRule` set.

Design principles
-----------------
* **Deterministic** — same inputs always produce the same attribution output.
* **Conservative** — attribution is advisory context only; it never overrides
  regime labels, signal directions, or confidence levels.
* **Heuristic** — all rules reflect analyst domain knowledge; outputs are
  explicitly labelled advisory.
* **Bounded** — only events that occurred *before* the snapshot's as-of date
  and within the rule's ``max_lag_days`` window are considered.
* **Best-match selection** — when multiple events match for the same delta,
  the closest (most recent) event within the lag window is selected as the
  primary candidate.  All other matches are included as secondary candidates.

Lag calculation
---------------
Lag is measured as calendar days: ``floor((as_of_date - event.occurred_at).total_seconds() / 86400)``.
Negative lags (events after the as-of date) are excluded.

Confidence assignment
---------------------
* ``high`` — exact rule match AND lag ≤ 50% of max_lag_days AND candidate
  reliability_tier is ``tier_1`` or ``tier_2``.
* ``medium`` — exact rule match AND lag ≤ max_lag_days.
* ``low`` — partial heuristic match (no explicit rule but related event type
  in the heuristic fallback map).
* ``unattributed`` — no plausible candidate found.

Partial / heuristic fallback
-----------------------------
When no explicit rule covers a ``(event_type, indicator_type)`` pair, the
engine consults a hard-coded heuristic fallback map that expresses broad
analytical knowledge (e.g. central_bank_decision → policy-related indicators).
Fallback matches produce ``confidence=low`` and ``match_status=partial``.
"""

from __future__ import annotations

from datetime import datetime

from domain.attribution.enums import AttributionConfidence, AttributionMatchStatus
from domain.attribution.models import (
    AttributionRule,
    AttributionRunResult,
    CandidateEventContext,
    CatalystContext,
    ChangeAttribution,
)
from domain.events.enums import SourceReliabilityTier
from domain.events.models import NormalizedExternalEvent
from domain.macro.comparison import FeatureDelta

# ---------------------------------------------------------------------------
# Heuristic fallback map
# (event_type → frozenset of indicator_types that are broadly related)
# ---------------------------------------------------------------------------

_HEURISTIC_FALLBACK: dict[str, frozenset[str]] = {
    "central_bank_decision": frozenset({
        "interest_rate", "policy_rate", "10y_yield", "yield_10y",
        "inflation", "cpi", "core_cpi", "pce",
    }),
    "policy_announcement": frozenset({
        "interest_rate", "policy_rate", "gdp", "retail_sales",
    }),
    "macro_release": frozenset({
        "gdp", "cpi", "core_cpi", "unemployment", "unemployment_rate",
        "retail_sales", "pmi", "manufacturing_pmi", "services_pmi",
        "10y_yield", "yield_10y", "inflation", "pce",
    }),
    "geopolitical_development": frozenset({
        "oil_price", "commodities", "fx", "equity_risk_premium",
    }),
    "market_catalyst": frozenset({
        "credit_spreads", "vix", "equity_risk_premium",
    }),
    "earnings_event": frozenset({
        "equity_earnings", "earnings_growth",
    }),
}

# ---------------------------------------------------------------------------
# Default built-in attribution rules (v1)
# ---------------------------------------------------------------------------

DEFAULT_ATTRIBUTION_RULES: list[AttributionRule] = [
    # Central bank decisions → rate and inflation indicators
    AttributionRule(
        rule_id="builtin-cbd-rate",
        event_type="central_bank_decision",
        indicator_type="interest_rate",
        max_lag_days=14,
        description="Fed/central bank decision affects short-term rates",
    ),
    AttributionRule(
        rule_id="builtin-cbd-10y",
        event_type="central_bank_decision",
        indicator_type="10y_yield",
        max_lag_days=21,
        description="Central bank decisions influence longer-dated yields",
    ),
    AttributionRule(
        rule_id="builtin-cbd-cpi",
        event_type="central_bank_decision",
        indicator_type="cpi",
        max_lag_days=30,
        description="Central bank decisions reflect inflation expectations",
    ),
    # CPI / macro release → inflation and unemployment
    AttributionRule(
        rule_id="builtin-mr-cpi",
        event_type="macro_release",
        indicator_type="cpi",
        max_lag_days=3,
        description="CPI release directly drives CPI delta",
    ),
    AttributionRule(
        rule_id="builtin-mr-unemployment",
        event_type="macro_release",
        indicator_type="unemployment_rate",
        max_lag_days=3,
        description="Jobs report drives unemployment rate delta",
    ),
    AttributionRule(
        rule_id="builtin-mr-gdp",
        event_type="macro_release",
        indicator_type="gdp",
        max_lag_days=5,
        description="GDP release drives GDP growth delta",
    ),
    AttributionRule(
        rule_id="builtin-mr-retail-sales",
        event_type="macro_release",
        indicator_type="retail_sales",
        max_lag_days=3,
        description="Retail sales release directly drives retail sales delta",
    ),
    AttributionRule(
        rule_id="builtin-mr-pmi",
        event_type="macro_release",
        indicator_type="pmi",
        max_lag_days=3,
        description="PMI release directly drives PMI delta",
    ),
    # Geopolitical events → broad macro uncertainty
    AttributionRule(
        rule_id="builtin-geo-10y",
        event_type="geopolitical_development",
        indicator_type="10y_yield",
        max_lag_days=14,
        description="Geopolitical shock can drive safe-haven yield moves",
    ),
]


# ---------------------------------------------------------------------------
# Attribution engine
# ---------------------------------------------------------------------------


def _compute_lag_days(event_occurred_at: datetime, as_of_date: datetime) -> int:
    """Return calendar days between event and as-of date (non-negative).

    Events after the as-of date return -1 (excluded by callers).
    """
    diff = as_of_date - event_occurred_at
    if diff.total_seconds() < 0:
        return -1
    return int(diff.total_seconds() / 86400)


def _is_high_confidence(
    lag_days: int,
    max_lag_days: int,
    reliability_tier: str,
) -> bool:
    """Return True when the match qualifies as high-confidence."""
    high_reliability = reliability_tier in {
        SourceReliabilityTier.TIER_1.value,
        SourceReliabilityTier.TIER_2.value,
    }
    lag_ok = lag_days <= max(1, max_lag_days // 2)
    return lag_ok and high_reliability


def _build_advisory_note(
    indicator_type: str,
    confidence: AttributionConfidence,
    candidate: CandidateEventContext | None,
) -> str:
    """Construct an analyst-facing advisory note for the attribution result."""
    if confidence == AttributionConfidence.UNATTRIBUTED:
        return (
            f"No candidate external event was identified as a plausible cause "
            f"for the observed change in {indicator_type!r}. "
            f"The delta may reflect data revisions, model noise, or events "
            f"not yet ingested."
        )
    assert candidate is not None  # noqa: S101
    conf_label = confidence.value
    return (
        f"Advisory ({conf_label} confidence): '{candidate.title}' "
        f"({candidate.event_type}, {candidate.source}) occurred "
        f"{candidate.lag_days} day(s) before the observed change in "
        f"{indicator_type!r}. This is a heuristic match — it does not "
        f"constitute a causal claim."
    )


def _candidate_from_event(
    event: NormalizedExternalEvent,
    lag_days: int,
    match_status: AttributionMatchStatus,
) -> CandidateEventContext:
    return CandidateEventContext(
        event_id=event.event_id,
        event_type=event.event_type.value,
        title=event.title,
        source=event.source,
        occurred_at=event.occurred_at,
        lag_days=lag_days,
        match_status=match_status,
        reliability_tier=event.reliability_tier.value,
    )


def attribute_delta(
    delta: FeatureDelta,
    candidate_events: list[NormalizedExternalEvent],
    as_of_date: datetime,
    rules: list[AttributionRule] | None = None,
) -> ChangeAttribution:
    """Attribute a single :class:`~domain.macro.comparison.FeatureDelta` to candidate events.

    Args:
        delta: The feature delta to attribute.
        candidate_events: External events to evaluate as candidate causes.
            Events after *as_of_date* are excluded automatically.
        as_of_date: The snapshot as-of date for lag calculation.
        rules: Attribution rules to apply.  Defaults to
            :data:`DEFAULT_ATTRIBUTION_RULES` when ``None``.

    Returns:
        A :class:`~domain.attribution.models.ChangeAttribution` read model.
    """
    active_rules = [r for r in (rules or DEFAULT_ATTRIBUTION_RULES) if r.is_active]

    indicator = delta.indicator_type
    matched_candidates: list[tuple[AttributionRule, CandidateEventContext]] = []
    partial_candidates: list[CandidateEventContext] = []

    for event in candidate_events:
        lag = _compute_lag_days(event.occurred_at, as_of_date)
        if lag < 0:
            continue  # exclude future events

        event_type_str = event.event_type.value

        # Check explicit rules first
        for rule in active_rules:
            if rule.event_type != event_type_str:
                continue
            if rule.indicator_type != indicator:
                continue
            if lag > rule.max_lag_days:
                continue
            candidate = _candidate_from_event(event, lag, AttributionMatchStatus.MATCHED)
            matched_candidates.append((rule, candidate))
            break
        else:
            # Heuristic fallback
            fallback_indicators = _HEURISTIC_FALLBACK.get(event_type_str, frozenset())
            if indicator in fallback_indicators and lag <= 30:
                candidate = _candidate_from_event(event, lag, AttributionMatchStatus.PARTIAL)
                partial_candidates.append(candidate)

    # Build typed candidates list — exact matches first (sorted by lag), then partial
    # matched_candidates contains (rule, candidate) tuples for exact matches
    exact: list[CandidateEventContext] = []
    best_rule: AttributionRule | None = None
    for rule, cand in matched_candidates:
        exact.append(cand)
        if best_rule is None:
            best_rule = rule

    exact.sort(key=lambda c: c.lag_days)
    partial_candidates.sort(key=lambda c: c.lag_days)

    all_candidates = exact + partial_candidates

    # Determine confidence
    if exact:
        best = exact[0]
        if _is_high_confidence(best.lag_days, best_rule.max_lag_days, best.reliability_tier):  # type: ignore[union-attr]
            confidence = AttributionConfidence.HIGH
        else:
            confidence = AttributionConfidence.MEDIUM
        primary = best
        rule_id = best_rule.rule_id if best_rule else None
    elif partial_candidates:
        primary = partial_candidates[0]
        confidence = AttributionConfidence.LOW
        rule_id = None
    else:
        primary = None
        confidence = AttributionConfidence.UNATTRIBUTED
        rule_id = None

    advisory_note = _build_advisory_note(indicator, confidence, primary)

    catalyst_ctx = CatalystContext(
        indicator_type=indicator,
        candidate_event_id=primary.event_id if primary else None,
        candidate_event_title=primary.title if primary else None,
        candidate_event_type=primary.event_type if primary else None,
        lag_days=primary.lag_days if primary else None,
        confidence=confidence,
        advisory_note=advisory_note,
        rule_id=rule_id,
    )

    return ChangeAttribution(
        indicator_type=indicator,
        direction=delta.direction,
        delta=delta.delta,
        confidence=confidence,
        candidates=all_candidates,
        catalyst_context=catalyst_ctx,
    )


def run_attribution(
    deltas: list[FeatureDelta],
    candidate_events: list[NormalizedExternalEvent],
    as_of_date: datetime,
    *,
    rules: list[AttributionRule] | None = None,
    snapshot_id: str | None = None,
    include_unchanged: bool = False,
) -> AttributionRunResult:
    """Run attribution for all feature deltas in a snapshot comparison.

    Args:
        deltas: Feature deltas from a ``SnapshotComparison``.
        candidate_events: External events to evaluate as candidate causes.
        as_of_date: The snapshot as-of date for lag calculation.
        rules: Attribution rules (defaults to :data:`DEFAULT_ATTRIBUTION_RULES`).
        snapshot_id: Optional snapshot ID for the result record.
        include_unchanged: When ``False`` (default), only ``increased`` and
            ``decreased`` deltas are attributed; ``unchanged`` and ``no_prior``
            deltas are skipped.

    Returns:
        An :class:`~domain.attribution.models.AttributionRunResult` with one
        attribution per qualifying delta.
    """
    attributions: list[ChangeAttribution] = []

    for delta in deltas:
        if not include_unchanged and delta.direction in {"unchanged", "no_prior"}:
            continue
        attribution = attribute_delta(
            delta=delta,
            candidate_events=candidate_events,
            as_of_date=as_of_date,
            rules=rules,
        )
        attributions.append(attribution)

    return AttributionRunResult(
        snapshot_id=snapshot_id,
        as_of_date=as_of_date,
        attributions=attributions,
    )
