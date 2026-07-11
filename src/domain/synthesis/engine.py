"""Cross-engine synthesis — deterministic, side-effect-free.

Combines outputs from four analytical engines into a single
:class:`~domain.synthesis.models.SynthesisView`.

Decision rules (evaluated in priority order)
---------------------------------------------
1. **insufficient_data** — fewer than two engines contribute meaningful data.
2. **risk_dominant** — avg VaR ≥ 5 % OR worst MDD ≤ −40 %.
3. **aligned_bullish** — regime constructive, quant strong, conflict ≤ 1.
4. **aligned_cautious** — regime cautious OR quant weak, no conflict spike.
5. **mixed_signals** — everything else (conflict ≥ 2 or quant absent).

Risk penalty
------------
``risk_penalty = min(1.0, var_weight + mdd_weight)``

- ``var_weight = min(0.5, max(0.0, (avg_var_95 - 1.0) / 10.0))``
  — 0 % at VaR ≤ 1 %, 0.5 at VaR ≥ 6 %.
- ``mdd_weight = min(0.5, max(0.0, (-worst_mdd_pct - 10.0) / 60.0))``
  — 0 % at MDD ≥ −10 %, 0.5 at MDD ≤ −40 %.
"""

from __future__ import annotations

from src.domain.synthesis.models import SynthesisStatus, SynthesisView

# ── thresholds ────────────────────────────────────────────────────────────────

_VAR_DOMINANT_THRESHOLD = 5.0       # avg VaR ≥ 5 % → risk dominant
_MDD_DOMINANT_THRESHOLD = -40.0     # worst MDD ≤ −40 % → risk dominant

_VAR_PENALTY_START = 1.0            # VaR below this → 0 penalty
_VAR_PENALTY_SCALE = 10.0           # range over which var penalty rises to 0.5

_MDD_PENALTY_START = -10.0          # MDD above this (less negative) → 0 penalty
_MDD_PENALTY_SCALE = 60.0           # range over which mdd penalty rises to 0.5

_CONFLICT_LOW = 1                   # ≤ 1 → "low" conflict surface
_CONFLICT_HIGH = 2                  # ≥ 2 → mixed / elevated

_BULLISH_REGIMES = {"expansion", "recovery"}
_CAUTIOUS_REGIMES = {"contraction", "slowdown", "stagflation"}

_STRONG_QUANT = {"strong_positive", "moderate_positive"}
_WEAK_QUANT = {"strong_negative", "moderate_negative", "neutral"}


# ── helpers ───────────────────────────────────────────────────────────────────


def _count_engines(
    regime_label: str,
    quant_overall_support: str,
    conflict_status: str,
    avg_var_95: float,
) -> int:
    """Count how many engines contributed meaningful, non-placeholder data."""
    count = 0
    if regime_label and regime_label not in {"unknown", "insufficient_data"}:
        count += 1
    if quant_overall_support and quant_overall_support not in {"unknown", "no_data"}:
        count += 1
    if conflict_status and conflict_status not in {"unknown", "no_data"}:
        count += 1
    if avg_var_95 > 0.0:
        count += 1
    return count


def _parse_conflict_level(conflict_status: str) -> int:
    """Return a numeric conflict level from a conflict status string.

    Strings containing "none" or "low" → 0–1.
    Strings containing "medium" or "moderate" → 1.
    Strings containing "high" or "critical" → 2+.
    Anything else (unknown, no_data) → 0 (treated as absent, not high).
    """
    s = conflict_status.lower()
    if any(k in s for k in ("critical", "high", "severe")):
        return 3
    if any(k in s for k in ("medium", "moderate", "elevated")):
        return 2
    if any(k in s for k in ("low",)):
        return 1
    return 0


def _compute_risk_penalty(avg_var_95: float, worst_mdd_pct: float) -> float:
    """Return a risk penalty in [0.0, 1.0]."""
    var_weight = min(0.5, max(0.0, (avg_var_95 - _VAR_PENALTY_START) / _VAR_PENALTY_SCALE))
    mdd_weight = min(0.5, max(0.0, (-worst_mdd_pct - (-_MDD_PENALTY_START)) / _MDD_PENALTY_SCALE))
    return min(1.0, round(var_weight + mdd_weight, 4))


# ── public entry point ────────────────────────────────────────────────────────


def compute_synthesis_view(
    *,
    regime_label: str,
    macro_confidence: float,
    quant_overall_support: str,
    conflict_status: str,
    avg_var_95: float,
    worst_mdd_pct: float,
) -> SynthesisView:
    """Compute a :class:`~domain.synthesis.models.SynthesisView`.

    Args:
        regime_label:         Macro regime string (e.g. ``"expansion"``).
        macro_confidence:     Macro engine confidence [0.0, 1.0].
        quant_overall_support: Quant scoring label (e.g. ``"strong_positive"``).
        conflict_status:      Signal conflict surface label.
        avg_var_95:           Average 1-day 95 % VaR across portfolio (%, ≥ 0).
        worst_mdd_pct:        Worst max-drawdown among tracked tickers (%, ≤ 0).

    Returns:
        :class:`~domain.synthesis.models.SynthesisView` with status, score,
        penalty, and a short narrative note.
    """
    engine_count = _count_engines(regime_label, quant_overall_support, conflict_status, avg_var_95)
    risk_penalty = _compute_risk_penalty(avg_var_95, worst_mdd_pct)
    conflict_level = _parse_conflict_level(conflict_status)

    # ── 1. insufficient data ─────────────────────────────────────────────────
    if engine_count < 2:
        return SynthesisView(
            synthesis_status=SynthesisStatus.INSUFFICIENT_DATA,
            conviction_score=0.0,
            risk_penalty=0.0,
            quant_support=quant_overall_support or "no_data",
            conflict_status=conflict_status or "no_data",
            dominant_concern="insufficient_engine_data",
            note="Fewer than two engines have contributed data; synthesis deferred.",
        )

    base_conviction = max(0.0, min(1.0, macro_confidence))

    # ── 2. risk dominant ─────────────────────────────────────────────────────
    if avg_var_95 >= _VAR_DOMINANT_THRESHOLD or worst_mdd_pct <= _MDD_DOMINANT_THRESHOLD:
        concern = "elevated_var" if avg_var_95 >= _VAR_DOMINANT_THRESHOLD else "severe_drawdown"
        return SynthesisView(
            synthesis_status=SynthesisStatus.RISK_DOMINANT,
            conviction_score=max(0.0, round(base_conviction - risk_penalty, 4)),
            risk_penalty=risk_penalty,
            quant_support=quant_overall_support,
            conflict_status=conflict_status,
            dominant_concern=concern,
            note=(
                f"Risk metrics are severe (VaR {avg_var_95:.1f}%, MDD {worst_mdd_pct:.1f}%)."
                " Capital preservation takes priority."
            ),
        )

    conviction_score = max(0.0, round(base_conviction - risk_penalty, 4))

    # ── 3. aligned bullish ───────────────────────────────────────────────────
    if (
        regime_label in _BULLISH_REGIMES
        and quant_overall_support in _STRONG_QUANT
        and conflict_level <= _CONFLICT_LOW
    ):
        return SynthesisView(
            synthesis_status=SynthesisStatus.ALIGNED_BULLISH,
            conviction_score=conviction_score,
            risk_penalty=risk_penalty,
            quant_support=quant_overall_support,
            conflict_status=conflict_status,
            dominant_concern=None,
            note=(
                f"Macro ({regime_label}), quant ({quant_overall_support}), and risk are"
                " all constructive. High conviction."
            ),
        )

    # ── 4. aligned cautious ──────────────────────────────────────────────────
    if (
        regime_label in _CAUTIOUS_REGIMES
        or quant_overall_support in _WEAK_QUANT
    ) and conflict_level < _CONFLICT_HIGH:
        concern = "cautious_macro" if regime_label in _CAUTIOUS_REGIMES else "weak_quant"
        return SynthesisView(
            synthesis_status=SynthesisStatus.ALIGNED_CAUTIOUS,
            conviction_score=conviction_score,
            risk_penalty=risk_penalty,
            quant_support=quant_overall_support,
            conflict_status=conflict_status,
            dominant_concern=concern,
            note=(
                f"Signals lean cautious (regime: {regime_label},"
                f" quant: {quant_overall_support}). Reduce position size."
            ),
        )

    # ── 5. mixed signals (default) ───────────────────────────────────────────
    concern = "mixed_conflict" if conflict_level >= _CONFLICT_HIGH else "mixed_macro_signals"
    return SynthesisView(
        synthesis_status=SynthesisStatus.MIXED_SIGNALS,
        conviction_score=conviction_score,
        risk_penalty=risk_penalty,
        quant_support=quant_overall_support,
        conflict_status=conflict_status,
        dominant_concern=concern,
        note=(
            "Macro, quant, and risk signals are mixed. Low directional conviction."
        ),
    )
