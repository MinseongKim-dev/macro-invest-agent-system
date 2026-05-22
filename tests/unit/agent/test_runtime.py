"""Unit tests for agent.runtime.agent_runtime.

Covers:
- AgentRuntime.invoke dispatches to the correct service method
- AgentRuntimeResult carries the correct operation label
- success / error_message convenience properties proxy the inner response
- AgentRuntime.invoke raises TypeError for unsupported request types
- Schema validity of AgentRuntimeResult on happy and failure paths
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.runtime.agent_runtime import AgentOperation, AgentRuntime, AgentRuntimeResult
from src.agent.schemas import (
    MacroSnapshotSummaryRequest,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
)
from src.agent.service import AgentService
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime() -> AgentRuntime:
    service = AgentService(
        macro_service=MacroService(),
        signal_service=SignalService(),
    )
    return AgentRuntime(service)


def _review_request(
    signal_ids: list[str] | None = None,
    country: str = "US",
    request_id: str = "rt-req-001",
) -> SignalReviewRequest:
    return SignalReviewRequest(
        request_id=request_id,
        signal_ids=signal_ids or ["bull_market"],
        country=country,
    )


def _snapshot_request(
    country: str = "US",
    request_id: str = "rt-req-002",
) -> MacroSnapshotSummaryRequest:
    return MacroSnapshotSummaryRequest(request_id=request_id, country=country)


# ---------------------------------------------------------------------------
# Dispatch — review_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentRuntimeDispatchReviewSignals:
    """Tests that SignalReviewRequest is dispatched to review_signals."""

    async def test_operation_label_is_review_signals(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request())

        assert result.operation == AgentOperation.REVIEW_SIGNALS

    async def test_response_type_is_signal_review_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request())

        assert isinstance(result.response, SignalReviewResponse)

    async def test_success_proxy_reflects_inner_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bull_market"]))

        assert result.success == result.response.success

    async def test_error_message_proxy_is_none_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bull_market"]))

        assert result.success is True
        assert result.error_message is None

    async def test_request_id_preserved_in_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(request_id="trace-rt-001"))

        assert result.response.request_id == "trace-rt-001"

    async def test_failed_review_has_correct_operation_label(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["unknown_signal_xyz"]))

        assert result.operation == AgentOperation.REVIEW_SIGNALS
        assert result.success is False
        assert result.error_message is not None

    async def test_result_is_schema_valid_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request())

        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.operation == AgentOperation.REVIEW_SIGNALS

    async def test_result_is_schema_valid_on_failure(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bad_id_xyz"]))

        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# Dispatch — summarize_macro_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentRuntimeDispatchSummarizeSnapshot:
    """Tests that MacroSnapshotSummaryRequest is dispatched to summarize_macro_snapshot."""

    async def test_operation_label_is_summarize_macro_snapshot(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())

        assert result.operation == AgentOperation.SUMMARIZE_MACRO_SNAPSHOT

    async def test_response_type_is_macro_snapshot_summary_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())

        assert isinstance(result.response, MacroSnapshotSummaryResponse)

    async def test_success_proxy_reflects_inner_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())

        assert result.success == result.response.success

    async def test_request_id_preserved_in_response(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request(request_id="trace-rt-002"))

        assert result.response.request_id == "trace-rt-002"

    async def test_failed_snapshot_has_correct_operation_label(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("feed down")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        runtime = AgentRuntime(service)

        result = await runtime.invoke(_snapshot_request())

        assert result.operation == AgentOperation.SUMMARIZE_MACRO_SNAPSHOT
        assert result.success is False

    async def test_result_is_schema_valid_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())

        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.operation == AgentOperation.SUMMARIZE_MACRO_SNAPSHOT

    async def test_result_is_schema_valid_on_failure(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        runtime = AgentRuntime(service)

        result = await runtime.invoke(_snapshot_request())
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# TypeError on unsupported request type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentRuntimeTypeError:
    """Tests that unsupported request types raise TypeError."""

    async def test_raises_type_error_for_unknown_type(self) -> None:
        runtime = _make_runtime()

        class FakeRequest:
            request_id = "fake"

        with pytest.raises(TypeError, match="Unsupported request type"):
            await runtime.invoke(FakeRequest())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AgentRuntimeResult schema
# ---------------------------------------------------------------------------


class TestAgentRuntimeResultSchema:
    """Tests for AgentRuntimeResult model validation."""

    def test_success_property_true(self) -> None:
        resp = SignalReviewResponse(
            request_id="r1",
            success=True,
            summary="ok",
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=resp,
        )
        assert result.success is True

    def test_success_property_false(self) -> None:
        resp = SignalReviewResponse(
            request_id="r2",
            success=False,
            error_message="oops",
        )
        result = AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=resp,
        )
        assert result.success is False
        assert result.error_message == "oops"
