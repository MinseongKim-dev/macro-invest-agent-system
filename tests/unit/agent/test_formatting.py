"""Unit tests for agent.formatting.summaries and agent.formatting.errors.

Covers:
- dominant_signal_type: all signal count combinations
- format_signal_review_summary: field inclusion, content correctness
- format_snapshot_summary: timestamp formatting, missing timestamp
- format_signal_review_error: user-facing wording
- format_snapshot_summary_error: user-facing wording
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.agent.formatting.errors import format_signal_review_error, format_snapshot_summary_error
from src.agent.formatting.summaries import (
    dominant_signal_type,
    format_signal_review_summary,
    format_snapshot_summary,
)
from src.agent.mcp.schemas.get_macro_features import GetMacroSnapshotResponse
from src.agent.mcp.schemas.run_signal_engine import RunSignalEngineResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine_response(
    *,
    buy: int = 0,
    sell: int = 0,
    hold: int = 0,
    engine_run_id: str = "run-001",
    execution_time_ms: float = 10.0,
) -> RunSignalEngineResponse:
    total = buy + sell + hold
    return RunSignalEngineResponse(
        request_id="req-001",
        success=True,
        engine_run_id=engine_run_id,
        signals_generated=total,
        buy_signals=buy,
        sell_signals=sell,
        hold_signals=hold,
        execution_time_ms=execution_time_ms,
    )


def _snapshot_response(
    *,
    features_count: int = 5,
    snapshot_timestamp: datetime | None = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
) -> GetMacroSnapshotResponse:
    return GetMacroSnapshotResponse(
        request_id="req-002",
        success=True,
        features_count=features_count,
        snapshot_timestamp=snapshot_timestamp,
    )


# ---------------------------------------------------------------------------
# dominant_signal_type
# ---------------------------------------------------------------------------


class TestDominantSignalType:
    """Tests for dominant_signal_type helper."""

    def test_returns_buy_when_buy_highest(self) -> None:
        resp = _engine_response(buy=3, sell=1, hold=1)
        assert dominant_signal_type(resp) == "BUY"

    def test_returns_sell_when_sell_highest(self) -> None:
        resp = _engine_response(buy=0, sell=2, hold=1)
        assert dominant_signal_type(resp) == "SELL"

    def test_returns_hold_when_hold_highest(self) -> None:
        resp = _engine_response(buy=1, sell=1, hold=3)
        assert dominant_signal_type(resp) == "HOLD"

    def test_returns_none_when_all_zero(self) -> None:
        resp = _engine_response(buy=0, sell=0, hold=0)
        assert dominant_signal_type(resp) == "none"

    def test_tie_broken_buy_over_sell(self) -> None:
        resp = _engine_response(buy=2, sell=2, hold=0)
        assert dominant_signal_type(resp) == "BUY"

    def test_tie_broken_buy_over_hold(self) -> None:
        resp = _engine_response(buy=2, sell=0, hold=2)
        assert dominant_signal_type(resp) == "BUY"

    def test_tie_broken_sell_over_hold(self) -> None:
        resp = _engine_response(buy=0, sell=2, hold=2)
        assert dominant_signal_type(resp) == "SELL"

    def test_single_buy_signal(self) -> None:
        resp = _engine_response(buy=1)
        assert dominant_signal_type(resp) == "BUY"


# ---------------------------------------------------------------------------
# format_signal_review_summary
# ---------------------------------------------------------------------------


class TestFormatSignalReviewSummary:
    """Tests for format_signal_review_summary."""

    def test_contains_signal_ids(self) -> None:
        resp = _engine_response(buy=1)
        result = format_signal_review_summary(resp, ["bull_market", "hold_neutral"], "US")
        assert "bull_market" in result
        assert "hold_neutral" in result

    def test_contains_country(self) -> None:
        resp = _engine_response(buy=1)
        result = format_signal_review_summary(resp, ["bull_market"], "JP")
        assert "JP" in result

    def test_contains_signal_counts(self) -> None:
        resp = _engine_response(buy=2, sell=1, hold=3)
        result = format_signal_review_summary(resp, ["s1"], "US")
        assert "BUY=2" in result
        assert "SELL=1" in result
        assert "HOLD=3" in result

    def test_contains_engine_run_id(self) -> None:
        resp = _engine_response(buy=1, engine_run_id="run-xyz-999")
        result = format_signal_review_summary(resp, ["s1"], "US")
        assert "run-xyz-999" in result

    def test_contains_execution_time(self) -> None:
        resp = _engine_response(buy=1, execution_time_ms=42.5)
        result = format_signal_review_summary(resp, ["s1"], "US")
        assert "42.5ms" in result

    def test_dominant_direction_included(self) -> None:
        resp = _engine_response(buy=3, sell=1, hold=0)
        result = format_signal_review_summary(resp, ["s1"], "US")
        assert "BUY" in result

    def test_no_signals_shows_none_direction(self) -> None:
        resp = _engine_response(buy=0, sell=0, hold=0)
        result = format_signal_review_summary(resp, ["s1"], "US")
        assert "none" in result

    def test_deterministic_output(self) -> None:
        resp = _engine_response(buy=1, sell=1, hold=1, engine_run_id="r1", execution_time_ms=5.0)
        ids = ["alpha", "beta"]
        result1 = format_signal_review_summary(resp, ids, "US")
        result2 = format_signal_review_summary(resp, ids, "US")
        assert result1 == result2


# ---------------------------------------------------------------------------
# format_snapshot_summary
# ---------------------------------------------------------------------------


class TestFormatSnapshotSummary:
    """Tests for format_snapshot_summary."""

    def test_contains_country(self) -> None:
        resp = _snapshot_response()
        result = format_snapshot_summary(resp, "DE")
        assert "DE" in result

    def test_contains_features_count(self) -> None:
        resp = _snapshot_response(features_count=7)
        result = format_snapshot_summary(resp, "US")
        assert "7" in result

    def test_contains_formatted_timestamp(self) -> None:
        ts = datetime(2026, 3, 5, 8, 30, 0, tzinfo=UTC)
        resp = _snapshot_response(snapshot_timestamp=ts)
        result = format_snapshot_summary(resp, "US")
        assert "2026-03-05T08:30:00Z" in result

    def test_none_timestamp_shows_unknown(self) -> None:
        resp = _snapshot_response(snapshot_timestamp=None)
        result = format_snapshot_summary(resp, "US")
        assert "unknown" in result

    def test_deterministic_output(self) -> None:
        resp = _snapshot_response(features_count=3)
        result1 = format_snapshot_summary(resp, "US")
        result2 = format_snapshot_summary(resp, "US")
        assert result1 == result2


# ---------------------------------------------------------------------------
# format_signal_review_error
# ---------------------------------------------------------------------------


class TestFormatSignalReviewError:
    """Tests for format_signal_review_error."""

    def test_contains_request_id(self) -> None:
        result = format_signal_review_error("some error", "req-99")
        assert "req-99" in result

    def test_contains_raw_error_detail(self) -> None:
        result = format_signal_review_error("unknown signal: foo", "req-1")
        assert "unknown signal: foo" in result

    def test_message_is_non_empty(self) -> None:
        result = format_signal_review_error("e", "r")
        assert len(result) > 0

    def test_deterministic(self) -> None:
        r1 = format_signal_review_error("err", "req-1")
        r2 = format_signal_review_error("err", "req-1")
        assert r1 == r2


# ---------------------------------------------------------------------------
# format_snapshot_summary_error
# ---------------------------------------------------------------------------


class TestFormatSnapshotSummaryError:
    """Tests for format_snapshot_summary_error."""

    def test_contains_request_id(self) -> None:
        result = format_snapshot_summary_error("feed offline", "req-55", "AU")
        assert "req-55" in result

    def test_contains_country(self) -> None:
        result = format_snapshot_summary_error("feed offline", "req-55", "AU")
        assert "AU" in result

    def test_contains_raw_error_detail(self) -> None:
        result = format_snapshot_summary_error("feed offline", "req-55", "AU")
        assert "feed offline" in result

    def test_message_is_non_empty(self) -> None:
        result = format_snapshot_summary_error("e", "r", "US")
        assert len(result) > 0

    def test_deterministic(self) -> None:
        r1 = format_snapshot_summary_error("err", "req-1", "US")
        r2 = format_snapshot_summary_error("err", "req-1", "US")
        assert r1 == r2
