"""Eval: prompt template regression — rendered output contains expected substrings.

Verifies that each render_* function produces output containing the key
factual fields and does not hallucinate unexpected fields.
"""

from __future__ import annotations

from agent.prompts.templates import (
    render_signal_review_summary,
    render_snapshot_comparison_summary,
    render_snapshot_summary,
)


class TestSignalReviewPromptTemplate:
    """render_signal_review_summary regression tests."""

    def _render(self, **overrides: object) -> str:
        defaults: dict[str, object] = {
            "signal_ids": "bull_market, bear_market",
            "country": "US",
            "signals_generated": 3,
            "buy_signals": 2,
            "sell_signals": 1,
            "hold_signals": 0,
            "dominant_direction": "BUY",
            "engine_run_id": "eng-001",
            "execution_time_ms": "12.5",
            "context_summary": "",
        }
        defaults.update(overrides)
        return render_signal_review_summary(**defaults)  # type: ignore[arg-type]

    def test_contains_signal_ids(self) -> None:
        assert "bull_market" in self._render()

    def test_contains_country(self) -> None:
        assert "US" in self._render()

    def test_contains_signals_generated_count(self) -> None:
        assert "3" in self._render()

    def test_contains_buy_count(self) -> None:
        assert "2" in self._render()

    def test_contains_sell_count(self) -> None:
        assert "1" in self._render()

    def test_contains_dominant_direction(self) -> None:
        assert "BUY" in self._render()

    def test_contains_engine_run_id(self) -> None:
        assert "eng-001" in self._render()

    def test_contains_execution_time(self) -> None:
        assert "12.5" in self._render()

    def test_does_not_contain_hallucinated_field(self) -> None:
        output = self._render()
        assert "recommendation" not in output.lower()
        assert "advice" not in output.lower()
        assert "invest" not in output.lower()


class TestSnapshotSummaryPromptTemplate:
    """render_snapshot_summary regression tests."""

    def _render(self, **overrides: object) -> str:
        defaults: dict[str, object] = {
            "country": "US",
            "features_count": 5,
            "snapshot_timestamp": "2026-01-01T00:00:00Z",
            "context_summary": "",
        }
        defaults.update(overrides)
        return render_snapshot_summary(**defaults)  # type: ignore[arg-type]

    def test_contains_country(self) -> None:
        assert "US" in self._render()

    def test_contains_features_count(self) -> None:
        assert "5" in self._render()

    def test_contains_timestamp(self) -> None:
        assert "2026-01-01" in self._render()

    def test_does_not_contain_hallucinated_field(self) -> None:
        output = self._render()
        assert "recommendation" not in output.lower()

    def test_different_country_renders_correctly(self) -> None:
        output = self._render(country="DE")
        assert "DE" in output
        assert "US" not in output


class TestSnapshotComparisonPromptTemplate:
    """render_snapshot_comparison_summary regression tests."""

    def _render(self, **overrides: object) -> str:
        defaults: dict[str, object] = {
            "country": "US",
            "prior_snapshot_label": "Q1-2026",
            "changed_count": 3,
            "unchanged_count": 2,
            "no_prior_count": 0,
            "context_summary": "",
        }
        defaults.update(overrides)
        return render_snapshot_comparison_summary(**defaults)  # type: ignore[arg-type]

    def test_contains_country(self) -> None:
        assert "US" in self._render()

    def test_contains_prior_label(self) -> None:
        assert "Q1-2026" in self._render()

    def test_contains_changed_count(self) -> None:
        assert "3" in self._render()

    def test_contains_unchanged_count(self) -> None:
        assert "2" in self._render()

    def test_no_prior_suffix_appears_when_nonzero(self) -> None:
        output = self._render(no_prior_count=1)
        assert "no prior" in output.lower()

    def test_no_prior_suffix_absent_when_zero(self) -> None:
        output = self._render(no_prior_count=0)
        assert "no prior" not in output.lower()

    def test_does_not_contain_hallucinated_field(self) -> None:
        output = self._render()
        assert "recommendation" not in output.lower()
        assert "advice" not in output.lower()
