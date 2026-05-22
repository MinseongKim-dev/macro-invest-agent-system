"""Quant Scoring Engine v1 — deterministic scoring functions.

Each public function accepts snapshot categorical states and produces a
:class:`~domain.quant.models.DimensionScore`.  All logic is explicit,
rule-based, and side-effect-free so it can be tested in isolation.

Scoring approach
----------------
Each dimension maps its known categorical states to a numeric score using a
small lookup table.  Where multiple states are available the worst-case
(most conservative) view is used to avoid overconfidence.

Score range: [0.0, 1.0] — higher = more supportive / healthier.

State-to-score mappings are intentionally coarse-grained.  Precise
calibration is deferred to future quant engine iterations.

Public entry point
------------------
:func:`score_snapshot` accepts a :class:`~domain.macro.snapshot.MacroSnapshotState`
and returns a fully-populated :class:`~domain.quant.models.QuantScoreBundle`.
"""

from __future__ import annotations

from domain.macro.snapshot import (
    FinancialConditionsState,
    GrowthState,
    InflationState,
    LaborState,
    MacroSnapshotState,
    PolicyState,
)
from domain.quant.models import (
    DimensionScore,
    QuantScoreBundle,
    ScoreDimension,
    ScoreLevel,
    _score_to_level,
)

# ---------------------------------------------------------------------------
# State → raw score tables
# ---------------------------------------------------------------------------

_GROWTH_SCORES: dict[GrowthState, float] = {
    GrowthState.ACCELERATING: 0.90,
    GrowthState.MIXED: 0.50,
    GrowthState.SLOWING: 0.20,
    GrowthState.UNKNOWN: None,  # type: ignore[dict-item]
}

# Inflation scoring: lower inflation pressure = higher score (more supportive)
_INFLATION_SCORES: dict[InflationState, float] = {
    InflationState.COOLING: 0.85,
    InflationState.STICKY: 0.50,
    InflationState.REACCELERATING: 0.15,
    InflationState.UNKNOWN: None,  # type: ignore[dict-item]
}

# Labor scoring: tight/healthy labour = higher score
_LABOR_SCORES: dict[LaborState, float] = {
    LaborState.TIGHT: 0.90,
    LaborState.SOFTENING: 0.50,
    LaborState.WEAK: 0.15,
    LaborState.UNKNOWN: None,  # type: ignore[dict-item]
}

# Policy scoring: easing bias = highest support; restrictive = low support
_POLICY_SCORES: dict[PolicyState, float] = {
    PolicyState.EASING_BIAS: 0.85,
    PolicyState.NEUTRAL: 0.60,
    PolicyState.RESTRICTIVE: 0.20,
    PolicyState.UNKNOWN: None,  # type: ignore[dict-item]
}

# Financial conditions scoring: loose = highest support
_FIN_CONDITIONS_SCORES: dict[FinancialConditionsState, float] = {
    FinancialConditionsState.LOOSE: 0.90,
    FinancialConditionsState.NEUTRAL: 0.55,
    FinancialConditionsState.TIGHT: 0.15,
    FinancialConditionsState.UNKNOWN: None,  # type: ignore[dict-item]
}


# ---------------------------------------------------------------------------
# Dimension scoring functions
# ---------------------------------------------------------------------------


def score_growth(snapshot: MacroSnapshotState) -> DimensionScore:
    """Score the growth dimension from snapshot growth state."""
    raw = _GROWTH_SCORES.get(snapshot.growth_state)
    return DimensionScore(
        dimension=ScoreDimension.GROWTH,
        score=raw,
        level=_score_to_level(raw),
        contributing_states=[snapshot.growth_state.value],
    )


def score_inflation(snapshot: MacroSnapshotState) -> DimensionScore:
    """Score the inflation dimension from snapshot inflation state.

    Higher score = more supportive (inflation is cooling or contained).
    """
    raw = _INFLATION_SCORES.get(snapshot.inflation_state)
    return DimensionScore(
        dimension=ScoreDimension.INFLATION,
        score=raw,
        level=_score_to_level(raw),
        contributing_states=[snapshot.inflation_state.value],
    )


def score_labor(snapshot: MacroSnapshotState) -> DimensionScore:
    """Score the labor dimension from snapshot labor state."""
    raw = _LABOR_SCORES.get(snapshot.labor_state)
    return DimensionScore(
        dimension=ScoreDimension.LABOR,
        score=raw,
        level=_score_to_level(raw),
        contributing_states=[snapshot.labor_state.value],
    )


def score_policy(snapshot: MacroSnapshotState) -> DimensionScore:
    """Score the policy dimension from snapshot policy state.

    Higher score = more supportive (easier / more accommodative policy).
    """
    raw = _POLICY_SCORES.get(snapshot.policy_state)
    return DimensionScore(
        dimension=ScoreDimension.POLICY,
        score=raw,
        level=_score_to_level(raw),
        contributing_states=[snapshot.policy_state.value],
    )


def score_financial_conditions(snapshot: MacroSnapshotState) -> DimensionScore:
    """Score the financial conditions dimension from snapshot state."""
    raw = _FIN_CONDITIONS_SCORES.get(snapshot.financial_conditions_state)
    return DimensionScore(
        dimension=ScoreDimension.FINANCIAL_CONDITIONS,
        score=raw,
        level=_score_to_level(raw),
        contributing_states=[snapshot.financial_conditions_state.value],
    )


# ---------------------------------------------------------------------------
# Secondary measures
# ---------------------------------------------------------------------------


def _compute_breadth(scores: list[DimensionScore]) -> float:
    """Fraction of dimensions with a known (non-None) score."""
    if not scores:
        return 0.0
    known = sum(1 for s in scores if s.score is not None)
    return known / len(scores)


def _compute_overall_support(scores: list[DimensionScore]) -> float:
    """Breadth-weighted mean of known dimension scores.

    When no dimension has a score this returns 0.0.
    """
    known = [s for s in scores if s.score is not None]
    if not known:
        return 0.0
    return sum(s.score for s in known) / len(known)  # type: ignore[misc]


def _compute_momentum(scores: list[DimensionScore]) -> float:
    """Estimate directional momentum as the proportion of strong/moderate scores.

    This is a v1 approximation — a future iteration will use time-series
    rate-of-change from consecutive snapshots.
    Returns 0.5 when no data is available (neutral / unknown).
    """
    known = [s for s in scores if s.score is not None]
    if not known:
        return 0.5
    high_count = sum(1 for s in known if s.level in {ScoreLevel.STRONG, ScoreLevel.MODERATE})
    return high_count / len(known)


def _compute_change_intensity(scores: list[DimensionScore]) -> float:
    """Estimate change intensity as the dispersion of known scores.

    High dispersion = some dimensions are very high, others very low →
    high change intensity (conflicted environment).

    Returns 0.0 when fewer than 2 dimensions are known.
    """
    known_vals = [s.score for s in scores if s.score is not None]
    if len(known_vals) < 2:
        return 0.0
    spread = max(known_vals) - min(known_vals)
    # Normalise to [0, 1]; max possible spread is 1.0
    return min(1.0, spread)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def score_snapshot(snapshot: MacroSnapshotState) -> QuantScoreBundle:
    """Compute a full :class:`~domain.quant.models.QuantScoreBundle` from a snapshot.

    This is the primary entry point for the Quant Scoring Engine v1.

    Args:
        snapshot: A fully-derived :class:`~domain.macro.snapshot.MacroSnapshotState`.

    Returns:
        :class:`~domain.quant.models.QuantScoreBundle` with scores for all five
        primary dimensions plus secondary measures.
    """
    growth = score_growth(snapshot)
    inflation = score_inflation(snapshot)
    labor = score_labor(snapshot)
    policy = score_policy(snapshot)
    fin_cond = score_financial_conditions(snapshot)

    all_scores = [growth, inflation, labor, policy, fin_cond]

    breadth = _compute_breadth(all_scores)
    overall = _compute_overall_support(all_scores)
    momentum = _compute_momentum(all_scores)
    intensity = _compute_change_intensity(all_scores)

    return QuantScoreBundle(
        growth=growth,
        inflation=inflation,
        labor=labor,
        policy=policy,
        financial_conditions=fin_cond,
        momentum=momentum,
        breadth=breadth,
        change_intensity=intensity,
        overall_support=overall,
    )
