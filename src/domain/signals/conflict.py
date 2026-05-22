"""Conflict Surface v1 — domain model and derivation logic.

Introduces an explicit, lightweight conflict model for macro signals.
This is distinct from ``is_degraded`` / ``DegradedStatus``:

  - **Degraded** = data/quality/freshness problem (input layer)
  - **Mixed / Conflicted** = analytical tension between macro drivers
    (interpretation layer)

Design goals
------------
- Model conflict explicitly rather than as ad hoc string patches.
- Keep derivation deterministic and testable.
- Produce a DTO that downstream API/UI can render without further processing.
- Leave room for a future full Conflict/Ensemble Engine (v2+).

Conflict status vocabulary
--------------------------
``clean``
    All macro drivers support the signal direction coherently.
``tension``
    At least one significant conflicting driver exists, but supporting
    drivers still outnumber conflicting ones.
``mixed``
    Conflicting and supporting drivers are roughly balanced, or no clear
    directional view can be formed.
``low_conviction``
    Signal has few or no supporting drivers, or quant overall_support is
    very weak.  User should not act with high conviction.

Deferred
--------
- Full cross-asset ensemble conflict resolution.
- Probabilistic conflict scoring.
- Time-series conflict trend tracking.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConflictStatus(StrEnum):
    """Conflict/conviction status for a single signal.

    Hierarchy (most to least conviction):
    clean > tension > mixed > low_conviction
    """

    CLEAN = "clean"
    TENSION = "tension"
    MIXED = "mixed"
    LOW_CONVICTION = "low_conviction"


class ConflictSurface(BaseModel, extra="forbid"):
    """Lightweight conflict descriptor attached to a :class:`~domain.signals.models.SignalOutput`.

    Attributes:
        conflict_status: Summary status of the conflict level for this signal.
        is_mixed: Convenience bool — True when status is ``mixed`` or
            ``low_conviction``.  Allows API consumers to implement a simple
            boolean gate without string comparison.
        conflicting_drivers: Macro factors that reduce confidence or oppose
            the signal direction.  Propagated from the underlying
            :class:`~domain.signals.regime_signal_rules.RegimeSignalRule`.
        supporting_drivers: Macro factors that support the signal direction.
        conflict_note: Optional analyst-facing explanation of the conflict
            situation.  None when conflict_status is ``clean``.
        quant_support_level: Human-readable quant support label derived from
            quant overall_support.  One of: ``strong``, ``moderate``,
            ``weak``, ``unknown``.
    """

    conflict_status: ConflictStatus = Field(
        default=ConflictStatus.CLEAN,
        description=(
            "Summary conflict level: clean | tension | mixed | low_conviction. "
            "See module docstring for semantics."
        ),
    )
    is_mixed: bool = Field(
        default=False,
        description=(
            "True when conflict_status is 'mixed' or 'low_conviction'. "
            "Convenience boolean for API consumers."
        ),
    )
    conflicting_drivers: list[str] = Field(
        default_factory=list,
        description="Macro factors that oppose or reduce confidence in this signal",
    )
    supporting_drivers: list[str] = Field(
        default_factory=list,
        description="Macro factors that support this signal direction",
    )
    conflict_note: str | None = Field(
        default=None,
        description=(
            "Analyst-facing explanation of why this signal is conflicted or low-conviction. "
            "None when conflict_status is 'clean'."
        ),
    )
    quant_support_level: str = Field(
        default="unknown",
        description=(
            "Quant support level derived from QuantScoreBundle.overall_support. "
            "One of: 'strong' (>=0.65), 'moderate' (>=0.40), 'weak' (<0.40), 'unknown'."
        ),
    )


def _quant_support_label(overall_support: float | None) -> str:
    """Map overall_support float to a human-readable label."""
    if overall_support is None:
        return "unknown"
    if overall_support >= 0.65:
        return "strong"
    if overall_support >= 0.40:
        return "moderate"
    return "weak"


def derive_conflict(
    supporting_drivers: list[str],
    conflicting_drivers: list[str],
    quant_overall_support: float | None = None,
    is_degraded: bool = False,
) -> ConflictSurface:
    """Derive a :class:`ConflictSurface` from driver lists and quant support.

    Conflict derivation rules
    -------------------------
    1. ``low_conviction`` when:
       - No supporting drivers at all, or
       - quant_overall_support < 0.35 (very weak quant backing).
    2. ``mixed`` when:
       - Conflicting drivers ≥ supporting drivers (roughly balanced), and
         not already classified as low_conviction.
    3. ``tension`` when:
       - At least one conflicting driver exists but supporting > conflicting.
    4. ``clean`` otherwise.

    Note: ``is_degraded`` being True does not change conflict status.
    Degraded is a separate, orthogonal concept (see module docstring).

    Args:
        supporting_drivers: Macro factors supporting the signal direction.
        conflicting_drivers: Macro factors opposing the signal direction.
        quant_overall_support: Optional quant bundle overall_support score.
        is_degraded: Whether the signal is already marked degraded (informational
            only — does not affect conflict logic).

    Returns:
        :class:`ConflictSurface` with status, flags, and note.
    """
    n_sup = len(supporting_drivers)
    n_con = len(conflicting_drivers)

    quant_label = _quant_support_label(quant_overall_support)
    quant_weak = quant_overall_support is not None and quant_overall_support < 0.35

    # --- Determine status ---
    if n_sup == 0 or quant_weak:
        status = ConflictStatus.LOW_CONVICTION
        note = _low_conviction_note(n_sup, quant_label, quant_weak)
    elif n_con >= n_sup:
        status = ConflictStatus.MIXED
        note = (
            f"Conflicting drivers ({n_con}) match or outnumber supporting drivers ({n_sup}). "
            f"Signal direction is contested — quant support: {quant_label}."
        )
    elif n_con > 0:
        status = ConflictStatus.TENSION
        note = (
            f"Signal direction supported ({n_sup} factors) but {n_con} conflicting "
            f"driver(s) reduce conviction. Quant support: {quant_label}."
        )
    else:
        status = ConflictStatus.CLEAN
        note = None

    is_mixed = status in {ConflictStatus.MIXED, ConflictStatus.LOW_CONVICTION}

    return ConflictSurface(
        conflict_status=status,
        is_mixed=is_mixed,
        conflicting_drivers=list(conflicting_drivers),
        supporting_drivers=list(supporting_drivers),
        conflict_note=note,
        quant_support_level=quant_label,
    )


def _low_conviction_note(n_sup: int, quant_label: str, quant_weak: bool) -> str:
    if n_sup == 0 and quant_weak:
        return (
            "No supporting drivers identified and quant support is weak. "
            "Signal lacks analytical backing — treat as indicative only."
        )
    if n_sup == 0:
        return (
            f"No supporting drivers identified for this signal. "
            f"Quant support: {quant_label}. Treat as low-conviction."
        )
    return (
        f"Quant support is very weak ({quant_label}). "
        "Signal may not be backed by sufficient macroeconomic evidence."
    )
