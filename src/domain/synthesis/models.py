"""Cross-engine synthesis domain models.

A :class:`SynthesisView` aggregates the outputs of four engines:

  1. Macro regime    — ``regime_label``, ``macro_confidence``
  2. Quant scoring   — ``quant_overall_support``
  3. Signal conflict — ``conflict_status``
  4. Risk engine     — ``avg_var_95``, ``worst_mdd_pct``

The synthesis engine produces a single :class:`SynthesisStatus` plus a
:attr:`SynthesisView.conviction_score` that prices in the risk penalty.

Status vocabulary
-----------------
``aligned_bullish``
    Macro, quant, and risk all point constructively — high conviction.
``aligned_cautious``
    Macro/quant lean cautious or risk is elevated — reduced position size.
``mixed_signals``
    Conflict surface is mixed or quant is weak — low directional conviction.
``risk_dominant``
    Risk metrics (VaR, MDD) are severe enough to override macro/quant signals.
    Protect capital first.
``insufficient_data``
    Fewer than two engines have data to contribute to a synthesis.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SynthesisStatus(StrEnum):
    """Summary status produced by the cross-engine synthesis."""

    ALIGNED_BULLISH = "aligned_bullish"
    ALIGNED_CAUTIOUS = "aligned_cautious"
    MIXED_SIGNALS = "mixed_signals"
    RISK_DOMINANT = "risk_dominant"
    INSUFFICIENT_DATA = "insufficient_data"


class SynthesisView(BaseModel, extra="forbid"):
    """Cross-engine synthesis output for a single analysis point.

    Attributes:
        synthesis_status:    Summary label — see :class:`SynthesisStatus`.
        conviction_score:    Risk-adjusted conviction [0.0, 1.0].  Derived from
                             ``quant_overall_support`` after subtracting the
                             ``risk_penalty``; clamped to [0, 1].
        risk_penalty:        Fraction deducted from conviction due to elevated
                             VaR or severe drawdown [0.0, 1.0].
        quant_support:       Human-readable quant support label passed through
                             from the Quant Scoring Engine.
        conflict_status:     Conflict surface status string passed through from
                             the Signal Engine.
        dominant_concern:    The single highest-priority concern identified by
                             the synthesis (e.g. ``"elevated_var"``,
                             ``"mixed_macro_signals"``).  ``None`` when no
                             significant concern is present.
        note:                Short analyst-facing synthesis narrative.
    """

    synthesis_status: SynthesisStatus
    conviction_score: float = Field(ge=0.0, le=1.0)
    risk_penalty: float = Field(ge=0.0, le=1.0)
    quant_support: str
    conflict_status: str
    dominant_concern: str | None
    note: str
