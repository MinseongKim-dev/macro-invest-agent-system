"""Tests for the regime narrative builder."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.domain.macro.narrative_builder import build_regime_narrative
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.pipelines.ingestion.models import FreshnessStatus


def _regime(
    *,
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
    transition_type: RegimeTransitionType = RegimeTransitionType.INITIAL,
    transition_from_prior: str | None = None,
    supporting_states: dict[str, str] | None = None,
    missing_inputs: list[str] | None = None,
) -> MacroRegime:
    from src.domain.macro.regime import REGIME_LABEL_FAMILY_MAP

    family = REGIME_LABEL_FAMILY_MAP[label]
    return MacroRegime(
        as_of_date=date(2026, 4, 1),
        regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-test",
        confidence=confidence,
        freshness_status=freshness,
        degraded_status=degraded,
        transition=RegimeTransition(
            transition_from_prior=transition_from_prior,
            transition_type=transition_type,
            changed=transition_type == RegimeTransitionType.SHIFT,
        ),
        supporting_states=supporting_states
        or {
            "growth_state": "accelerating",
            "inflation_state": "cooling",
            "labor_state": "tight",
            "policy_state": "neutral",
            "financial_conditions_state": "neutral",
        },
        missing_inputs=missing_inputs or [],
    )


class TestBuildRegimeNarrative:
    def test_returns_expected_keys(self) -> None:
        narrative = build_regime_narrative(_regime())
        assert "summary" in narrative
        assert "rationale_points" in narrative
        assert "caveats" in narrative
        assert "data_quality_notes" in narrative
        assert "regime_label" in narrative
        assert "regime_context" in narrative
        assert "generated_at" in narrative

    def test_summary_is_non_empty_string(self) -> None:
        narrative = build_regime_narrative(_regime())
        assert isinstance(narrative["summary"], str)
        assert len(narrative["summary"]) > 50

    def test_rationale_points_is_list(self) -> None:
        narrative = build_regime_narrative(_regime())
        points = narrative["rationale_points"]
        assert isinstance(points, list)
        assert len(points) >= 3

    def test_regime_label_matches(self) -> None:
        narrative = build_regime_narrative(_regime(label=RegimeLabel.CONTRACTION))
        assert narrative["regime_label"] == "contraction"

    def test_regime_context_has_required_keys(self) -> None:
        narrative = build_regime_narrative(_regime())
        ctx = narrative["regime_context"]
        assert isinstance(ctx, dict)
        # Minimum documented keys
        for key in ("label", "family", "confidence", "transition", "freshness", "degraded_status"):
            assert key in ctx, f"Missing minimum regime_context key: {key}"

    def test_goldilocks_summary_mentions_risk_on(self) -> None:
        narrative = build_regime_narrative(_regime(label=RegimeLabel.GOLDILOCKS))
        assert "goldilocks" in narrative["summary"].lower() or "risk" in narrative["summary"].lower()

    def test_contraction_summary_mentions_contraction(self) -> None:
        narrative = build_regime_narrative(_regime(label=RegimeLabel.CONTRACTION))
        assert "contraction" in narrative["summary"].lower()

    def test_stagflation_summary_mentions_inflation(self) -> None:
        narrative = build_regime_narrative(_regime(label=RegimeLabel.STAGFLATION_RISK))
        assert "inflation" in narrative["summary"].lower()

    def test_low_confidence_reflected_in_summary(self) -> None:
        narrative = build_regime_narrative(_regime(confidence=RegimeConfidence.LOW))
        assert "low" in narrative["summary"].lower()

    def test_stale_freshness_reflected_in_summary(self) -> None:
        narrative = build_regime_narrative(
            _regime(freshness=FreshnessStatus.STALE, label=RegimeLabel.SLOWDOWN)
        )
        assert "stale" in narrative["summary"].lower()

    def test_degraded_partial_reflected_in_summary(self) -> None:
        narrative = build_regime_narrative(
            _regime(degraded=DegradedStatus.PARTIAL, label=RegimeLabel.SLOWDOWN)
        )
        assert "partial" in narrative["summary"].lower() or "missing" in narrative["summary"].lower()

    def test_missing_inputs_in_rationale(self) -> None:
        narrative = build_regime_narrative(
            _regime(missing_inputs=["pmi", "retail_sales"])
        )
        # Missing inputs are surfaced in data_quality_notes (not rationale_points)
        dq_text = " ".join(narrative["data_quality_notes"])
        assert "pmi" in dq_text
        assert "retail_sales" in dq_text

    def test_transition_from_prior_in_rationale(self) -> None:
        narrative = build_regime_narrative(
            _regime(
                transition_type=RegimeTransitionType.SHIFT,
                transition_from_prior="contraction",
            )
        )
        points_text = " ".join(narrative["rationale_points"])
        assert "contraction" in points_text

    def test_all_five_states_in_rationale(self) -> None:
        narrative = build_regime_narrative(_regime())
        points_text = " ".join(narrative["rationale_points"])
        for state_label in ("Growth", "Inflation", "Labour", "Policy", "Financial Conditions"):
            assert state_label in points_text

    def test_caveats_is_list(self) -> None:
        narrative = build_regime_narrative(_regime())
        assert isinstance(narrative["caveats"], list)

    def test_data_quality_notes_is_list(self) -> None:
        narrative = build_regime_narrative(_regime())
        assert isinstance(narrative["data_quality_notes"], list)

    def test_initial_transition_adds_caveat(self) -> None:
        narrative = build_regime_narrative(_regime(transition_type=RegimeTransitionType.INITIAL))
        caveats_text = " ".join(narrative["caveats"])
        assert "prior" in caveats_text.lower() or "baseline" in caveats_text.lower()

    def test_low_confidence_adds_caveat(self) -> None:
        narrative = build_regime_narrative(_regime(confidence=RegimeConfidence.LOW))
        caveats_text = " ".join(narrative["caveats"])
        assert "low confidence" in caveats_text.lower() or "low" in caveats_text.lower()

    def test_stale_data_adds_data_quality_note(self) -> None:
        narrative = build_regime_narrative(
            _regime(freshness=FreshnessStatus.STALE, label=RegimeLabel.SLOWDOWN)
        )
        dq_text = " ".join(narrative["data_quality_notes"])
        assert "stale" in dq_text.lower()

    def test_seeded_regime_adds_data_quality_note(self) -> None:
        from src.domain.macro.regime import (
            REGIME_LABEL_FAMILY_MAP,
            MacroRegime,
            RegimeTransition,
        )
        regime = MacroRegime(
            as_of_date=date(2026, 4, 1),
            regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            regime_label=RegimeLabel.SLOWDOWN,
            regime_family=REGIME_LABEL_FAMILY_MAP[RegimeLabel.SLOWDOWN],
            supporting_snapshot_id="snap-seed",
            confidence=RegimeConfidence.HIGH,
            freshness_status=FreshnessStatus.FRESH,
            degraded_status=DegradedStatus.NONE,
            transition=RegimeTransition(transition_type=RegimeTransitionType.INITIAL),
            metadata={"seeded": "true", "source": "synthetic_seed"},
        )
        narrative = build_regime_narrative(regime)
        dq_text = " ".join(narrative["data_quality_notes"])
        assert "bootstrap" in dq_text.lower() or "synthetic" in dq_text.lower()

    def test_missing_inputs_adds_both_caveat_and_data_quality_note(self) -> None:
        narrative = build_regime_narrative(
            _regime(missing_inputs=["pmi", "retail_sales"])
        )
        caveats_text = " ".join(narrative["caveats"])
        dq_text = " ".join(narrative["data_quality_notes"])
        assert "missing" in caveats_text.lower() or "partial" in caveats_text.lower()
        assert "pmi" in dq_text.lower()

    def test_all_all_regime_labels_produce_non_empty_summary(self) -> None:
        """Every RegimeLabel must produce a non-empty summary narrative."""
        for label in RegimeLabel:
            narrative = build_regime_narrative(_regime(label=label))
            assert len(narrative["summary"]) > 20, f"Empty summary for {label}"
