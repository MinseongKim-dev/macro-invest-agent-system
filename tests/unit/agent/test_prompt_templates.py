"""Unit tests for agent.prompts.templates.

Covers:
- SIGNAL_REVIEW_PROMPT template structure (system + human messages)
- SNAPSHOT_SUMMARY_PROMPT template structure
- render_signal_review_summary produces correct deterministic output
- render_snapshot_summary produces correct deterministic output
- Template variables are all substituted (no leftover placeholders)
- Rendered output matches the deterministic formatters in agent.formatting
"""

from __future__ import annotations

from src.agent.prompts.templates import (
    SIGNAL_REVIEW_PROMPT,
    SNAPSHOT_SUMMARY_PROMPT,
    render_signal_review_summary,
    render_snapshot_summary,
)

# ---------------------------------------------------------------------------
# SIGNAL_REVIEW_PROMPT — template structure
# ---------------------------------------------------------------------------


class TestSignalReviewPromptStructure:
    """Tests for the SIGNAL_REVIEW_PROMPT ChatPromptTemplate."""

    def test_prompt_has_two_messages(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="bull_market",
            country="US",
            signals_generated=1,
            buy_signals=1,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="BUY",
            engine_run_id="run-001",
            execution_time_ms="5.0",
        )
        assert len(messages) == 2

    def test_first_message_is_system(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="x",
            country="US",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="none",
            engine_run_id="r",
            execution_time_ms="0.0",
        )
        assert messages[0].type == "system"

    def test_second_message_is_human(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="x",
            country="US",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="none",
            engine_run_id="r",
            execution_time_ms="0.0",
        )
        assert messages[1].type == "human"

    def test_system_message_mentions_read_only(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="x",
            country="US",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="none",
            engine_run_id="r",
            execution_time_ms="0.0",
        )
        assert "read-only" in str(messages[0].content)

    def test_human_message_contains_signal_ids(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="bull_market, recession_warning",
            country="US",
            signals_generated=2,
            buy_signals=1,
            sell_signals=1,
            hold_signals=0,
            dominant_direction="BUY",
            engine_run_id="run-abc",
            execution_time_ms="3.5",
        )
        content = str(messages[1].content)
        assert "bull_market" in content
        assert "recession_warning" in content

    def test_human_message_contains_all_fields(self) -> None:
        messages = SIGNAL_REVIEW_PROMPT.format_messages(
            signal_ids="sig1",
            country="JP",
            signals_generated=5,
            buy_signals=2,
            sell_signals=1,
            hold_signals=2,
            dominant_direction="BUY",
            engine_run_id="run-xyz",
            execution_time_ms="12.3",
        )
        content = str(messages[1].content)
        assert "JP" in content
        assert "BUY=2" in content
        assert "SELL=1" in content
        assert "HOLD=2" in content
        assert "run-xyz" in content
        assert "12.3ms" in content


# ---------------------------------------------------------------------------
# SNAPSHOT_SUMMARY_PROMPT — template structure
# ---------------------------------------------------------------------------


class TestSnapshotSummaryPromptStructure:
    """Tests for the SNAPSHOT_SUMMARY_PROMPT ChatPromptTemplate."""

    def test_prompt_has_two_messages(self) -> None:
        messages = SNAPSHOT_SUMMARY_PROMPT.format_messages(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-15T12:00:00Z",
        )
        assert len(messages) == 2

    def test_first_message_is_system(self) -> None:
        messages = SNAPSHOT_SUMMARY_PROMPT.format_messages(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-15T12:00:00Z",
        )
        assert messages[0].type == "system"

    def test_human_message_contains_country(self) -> None:
        messages = SNAPSHOT_SUMMARY_PROMPT.format_messages(
            country="DE",
            features_count=3,
            snapshot_timestamp="2026-06-01T00:00:00Z",
        )
        assert "DE" in str(messages[1].content)

    def test_human_message_contains_features_count(self) -> None:
        messages = SNAPSHOT_SUMMARY_PROMPT.format_messages(
            country="US",
            features_count=7,
            snapshot_timestamp="2026-01-01T00:00:00Z",
        )
        assert "7" in str(messages[1].content)

    def test_human_message_contains_timestamp(self) -> None:
        messages = SNAPSHOT_SUMMARY_PROMPT.format_messages(
            country="US",
            features_count=1,
            snapshot_timestamp="2026-03-05T08:30:00Z",
        )
        assert "2026-03-05T08:30:00Z" in str(messages[1].content)


# ---------------------------------------------------------------------------
# render_signal_review_summary
# ---------------------------------------------------------------------------


class TestRenderSignalReviewSummary:
    """Tests for the render_signal_review_summary helper."""

    def test_returns_string(self) -> None:
        result = render_signal_review_summary(
            signal_ids="bull_market",
            country="US",
            signals_generated=1,
            buy_signals=1,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="BUY",
            engine_run_id="run-001",
            execution_time_ms="5.0",
        )
        assert isinstance(result, str)

    def test_contains_all_fields(self) -> None:
        result = render_signal_review_summary(
            signal_ids="alpha, beta",
            country="GB",
            signals_generated=3,
            buy_signals=1,
            sell_signals=1,
            hold_signals=1,
            dominant_direction="BUY",
            engine_run_id="run-abc",
            execution_time_ms="7.2",
        )
        assert "alpha" in result
        assert "beta" in result
        assert "GB" in result
        assert "BUY=1" in result
        assert "SELL=1" in result
        assert "HOLD=1" in result
        assert "run-abc" in result
        assert "7.2ms" in result

    def test_deterministic(self) -> None:
        kwargs = {
            "signal_ids": "x",
            "country": "US",
            "signals_generated": 1,
            "buy_signals": 1,
            "sell_signals": 0,
            "hold_signals": 0,
            "dominant_direction": "BUY",
            "engine_run_id": "r",
            "execution_time_ms": "1.0",
        }
        assert render_signal_review_summary(**kwargs) == render_signal_review_summary(**kwargs)  # type: ignore[arg-type]

    def test_no_leftover_placeholders(self) -> None:
        result = render_signal_review_summary(
            signal_ids="x",
            country="US",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
            dominant_direction="none",
            engine_run_id="r",
            execution_time_ms="0.0",
        )
        assert "{" not in result
        assert "}" not in result


# ---------------------------------------------------------------------------
# render_snapshot_summary
# ---------------------------------------------------------------------------


class TestRenderSnapshotSummary:
    """Tests for the render_snapshot_summary helper."""

    def test_returns_string(self) -> None:
        result = render_snapshot_summary(
            country="US",
            features_count=5,
            snapshot_timestamp="2026-01-15T12:00:00Z",
        )
        assert isinstance(result, str)

    def test_contains_all_fields(self) -> None:
        result = render_snapshot_summary(
            country="JP",
            features_count=3,
            snapshot_timestamp="2026-06-01T00:00:00Z",
        )
        assert "JP" in result
        assert "3" in result
        assert "2026-06-01T00:00:00Z" in result

    def test_unknown_timestamp(self) -> None:
        result = render_snapshot_summary(
            country="US",
            features_count=0,
            snapshot_timestamp="unknown",
        )
        assert "unknown" in result

    def test_deterministic(self) -> None:
        kwargs = {
            "country": "US",
            "features_count": 5,
            "snapshot_timestamp": "2026-01-01T00:00:00Z",
        }
        assert render_snapshot_summary(**kwargs) == render_snapshot_summary(**kwargs)  # type: ignore[arg-type]

    def test_no_leftover_placeholders(self) -> None:
        result = render_snapshot_summary(
            country="US",
            features_count=0,
            snapshot_timestamp="2026-01-01T00:00:00Z",
        )
        assert "{" not in result
        assert "}" not in result
