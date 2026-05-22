"""Unit tests for agent/schemas.py — validators and schema constraints.

Covers:
- SignalReviewRequest.signal_ids validator (empty list, empty string IDs)
- AgentResponse.model_validator (error_message required when success=False)
- SignalReviewResponse field constraints (ge=0)
- MacroSnapshotSummaryResponse field constraints (ge=0)
- Schema round-trip validity (model_dump → model_validate)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.schemas import (
    AgentResponse,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
)

# ---------------------------------------------------------------------------
# SignalReviewRequest validators
# ---------------------------------------------------------------------------


class TestSignalReviewRequestValidators:
    """Tests for SignalReviewRequest field validators."""

    def test_valid_signal_ids_accepted(self) -> None:
        req = SignalReviewRequest(request_id="r1", signal_ids=["bull_market"])
        assert req.signal_ids == ["bull_market"]

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="r1", signal_ids=[])

    def test_empty_string_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="r1", signal_ids=[""])

    def test_whitespace_only_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="r1", signal_ids=["   "])

    def test_multiple_valid_ids_accepted(self) -> None:
        req = SignalReviewRequest(request_id="r1", signal_ids=["a", "b", "c"])
        assert len(req.signal_ids) == 3

    def test_request_id_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="", signal_ids=["bull_market"])


# ---------------------------------------------------------------------------
# AgentResponse model_validator
# ---------------------------------------------------------------------------


class TestAgentResponseModelValidator:
    """Tests for AgentResponse.error_message_present_on_failure validator."""

    def test_success_true_without_error_message_passes(self) -> None:
        resp = AgentResponse(request_id="r1", success=True)
        assert resp.success is True
        assert resp.error_message is None

    def test_failure_with_error_message_passes(self) -> None:
        resp = AgentResponse(
            request_id="r1",
            success=False,
            error_message="something went wrong",
        )
        assert resp.success is False
        assert resp.error_message is not None

    def test_failure_without_error_message_raises(self) -> None:
        with pytest.raises(ValidationError, match="error_message must be set"):
            AgentResponse(request_id="r1", success=False)


# ---------------------------------------------------------------------------
# SignalReviewResponse field constraints
# ---------------------------------------------------------------------------


class TestSignalReviewResponseConstraints:
    """Tests for SignalReviewResponse field ge=0 constraints."""

    def test_valid_response_accepts_zero_counts(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
            execution_time_ms=0.0,
        )
        assert resp.signals_generated == 0

    def test_negative_signals_generated_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewResponse(
                request_id="r1",
                success=True,
                summary="ok",
                signals_generated=-1,
            )

    def test_negative_buy_signals_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewResponse(
                request_id="r1",
                success=True,
                summary="ok",
                buy_signals=-1,
            )

    def test_negative_execution_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewResponse(
                request_id="r1",
                success=True,
                summary="ok",
                execution_time_ms=-0.1,
            )

    def test_error_response_defaults_are_valid(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=False,
            error_message="tool failed",
        )
        assert resp.signals_generated == 0
        assert resp.buy_signals == 0
        assert resp.execution_time_ms == 0.0


# ---------------------------------------------------------------------------
# MacroSnapshotSummaryResponse field constraints
# ---------------------------------------------------------------------------


class TestMacroSnapshotSummaryResponseConstraints:
    """Tests for MacroSnapshotSummaryResponse field ge=0 constraints."""

    def test_negative_features_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroSnapshotSummaryResponse(
                request_id="r1",
                success=True,
                summary="ok",
                features_count=-1,
            )

    def test_zero_features_count_accepted(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r1",
            success=True,
            summary="ok",
            features_count=0,
        )
        assert resp.features_count == 0

    def test_error_response_defaults_are_valid(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r1",
            success=False,
            error_message="snapshot unavailable",
            country="US",
        )
        assert resp.features_count == 0
        assert resp.snapshot_timestamp is None


# ---------------------------------------------------------------------------
# Schema round-trip
# ---------------------------------------------------------------------------


class TestSchemaRoundTrip:
    """Tests that model_dump → model_validate round-trips preserve all values."""

    def test_signal_review_response_round_trip_success(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="all good",
            engine_run_id="run-abc",
            signals_generated=3,
            buy_signals=2,
            sell_signals=1,
            hold_signals=0,
            execution_time_ms=5.5,
        )
        reparsed = SignalReviewResponse.model_validate(resp.model_dump())
        assert reparsed.engine_run_id == "run-abc"
        assert reparsed.buy_signals == 2

    def test_signal_review_response_round_trip_failure(self) -> None:
        resp = SignalReviewResponse(
            request_id="r2",
            success=False,
            error_message="engine failed",
        )
        reparsed = SignalReviewResponse.model_validate(resp.model_dump())
        assert reparsed.success is False
        assert reparsed.error_message == "engine failed"

    def test_snapshot_summary_response_round_trip(self) -> None:
        from datetime import UTC, datetime

        resp = MacroSnapshotSummaryResponse(
            request_id="r3",
            success=True,
            summary="snapshot ok",
            country="DE",
            features_count=7,
            snapshot_timestamp=datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC),
        )
        reparsed = MacroSnapshotSummaryResponse.model_validate(resp.model_dump())
        assert reparsed.country == "DE"
        assert reparsed.features_count == 7
