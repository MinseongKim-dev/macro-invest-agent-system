"""Deterministic Phase 3 rules mapping snapshot states to regime labels."""

from __future__ import annotations

from domain.macro.regime import (
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    regime_family_for_label,
)
from domain.macro.snapshot import (
    DegradedStatus,
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    MacroSnapshotState,
    PolicyState,
)
from domain.quant.models import QuantScoreBundle
from pipelines.ingestion.models import FreshnessStatus


def _has_unknown_state(snapshot: MacroSnapshotState) -> bool:
    states = (
        snapshot.growth_state,
        snapshot.inflation_state,
        snapshot.labor_state,
        snapshot.policy_state,
        snapshot.financial_conditions_state,
    )
    return any(str(state).endswith("unknown") for state in states)


def map_snapshot_to_regime_label(snapshot: MacroSnapshotState) -> RegimeLabel:
    """Map a macro snapshot to a regime label using explicit rule order."""
    if snapshot.degraded_status in {
        DegradedStatus.MISSING,
        DegradedStatus.SOURCE_UNAVAILABLE,
    }:
        return RegimeLabel.UNCLEAR
    if snapshot.freshness_status in {FreshnessStatus.STALE, FreshnessStatus.UNKNOWN}:
        return RegimeLabel.UNCLEAR
    if _has_unknown_state(snapshot):
        return RegimeLabel.MIXED

    if (
        snapshot.growth_state == GrowthState.ACCELERATING
        and snapshot.inflation_state == InflationState.COOLING
        and snapshot.labor_state in {LaborState.TIGHT, LaborState.SOFTENING}
        and snapshot.policy_state in {PolicyState.NEUTRAL, PolicyState.EASING_BIAS}
        and snapshot.financial_conditions_state
        in {FinancialConditionsState.NEUTRAL, FinancialConditionsState.LOOSE}
    ):
        return RegimeLabel.GOLDILOCKS

    if snapshot.inflation_state == InflationState.COOLING and snapshot.growth_state in {
        GrowthState.MIXED,
        GrowthState.SLOWING,
    }:
        return RegimeLabel.DISINFLATION

    if (
        snapshot.growth_state == GrowthState.SLOWING
        and snapshot.labor_state == LaborState.WEAK
        and snapshot.policy_state == PolicyState.RESTRICTIVE
        and snapshot.financial_conditions_state == FinancialConditionsState.TIGHT
    ):
        return RegimeLabel.CONTRACTION

    if (
        snapshot.policy_state == PolicyState.RESTRICTIVE
        and snapshot.financial_conditions_state == FinancialConditionsState.TIGHT
        and snapshot.growth_state in {GrowthState.SLOWING, GrowthState.MIXED}
    ):
        return RegimeLabel.POLICY_TIGHTENING_DRAG

    if (
        snapshot.growth_state == GrowthState.SLOWING
        and snapshot.inflation_state == InflationState.REACCELERATING
        and snapshot.labor_state in {LaborState.SOFTENING, LaborState.WEAK}
    ):
        return RegimeLabel.STAGFLATION_RISK

    if (
        snapshot.inflation_state == InflationState.REACCELERATING
        and snapshot.growth_state in {GrowthState.ACCELERATING, GrowthState.MIXED}
        and snapshot.policy_state == PolicyState.EASING_BIAS
    ):
        return RegimeLabel.REFLATION

    if (
        snapshot.growth_state == GrowthState.SLOWING
        and snapshot.labor_state in {LaborState.SOFTENING, LaborState.WEAK}
        and snapshot.inflation_state in {InflationState.STICKY, InflationState.COOLING}
    ):
        return RegimeLabel.SLOWDOWN

    return RegimeLabel.MIXED


def map_snapshot_to_regime(snapshot: MacroSnapshotState) -> tuple[RegimeLabel, RegimeFamily]:
    label = map_snapshot_to_regime_label(snapshot)
    return label, regime_family_for_label(label)


def build_regime_rationale(snapshot: MacroSnapshotState, label: RegimeLabel) -> str:
    return (
        "growth="
        f"{snapshot.growth_state.value}, inflation={snapshot.inflation_state.value}, "
        f"labor={snapshot.labor_state.value}, policy={snapshot.policy_state.value}, "
        f"financial_conditions={snapshot.financial_conditions_state.value}, "
        f"label={label.value}"
    )


def derive_regime_confidence(
    snapshot: MacroSnapshotState,
    label: RegimeLabel,
    quant_scores: QuantScoreBundle | None = None,
) -> RegimeConfidence:
    """Derive confidence from freshness, degraded status, state coherence, and quant scores.

    Confidence derivation order
    ---------------------------
    1. Hard floor conditions — always LOW regardless of quant support:
       - critical degraded status (``missing``, ``source_unavailable``)
       - stale or unknown freshness
    2. Partial / late conditions — floor at MEDIUM:
       - ``degraded_status = partial``
       - ``freshness_status = late``
    3. Unknown category states — one unknown → MEDIUM; two or more → LOW.
    4. Non-directional labels — ``mixed`` / ``unclear`` → always LOW.
    5. Quant score adjustment (applied only when quant_scores provided and
       preliminary confidence is HIGH or MEDIUM):
       - ``breadth < 0.60`` (fewer than 3 of 5 dimensions known) →
         cap at MEDIUM, cannot be HIGH.
       - ``overall_support < 0.40`` → downgrade HIGH → MEDIUM; MEDIUM → LOW
         (quant shows insufficient positive support for the current label).
       - ``overall_support >= 0.65`` and all states clean → confirm HIGH.

    Args:
        snapshot: The macro snapshot used to derive this regime.
        label: The resolved regime label.
        quant_scores: Optional :class:`~domain.quant.models.QuantScoreBundle`.
            When provided, quant signals may further adjust confidence.

    Returns:
        :class:`RegimeConfidence` — ``high``, ``medium``, or ``low``.
    """
    # --- Hard floor conditions (always LOW) ---
    if snapshot.degraded_status in {DegradedStatus.MISSING, DegradedStatus.SOURCE_UNAVAILABLE}:
        return RegimeConfidence.LOW
    if snapshot.freshness_status in {FreshnessStatus.STALE, FreshnessStatus.UNKNOWN}:
        return RegimeConfidence.LOW

    confidence = RegimeConfidence.HIGH

    # --- Partial / late → floor at MEDIUM ---
    if snapshot.degraded_status == DegradedStatus.PARTIAL:
        confidence = RegimeConfidence.MEDIUM
    if snapshot.freshness_status == FreshnessStatus.LATE:
        confidence = RegimeConfidence.MEDIUM

    # --- Unknown category states ---
    unknown_count = sum(
        1
        for state in (
            snapshot.growth_state,
            snapshot.inflation_state,
            snapshot.labor_state,
            snapshot.policy_state,
            snapshot.financial_conditions_state,
        )
        if str(state).endswith("unknown")
    )
    if unknown_count > 0:
        confidence = RegimeConfidence.MEDIUM if unknown_count == 1 else RegimeConfidence.LOW

    # --- Non-directional labels always LOW ---
    if label in {RegimeLabel.MIXED, RegimeLabel.UNCLEAR}:
        return RegimeConfidence.LOW

    # --- Quant score adjustment (Chunk 2 addition) ---
    if quant_scores is not None and confidence != RegimeConfidence.LOW:
        if quant_scores.breadth < 0.60 and confidence == RegimeConfidence.HIGH:
            # Insufficient dimension coverage — cannot support HIGH confidence
            confidence = RegimeConfidence.MEDIUM
        if quant_scores.overall_support < 0.40:
            # Weak quant support — downgrade one level
            if confidence == RegimeConfidence.HIGH:
                confidence = RegimeConfidence.MEDIUM
            elif confidence == RegimeConfidence.MEDIUM:
                confidence = RegimeConfidence.LOW

    return confidence


def derive_regime_missing_inputs(snapshot: MacroSnapshotState) -> list[str]:
    return list(snapshot.missing_indicators)


def derive_regime_warnings(
    snapshot: MacroSnapshotState,
    label: RegimeLabel,
    confidence: RegimeConfidence,
    missing_inputs: list[str],
    is_seeded: bool = False,
) -> list[str]:
    """Derive analyst-facing warning strings from snapshot and regime state.

    Each warning is a concise, human-readable sentence suitable for direct
    rendering as a badge or tooltip in the product UI.  Warnings do not
    duplicate the ``rationale_summary``; they specifically flag degraded,
    stale, missing-input, or bootstrap conditions that require analyst
    attention.

    Args:
        snapshot: The macro snapshot state used to derive this regime.
        label: The resolved regime label.
        confidence: The derived regime confidence level.
        missing_inputs: Indicators that were absent when the regime was built.
        is_seeded: True when this regime was created by the startup bootstrap
            seeder from synthetic data.

    Returns:
        Ordered list of warning strings.  Empty list when the regime is
        fully healthy and not synthetic.
    """
    warnings: list[str] = []

    if is_seeded:
        warnings.append(
            "Bootstrap data: this regime was generated from synthetic seed data "
            "and does not reflect a real ingestion pipeline run."
        )

    if snapshot.freshness_status == FreshnessStatus.STALE:
        warnings.append(
            "Stale data: underlying indicators are older than the expected "
            "update window.  This regime classification may be outdated."
        )
    elif snapshot.freshness_status == FreshnessStatus.LATE:
        warnings.append(
            "Late data: some indicators have not been updated within their "
            "expected window.  Regime accuracy may be reduced."
        )
    elif snapshot.freshness_status == FreshnessStatus.UNKNOWN:
        warnings.append(
            "Data freshness unknown: unable to confirm whether underlying "
            "indicators are current.  Treat this regime with caution."
        )

    if snapshot.degraded_status == DegradedStatus.MISSING:
        warnings.append(
            "Critical data missing: the regime was derived from a severely "
            "incomplete snapshot.  Classification accuracy is significantly reduced."
        )
    elif snapshot.degraded_status == DegradedStatus.PARTIAL:
        warnings.append(
            "Partial data: some indicators were missing when this regime was "
            "built.  Classification may be less reliable than usual."
        )
    elif snapshot.degraded_status == DegradedStatus.SOURCE_UNAVAILABLE:
        warnings.append(
            "Data source unavailable: regime reflects the last available "
            "snapshot.  Real-time conditions may have changed."
        )

    if missing_inputs:
        count = len(missing_inputs)
        names = ", ".join(missing_inputs[:3])
        suffix = f" and {count - 3} more" if count > 3 else ""
        warnings.append(
            f"Missing {count} indicator(s): {names}{suffix}. "
            "Regime derived from partial evidence."
        )

    if confidence == RegimeConfidence.LOW:
        warnings.append(
            "Low confidence: conflicting or insufficient signals reduce the "
            "reliability of this regime label.  Do not base high-conviction "
            "decisions on this classification alone."
        )

    if label in {RegimeLabel.MIXED, RegimeLabel.UNCLEAR}:
        warnings.append(
            "Non-directional regime (mixed/unclear): no asset-level signals "
            "can be derived with meaningful confidence from this classification."
        )

    return warnings
