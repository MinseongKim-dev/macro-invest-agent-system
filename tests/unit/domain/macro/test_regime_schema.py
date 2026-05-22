"""Unit tests for Phase 3 macro regime schema contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.domain.macro.regime import (
    REGIME_LABEL_FAMILY_MAP,
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
    regime_family_for_label,
)


class TestRegimeEnums:
    def test_regime_labels_include_core_values(self) -> None:
        assert RegimeLabel.GOLDILOCKS.value == "goldilocks"
        assert RegimeLabel.STAGFLATION_RISK.value == "stagflation_risk"
        assert RegimeLabel.UNCLEAR.value == "unclear"

    def test_confidence_levels(self) -> None:
        assert RegimeConfidence.HIGH.value == "high"
        assert RegimeConfidence.MEDIUM.value == "medium"
        assert RegimeConfidence.LOW.value == "low"

    def test_label_family_map_covers_all_labels(self) -> None:
        assert set(REGIME_LABEL_FAMILY_MAP) == set(RegimeLabel)
        assert regime_family_for_label(RegimeLabel.GOLDILOCKS) == RegimeFamily.EXPANSION
        assert regime_family_for_label(RegimeLabel.UNCLEAR) == RegimeFamily.UNCERTAIN


class TestRegimeTransition:
    def test_defaults(self) -> None:
        t = RegimeTransition()
        assert t.transition_type == RegimeTransitionType.UNKNOWN
        assert t.changed is False

    def test_round_trip(self) -> None:
        t = RegimeTransition(
            transition_from_prior="slowdown",
            transition_type=RegimeTransitionType.SHIFT,
            changed=True,
        )
        reparsed = RegimeTransition.model_validate(t.model_dump())
        assert reparsed == t


class TestMacroRegime:
    def test_valid_construction(self) -> None:
        r = MacroRegime(
            as_of_date=date(2026, 2, 1),
            regime_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
            regime_label=RegimeLabel.DISINFLATION,
            regime_family=RegimeFamily.INFLATION_TRANSITION,
            supporting_snapshot_id="snap-001",
            supporting_states={
                "growth_state": "mixed",
                "inflation_state": "cooling",
            },
            confidence=RegimeConfidence.MEDIUM,
            rationale_summary="Inflation cooling while growth is mixed.",
        )
        assert r.supporting_snapshot_id == "snap-001"
        assert r.regime_label == RegimeLabel.DISINFLATION
        assert r.confidence == RegimeConfidence.MEDIUM

    def test_supporting_snapshot_id_required(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegime(
                as_of_date=date(2026, 2, 1),
                supporting_snapshot_id="",
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegime(
                as_of_date=date(2026, 2, 1),
                supporting_snapshot_id="snap-001",
                bad="x",  # type: ignore[call-arg]
            )

    def test_rejects_label_family_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="must match regime_label"):
            MacroRegime(
                as_of_date=date(2026, 2, 1),
                supporting_snapshot_id="snap-001",
                regime_label=RegimeLabel.CONTRACTION,
                regime_family=RegimeFamily.EXPANSION,
            )
