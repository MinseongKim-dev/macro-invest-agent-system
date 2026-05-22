"""Unit tests for agent.runtime.output_validation.

Covers:
- validate_agent_response round-trip on success and failure
- validate_signal_review_response domain invariant check
- validate_snapshot_summary_response round-trip
- validate_runtime_result envelope + inner validation
- OutputValidationError attributes
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agent.runtime.agent_runtime import AgentOperation, AgentRuntimeResult
from src.agent.runtime.output_validation import (
    OutputValidationError,
    validate_agent_response,
    validate_runtime_result,
    validate_signal_review_response,
    validate_snapshot_summary_response,
)
from src.agent.schemas import (
    AgentResponse,
    MacroSnapshotSummaryResponse,
    SignalReviewResponse,
)

# ---------------------------------------------------------------------------
# validate_agent_response
# ---------------------------------------------------------------------------


class TestValidateAgentResponse:
    """Tests for validate_agent_response."""

    def test_success_response_passes(self) -> None:
        resp = AgentResponse(request_id="r1", success=True, summary="ok")
        assert validate_agent_response(resp) is resp

    def test_failure_response_passes(self) -> None:
        resp = AgentResponse(
            request_id="r1",
            success=False,
            error_message="failed",
        )
        assert validate_agent_response(resp) is resp

    def test_returns_same_object(self) -> None:
        resp = AgentResponse(request_id="r1", success=True)
        validated = validate_agent_response(resp)
        assert validated is resp


# ---------------------------------------------------------------------------
# validate_signal_review_response
# ---------------------------------------------------------------------------


class TestValidateSignalReviewResponse:
    """Tests for validate_signal_review_response."""

    def test_valid_success_response_passes(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
            signals_generated=3,
            buy_signals=1,
            sell_signals=1,
            hold_signals=1,
            execution_time_ms=5.0,
        )
        assert validate_signal_review_response(resp) is resp

    def test_valid_failure_response_passes(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=False,
            error_message="oops",
        )
        assert validate_signal_review_response(resp) is resp

    def test_mismatched_signal_counts_raises(self) -> None:
        """signals_generated != buy + sell + hold triggers validation error."""
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
            signals_generated=10,
            buy_signals=1,
            sell_signals=1,
            hold_signals=1,
        )
        with pytest.raises(OutputValidationError, match="does not equal"):
            validate_signal_review_response(resp)

    def test_mismatched_counts_skipped_on_failure(self) -> None:
        """Count mismatch is not checked when success=False."""
        resp = SignalReviewResponse(
            request_id="r1",
            success=False,
            error_message="error",
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            hold_signals=0,
        )
        assert validate_signal_review_response(resp) is resp


# ---------------------------------------------------------------------------
# validate_snapshot_summary_response
# ---------------------------------------------------------------------------


class TestValidateSnapshotSummaryResponse:
    """Tests for validate_snapshot_summary_response."""

    def test_valid_success_response_passes(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r1",
            success=True,
            summary="ok",
            country="US",
            features_count=5,
            snapshot_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert validate_snapshot_summary_response(resp) is resp

    def test_valid_failure_response_passes(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r1",
            success=False,
            error_message="offline",
            country="US",
        )
        assert validate_snapshot_summary_response(resp) is resp


# ---------------------------------------------------------------------------
# validate_runtime_result
# ---------------------------------------------------------------------------


class TestValidateRuntimeResult:
    """Tests for validate_runtime_result."""

    def test_valid_signal_review_result_passes(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
            signals_generated=2,
            buy_signals=1,
            sell_signals=1,
            hold_signals=0,
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=resp,
        )
        assert validate_runtime_result(result) is result

    def test_valid_snapshot_result_passes(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r1",
            success=True,
            summary="ok",
            country="US",
            features_count=3,
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.SUMMARIZE_MACRO_SNAPSHOT,
            response=resp,
        )
        assert validate_runtime_result(result) is result

    def test_invalid_inner_response_raises(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
            signals_generated=99,
            buy_signals=1,
            sell_signals=0,
            hold_signals=0,
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=resp,
        )
        with pytest.raises(OutputValidationError):
            validate_runtime_result(result)

    def test_failure_result_passes_validation(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=False,
            error_message="bad",
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=resp,
        )
        assert validate_runtime_result(result) is result


# ---------------------------------------------------------------------------
# OutputValidationError
# ---------------------------------------------------------------------------


class TestOutputValidationError:
    """Tests for the OutputValidationError exception."""

    def test_detail_attribute(self) -> None:
        exc = OutputValidationError(detail="something broke")
        assert exc.detail == "something broke"

    def test_pydantic_error_is_none_by_default(self) -> None:
        exc = OutputValidationError(detail="msg")
        assert exc.pydantic_error is None

    def test_str_representation(self) -> None:
        exc = OutputValidationError(detail="test error")
        assert str(exc) == "test error"
