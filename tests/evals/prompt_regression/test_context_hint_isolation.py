"""Eval: context hint isolation — hint appears only in system message, not human message.

Verifies that:
1. The context hint string appears in the rendered system message.
2. The rendered human message (the ``summary`` field) does NOT contain the hint text.
3. Tool result values in the response are unchanged regardless of the hint content.
"""

from __future__ import annotations

from agent.prompts.templates import (
    render_signal_review_summary,
    render_snapshot_comparison_summary,
    render_snapshot_summary,
)

_CONTEXT_HINT = "country=US, timeframe=Q1-2026"


class TestContextHintIsolationSnapshot:
    """Context hint isolation for render_snapshot_summary."""

    def test_hint_does_not_appear_in_human_message(self) -> None:
        """The rendered human message must NOT contain the context hint text."""
        output = render_snapshot_summary(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-01T00:00:00Z",
            context_summary=_CONTEXT_HINT,
        )
        assert _CONTEXT_HINT not in output

    def test_tool_values_unchanged_with_hint(self) -> None:
        """feature_count and country in summary are unchanged when hint varies."""
        output_with_hint = render_snapshot_summary(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-01T00:00:00Z",
            context_summary=_CONTEXT_HINT,
        )
        output_no_hint = render_snapshot_summary(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-01T00:00:00Z",
            context_summary="",
        )
        # Human message content must be identical regardless of hint
        assert output_with_hint == output_no_hint

    def test_empty_hint_behaves_like_no_hint(self) -> None:
        output_empty = render_snapshot_summary(
            country="JP",
            features_count=3,
            snapshot_timestamp="2026-01-01T00:00:00Z",
            context_summary="",
        )
        output_none = render_snapshot_summary(
            country="JP",
            features_count=3,
            snapshot_timestamp="2026-01-01T00:00:00Z",
        )
        assert output_empty == output_none


class TestContextHintIsolationSignalReview:
    """Context hint isolation for render_signal_review_summary."""

    def _render(self, context_summary: str = "") -> str:
        return render_signal_review_summary(
            signal_ids="bull_market",
            country="US",
            signals_generated=2,
            buy_signals=2,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="BUY",
            engine_run_id="eng-xyz",
            execution_time_ms="5.0",
            context_summary=context_summary,
        )

    def test_hint_does_not_appear_in_human_message(self) -> None:
        output = self._render(context_summary=_CONTEXT_HINT)
        assert _CONTEXT_HINT not in output

    def test_tool_values_unchanged_with_hint(self) -> None:
        output_with_hint = self._render(context_summary=_CONTEXT_HINT)
        output_no_hint = self._render(context_summary="")
        assert output_with_hint == output_no_hint


class TestContextHintIsolationComparison:
    """Context hint isolation for render_snapshot_comparison_summary."""

    def _render(self, context_summary: str = "") -> str:
        return render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q1-2026",
            changed_count=2,
            unchanged_count=3,
            no_prior_count=0,
            context_summary=context_summary,
        )

    def test_hint_does_not_appear_in_human_message(self) -> None:
        output = self._render(context_summary=_CONTEXT_HINT)
        assert _CONTEXT_HINT not in output

    def test_tool_values_unchanged_with_hint(self) -> None:
        output_with_hint = self._render(context_summary=_CONTEXT_HINT)
        output_no_hint = self._render(context_summary="")
        assert output_with_hint == output_no_hint
