"""Tests for domain/macro/change_detection.py — Change Detection Engine v1."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.domain.macro.change_detection import (
    ChangeSeverity,
    ConfidenceDirection,
    RegimeDelta,
    detect_regime_change,
)
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.pipelines.ingestion.models import FreshnessStatus


def _regime(
    *,
    as_of_date: date = date(2026, 1, 1),
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    family: RegimeFamily = RegimeFamily.EXPANSION,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
) -> MacroRegime:
    return MacroRegime(
        as_of_date=as_of_date,
        regime_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-1",
        confidence=confidence,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        transition=RegimeTransition(
            transition_type=RegimeTransitionType.INITIAL,
            changed=False,
        ),
    )


class TestDetectRegimeChangeInitial:
    """No prior regime — initial state."""

    def test_no_prior_returns_initial_delta(self) -> None:
        current = _regime()
        delta = detect_regime_change(current=current, previous=None)
        assert delta.is_initial is True
        assert delta.severity == ChangeSeverity.UNCHANGED
        assert delta.label_changed is False
        assert delta.confidence_changed is False
        assert delta.changed_dimensions == []
        assert delta.prior_label is None
        assert delta.confidence_direction == ConfidenceDirection.NOT_APPLICABLE

    def test_initial_carries_current_label(self) -> None:
        current = _regime(label=RegimeLabel.SLOWDOWN, family=RegimeFamily.DOWNSHIFT)
        delta = detect_regime_change(current=current, previous=None)
        assert delta.current_label == "slowdown"
        assert delta.current_family == "downshift"
        assert delta.current_confidence == "high"


class TestDetectRegimeChangeUnchanged:
    """Label and confidence both identical."""

    def test_identical_regimes_produce_unchanged(self) -> None:
        current = _regime()
        previous = _regime()
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.UNCHANGED
        assert delta.label_changed is False
        assert delta.confidence_changed is False
        assert delta.is_regime_transition is False
        assert delta.changed_dimensions == []

    def test_unchanged_confidence_direction(self) -> None:
        delta = detect_regime_change(
            current=_regime(confidence=RegimeConfidence.MEDIUM),
            previous=_regime(confidence=RegimeConfidence.MEDIUM),
        )
        assert delta.confidence_direction == ConfidenceDirection.UNCHANGED


class TestDetectRegimeChangeMinor:
    """Label stable; confidence shifts by one level."""

    def test_confidence_high_to_medium_is_minor(self) -> None:
        current = _regime(confidence=RegimeConfidence.MEDIUM)
        previous = _regime(confidence=RegimeConfidence.HIGH)
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MINOR
        assert delta.confidence_changed is True
        assert delta.confidence_direction == ConfidenceDirection.WEAKENED
        assert "confidence" in delta.changed_dimensions
        assert delta.label_changed is False

    def test_confidence_medium_to_high_is_minor(self) -> None:
        current = _regime(confidence=RegimeConfidence.HIGH)
        previous = _regime(confidence=RegimeConfidence.MEDIUM)
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MINOR
        assert delta.confidence_direction == ConfidenceDirection.IMPROVED

    def test_confidence_medium_to_low_is_minor(self) -> None:
        current = _regime(confidence=RegimeConfidence.LOW)
        previous = _regime(confidence=RegimeConfidence.MEDIUM)
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MINOR
        assert delta.confidence_direction == ConfidenceDirection.WEAKENED

    def test_confidence_transition_string_populated(self) -> None:
        current = _regime(confidence=RegimeConfidence.MEDIUM)
        previous = _regime(confidence=RegimeConfidence.HIGH)
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.confidence_transition == "high → medium"


class TestDetectRegimeChangeModerate:
    """Label changes within same family, or confidence jumps two levels."""

    def test_same_family_label_change_is_moderate(self) -> None:
        # Both goldilocks and disinflation are loosely within inflation/expansion families
        # but they differ — and the key test is same-family change
        current = _regime(
            label=RegimeLabel.REFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
        )
        previous = _regime(
            label=RegimeLabel.DISINFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MODERATE
        assert delta.label_changed is True
        assert delta.family_changed is False
        assert delta.is_regime_transition is True
        assert "label" in delta.changed_dimensions

    def test_confidence_jump_two_levels_is_moderate(self) -> None:
        current = _regime(confidence=RegimeConfidence.LOW)
        previous = _regime(confidence=RegimeConfidence.HIGH)
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MODERATE
        assert "confidence_jump" in delta.notable_flags

    def test_label_transition_string_populated(self) -> None:
        current = _regime(
            label=RegimeLabel.REFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
        )
        previous = _regime(
            label=RegimeLabel.DISINFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.label_transition == "disinflation → reflation"


class TestDetectRegimeChangeMajor:
    """Cross-family transition or high-severity destination."""

    def test_cross_family_transition_is_major(self) -> None:
        current = _regime(
            label=RegimeLabel.CONTRACTION,
            family=RegimeFamily.CONTRACTION,
        )
        previous = _regime(
            label=RegimeLabel.GOLDILOCKS,
            family=RegimeFamily.EXPANSION,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MAJOR
        assert delta.family_changed is True
        assert delta.label_changed is True
        assert "cross_family_transition" in delta.notable_flags

    def test_contraction_destination_is_major(self) -> None:
        current = _regime(
            label=RegimeLabel.CONTRACTION,
            family=RegimeFamily.CONTRACTION,
        )
        previous = _regime(
            label=RegimeLabel.SLOWDOWN,
            family=RegimeFamily.DOWNSHIFT,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MAJOR
        assert "high_severity_destination" in delta.notable_flags

    def test_stagflation_risk_destination_is_major(self) -> None:
        current = _regime(
            label=RegimeLabel.STAGFLATION_RISK,
            family=RegimeFamily.LATE_CYCLE,
        )
        previous = _regime(
            label=RegimeLabel.GOLDILOCKS,
            family=RegimeFamily.EXPANSION,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MAJOR

    def test_major_includes_cross_family_flag(self) -> None:
        current = _regime(
            label=RegimeLabel.SLOWDOWN,
            family=RegimeFamily.DOWNSHIFT,
        )
        previous = _regime(
            label=RegimeLabel.GOLDILOCKS,
            family=RegimeFamily.EXPANSION,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.severity == ChangeSeverity.MAJOR
        assert "cross_family_transition" in delta.notable_flags


class TestRegimeDeltaFields:
    """Verify all RegimeDelta fields are populated correctly."""

    def test_prior_fields_populated_on_shift(self) -> None:
        current = _regime(
            label=RegimeLabel.SLOWDOWN,
            family=RegimeFamily.DOWNSHIFT,
            confidence=RegimeConfidence.MEDIUM,
        )
        previous = _regime(
            label=RegimeLabel.GOLDILOCKS,
            family=RegimeFamily.EXPANSION,
            confidence=RegimeConfidence.HIGH,
        )
        delta = detect_regime_change(current=current, previous=previous)
        assert delta.prior_label == "goldilocks"
        assert delta.prior_family == "expansion"
        assert delta.prior_confidence == "high"
        assert delta.current_label == "slowdown"
        assert delta.current_family == "downshift"
        assert delta.current_confidence == "medium"

    def test_severity_rationale_non_empty(self) -> None:
        current = _regime(label=RegimeLabel.CONTRACTION, family=RegimeFamily.CONTRACTION)
        previous = _regime()
        delta = detect_regime_change(current=current, previous=previous)
        assert len(delta.severity_rationale) > 0

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            RegimeDelta(
                unknown_field="x",  # type: ignore[call-arg]
                severity="major",
            )
