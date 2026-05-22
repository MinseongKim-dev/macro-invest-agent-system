"""Tests for deterministic regime transition classification."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransitionType,
)
from src.domain.macro.regime_transition import derive_regime_transition


def _regime(label: RegimeLabel, family: RegimeFamily, confidence: RegimeConfidence) -> MacroRegime:
    return MacroRegime(
        as_of_date=date(2026, 2, 1),
        regime_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        confidence=confidence,
        supporting_snapshot_id="snap-1",
    )


class TestRegimeTransition:
    def test_initial_without_prior(self) -> None:
        current = _regime(RegimeLabel.GOLDILOCKS, RegimeFamily.EXPANSION, RegimeConfidence.HIGH)
        t = derive_regime_transition(current=current, previous=None)
        assert t.transition_type == RegimeTransitionType.INITIAL
        assert t.changed is False

    def test_shift_when_label_changes(self) -> None:
        current = _regime(
            RegimeLabel.CONTRACTION, RegimeFamily.CONTRACTION, RegimeConfidence.MEDIUM
        )
        prior = _regime(RegimeLabel.SLOWDOWN, RegimeFamily.DOWNSHIFT, RegimeConfidence.MEDIUM)
        t = derive_regime_transition(current=current, previous=prior)
        assert t.transition_type == RegimeTransitionType.SHIFT
        assert t.changed is True

    def test_strengthening_and_weakening_by_confidence(self) -> None:
        base = _regime(
            RegimeLabel.DISINFLATION, RegimeFamily.INFLATION_TRANSITION, RegimeConfidence.MEDIUM
        )
        stronger = _regime(
            RegimeLabel.DISINFLATION, RegimeFamily.INFLATION_TRANSITION, RegimeConfidence.HIGH
        )
        weaker = _regime(
            RegimeLabel.DISINFLATION, RegimeFamily.INFLATION_TRANSITION, RegimeConfidence.LOW
        )
        assert (
            derive_regime_transition(current=stronger, previous=base).transition_type
            == RegimeTransitionType.STRENGTHENING
        )
        assert (
            derive_regime_transition(current=weaker, previous=base).transition_type
            == RegimeTransitionType.WEAKENING
        )
