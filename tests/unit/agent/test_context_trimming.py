"""Unit tests for agent.context.trimming.

Covers:
- trim_to_max_turns: keeps up to max_turns newest turns, raises on invalid max_turns
- keep_successful_only: filters to successful turns only
- extract_recent_summaries: returns last N non-empty summaries, raises on invalid limit
"""

from __future__ import annotations

import pytest

from src.agent.context.models import AnalysisParameters, ConversationTurn
from src.agent.context.trimming import (
    extract_recent_summaries,
    keep_successful_only,
    trim_to_max_turns,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _turn(
    request_type: str = "T",
    response_summary: str = "ok",
    success: bool = True,
) -> ConversationTurn:
    return ConversationTurn(
        request_type=request_type,
        request_snapshot={},
        response_summary=response_summary,
        success=success,
        active_parameters=AnalysisParameters(),
    )


def _turns(n: int) -> list[ConversationTurn]:
    return [_turn(request_type=f"Type{i}", response_summary=f"summary-{i}") for i in range(n)]


# ---------------------------------------------------------------------------
# trim_to_max_turns
# ---------------------------------------------------------------------------


class TestTrimToMaxTurns:
    def test_returns_same_list_when_under_cap(self) -> None:
        turns = _turns(3)
        result = trim_to_max_turns(turns, max_turns=5)
        assert result is turns

    def test_returns_same_list_exactly_at_cap(self) -> None:
        turns = _turns(3)
        result = trim_to_max_turns(turns, max_turns=3)
        assert result is turns

    def test_trims_oldest_when_over_cap(self) -> None:
        turns = _turns(5)
        result = trim_to_max_turns(turns, max_turns=3)
        assert len(result) == 3
        # The 3 most recent (newest-last) should be kept.
        assert result[0].request_type == "Type2"
        assert result[1].request_type == "Type3"
        assert result[2].request_type == "Type4"

    def test_trims_to_one(self) -> None:
        turns = _turns(5)
        result = trim_to_max_turns(turns, max_turns=1)
        assert len(result) == 1
        assert result[0].request_type == "Type4"

    def test_empty_list_stays_empty(self) -> None:
        result = trim_to_max_turns([], max_turns=5)
        assert result == []

    def test_does_not_mutate_input(self) -> None:
        turns = _turns(5)
        original_len = len(turns)
        trim_to_max_turns(turns, max_turns=2)
        assert len(turns) == original_len

    def test_raises_on_zero_max_turns(self) -> None:
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            trim_to_max_turns(_turns(3), max_turns=0)

    def test_raises_on_negative_max_turns(self) -> None:
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            trim_to_max_turns(_turns(3), max_turns=-1)

    def test_result_is_new_list_when_trimmed(self) -> None:
        turns = _turns(5)
        result = trim_to_max_turns(turns, max_turns=2)
        assert result is not turns


# ---------------------------------------------------------------------------
# keep_successful_only
# ---------------------------------------------------------------------------


class TestKeepSuccessfulOnly:
    def test_all_successful(self) -> None:
        turns = [_turn(success=True) for _ in range(3)]
        result = keep_successful_only(turns)
        assert len(result) == 3

    def test_all_failed(self) -> None:
        turns = [_turn(success=False) for _ in range(3)]
        result = keep_successful_only(turns)
        assert result == []

    def test_mixed(self) -> None:
        turns = [
            _turn(request_type="A", success=True),
            _turn(request_type="B", success=False),
            _turn(request_type="C", success=True),
        ]
        result = keep_successful_only(turns)
        assert len(result) == 2
        assert result[0].request_type == "A"
        assert result[1].request_type == "C"

    def test_empty_list(self) -> None:
        result = keep_successful_only([])
        assert result == []

    def test_does_not_mutate_input(self) -> None:
        turns = [
            _turn(success=True),
            _turn(success=False),
        ]
        original_len = len(turns)
        keep_successful_only(turns)
        assert len(turns) == original_len

    def test_returns_new_list(self) -> None:
        turns = [_turn(success=True)]
        result = keep_successful_only(turns)
        assert result is not turns


# ---------------------------------------------------------------------------
# extract_recent_summaries
# ---------------------------------------------------------------------------


class TestExtractRecentSummaries:
    def test_returns_last_n_summaries(self) -> None:
        turns = [_turn(response_summary=f"s{i}") for i in range(5)]
        result = extract_recent_summaries(turns, limit=3)
        assert result == ["s2", "s3", "s4"]

    def test_skips_empty_summaries(self) -> None:
        turns = [
            _turn(response_summary=""),
            _turn(response_summary="non-empty"),
            _turn(response_summary=""),
        ]
        result = extract_recent_summaries(turns, limit=3)
        assert result == ["non-empty"]

    def test_returns_fewer_when_fewer_available(self) -> None:
        turns = [_turn(response_summary="only-one")]
        result = extract_recent_summaries(turns, limit=5)
        assert result == ["only-one"]

    def test_empty_list_returns_empty(self) -> None:
        result = extract_recent_summaries([], limit=3)
        assert result == []

    def test_default_limit_is_three(self) -> None:
        turns = [_turn(response_summary=f"s{i}") for i in range(10)]
        result = extract_recent_summaries(turns)
        assert len(result) == 3
        assert result == ["s7", "s8", "s9"]

    def test_limit_one(self) -> None:
        turns = [_turn(response_summary=f"s{i}") for i in range(5)]
        result = extract_recent_summaries(turns, limit=1)
        assert result == ["s4"]

    def test_raises_on_zero_limit(self) -> None:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            extract_recent_summaries(_turns(3), limit=0)

    def test_raises_on_negative_limit(self) -> None:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            extract_recent_summaries(_turns(3), limit=-1)

    def test_does_not_mutate_input(self) -> None:
        turns = [_turn(response_summary=f"s{i}") for i in range(5)]
        original_len = len(turns)
        extract_recent_summaries(turns, limit=2)
        assert len(turns) == original_len

    def test_all_empty_summaries_returns_empty(self) -> None:
        turns = [_turn(response_summary="") for _ in range(4)]
        result = extract_recent_summaries(turns, limit=3)
        assert result == []
