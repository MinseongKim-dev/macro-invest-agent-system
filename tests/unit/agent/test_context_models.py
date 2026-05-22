"""Unit tests for agent.context.models.

Covers:
- AnalysisParameters: defaults, is_empty, as_context_hint, merge, extra=forbid, round-trip
- ConversationTurn: construction, defaults, extra=forbid, round-trip
- ConversationContext: add_turn, active_parameters merging, turns list copy safety,
  FIFO eviction, context_summary, clear, max_turns validation
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.context.models import AnalysisParameters, ConversationContext, ConversationTurn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(
    request_type: str = "SignalReviewRequest",
    response_summary: str = "ok",
    success: bool = True,
    active_parameters: AnalysisParameters | None = None,
) -> ConversationTurn:
    return ConversationTurn(
        request_type=request_type,
        request_snapshot={"request_id": "r1"},
        response_summary=response_summary,
        success=success,
        active_parameters=active_parameters or AnalysisParameters(),
    )


# ---------------------------------------------------------------------------
# AnalysisParameters — defaults
# ---------------------------------------------------------------------------


class TestAnalysisParametersDefaults:
    def test_all_fields_default_to_none(self) -> None:
        p = AnalysisParameters()
        assert p.country is None
        assert p.timeframe is None
        assert p.signal_type is None
        assert p.comparison_target is None

    def test_is_empty_true_when_all_none(self) -> None:
        assert AnalysisParameters().is_empty() is True

    def test_is_empty_false_when_country_set(self) -> None:
        assert AnalysisParameters(country="US").is_empty() is False

    def test_is_empty_false_when_timeframe_set(self) -> None:
        assert AnalysisParameters(timeframe="Q1-2026").is_empty() is False

    def test_is_empty_false_when_signal_type_set(self) -> None:
        assert AnalysisParameters(signal_type="BUY").is_empty() is False

    def test_is_empty_false_when_comparison_target_set(self) -> None:
        assert AnalysisParameters(comparison_target="prior-snap").is_empty() is False

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisParameters(unknown_field="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AnalysisParameters — as_context_hint
# ---------------------------------------------------------------------------


class TestAnalysisParametersContextHint:
    def test_empty_returns_empty_string(self) -> None:
        assert AnalysisParameters().as_context_hint() == ""

    def test_country_only(self) -> None:
        hint = AnalysisParameters(country="US").as_context_hint()
        assert "country=US" in hint

    def test_all_fields_included(self) -> None:
        p = AnalysisParameters(
            country="JP",
            timeframe="Q1-2026",
            signal_type="SELL",
            comparison_target="snap-prev",
        )
        hint = p.as_context_hint()
        assert "country=JP" in hint
        assert "timeframe=Q1-2026" in hint
        assert "signal_type=SELL" in hint
        assert "comparison_target=snap-prev" in hint

    def test_only_set_fields_appear(self) -> None:
        hint = AnalysisParameters(country="GB", signal_type="HOLD").as_context_hint()
        assert "country=GB" in hint
        assert "signal_type=HOLD" in hint
        assert "timeframe" not in hint
        assert "comparison_target" not in hint


# ---------------------------------------------------------------------------
# AnalysisParameters — merge
# ---------------------------------------------------------------------------


class TestAnalysisParametersMerge:
    def test_current_overrides_prior(self) -> None:
        prior = AnalysisParameters(country="US", timeframe="Q1-2026")
        current = AnalysisParameters(country="JP")
        merged = current.merge(prior)
        assert merged.country == "JP"

    def test_none_in_current_falls_back_to_prior(self) -> None:
        prior = AnalysisParameters(country="US", timeframe="Q1-2026")
        current = AnalysisParameters(signal_type="BUY")
        merged = current.merge(prior)
        assert merged.country == "US"
        assert merged.timeframe == "Q1-2026"
        assert merged.signal_type == "BUY"

    def test_none_in_both_stays_none(self) -> None:
        merged = AnalysisParameters().merge(AnalysisParameters())
        assert merged.country is None
        assert merged.timeframe is None

    def test_prior_does_not_override_current(self) -> None:
        prior = AnalysisParameters(country="US")
        current = AnalysisParameters(country="DE")
        merged = current.merge(prior)
        assert merged.country == "DE"

    def test_merge_returns_new_instance(self) -> None:
        prior = AnalysisParameters(country="US")
        current = AnalysisParameters(timeframe="Q2-2025")
        merged = current.merge(prior)
        assert merged is not prior
        assert merged is not current

    def test_all_fields_merged(self) -> None:
        prior = AnalysisParameters(
            country="US",
            timeframe="Q1-2026",
            signal_type="BUY",
            comparison_target="snap-A",
        )
        current = AnalysisParameters(country="JP")
        merged = current.merge(prior)
        assert merged.country == "JP"
        assert merged.timeframe == "Q1-2026"
        assert merged.signal_type == "BUY"
        assert merged.comparison_target == "snap-A"

    def test_full_current_shadows_all_prior(self) -> None:
        prior = AnalysisParameters(
            country="US", timeframe="Q1", signal_type="BUY", comparison_target="old"
        )
        current = AnalysisParameters(
            country="GB", timeframe="Q2", signal_type="SELL", comparison_target="new"
        )
        merged = current.merge(prior)
        assert merged.country == "GB"
        assert merged.timeframe == "Q2"
        assert merged.signal_type == "SELL"
        assert merged.comparison_target == "new"


# ---------------------------------------------------------------------------
# AnalysisParameters — round-trip
# ---------------------------------------------------------------------------


class TestAnalysisParametersRoundTrip:
    def test_round_trip_empty(self) -> None:
        p = AnalysisParameters()
        reparsed = AnalysisParameters.model_validate(p.model_dump())
        assert reparsed == p

    def test_round_trip_with_values(self) -> None:
        p = AnalysisParameters(country="US", timeframe="Q1-2026", signal_type="BUY")
        reparsed = AnalysisParameters.model_validate(p.model_dump())
        assert reparsed == p


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------


class TestConversationTurn:
    def test_required_fields(self) -> None:
        turn = ConversationTurn(
            request_type="SignalReviewRequest",
            request_snapshot={"request_id": "r1"},
        )
        assert turn.request_type == "SignalReviewRequest"
        assert turn.request_snapshot == {"request_id": "r1"}

    def test_defaults(self) -> None:
        turn = ConversationTurn(
            request_type="T",
            request_snapshot={},
        )
        assert turn.response_summary == ""
        assert turn.success is True
        assert turn.active_parameters == AnalysisParameters()

    def test_success_false(self) -> None:
        turn = ConversationTurn(
            request_type="T",
            request_snapshot={},
            success=False,
        )
        assert turn.success is False

    def test_active_parameters_carried(self) -> None:
        params = AnalysisParameters(country="US")
        turn = ConversationTurn(
            request_type="T",
            request_snapshot={},
            active_parameters=params,
        )
        assert turn.active_parameters.country == "US"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ConversationTurn(
                request_type="T",
                request_snapshot={},
                unknown_extra="bad",  # type: ignore[call-arg]
            )

    def test_round_trip(self) -> None:
        turn = ConversationTurn(
            request_type="MacroSnapshotSummaryRequest",
            request_snapshot={"country": "US"},
            response_summary="snapshot ok",
            success=True,
            active_parameters=AnalysisParameters(country="US"),
        )
        reparsed = ConversationTurn.model_validate(turn.model_dump())
        assert reparsed.request_type == "MacroSnapshotSummaryRequest"
        assert reparsed.response_summary == "snapshot ok"
        assert reparsed.active_parameters.country == "US"


# ---------------------------------------------------------------------------
# ConversationContext — construction
# ---------------------------------------------------------------------------


class TestConversationContextConstruction:
    def test_default_max_turns_accepted(self) -> None:
        ctx = ConversationContext()
        assert ctx.turn_count == 0

    def test_custom_max_turns(self) -> None:
        ctx = ConversationContext(max_turns=3)
        assert ctx.turn_count == 0

    def test_max_turns_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            ConversationContext(max_turns=0)

    def test_max_turns_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            ConversationContext(max_turns=-5)

    def test_initially_empty(self) -> None:
        ctx = ConversationContext()
        assert ctx.turns == []
        assert ctx.turn_count == 0


# ---------------------------------------------------------------------------
# ConversationContext — add_turn and active_parameters
# ---------------------------------------------------------------------------


class TestConversationContextAddTurn:
    def test_add_single_turn(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn())
        assert ctx.turn_count == 1

    def test_turn_is_recorded(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(request_type="SignalReviewRequest"))
        assert ctx.turns[0].request_type == "SignalReviewRequest"

    def test_active_parameters_updated_on_add(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="US")))
        assert ctx.active_parameters.country == "US"

    def test_active_parameters_merges_across_turns(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="US")))
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(signal_type="BUY")))
        # country should be inherited from the first turn
        assert ctx.active_parameters.country == "US"
        assert ctx.active_parameters.signal_type == "BUY"

    def test_active_parameters_override_in_later_turn(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="US")))
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="JP")))
        assert ctx.active_parameters.country == "JP"

    def test_active_parameters_empty_initially(self) -> None:
        ctx = ConversationContext()
        assert ctx.active_parameters.is_empty() is True

    def test_turns_returns_chronological_order(self) -> None:
        ctx = ConversationContext()
        for i in range(3):
            ctx.add_turn(_make_turn(request_type=f"Type{i}"))
        types = [t.request_type for t in ctx.turns]
        assert types == ["Type0", "Type1", "Type2"]


# ---------------------------------------------------------------------------
# ConversationContext — FIFO eviction
# ---------------------------------------------------------------------------


class TestConversationContextFIFO:
    def test_fifo_eviction_at_cap(self) -> None:
        ctx = ConversationContext(max_turns=2)
        for i in range(5):
            ctx.add_turn(_make_turn(request_type=f"Type{i}"))
        assert ctx.turn_count == 2
        assert ctx.turns[0].request_type == "Type3"
        assert ctx.turns[1].request_type == "Type4"

    def test_exactly_at_cap_no_eviction(self) -> None:
        ctx = ConversationContext(max_turns=3)
        for i in range(3):
            ctx.add_turn(_make_turn(request_type=f"Type{i}"))
        assert ctx.turn_count == 3

    def test_one_turn_cap_keeps_only_latest(self) -> None:
        ctx = ConversationContext(max_turns=1)
        ctx.add_turn(_make_turn(request_type="TypeA"))
        ctx.add_turn(_make_turn(request_type="TypeB"))
        assert ctx.turn_count == 1
        assert ctx.turns[0].request_type == "TypeB"


# ---------------------------------------------------------------------------
# ConversationContext — turns list copy safety
# ---------------------------------------------------------------------------


class TestConversationContextTurnsCopy:
    def test_mutating_turns_list_does_not_affect_context(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn())
        turns = ctx.turns
        turns.clear()
        assert ctx.turn_count == 1


# ---------------------------------------------------------------------------
# ConversationContext — context_summary
# ---------------------------------------------------------------------------


class TestConversationContextSummary:
    def test_empty_context_returns_empty_string(self) -> None:
        ctx = ConversationContext()
        assert ctx.context_summary() == ""

    def test_summary_includes_active_parameters(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="US")))
        summary = ctx.context_summary()
        assert "country=US" in summary

    def test_summary_includes_recent_turn_type(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(request_type="SignalReviewRequest", response_summary="3 signals"))
        summary = ctx.context_summary()
        assert "SignalReviewRequest" in summary

    def test_summary_includes_turn_status_ok(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(success=True))
        summary = ctx.context_summary()
        assert "ok" in summary

    def test_summary_includes_turn_status_failed(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(success=False))
        summary = ctx.context_summary()
        assert "failed" in summary

    def test_summary_truncates_to_three_recent_turns(self) -> None:
        ctx = ConversationContext(max_turns=10)
        for i in range(6):
            ctx.add_turn(_make_turn(request_type=f"Type{i}", response_summary=f"summary-{i}"))
        summary = ctx.context_summary()
        # Only last 3 turn summaries should appear: Type3, Type4, Type5
        assert "Type5" in summary
        assert "Type0" not in summary

    def test_summary_is_string(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn())
        assert isinstance(ctx.context_summary(), str)


# ---------------------------------------------------------------------------
# ConversationContext — clear
# ---------------------------------------------------------------------------


class TestConversationContextClear:
    def test_clear_removes_all_turns(self) -> None:
        ctx = ConversationContext()
        for _ in range(3):
            ctx.add_turn(_make_turn())
        ctx.clear()
        assert ctx.turn_count == 0
        assert ctx.turns == []

    def test_clear_resets_active_parameters(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(active_parameters=AnalysisParameters(country="US")))
        ctx.clear()
        assert ctx.active_parameters.is_empty() is True

    def test_clear_on_empty_context_is_safe(self) -> None:
        ctx = ConversationContext()
        ctx.clear()  # Should not raise
        assert ctx.turn_count == 0

    def test_add_turn_after_clear(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(_make_turn(request_type="BeforeClear"))
        ctx.clear()
        ctx.add_turn(_make_turn(request_type="AfterClear"))
        assert ctx.turn_count == 1
        assert ctx.turns[0].request_type == "AfterClear"
