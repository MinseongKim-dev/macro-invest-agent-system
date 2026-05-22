"""Deterministic regime-to-signal mapping rules.

Maps each :class:`~domain.macro.regime.RegimeLabel` to a set of investment
signals grounded in the current macro regime.  This is the Rule-Based Macro
Engine layer of the multi-engine analysis hub.

Conceptual regime coverage
--------------------------
The :class:`~domain.macro.regime.RegimeLabel` enum defines the canonical
labels used throughout this system.  The mapping below covers all nine
labels and explicitly comments on their relationship to broader conceptual
frameworks used in macro investment research:

* GOLDILOCKS           → growth ↑, inflation ↓, policy neutral   (classic risk-on)
* REFLATION            → growth recovering, inflation ↑, policy easing
                         (conceptual equivalent: "Policy Easing Transition" / "Reflationary Recovery")
* DISINFLATION         → inflation ↓, growth mixed                (conceptual: "Disinflation Slowdown")
* STAGFLATION_RISK     → growth ↓, inflation ↑, labor ↓          (conceptual: "Stagflation Risk")
* CONTRACTION          → growth contracting, tight conditions, labor weak
* POLICY_TIGHTENING_DRAG → restrictive policy drag on growth      (conceptual: early-cycle "Overheating" response)
* SLOWDOWN             → growth decelerating, labor softening
* MIXED                → conflicting macro signals
* UNCLEAR              → insufficient / stale data

Signal structure
----------------
Each :class:`RegimeSignalRule` carries:

* ``asset_class``         — target asset class (equities, bonds, commodities, cash, all)
* ``signal_direction``    — BUY / SELL / HOLD / NEUTRAL
* ``signal_strength``     — VERY_WEAK … VERY_STRONG
* ``signal_confidence``   — numeric 0.0–1.0 (regime conviction)
* ``supporting_regime``   — the regime label text that grounds this rule
* ``supporting_drivers``  — macro factors that support the signal direction
* ``conflicting_drivers`` — macro factors that reduce signal confidence
* ``regime_rationale``    — analyst-facing narrative (reusable by explanation layer)

Design principles
-----------------
* Every regime label maps to at least one signal.
* MIXED and UNCLEAR regimes always map to HOLD/NEUTRAL with low confidence.
* All signal IDs are unique across the entire map.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.macro.regime import RegimeLabel
from domain.signals.enums import SignalStrength, SignalType, TrendDirection


@dataclass(frozen=True)
class RegimeSignalRule:
    """A single regime-derived signal rule."""

    signal_id: str
    asset_class: str
    signal_direction: SignalType       # use signal_direction to separate from legacy signal_type
    signal_strength: SignalStrength
    signal_confidence: float           # 0.0 – 1.0, regime-level conviction
    trend: TrendDirection
    supporting_regime: str             # regime label text that grounds this rule
    supporting_drivers: tuple[str, ...] = field(default_factory=tuple)
    conflicting_drivers: tuple[str, ...] = field(default_factory=tuple)
    regime_rationale: str = ""


# ---------------------------------------------------------------------------
# Regime → signal rule table
# ---------------------------------------------------------------------------

REGIME_SIGNAL_MAP: dict[RegimeLabel, list[RegimeSignalRule]] = {

    # -----------------------------------------------------------------------
    # GOLDILOCKS: growth accelerating, inflation cooling, policy neutral
    # Conceptual label: "Classic Expansion / Goldilocks"
    # -----------------------------------------------------------------------
    RegimeLabel.GOLDILOCKS: [
        RegimeSignalRule(
            signal_id="goldilocks_equities_buy",
            asset_class="equities",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.80,
            trend=TrendDirection.UP,
            supporting_regime="goldilocks",
            supporting_drivers=(
                "growth_accelerating",
                "inflation_cooling",
                "policy_neutral",
                "financial_conditions_neutral",
            ),
            conflicting_drivers=(),
            regime_rationale=(
                "Goldilocks: growth accelerating with inflation cooling and neutral policy. "
                "Risk-on environment strongly favours equity exposure. "
                "Cyclical and quality factors preferred; reduce defensive tilt."
            ),
        ),
        RegimeSignalRule(
            signal_id="goldilocks_bonds_hold",
            asset_class="bonds",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.55,
            trend=TrendDirection.NEUTRAL,
            supporting_regime="goldilocks",
            supporting_drivers=("inflation_cooling", "policy_neutral"),
            conflicting_drivers=("growth_accelerating",),
            regime_rationale=(
                "Goldilocks: neutral policy stance reduces duration risk but growth "
                "momentum limits bond upside. Maintain existing allocation; "
                "prefer shorter-duration instruments."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # DISINFLATION: inflation retreating, growth mixed or slowing
    # Conceptual label: "Disinflation Slowdown"
    # -----------------------------------------------------------------------
    RegimeLabel.DISINFLATION: [
        RegimeSignalRule(
            signal_id="disinflation_bonds_buy",
            asset_class="bonds",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.75,
            trend=TrendDirection.UP,
            supporting_regime="disinflation",
            supporting_drivers=("inflation_cooling", "policy_easing_potential"),
            conflicting_drivers=("growth_mixed",),
            regime_rationale=(
                "Disinflation: inflation cooling reduces rate pressure and raises the "
                "probability of a policy pivot. Duration-extending environment for bonds. "
                "Favour high-quality sovereign duration."
            ),
        ),
        RegimeSignalRule(
            signal_id="disinflation_equities_hold",
            asset_class="equities",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.50,
            trend=TrendDirection.NEUTRAL,
            supporting_regime="disinflation",
            supporting_drivers=("inflation_cooling",),
            conflicting_drivers=("growth_slowing", "growth_mixed"),
            regime_rationale=(
                "Disinflation: growth is mixed or slowing, limiting equity upside. "
                "Maintain current exposure; rotate toward quality and dividend defensives."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # REFLATION: growth recovering, inflation re-accelerating, policy easing
    # Conceptual label: "Policy Easing Transition / Reflationary Recovery"
    # -----------------------------------------------------------------------
    RegimeLabel.REFLATION: [
        RegimeSignalRule(
            signal_id="reflation_commodities_buy",
            asset_class="commodities",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.80,
            trend=TrendDirection.UP,
            supporting_regime="reflation",
            supporting_drivers=("inflation_reaccelerating", "growth_recovering", "policy_easing"),
            conflicting_drivers=(),
            regime_rationale=(
                "Reflation: re-accelerating inflation with growth recovery and easing policy. "
                "Commodity and inflation-linked assets are strongly favoured. "
                "Energy and materials sectors preferred."
            ),
        ),
        RegimeSignalRule(
            signal_id="reflation_equities_buy",
            asset_class="equities",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.65,
            trend=TrendDirection.UP,
            supporting_regime="reflation",
            supporting_drivers=("growth_recovering", "policy_easing"),
            conflicting_drivers=("inflation_reaccelerating",),
            regime_rationale=(
                "Reflation: easing policy and improving growth support equity multiples "
                "despite rising inflation. Cyclical and value tilts preferred. "
                "Financials and industrials favoured."
            ),
        ),
        RegimeSignalRule(
            signal_id="reflation_bonds_sell",
            asset_class="bonds",
            signal_direction=SignalType.SELL,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.65,
            trend=TrendDirection.DOWN,
            supporting_regime="reflation",
            supporting_drivers=("inflation_reaccelerating",),
            conflicting_drivers=("policy_easing",),
            regime_rationale=(
                "Reflation: re-accelerating inflation erodes real bond returns. "
                "Reduce nominal duration; prefer inflation-linked or floating-rate instruments."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # SLOWDOWN: growth decelerating, labour softening
    # Conceptual label: "Late-Cycle Slowdown"
    # -----------------------------------------------------------------------
    RegimeLabel.SLOWDOWN: [
        RegimeSignalRule(
            signal_id="slowdown_equities_hold",
            asset_class="equities",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.55,
            trend=TrendDirection.DOWN,
            supporting_regime="slowdown",
            supporting_drivers=("growth_slowing", "labor_softening"),
            conflicting_drivers=("inflation_not_yet_cooling",),
            regime_rationale=(
                "Slowdown: growth decelerating with softening labour market. "
                "Reduce cyclical risk; rotate toward defensive and quality factors. "
                "Avoid adding new equity risk until a policy pivot materialises."
            ),
        ),
        RegimeSignalRule(
            signal_id="slowdown_bonds_buy",
            asset_class="bonds",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.60,
            trend=TrendDirection.UP,
            supporting_regime="slowdown",
            supporting_drivers=("growth_slowing", "labor_softening"),
            conflicting_drivers=("inflation_sticky",),
            regime_rationale=(
                "Slowdown: decelerating growth raises probability of policy pivot. "
                "Moderate duration extension attractive, particularly in high-quality sovereigns."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # STAGFLATION_RISK: growth slowing, inflation re-accelerating, labour weak
    # Conceptual label: "Stagflation Risk" (worst combination for traditional portfolios)
    # -----------------------------------------------------------------------
    RegimeLabel.STAGFLATION_RISK: [
        RegimeSignalRule(
            signal_id="stagflation_equities_sell",
            asset_class="equities",
            signal_direction=SignalType.SELL,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.80,
            trend=TrendDirection.DOWN,
            supporting_regime="stagflation_risk",
            supporting_drivers=(
                "growth_slowing",
                "inflation_reaccelerating",
                "labor_weakening",
            ),
            conflicting_drivers=(),
            regime_rationale=(
                "Stagflation risk: slowing growth with re-accelerating inflation and "
                "weakening labour market — the worst combination for equity risk premia. "
                "Materially reduce equity exposure; rotate to real assets and cash."
            ),
        ),
        RegimeSignalRule(
            signal_id="stagflation_bonds_sell",
            asset_class="bonds",
            signal_direction=SignalType.SELL,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.65,
            trend=TrendDirection.DOWN,
            supporting_regime="stagflation_risk",
            supporting_drivers=("inflation_reaccelerating",),
            conflicting_drivers=("growth_slowing",),
            regime_rationale=(
                "Stagflation risk: inflation re-acceleration limits nominal bond upside. "
                "Prefer inflation-linked; reduce nominal duration significantly."
            ),
        ),
        RegimeSignalRule(
            signal_id="stagflation_commodities_buy",
            asset_class="commodities",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.60,
            trend=TrendDirection.UP,
            supporting_regime="stagflation_risk",
            supporting_drivers=("inflation_reaccelerating",),
            conflicting_drivers=("growth_slowing",),
            regime_rationale=(
                "Stagflation risk: real assets and commodities provide partial inflation hedge "
                "in a growth-challenged environment. Selective commodity exposure preferred."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # CONTRACTION: broad growth contracting, tight conditions, weak labour
    # Conceptual label: "Recessionary Contraction"
    # -----------------------------------------------------------------------
    RegimeLabel.CONTRACTION: [
        RegimeSignalRule(
            signal_id="contraction_equities_sell",
            asset_class="equities",
            signal_direction=SignalType.SELL,
            signal_strength=SignalStrength.VERY_STRONG,
            signal_confidence=0.90,
            trend=TrendDirection.DOWN,
            supporting_regime="contraction",
            supporting_drivers=(
                "growth_contracting",
                "financial_conditions_tight",
                "labor_weak",
            ),
            conflicting_drivers=(),
            regime_rationale=(
                "Contraction: broad growth contraction with tight financial conditions and "
                "weak labour market — maximum risk-off. Materially reduce equity exposure. "
                "Favour defensive sectors; avoid cyclicals and small caps."
            ),
        ),
        RegimeSignalRule(
            signal_id="contraction_bonds_buy",
            asset_class="bonds",
            signal_direction=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.80,
            trend=TrendDirection.UP,
            supporting_regime="contraction",
            supporting_drivers=("growth_contracting", "policy_easing_expected"),
            conflicting_drivers=("financial_conditions_tight",),
            regime_rationale=(
                "Contraction: flight-to-safety and expected policy easing strongly support "
                "government bonds. Extend duration in high-quality sovereigns. "
                "Avoid credit risk — spread widening expected."
            ),
        ),
        RegimeSignalRule(
            signal_id="contraction_cash_hold",
            asset_class="cash",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.STRONG,
            signal_confidence=0.75,
            trend=TrendDirection.NEUTRAL,
            supporting_regime="contraction",
            supporting_drivers=("risk_off", "drawdown_protection"),
            conflicting_drivers=(),
            regime_rationale=(
                "Contraction: elevated cash allocation reduces drawdown risk while "
                "awaiting a clearer inflection signal or confirmed policy pivot."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # POLICY_TIGHTENING_DRAG: restrictive policy + tight financial conditions
    # Conceptual label: "Overheating Response / Policy Tightening Drag"
    # Note: The preceding OVERHEATING phase (pre-tightening) typically transitions
    # into this label once policy tightening takes effect and growth starts to feel it.
    # -----------------------------------------------------------------------
    RegimeLabel.POLICY_TIGHTENING_DRAG: [
        RegimeSignalRule(
            signal_id="policy_drag_equities_hold",
            asset_class="equities",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.55,
            trend=TrendDirection.DOWN,
            supporting_regime="policy_tightening_drag",
            supporting_drivers=("policy_restrictive", "financial_conditions_tight"),
            conflicting_drivers=("growth_not_yet_contracting",),
            regime_rationale=(
                "Policy tightening drag: restrictive policy and tight financial conditions "
                "compress multiples. Limit new equity risk; prefer short-duration growth "
                "and dividend defensives. Avoid rate-sensitive sectors."
            ),
        ),
        RegimeSignalRule(
            signal_id="policy_drag_bonds_sell",
            asset_class="bonds",
            signal_direction=SignalType.SELL,
            signal_strength=SignalStrength.MODERATE,
            signal_confidence=0.60,
            trend=TrendDirection.DOWN,
            supporting_regime="policy_tightening_drag",
            supporting_drivers=("policy_restrictive", "yields_elevated"),
            conflicting_drivers=(),
            regime_rationale=(
                "Policy tightening drag: elevated yields reflect restrictive stance. "
                "Avoid extending duration until policy pivot is confirmed. "
                "Prefer money-market instruments or floating-rate credit."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # MIXED: conflicting macro signals — no high-conviction call possible
    # -----------------------------------------------------------------------
    RegimeLabel.MIXED: [
        RegimeSignalRule(
            signal_id="mixed_equities_hold",
            asset_class="equities",
            signal_direction=SignalType.HOLD,
            signal_strength=SignalStrength.WEAK,
            signal_confidence=0.30,
            trend=TrendDirection.NEUTRAL,
            supporting_regime="mixed",
            supporting_drivers=(),
            conflicting_drivers=("conflicting_growth_signals", "conflicting_inflation_signals"),
            regime_rationale=(
                "Mixed regime: opposing macro signals across growth, inflation, labour, "
                "and financial conditions reduce the reliability of any directional call. "
                "Maintain a balanced, diversified allocation and wait for clearer regime."
            ),
        ),
    ],

    # -----------------------------------------------------------------------
    # UNCLEAR: insufficient or stale data — no regime classification possible
    # -----------------------------------------------------------------------
    RegimeLabel.UNCLEAR: [
        RegimeSignalRule(
            signal_id="unclear_neutral",
            asset_class="all",
            signal_direction=SignalType.NEUTRAL,
            signal_strength=SignalStrength.VERY_WEAK,
            signal_confidence=0.10,
            trend=TrendDirection.UNKNOWN,
            supporting_regime="unclear",
            supporting_drivers=(),
            conflicting_drivers=("data_insufficient", "data_stale"),
            regime_rationale=(
                "Unclear regime: insufficient or stale macro data prevents reliable "
                "regime classification. No actionable signal. "
                "Refresh data sources and re-evaluate before acting."
            ),
        ),
    ],
}


def get_regime_signal_rules(label: RegimeLabel) -> list[RegimeSignalRule]:
    """Return the list of signal rules for *label*.

    Always returns a non-empty list — falls back to UNCLEAR rules if *label*
    is not present in the map (defensive).
    """
    return REGIME_SIGNAL_MAP.get(label, REGIME_SIGNAL_MAP[RegimeLabel.UNCLEAR])
