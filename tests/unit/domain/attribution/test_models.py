"""Tests for the attribution domain models (Chapter 8)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.attribution.enums import AttributionConfidence, AttributionMatchStatus
from src.domain.attribution.models import (
    AttributionRule,
    AttributionRunResult,
    CandidateEventContext,
    CatalystContext,
    ChangeAttribution,
)


class TestAttributionRule:
    def test_valid_rule_creates_successfully(self) -> None:
        rule = AttributionRule(
            rule_id="r1",
            event_type="macro_release",
            indicator_type="cpi",
            max_lag_days=3,
        )
        assert rule.rule_id == "r1"
        assert rule.event_type == "macro_release"
        assert rule.indicator_type == "cpi"
        assert rule.max_lag_days == 3
        assert rule.is_active is True

    def test_rule_auto_generates_id(self) -> None:
        rule = AttributionRule(
            event_type="central_bank_decision",
            indicator_type="interest_rate",
            max_lag_days=14,
        )
        assert rule.rule_id  # non-empty

    def test_inactive_rule(self) -> None:
        rule = AttributionRule(
            event_type="macro_release",
            indicator_type="cpi",
            max_lag_days=3,
            is_active=False,
        )
        assert rule.is_active is False

    def test_zero_lag_allowed(self) -> None:
        rule = AttributionRule(
            event_type="macro_release",
            indicator_type="cpi",
            max_lag_days=0,
        )
        assert rule.max_lag_days == 0


class TestCandidateEventContext:
    def _make(self, lag_days: int = 2) -> CandidateEventContext:
        return CandidateEventContext(
            event_id="e1",
            event_type="macro_release",
            title="CPI report",
            source="BLS",
            occurred_at=datetime.now(UTC),
            lag_days=lag_days,
            match_status=AttributionMatchStatus.MATCHED,
            reliability_tier="tier_1",
        )

    def test_fields_accessible(self) -> None:
        c = self._make()
        assert c.event_id == "e1"
        assert c.lag_days == 2
        assert c.match_status == AttributionMatchStatus.MATCHED


class TestCatalystContext:
    def test_unattributed_context(self) -> None:
        ctx = CatalystContext(
            indicator_type="cpi",
            confidence=AttributionConfidence.UNATTRIBUTED,
            advisory_note="No candidate found",
        )
        assert ctx.candidate_event_id is None
        assert ctx.confidence == AttributionConfidence.UNATTRIBUTED

    def test_attributed_context(self) -> None:
        ctx = CatalystContext(
            indicator_type="cpi",
            candidate_event_id="e1",
            candidate_event_title="CPI report",
            candidate_event_type="macro_release",
            lag_days=1,
            confidence=AttributionConfidence.HIGH,
            advisory_note="High confidence match",
            rule_id="builtin-mr-cpi",
        )
        assert ctx.lag_days == 1
        assert ctx.rule_id == "builtin-mr-cpi"


class TestChangeAttribution:
    def _make_attribution(
        self, confidence: AttributionConfidence = AttributionConfidence.HIGH
    ) -> ChangeAttribution:
        ctx = CatalystContext(
            indicator_type="cpi",
            candidate_event_id="e1",
            candidate_event_title="CPI report",
            candidate_event_type="macro_release",
            lag_days=1,
            confidence=confidence,
            advisory_note="Test",
            rule_id="r1",
        )
        candidates = [
            CandidateEventContext(
                event_id="e1",
                event_type="macro_release",
                title="CPI report",
                source="BLS",
                occurred_at=datetime.now(UTC),
                lag_days=1,
                match_status=AttributionMatchStatus.MATCHED,
            )
        ]
        return ChangeAttribution(
            indicator_type="cpi",
            direction="increased",
            delta=0.2,
            confidence=confidence,
            candidates=candidates,
            catalyst_context=ctx,
        )

    def test_is_attributed_true_for_high(self) -> None:
        a = self._make_attribution(AttributionConfidence.HIGH)
        assert a.is_attributed() is True

    def test_is_attributed_true_for_medium(self) -> None:
        a = self._make_attribution(AttributionConfidence.MEDIUM)
        assert a.is_attributed() is True

    def test_is_attributed_true_for_low(self) -> None:
        a = self._make_attribution(AttributionConfidence.LOW)
        assert a.is_attributed() is True

    def test_is_attributed_false_for_unattributed(self) -> None:
        ctx = CatalystContext(
            indicator_type="cpi",
            confidence=AttributionConfidence.UNATTRIBUTED,
            advisory_note="No match",
        )
        a = ChangeAttribution(
            indicator_type="cpi",
            direction="increased",
            confidence=AttributionConfidence.UNATTRIBUTED,
            candidates=[],
            catalyst_context=ctx,
        )
        assert a.is_attributed() is False

    def test_best_candidate_returns_first(self) -> None:
        a = self._make_attribution()
        assert a.best_candidate() is not None
        assert a.best_candidate().event_id == "e1"  # type: ignore[union-attr]

    def test_lag_days_from_best_candidate(self) -> None:
        a = self._make_attribution()
        assert a.lag_days == 1

    def test_within_lag_window(self) -> None:
        a = self._make_attribution()
        assert a.with_lag_window(5) is True
        assert a.with_lag_window(0) is False


class TestAttributionRunResult:
    def _make_unattributed(self, indicator: str) -> ChangeAttribution:
        ctx = CatalystContext(
            indicator_type=indicator,
            confidence=AttributionConfidence.UNATTRIBUTED,
            advisory_note="No match",
        )
        return ChangeAttribution(
            indicator_type=indicator,
            direction="increased",
            confidence=AttributionConfidence.UNATTRIBUTED,
            candidates=[],
            catalyst_context=ctx,
        )

    def _make_attributed(self, indicator: str) -> ChangeAttribution:
        ctx = CatalystContext(
            indicator_type=indicator,
            candidate_event_id="e1",
            candidate_event_title="Test event",
            candidate_event_type="macro_release",
            lag_days=1,
            confidence=AttributionConfidence.HIGH,
            advisory_note="Match",
        )
        return ChangeAttribution(
            indicator_type=indicator,
            direction="increased",
            confidence=AttributionConfidence.HIGH,
            candidates=[],
            catalyst_context=ctx,
        )

    def test_counts_computed_automatically(self) -> None:
        result = AttributionRunResult(
            as_of_date=datetime.now(UTC),
            attributions=[
                self._make_attributed("cpi"),
                self._make_unattributed("gdp"),
                self._make_attributed("unemployment_rate"),
            ],
        )
        assert result.total_attributed == 2
        assert result.total_unattributed == 1

    def test_empty_attributions(self) -> None:
        result = AttributionRunResult(
            as_of_date=datetime.now(UTC),
            attributions=[],
        )
        assert result.total_attributed == 0
        assert result.total_unattributed == 0

    def test_summary_context_filters_attributed(self) -> None:
        result = AttributionRunResult(
            as_of_date=datetime.now(UTC),
            attributions=[
                self._make_attributed("cpi"),
                self._make_unattributed("gdp"),
            ],
        )
        contexts = result.summary_context()
        assert len(contexts) == 1
        assert contexts[0].indicator_type == "cpi"
