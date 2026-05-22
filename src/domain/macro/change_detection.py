"""Change Detection Engine v1 — deterministic regime change classification.

This module converts raw before/after regime comparisons into structured,
analyst-meaningful change objects.  It answers:

* **What changed?** — which dimensions differ (label, family, confidence).
* **How meaningful is it?** — severity classification from ``unchanged``
  through ``minor``, ``moderate``, to ``major``.
* **Which direction?** — confidence improved, weakened, or unchanged.
* **Is this a regime transition?** — distinct from noise or minor drift.

Design principles
-----------------
* **Deterministic**: same inputs always produce the same output.
* **Heuristic, not statistically calibrated**: severity is based on explicit
  rules documented below, not probabilistic models.  The heuristic nature
  is stated explicitly so callers are not misled.
* **Explicit, not inferred**: raw deltas are always surfaced alongside the
  interpreted severity so traceability is preserved.
* **Distinct semantics**: ``changed`` ≠ ``degraded`` ≠ ``mixed/conflicted``.
  - ``changed`` = time-based difference relative to an earlier state.
  - ``degraded`` = data quality / freshness limitation.
  - ``mixed/conflicted`` = analytical tension in the current classification.

Severity heuristic (v1, explicitly heuristic)
----------------------------------------------
The following rules are applied in priority order:

``major``
    Regime label changed **and** the source and destination labels belong to
    different regime families.  This indicates a cross-family transition
    (e.g. expansion → contraction).

    Also ``major`` when the destination label is ``contraction`` or
    ``stagflation_risk`` regardless of prior family, because those regimes
    represent the most severe outcomes.

``moderate``
    Regime label changed within the same family (e.g. goldilocks →
    disinflation, both in expansion/inflation_transition families), **or**
    regime label did not change but confidence shifted by more than one
    level (high → low or low → high — skipping medium).

``minor``
    Regime label did not change but confidence changed by exactly one level
    (e.g. high → medium or medium → low).

``unchanged``
    No label change and no confidence change.  The transition type is
    ``unchanged`` or ``initial``.

Notes
-----
* The ``initial`` transition (no prior baseline) produces a ``RegimeDelta``
  with ``severity=unchanged`` and ``is_initial=True``.  Callers should
  check ``is_initial`` before rendering change UI.
* When ``previous`` is ``None`` the function returns an initial-state delta.
* These heuristics are clearly labelled as v1 and subject to future
  calibration in later PRs.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeLabel,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

_HIGH_SEVERITY_DESTINATION_LABELS = {
    RegimeLabel.CONTRACTION,
    RegimeLabel.STAGFLATION_RISK,
}

_CONFIDENCE_RANK: dict[RegimeConfidence, int] = {
    RegimeConfidence.LOW: 1,
    RegimeConfidence.MEDIUM: 2,
    RegimeConfidence.HIGH: 3,
}


class ChangeSeverity(StrEnum):
    """Heuristic severity of a regime change.

    These are **explicitly heuristic** — not statistically calibrated.

    ``unchanged``
        No meaningful difference detected.
    ``minor``
        Small shift (e.g. confidence changed by one level; label stable).
    ``moderate``
        Moderate shift (e.g. label changed within family, or confidence
        jumped/dropped two levels).
    ``major``
        Significant transition (cross-family label change, or destination is
        contraction / stagflation_risk).
    """

    UNCHANGED = "unchanged"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


class ConfidenceDirection(StrEnum):
    """Direction of confidence change between two regimes."""

    IMPROVED = "improved"
    WEAKENED = "weakened"
    UNCHANGED = "unchanged"
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# Change model
# ---------------------------------------------------------------------------


class RegimeDelta(BaseModel, extra="forbid"):
    """Structured change between a current and prior regime.

    This is the primary output of :func:`detect_regime_change`.

    Attributes:
        is_initial: ``True`` when there is no prior regime — no comparison
            can be made.  In this case most fields carry their zero/default
            values.
        label_changed: ``True`` when the regime label differs.
        family_changed: ``True`` when the regime family differs.
        confidence_changed: ``True`` when the confidence level differs.
        confidence_direction: Direction of confidence change.
        severity: Heuristic severity classification (v1, explicitly heuristic).
        changed_dimensions: List of dimension names that changed.
            Possible values: ``"label"``, ``"family"``, ``"confidence"``.
        prior_label: Prior regime label; ``None`` for initial regimes.
        prior_family: Prior regime family; ``None`` for initial regimes.
        prior_confidence: Prior confidence level; ``None`` for initial.
        current_label: Current regime label.
        current_family: Current regime family.
        current_confidence: Current confidence level.
        label_transition: Human-readable label transition summary, e.g.
            ``"goldilocks → slowdown"``; ``None`` when label did not change
            or this is the initial regime.
        confidence_transition: Human-readable confidence transition, e.g.
            ``"high → medium"``; ``None`` when confidence did not change.
        is_regime_transition: ``True`` when a regime label change occurred.
            This is distinct from a confidence-only shift.
        notable_flags: Analyst-facing flags for notable conditions, e.g.
            ``["cross_family_transition"]``, ``["high_severity_destination"]``.
        severity_rationale: Short analyst-facing explanation of why this
            severity was assigned.
    """

    is_initial: bool = Field(
        default=False,
        description="True when there is no prior regime (no comparison possible)",
    )
    label_changed: bool = Field(default=False)
    family_changed: bool = Field(default=False)
    confidence_changed: bool = Field(default=False)
    confidence_direction: str = Field(
        default=ConfidenceDirection.NOT_APPLICABLE,
        description="improved | weakened | unchanged | not_applicable",
    )
    severity: str = Field(
        default=ChangeSeverity.UNCHANGED,
        description=(
            "Heuristic change severity (v1, explicitly heuristic — not statistically "
            "calibrated): unchanged | minor | moderate | major"
        ),
    )
    changed_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Dimensions that changed: may include 'label', 'family', 'confidence'. "
            "Empty when severity is 'unchanged' or 'not_applicable'."
        ),
    )
    prior_label: str | None = Field(default=None)
    prior_family: str | None = Field(default=None)
    prior_confidence: str | None = Field(default=None)
    current_label: str = Field(default="")
    current_family: str = Field(default="")
    current_confidence: str = Field(default="")
    label_transition: str | None = Field(
        default=None,
        description=(
            "Human-readable label transition (e.g. 'goldilocks → slowdown'). "
            "None when label did not change or this is the initial regime."
        ),
    )
    confidence_transition: str | None = Field(
        default=None,
        description=(
            "Human-readable confidence transition (e.g. 'high → medium'). "
            "None when confidence did not change."
        ),
    )
    is_regime_transition: bool = Field(
        default=False,
        description=(
            "True when a regime label change occurred. "
            "Distinct from confidence-only shifts."
        ),
    )
    notable_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Analyst-facing flags for notable conditions. "
            "Possible values: 'cross_family_transition', 'high_severity_destination', "
            "'confidence_jump' (skipped a level)."
        ),
    )
    severity_rationale: str = Field(
        default="",
        description="Short analyst-facing explanation of why this severity was assigned",
    )


# ---------------------------------------------------------------------------
# Detection function
# ---------------------------------------------------------------------------


def detect_regime_change(
    current: MacroRegime,
    previous: MacroRegime | None,
) -> RegimeDelta:
    """Derive a structured :class:`RegimeDelta` from two regimes.

    This is the primary entry point for the Change Detection Engine v1.

    The function is deterministic: the same inputs always produce the same
    output.  No external I/O is involved.

    Severity classification is explicitly heuristic (v1).  See module
    docstring for the full rule specification.

    Args:
        current: The current (more recent) :class:`~domain.macro.regime.MacroRegime`.
        previous: The prior regime; ``None`` for the initial regime (no baseline).

    Returns:
        A :class:`RegimeDelta` describing the change.
    """
    current_label = current.regime_label
    current_family = current.regime_family
    current_confidence = current.confidence

    if previous is None:
        return RegimeDelta(
            is_initial=True,
            label_changed=False,
            family_changed=False,
            confidence_changed=False,
            confidence_direction=ConfidenceDirection.NOT_APPLICABLE,
            severity=ChangeSeverity.UNCHANGED,
            changed_dimensions=[],
            prior_label=None,
            prior_family=None,
            prior_confidence=None,
            current_label=current_label.value,
            current_family=current_family.value,
            current_confidence=current_confidence.value,
            label_transition=None,
            confidence_transition=None,
            is_regime_transition=False,
            notable_flags=[],
            severity_rationale="No prior regime available — initial state.",
        )

    prior_label = previous.regime_label
    prior_family = previous.regime_family
    prior_confidence = previous.confidence

    # --- Dimension deltas ---
    label_changed = current_label != prior_label
    family_changed = current_family != prior_family
    confidence_changed = current_confidence != prior_confidence

    changed_dimensions: list[str] = []
    if label_changed:
        changed_dimensions.append("label")
    if family_changed:
        changed_dimensions.append("family")
    if confidence_changed:
        changed_dimensions.append("confidence")

    # --- Confidence direction ---
    if not confidence_changed:
        confidence_direction = ConfidenceDirection.UNCHANGED
    elif _CONFIDENCE_RANK[current_confidence] > _CONFIDENCE_RANK[prior_confidence]:
        confidence_direction = ConfidenceDirection.IMPROVED
    else:
        confidence_direction = ConfidenceDirection.WEAKENED

    # --- Label and confidence transition strings ---
    label_transition = (
        f"{prior_label.value} → {current_label.value}" if label_changed else None
    )
    confidence_transition = (
        f"{prior_confidence.value} → {current_confidence.value}" if confidence_changed else None
    )

    # --- Notable flags ---
    notable_flags: list[str] = []
    if label_changed and family_changed:
        notable_flags.append("cross_family_transition")
    if label_changed and current_label in _HIGH_SEVERITY_DESTINATION_LABELS:
        notable_flags.append("high_severity_destination")
    if confidence_changed:
        curr_rank = _CONFIDENCE_RANK[current_confidence]
        prev_rank = _CONFIDENCE_RANK[prior_confidence]
        if abs(curr_rank - prev_rank) > 1:
            notable_flags.append("confidence_jump")

    # --- Severity classification (v1, heuristic) ---
    severity, severity_rationale = _classify_severity(
        label_changed=label_changed,
        family_changed=family_changed,
        confidence_changed=confidence_changed,
        current_label=current_label,
        current_confidence=current_confidence,
        prior_confidence=prior_confidence,
        notable_flags=notable_flags,
    )

    return RegimeDelta(
        is_initial=False,
        label_changed=label_changed,
        family_changed=family_changed,
        confidence_changed=confidence_changed,
        confidence_direction=confidence_direction.value,
        severity=severity.value,
        changed_dimensions=changed_dimensions,
        prior_label=prior_label.value,
        prior_family=prior_family.value,
        prior_confidence=prior_confidence.value,
        current_label=current_label.value,
        current_family=current_family.value,
        current_confidence=current_confidence.value,
        label_transition=label_transition,
        confidence_transition=confidence_transition,
        is_regime_transition=label_changed,
        notable_flags=notable_flags,
        severity_rationale=severity_rationale,
    )


def _classify_severity(
    *,
    label_changed: bool,
    family_changed: bool,
    confidence_changed: bool,
    current_label: RegimeLabel,
    current_confidence: RegimeConfidence,
    prior_confidence: RegimeConfidence,
    notable_flags: list[str],
) -> tuple[ChangeSeverity, str]:
    """Classify heuristic severity from change dimensions.

    Returns a ``(ChangeSeverity, rationale_string)`` tuple.
    All rules are v1 heuristics — explicitly not statistically calibrated.
    """
    if not label_changed and not confidence_changed:
        return ChangeSeverity.UNCHANGED, "No label or confidence change detected."

    if label_changed:
        # Major: cross-family transition
        if family_changed:
            return (
                ChangeSeverity.MAJOR,
                (
                    "Cross-family regime transition (label and family both changed). "
                    "Heuristic severity: major (v1, not statistically calibrated)."
                ),
            )
        # Major: destination is a high-severity label
        if "high_severity_destination" in notable_flags:
            return (
                ChangeSeverity.MAJOR,
                (
                    f"Regime shifted to '{current_label.value}', a high-severity label. "
                    "Heuristic severity: major (v1, not statistically calibrated)."
                ),
            )
        # Moderate: label changed within same family
        return (
            ChangeSeverity.MODERATE,
            (
                "Regime label changed within the same family. "
                "Heuristic severity: moderate (v1, not statistically calibrated)."
            ),
        )

    # Label unchanged; only confidence changed
    curr_rank = _CONFIDENCE_RANK[current_confidence]
    prev_rank = _CONFIDENCE_RANK[prior_confidence]
    rank_diff = abs(curr_rank - prev_rank)

    if rank_diff > 1:
        return (
            ChangeSeverity.MODERATE,
            (
                f"Confidence skipped a level ({prior_confidence.value} → "
                f"{current_confidence.value}). "
                "Heuristic severity: moderate (v1, not statistically calibrated)."
            ),
        )
    return (
        ChangeSeverity.MINOR,
        (
            f"Confidence changed by one level ({prior_confidence.value} → "
            f"{current_confidence.value}). Label unchanged. "
            "Heuristic severity: minor (v1, not statistically calibrated)."
        ),
    )
