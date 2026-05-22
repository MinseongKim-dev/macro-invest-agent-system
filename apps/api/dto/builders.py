"""Utility functions for building product DTOs from domain objects.

These helpers translate internal domain models into frontend-friendly
DTOs without leaking domain internals into the product surface.

All functions are pure and deterministic.
"""

from __future__ import annotations

from apps.api.dto.explanations import (
    AnalystWorkflowDTO,
    ReasoningStep,
    WhatChangedDTO,
)
from apps.api.dto.signals import SignalSummaryDTO
from apps.api.dto.snapshots import FeatureDeltaDTO, FeatureDTO
from apps.api.dto.trust import DataAvailability, FreshnessStatus, SourceAttribution, TrustMetadata
from src.domain.macro.comparison import FeatureDelta, SnapshotComparison
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.macro.narrative_builder import RegimeNarrative
from src.domain.signals.models import SignalOutput, SignalResult

# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

_INDICATOR_LABELS: dict[str, str] = {
    "gdp": "GDP Growth",
    "inflation": "Inflation",
    "unemployment": "Unemployment Rate",
    "interest_rate": "Interest Rate",
    "exchange_rate": "Exchange Rate",
    "stock_index": "Stock Index",
    "bond_yield": "Bond Yield",
    "credit_spread": "Credit Spread",
    "commodity_price": "Commodity Price",
    "pmi": "PMI",
}

_SOURCE_LABELS: dict[str, str] = {
    "fred": "FRED — Federal Reserve",
    "world_bank": "World Bank",
    "imf": "IMF",
    "oecd": "OECD",
    "ecb": "ECB — European Central Bank",
    "market_data": "Market Data",
    "custom": "Custom",
    "synthetic": "Synthetic (placeholder)",
}


def _indicator_label(indicator_type: str) -> str:
    return _INDICATOR_LABELS.get(indicator_type, indicator_type.replace("_", " ").title())


def _source_label(source_id: str) -> str:
    return _SOURCE_LABELS.get(source_id, source_id.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Trust metadata builders
# ---------------------------------------------------------------------------


def build_trust_from_snapshot(snapshot: MacroSnapshot) -> TrustMetadata:
    """Build :class:`~apps.api.dto.trust.TrustMetadata` from a domain snapshot.

    Freshness is always ``FRESH`` for a live-fetched snapshot; staleness
    detection requires a maximum-age policy (deferred to a future enhancement).
    """
    source_ids: list[str] = list(
        {str(f.source) for f in snapshot.features}
    )
    sources = [
        SourceAttribution(
            source_id=sid,
            source_label=_source_label(sid),
            retrieval_timestamp=snapshot.snapshot_time,
        )
        for sid in source_ids
    ]
    return TrustMetadata(
        snapshot_timestamp=snapshot.snapshot_time,
        freshness_status=FreshnessStatus.FRESH,
        availability=DataAvailability.FULL if snapshot.features else DataAvailability.UNAVAILABLE,
        is_degraded=False,
        sources=sources,
    )


def build_trust_from_comparison(
    comparison: SnapshotComparison,
    current_snapshot: MacroSnapshot,
    prior_snapshot_timestamp: object | None = None,
) -> TrustMetadata:
    """Build :class:`~apps.api.dto.trust.TrustMetadata` for a comparison response."""
    base = build_trust_from_snapshot(current_snapshot)
    availability = DataAvailability.FULL
    if comparison.no_prior_count > 0 and comparison.no_prior_count == len(comparison.deltas):
        availability = DataAvailability.UNAVAILABLE
    elif comparison.no_prior_count > 0:
        availability = DataAvailability.PARTIAL

    from datetime import datetime

    prior_ts: datetime | None = None
    if isinstance(prior_snapshot_timestamp, datetime):
        prior_ts = prior_snapshot_timestamp

    return TrustMetadata(
        snapshot_timestamp=base.snapshot_timestamp,
        previous_snapshot_timestamp=prior_ts,
        freshness_status=base.freshness_status,
        availability=availability,
        is_degraded=availability == DataAvailability.DEGRADED,
        sources=base.sources,
        changed_indicators_count=comparison.changed_count,
    )


def build_trust_from_signal_result(
    result: SignalResult,
) -> TrustMetadata:
    """Build :class:`~apps.api.dto.trust.TrustMetadata` for a signal result."""
    base = build_trust_from_snapshot(result.macro_snapshot)
    availability = DataAvailability.FULL if result.signals else DataAvailability.PARTIAL
    if not result.success:
        availability = DataAvailability.UNAVAILABLE
    return TrustMetadata(
        snapshot_timestamp=base.snapshot_timestamp,
        freshness_status=base.freshness_status,
        availability=availability,
        is_degraded=not result.success,
        sources=base.sources,
    )


# ---------------------------------------------------------------------------
# Domain → DTO converters
# ---------------------------------------------------------------------------


def feature_to_dto(feature: MacroFeature) -> FeatureDTO:
    """Convert a domain :class:`~domain.macro.models.MacroFeature` to :class:`FeatureDTO`."""
    return FeatureDTO(
        indicator_type=str(feature.indicator_type),
        indicator_label=_indicator_label(str(feature.indicator_type)),
        value=feature.value,
        source_id=str(feature.source),
        frequency=str(feature.frequency),
        country=feature.country,
        observed_at=feature.timestamp,
    )


def delta_to_dto(delta: FeatureDelta) -> FeatureDeltaDTO:
    """Convert a domain :class:`~domain.macro.comparison.FeatureDelta` to :class:`FeatureDeltaDTO`."""
    return FeatureDeltaDTO(
        indicator_type=delta.indicator_type,
        indicator_label=_indicator_label(delta.indicator_type),
        current_value=delta.current_value,
        prior_value=delta.prior_value,
        delta=delta.delta,
        direction=delta.direction,
        is_significant=False,
    )


def signal_output_to_dto(signal: SignalOutput) -> SignalSummaryDTO:
    """Convert a domain :class:`~domain.signals.models.SignalOutput` to :class:`SignalSummaryDTO`."""
    rules_total = len(signal.rule_results)
    rules_passed = sum(1 for v in signal.rule_results.values() if v)

    # Conflict surface fields — flatten from ConflictSurface if present
    conflict_status = "clean"
    is_mixed = False
    conflict_note = None
    quant_support_level = "unknown"
    if signal.conflict is not None:
        conflict_status = signal.conflict.conflict_status.value
        is_mixed = signal.conflict.is_mixed
        conflict_note = signal.conflict.conflict_note
        quant_support_level = signal.conflict.quant_support_level

    return SignalSummaryDTO(
        signal_id=signal.signal_id,
        signal_type=str(signal.signal_type),
        strength=str(signal.strength),
        score=signal.score,
        trend=str(signal.trend),
        rationale=signal.rationale,
        triggered_at=signal.triggered_at,
        rule_results=signal.rule_results,
        rules_passed=rules_passed,
        rules_total=rules_total,
        asset_class=signal.asset_class,
        supporting_regime=signal.supporting_regime,
        supporting_drivers=list(signal.supporting_drivers),
        conflicting_drivers=list(signal.conflicting_drivers),
        is_degraded=signal.is_degraded,
        caveat=signal.caveat,
        conflict_status=conflict_status,
        is_mixed=is_mixed,
        conflict_note=conflict_note,
        quant_support_level=quant_support_level,
    )


# ---------------------------------------------------------------------------
# Explanation Engine v2 builders
# ---------------------------------------------------------------------------

_STATE_LABELS: dict[str, str] = {
    "growth_state": "Growth",
    "inflation_state": "Inflation",
    "labor_state": "Labor",
    "policy_state": "Policy",
    "financial_conditions_state": "Financial Conditions",
}


def build_reasoning_chain(
    narrative: RegimeNarrative,
    conflict_status: str = "clean",
    conflict_note: str | None = None,
    quant_support_level: str = "unknown",
) -> list[ReasoningStep]:
    """Build a deterministic 6-step reasoning chain from a :class:`RegimeNarrative`.

    The chain is always returned with exactly 6 steps in canonical order:
    current_state → why → confidence → conflict → caveats → what_changed.

    Args:
        narrative: The :class:`~domain.macro.narrative_builder.RegimeNarrative` produced
            by :func:`~domain.macro.narrative_builder.build_regime_narrative`.
        conflict_status: Conflict/conviction status string from the signal's
            ConflictSurface (default ``"clean"``).
        conflict_note: Analyst-facing conflict explanation; ``None`` for clean signals.
        quant_support_level: Quant support level label (strong / moderate / weak / unknown).

    Returns:
        List of exactly 6 :class:`ReasoningStep` objects.
    """
    ctx = narrative["regime_context"]
    label = ctx.get("label", "unknown")
    family = ctx.get("family", "unknown")
    confidence = ctx.get("confidence", "unknown")
    transition = ctx.get("transition", "initial")
    transition_from_prior = ctx.get("transition_from_prior", "")

    # Step 1 — current_state
    state_parts = [
        f"{human_label}: {ctx.get(state_key, 'unknown')}"
        for state_key, human_label in _STATE_LABELS.items()
        if state_key in ctx
    ]
    # Fall back to the rationale_points state lines when context doesn't carry states
    if not state_parts:
        state_parts = [
            p for p in narrative["rationale_points"]
            if any(sl in p for sl in _STATE_LABELS.values())
        ]
    why_detail = "; ".join(state_parts) if state_parts else "See rationale points."

    # Step 3 — confidence detail
    confidence_detail_map = {
        "high": "All key indicators are fresh and non-conflicting.",
        "medium": "Some indicators are late or partially missing.",
        "low": "Significant data gaps, staleness, or conflicting signals present.",
    }
    confidence_detail = confidence_detail_map.get(confidence, "Confidence level uncertain.")

    # Step 4 — conflict
    conflict_value = conflict_status
    conflict_detail = conflict_note
    if conflict_detail is None and conflict_status != "clean":
        conflict_detail = f"Quant support: {quant_support_level}."

    # Step 5 — caveats
    caveats = narrative.get("caveats", [])
    if caveats:
        caveats_value = f"{len(caveats)} caveat(s)"
        caveats_detail = " | ".join(caveats)
    else:
        caveats_value = "none"
        caveats_detail = None

    # Step 6 — what_changed
    if transition == "initial" or not transition_from_prior:
        what_changed_value = "initial (no prior baseline)"
        what_changed_detail = "No prior regime available — transition analysis cannot be performed."
    else:
        what_changed_value = f"{transition} from {transition_from_prior}"
        what_changed_detail = (
            f"Regime transitioned from '{transition_from_prior}' "
            f"({transition}). Current label: '{label}'."
        )

    return [
        ReasoningStep(
            step=1,
            key="current_state",
            label="Current State",
            value=f"{label} ({family} family)",
            detail=narrative.get("summary", "")[:200] or None,
        ),
        ReasoningStep(
            step=2,
            key="why",
            label="Why",
            value=f"Regime: {label}",
            detail=why_detail,
        ),
        ReasoningStep(
            step=3,
            key="confidence",
            label="Confidence",
            value=confidence,
            detail=confidence_detail,
        ),
        ReasoningStep(
            step=4,
            key="conflict",
            label="Conflict",
            value=conflict_value,
            detail=conflict_detail,
        ),
        ReasoningStep(
            step=5,
            key="caveats",
            label="Caveats",
            value=caveats_value,
            detail=caveats_detail,
        ),
        ReasoningStep(
            step=6,
            key="what_changed",
            label="What Changed",
            value=what_changed_value,
            detail=what_changed_detail,
        ),
    ]


def build_what_changed(narrative: RegimeNarrative) -> WhatChangedDTO | None:
    """Build a :class:`WhatChangedDTO` from a :class:`RegimeNarrative`.

    Returns ``None`` when this is an initial regime (no prior baseline).

    Note: This builder derives change metadata from the ``RegimeNarrative`` context,
    which carries transition type and prior label but not the full prior ``MacroRegime``
    object.  For a complete change analysis with full severity classification, use
    :func:`~domain.macro.change_detection.detect_regime_change` with the actual
    domain objects (as the compare endpoint does).

    Args:
        narrative: The :class:`~domain.macro.narrative_builder.RegimeNarrative` to
            derive ``what_changed`` from.

    Returns:
        :class:`WhatChangedDTO` when transition data is available; ``None`` for initial regimes.
    """
    ctx = narrative["regime_context"]
    transition = ctx.get("transition", "initial")
    transition_from_prior = ctx.get("transition_from_prior", "")

    if transition == "initial" or not transition_from_prior:
        return None

    changed = transition not in {"unchanged", "initial", "unknown"}

    # Derive changed_dimensions and confidence_direction from transition type.
    # This is a best-effort approximation from the narrative context only.
    # The compare endpoint provides a more complete delta via detect_regime_change().
    changed_dimensions: list[str] = []
    confidence_direction = "unchanged"
    severity = "unchanged"

    if transition == "shift":
        changed_dimensions.append("label")
        severity = "moderate"  # minimum for a label change; compare endpoint refines further
    elif transition == "strengthening":
        changed_dimensions.append("confidence")
        confidence_direction = "improved"
        severity = "minor"
    elif transition == "weakening":
        changed_dimensions.append("confidence")
        confidence_direction = "weakened"
        severity = "minor"
    elif changed:
        severity = "minor"

    return WhatChangedDTO(
        prior_regime_label=transition_from_prior or None,
        transition_type=transition,
        changed=changed,
        severity=severity,
        changed_dimensions=changed_dimensions,
        confidence_direction=confidence_direction,
    )


def build_analyst_workflow(reasoning_chain: list[ReasoningStep]) -> AnalystWorkflowDTO:
    """Wrap a reasoning chain in an :class:`AnalystWorkflowDTO` for UI rendering.

    Args:
        reasoning_chain: The ordered list of :class:`ReasoningStep` objects from
            :func:`build_reasoning_chain`.

    Returns:
        :class:`AnalystWorkflowDTO` with the same steps.
    """
    return AnalystWorkflowDTO(steps=list(reasoning_chain))

