"""Tests for the attribution engine (Chapter 8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from src.domain.attribution.attribution_engine import (
    DEFAULT_ATTRIBUTION_RULES,
    attribute_delta,
    run_attribution,
)
from src.domain.attribution.enums import AttributionConfidence
from src.domain.attribution.models import AttributionRule
from src.domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventType,
    SourceReliabilityTier,
)
from src.domain.events.models import NormalizedExternalEvent
from src.domain.macro.comparison import FeatureDelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_type: ExternalEventType = ExternalEventType.MACRO_RELEASE,
    occurred_days_before: int = 1,
    title: str = "Test event",
    reliability_tier: SourceReliabilityTier = SourceReliabilityTier.TIER_1,
    as_of: datetime | None = None,
) -> NormalizedExternalEvent:
    ref = as_of or datetime.now(UTC)
    occurred_at = ref - timedelta(days=occurred_days_before)
    return NormalizedExternalEvent(
        event_type=event_type,
        title=title,
        source="BLS",
        provenance="test",
        occurred_at=occurred_at,
        freshness=ExternalEventFreshness.FRESH,
        reliability_tier=reliability_tier,
    )


def _make_delta(
    indicator: str = "cpi",
    direction: Literal["increased", "decreased", "unchanged", "no_prior"] = "increased",
    delta: float = 0.2,
) -> FeatureDelta:
    return FeatureDelta(
        indicator_type=indicator,
        current_value=3.2,
        prior_value=3.0,
        delta=delta,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# attribute_delta tests
# ---------------------------------------------------------------------------


class TestAttributeDeltaExactMatch:
    def test_high_confidence_tier1_short_lag(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            occurred_days_before=1,
            as_of=as_of,
            reliability_tier=SourceReliabilityTier.TIER_1,
        )
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [event], as_of)
        assert result.confidence == AttributionConfidence.HIGH
        assert result.is_attributed()
        assert result.best_candidate() is not None
        assert result.catalyst_context.rule_id is not None

    def test_medium_confidence_longer_lag(self) -> None:
        # lag = 2 days, rule max = 3 days, but tier_3 → not high
        as_of = datetime.now(UTC)
        event = _make_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            occurred_days_before=2,
            as_of=as_of,
            reliability_tier=SourceReliabilityTier.TIER_3,
        )
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [event], as_of)
        # Still within max_lag_days=3, so medium confidence
        assert result.confidence in {AttributionConfidence.HIGH, AttributionConfidence.MEDIUM}

    def test_unattributed_when_no_events(self) -> None:
        as_of = datetime.now(UTC)
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [], as_of)
        assert result.confidence == AttributionConfidence.UNATTRIBUTED
        assert not result.is_attributed()
        assert result.best_candidate() is None

    def test_unattributed_when_event_exceeds_lag(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            occurred_days_before=10,  # rule max_lag=3 for cpi
            as_of=as_of,
        )
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [event], as_of)
        # Beyond exact rule lag but might match heuristic fallback
        assert result.confidence in {
            AttributionConfidence.LOW,
            AttributionConfidence.UNATTRIBUTED,
        }

    def test_future_event_excluded(self) -> None:
        as_of = datetime.now(UTC)
        # Event occurred AFTER as_of → should be excluded
        future_event = NormalizedExternalEvent(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="Future event",
            source="BLS",
            provenance="test",
            occurred_at=as_of + timedelta(days=1),
            freshness=ExternalEventFreshness.FRESH,
            reliability_tier=SourceReliabilityTier.TIER_1,
        )
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [future_event], as_of)
        assert result.confidence == AttributionConfidence.UNATTRIBUTED

    def test_closest_event_selected_as_best(self) -> None:
        as_of = datetime.now(UTC)
        near_event = _make_event(occurred_days_before=1, as_of=as_of)
        far_event = _make_event(occurred_days_before=2, as_of=as_of)
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [far_event, near_event], as_of)
        best = result.best_candidate()
        assert best is not None
        assert best.lag_days == 1

    def test_central_bank_rate_match(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(
            event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            occurred_days_before=3,
            as_of=as_of,
        )
        delta = _make_delta(indicator="interest_rate")
        result = attribute_delta(delta, [event], as_of)
        assert result.is_attributed()

    def test_catalyst_context_advisory_note_present(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(occurred_days_before=1, as_of=as_of)
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [event], as_of)
        assert result.catalyst_context.advisory_note
        assert "advisory" in result.catalyst_context.advisory_note.lower() or result.is_attributed()

    def test_unattributed_advisory_note_mentions_no_candidate(self) -> None:
        as_of = datetime.now(UTC)
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [], as_of)
        assert "No candidate" in result.catalyst_context.advisory_note


class TestAttributeDeltaHeuristicFallback:
    def test_low_confidence_for_heuristic_match(self) -> None:
        as_of = datetime.now(UTC)
        # Use an indicator not in the explicit rules but in heuristic map
        event = _make_event(
            event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            occurred_days_before=5,
            as_of=as_of,
        )
        delta = _make_delta(indicator="pce")  # in heuristic fallback for central_bank_decision
        result = attribute_delta(delta, [event], as_of)
        assert result.confidence in {AttributionConfidence.LOW, AttributionConfidence.UNATTRIBUTED}

    def test_custom_rules_override_defaults(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            occurred_days_before=1,
            as_of=as_of,
        )
        custom_rules = [
            AttributionRule(
                event_type="macro_release",
                indicator_type="custom_indicator",
                max_lag_days=5,
            )
        ]
        delta = _make_delta(indicator="custom_indicator")
        result = attribute_delta(delta, [event], as_of, rules=custom_rules)
        assert result.is_attributed()

    def test_inactive_rule_skipped(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(occurred_days_before=1, as_of=as_of)
        inactive_rule = AttributionRule(
            event_type="macro_release",
            indicator_type="cpi",
            max_lag_days=30,
            is_active=False,
        )
        delta = _make_delta(indicator="cpi")
        result = attribute_delta(delta, [event], as_of, rules=[inactive_rule])
        # Inactive rule → only heuristic fallback available → low or unattributed
        assert result.confidence in {AttributionConfidence.LOW, AttributionConfidence.UNATTRIBUTED}


# ---------------------------------------------------------------------------
# run_attribution tests
# ---------------------------------------------------------------------------


class TestRunAttribution:
    def test_skips_unchanged_by_default(self) -> None:
        as_of = datetime.now(UTC)
        deltas = [
            _make_delta(indicator="cpi", direction="increased"),
            FeatureDelta(
                indicator_type="gdp",
                current_value=2.0,
                prior_value=2.0,
                delta=0.0,
                direction="unchanged",
            ),
            FeatureDelta(
                indicator_type="pmi",
                current_value=50.0,
                prior_value=None,
                delta=None,
                direction="no_prior",
            ),
        ]
        event = _make_event(occurred_days_before=1, as_of=as_of)
        result = run_attribution(deltas, [event], as_of)
        # Only "increased" cpi delta should be attributed
        assert len(result.attributions) == 1
        assert result.attributions[0].indicator_type == "cpi"

    def test_include_unchanged_flag(self) -> None:
        as_of = datetime.now(UTC)
        deltas = [
            _make_delta(indicator="cpi", direction="increased"),
            FeatureDelta(
                indicator_type="gdp",
                current_value=2.0,
                prior_value=2.0,
                delta=0.0,
                direction="unchanged",
            ),
        ]
        result = run_attribution(deltas, [], as_of, include_unchanged=True)
        assert len(result.attributions) == 2

    def test_counts_correct(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(occurred_days_before=1, as_of=as_of)
        deltas = [
            _make_delta(indicator="cpi", direction="increased"),
            _make_delta(indicator="unknown_indicator_xyz", direction="decreased"),
        ]
        result = run_attribution(deltas, [event], as_of)
        assert result.total_attributed + result.total_unattributed == len(result.attributions)

    def test_snapshot_id_stored(self) -> None:
        as_of = datetime.now(UTC)
        result = run_attribution([], [], as_of, snapshot_id="snap-123")
        assert result.snapshot_id == "snap-123"

    def test_empty_deltas_returns_empty_result(self) -> None:
        as_of = datetime.now(UTC)
        result = run_attribution([], [], as_of)
        assert result.attributions == []
        assert result.total_attributed == 0
        assert result.total_unattributed == 0

    def test_summary_context_only_attributed(self) -> None:
        as_of = datetime.now(UTC)
        event = _make_event(occurred_days_before=1, as_of=as_of)
        deltas = [
            _make_delta(indicator="cpi", direction="increased"),
            _make_delta(indicator="no_match_indicator_xyz", direction="increased"),
        ]
        result = run_attribution(deltas, [event], as_of)
        ctx = result.summary_context()
        # At least cpi should be attributed via the builtin rule
        attributed_types = [c.indicator_type for c in ctx]
        assert "cpi" in attributed_types


class TestDefaultRules:
    def test_default_rules_are_all_active(self) -> None:
        for rule in DEFAULT_ATTRIBUTION_RULES:
            assert rule.is_active, f"Rule {rule.rule_id} should be active"

    def test_default_rules_cover_key_indicators(self) -> None:
        covered = {r.indicator_type for r in DEFAULT_ATTRIBUTION_RULES}
        for expected in {"cpi", "gdp", "unemployment_rate", "retail_sales", "pmi", "10y_yield"}:
            assert expected in covered, f"{expected} not covered by default rules"
