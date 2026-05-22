"""Eval: failure_category field schema conformance.

Verifies that:
- failure_category is None on success responses.
- failure_category is set (non-None) on failure responses.
- is_degraded is False on success.
- Round-trip model_dump() preserves failure_category and is_degraded values.
- Extra fields are rejected on new schemas (extra="forbid").
"""

from __future__ import annotations

import pytest

from agent.schemas import MacroSnapshotSummaryResponse, SignalReviewResponse
from core.exceptions.failure_category import FailureCategory
from mcp.schemas.get_macro_features import GetMacroSnapshotResponse
from mcp.schemas.run_signal_engine import RunSignalEngineResponse


class TestFailureCategoryOnMCPResponse:
    """MCPResponse subclasses carry failure_category and is_degraded correctly."""

    def test_get_snapshot_success_has_no_failure_category(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="r",
            success=True,
            features_count=3,
        )
        assert resp.failure_category is None
        assert resp.is_degraded is False

    def test_get_snapshot_failure_has_failure_category(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="r",
            success=False,
            error_message="provider timed out",
            features_count=0,
            failure_category=FailureCategory.PROVIDER_TIMEOUT,
        )
        assert resp.failure_category == FailureCategory.PROVIDER_TIMEOUT
        assert resp.is_degraded is False

    def test_get_snapshot_stale_sets_is_degraded(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="r",
            success=False,
            error_message="stale data",
            features_count=0,
            failure_category=FailureCategory.STALE_DATA,
            is_degraded=True,
        )
        assert resp.is_degraded is True
        assert resp.failure_category == FailureCategory.STALE_DATA

    def test_run_signal_engine_success_has_no_failure_category(self) -> None:
        resp = RunSignalEngineResponse(
            request_id="r",
            engine_run_id="eng-001",
            success=True,
            signals_generated=3,
        )
        assert resp.failure_category is None
        assert resp.is_degraded is False

    def test_run_signal_engine_failure_has_failure_category(self) -> None:
        resp = RunSignalEngineResponse(
            request_id="r",
            engine_run_id="",
            success=False,
            error_message="HTTP 503",
            failure_category=FailureCategory.PROVIDER_HTTP,
        )
        assert resp.failure_category == FailureCategory.PROVIDER_HTTP


class TestFailureCategoryRoundTrip:
    """model_dump() preserves failure_category and is_degraded values."""

    def test_success_round_trip_no_failure_category(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="round-trip-1",
            success=True,
            features_count=5,
        )
        data = resp.model_dump()
        assert data["failure_category"] is None
        assert data["is_degraded"] is False

    def test_failure_round_trip_preserves_category(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="round-trip-2",
            success=False,
            error_message="timeout",
            features_count=0,
            failure_category=FailureCategory.PROVIDER_TIMEOUT,
        )
        data = resp.model_dump()
        # StrEnum serialises to string
        assert data["failure_category"] == "PROVIDER_TIMEOUT"
        assert data["is_degraded"] is False

    def test_degraded_round_trip(self) -> None:
        resp = GetMacroSnapshotResponse(
            request_id="round-trip-3",
            success=False,
            error_message="stale",
            features_count=0,
            failure_category=FailureCategory.STALE_DATA,
            is_degraded=True,
        )
        data = resp.model_dump()
        assert data["failure_category"] == "STALE_DATA"
        assert data["is_degraded"] is True

    def test_partial_data_round_trip(self) -> None:
        from mcp.schemas.get_macro_features import GetMacroFeaturesResponse

        resp = GetMacroFeaturesResponse(
            request_id="round-trip-4",
            success=False,
            error_message="partial",
            features_count=2,
            failure_category=FailureCategory.PARTIAL_DATA,
            is_degraded=True,
        )
        data = resp.model_dump()
        assert data["failure_category"] == "PARTIAL_DATA"
        assert data["is_degraded"] is True
        assert data["features_count"] == 2


class TestAgentResponseFailureCategory:
    """AgentResponse subclasses carry is_degraded and failure_category."""

    def test_snapshot_summary_response_success_defaults(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r",
            success=True,
            summary="Macro snapshot for US.",
            features_count=3,
        )
        assert resp.is_degraded is False
        assert resp.failure_category is None

    def test_snapshot_summary_response_failure_has_category(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="r",
            success=False,
            error_message="provider error",
            failure_category="PROVIDER_HTTP",
        )
        assert resp.failure_category == "PROVIDER_HTTP"

    def test_signal_review_response_success_defaults(self) -> None:
        resp = SignalReviewResponse(
            request_id="r",
            success=True,
            summary="Signal review complete.",
            signals_generated=2,
        )
        assert resp.is_degraded is False
        assert resp.failure_category is None

    def test_extra_fields_rejected_on_mcp_response(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GetMacroSnapshotResponse(
                request_id="r",
                success=True,
                features_count=1,
                unknown_extra_field="should_fail",  # type: ignore[call-arg]
            )
