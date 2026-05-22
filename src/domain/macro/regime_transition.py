"""Deterministic transition logic between current and prior regimes."""

from __future__ import annotations

from domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeTransition,
    RegimeTransitionType,
)

_CONFIDENCE_RANK = {
    RegimeConfidence.LOW: 1,
    RegimeConfidence.MEDIUM: 2,
    RegimeConfidence.HIGH: 3,
}


def derive_regime_transition(
    current: MacroRegime,
    previous: MacroRegime | None,
) -> RegimeTransition:
    if previous is None:
        return RegimeTransition(
            transition_from_prior=None,
            transition_type=RegimeTransitionType.INITIAL,
            changed=False,
        )

    if current.regime_label != previous.regime_label:
        return RegimeTransition(
            transition_from_prior=previous.regime_label.value,
            transition_type=RegimeTransitionType.SHIFT,
            changed=True,
        )

    curr_rank = _CONFIDENCE_RANK[current.confidence]
    prev_rank = _CONFIDENCE_RANK[previous.confidence]
    if curr_rank > prev_rank:
        transition_type = RegimeTransitionType.STRENGTHENING
        changed = True
    elif curr_rank < prev_rank:
        transition_type = RegimeTransitionType.WEAKENING
        changed = True
    else:
        transition_type = RegimeTransitionType.UNCHANGED
        changed = False

    return RegimeTransition(
        transition_from_prior=previous.regime_label.value,
        transition_type=transition_type,
        changed=changed,
    )
