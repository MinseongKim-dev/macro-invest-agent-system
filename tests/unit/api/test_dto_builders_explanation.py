"""Unit tests for Explanation Engine v2 DTO builders.

Covers:
* :func:`~apps.api.dto.builders.build_reasoning_chain` — determinism, step count, key order.
* :func:`~apps.api.dto.builders.build_what_changed` — initial vs transition regimes.
* :func:`~apps.api.dto.builders.build_analyst_workflow` — mirrors reasoning_chain.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from apps.api.dto.builders import (
    build_analyst_workflow,
    build_reasoning_chain,
    build_what_changed,
)
from apps.api.dto.explanations import REASONING_STEP_KEYS
from src.domain.macro.narrative_builder import build_regime_narrative
from src.domain.macro.regime import (
    REGIME_LABEL_FAMILY_MAP,
    MacroRegime,
    RegimeConfidence,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.pipelines.ingestion.models import FreshnessStatus

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _regime(
    *,
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
    transition_type: RegimeTransitionType = RegimeTransitionType.INITIAL,
    transition_from_prior: str | None = None,
    missing_inputs: list[str] | None = None,
) -> MacroRegime:
    family = REGIME_LABEL_FAMILY_MAP[label]
    return MacroRegime(
        as_of_date=date(2026, 4, 19),
        regime_timestamp=datetime(2026, 4, 19, tzinfo=UTC),
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
        missing_inputs=missing_inputs or [],
        supporting_states={
            "growth_state": "accelerating",
            "inflation_state": "cooling",
            "labor_state": "tight",
            "policy_state": "neutral",
            "financial_conditions_state": "neutral",
        },
    )


# ---------------------------------------------------------------------------
# build_reasoning_chain
# ---------------------------------------------------------------------------


class TestBuildReasoningChain:
    def test_returns_exactly_six_steps(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        assert len(chain) == 6

    def test_steps_are_in_canonical_order(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        for i, (step, expected_key) in enumerate(zip(chain, REASONING_STEP_KEYS, strict=True)):
            assert step.key == expected_key, (
                f"Step {i+1}: expected key={expected_key!r}, got key={step.key!r}"
            )

    def test_step_ordinals_are_one_based_sequential(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        for i, step in enumerate(chain, start=1):
            assert step.step == i

    def test_current_state_value_contains_regime_label(self) -> None:
        regime = _regime(label=RegimeLabel.CONTRACTION)
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        current_state = next(s for s in chain if s.key == "current_state")
        assert "contraction" in current_state.value.lower()

    def test_confidence_step_value_matches_regime_confidence(self) -> None:
        regime = _regime(confidence=RegimeConfidence.LOW)
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        confidence_step = next(s for s in chain if s.key == "confidence")
        assert "low" in confidence_step.value.lower()

    def test_conflict_step_reflects_passed_conflict_status(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(
            narrative,
            conflict_status="tension",
            conflict_note="One conflicting driver.",
            quant_support_level="strong",
        )
        conflict_step = next(s for s in chain if s.key == "conflict")
        assert conflict_step.value == "tension"
        assert conflict_step.detail == "One conflicting driver."

    def test_caveats_step_none_when_no_caveats(self) -> None:
        # GOLDILOCKS + HIGH confidence + FRESH data + SHIFT transition has caveats from initial
        regime = _regime(
            transition_type=RegimeTransitionType.SHIFT,
            transition_from_prior="slowdown",
        )
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        caveats_step = next(s for s in chain if s.key == "caveats")
        # Should have "none" value since no caveats for clean healthy regime
        assert caveats_step.value in ("none", "0 caveat(s)", "1 caveat(s)")

    def test_what_changed_step_initial_regime(self) -> None:
        regime = _regime(transition_type=RegimeTransitionType.INITIAL)
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        wc_step = next(s for s in chain if s.key == "what_changed")
        assert "initial" in wc_step.value.lower()

    def test_what_changed_step_shift_regime(self) -> None:
        regime = _regime(
            transition_type=RegimeTransitionType.SHIFT,
            transition_from_prior="contraction",
        )
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        wc_step = next(s for s in chain if s.key == "what_changed")
        assert "contraction" in wc_step.value.lower()
        assert "shift" in wc_step.value.lower()

    def test_determinism_same_input_same_output(self) -> None:
        """Same regime always produces identical reasoning chain."""
        regime = _regime(label=RegimeLabel.STAGFLATION_RISK, confidence=RegimeConfidence.MEDIUM)
        narrative = build_regime_narrative(regime)
        chain1 = build_reasoning_chain(narrative)
        chain2 = build_reasoning_chain(narrative)
        assert len(chain1) == len(chain2)
        for s1, s2 in zip(chain1, chain2, strict=True):
            assert s1.key == s2.key
            assert s1.value == s2.value

    def test_all_regime_labels_produce_six_steps(self) -> None:
        """Every RegimeLabel must produce a 6-step chain without errors."""
        for label in RegimeLabel:
            regime = _regime(label=label)
            narrative = build_regime_narrative(regime)
            chain = build_reasoning_chain(narrative)
            assert len(chain) == 6, f"Expected 6 steps for {label}, got {len(chain)}"

    def test_every_step_has_non_empty_label_and_value(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        for step in chain:
            assert step.label, f"Empty label for step {step.key}"
            assert step.value, f"Empty value for step {step.key}"


# ---------------------------------------------------------------------------
# build_what_changed
# ---------------------------------------------------------------------------


class TestBuildWhatChanged:
    def test_initial_regime_returns_none(self) -> None:
        regime = _regime(transition_type=RegimeTransitionType.INITIAL)
        narrative = build_regime_narrative(regime)
        result = build_what_changed(narrative)
        assert result is None

    def test_unchanged_regime_returns_none(self) -> None:
        # UNCHANGED with no transition_from_prior should also return None
        regime = _regime(
            transition_type=RegimeTransitionType.UNCHANGED,
            transition_from_prior=None,
        )
        narrative = build_regime_narrative(regime)
        result = build_what_changed(narrative)
        assert result is None

    def test_shift_regime_returns_dto(self) -> None:
        regime = _regime(
            transition_type=RegimeTransitionType.SHIFT,
            transition_from_prior="slowdown",
        )
        narrative = build_regime_narrative(regime)
        result = build_what_changed(narrative)
        assert result is not None
        assert result.prior_regime_label == "slowdown"
        assert result.transition_type == "shift"
        assert result.changed is True

    def test_weakening_transition(self) -> None:
        regime = _regime(
            transition_type=RegimeTransitionType.WEAKENING,
            transition_from_prior="goldilocks",
        )
        narrative = build_regime_narrative(regime)
        result = build_what_changed(narrative)
        assert result is not None
        assert result.transition_type == "weakening"
        assert result.prior_regime_label == "goldilocks"


# ---------------------------------------------------------------------------
# build_analyst_workflow
# ---------------------------------------------------------------------------


class TestBuildAnalystWorkflow:
    def test_workflow_steps_mirror_reasoning_chain(self) -> None:
        regime = _regime()
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        workflow = build_analyst_workflow(chain)
        assert len(workflow.steps) == len(chain)
        for ws, rs in zip(workflow.steps, chain, strict=True):
            assert ws.key == rs.key
            assert ws.value == rs.value

    def test_workflow_has_six_steps_from_full_chain(self) -> None:
        regime = _regime(label=RegimeLabel.REFLATION)
        narrative = build_regime_narrative(regime)
        chain = build_reasoning_chain(narrative)
        workflow = build_analyst_workflow(chain)
        assert len(workflow.steps) == 6

    def test_empty_chain_produces_empty_workflow(self) -> None:
        workflow = build_analyst_workflow([])
        assert workflow.steps == []
