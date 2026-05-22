"""Unit tests for the agent service layer.

Covers:
- Happy-path signal review
- Happy-path macro snapshot summary
- Tool failure surfacing for both operations
- Schema validity of all responses
- Request ID tracing across layers
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.mcp_adapter import MCPAdapter, MCPToolError
from src.agent.schemas import (
    MacroSnapshotSummaryRequest,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
)
from src.agent.service import AgentService
from src.domain.signals.registry import SignalRegistry, default_registry
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review_request(
    signal_ids: list[str],
    country: str = "US",
    request_id: str = "agent-req-001",
) -> SignalReviewRequest:
    return SignalReviewRequest(
        request_id=request_id,
        signal_ids=signal_ids,
        country=country,
    )


def _snapshot_request(
    country: str = "US",
    request_id: str = "agent-req-002",
) -> MacroSnapshotSummaryRequest:
    return MacroSnapshotSummaryRequest(request_id=request_id, country=country)


def _make_service(registry: SignalRegistry | None = None) -> AgentService:
    return AgentService(
        macro_service=MacroService(),
        signal_service=SignalService(),
        registry=registry,
    )


# ---------------------------------------------------------------------------
# AgentService.review_signals — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReviewSignalsHappyPath:
    """Happy-path tests for AgentService.review_signals."""

    async def test_success_with_known_signal_id(self) -> None:
        """Valid signal ID returns a successful, schema-valid response."""
        service = _make_service()
        response = await service.review_signals(_review_request(["bull_market"]))

        assert isinstance(response, SignalReviewResponse)
        assert response.success is True
        assert response.error_message is None
        assert response.engine_run_id != ""
        assert response.signals_generated >= 0

    async def test_success_echoes_request_id(self) -> None:
        """Response request_id matches request."""
        service = _make_service()
        response = await service.review_signals(
            _review_request(["bull_market"], request_id="trace-me")
        )

        assert response.request_id == "trace-me"

    async def test_success_summary_is_non_empty(self) -> None:
        """Successful review always includes a non-empty summary string."""
        service = _make_service()
        response = await service.review_signals(_review_request(["bull_market"]))

        assert response.success is True
        assert len(response.summary) > 0

    async def test_summary_contains_signal_id(self) -> None:
        """Summary text references the reviewed signal ID."""
        service = _make_service()
        response = await service.review_signals(_review_request(["recession_warning"]))

        assert "recession_warning" in response.summary

    async def test_summary_contains_country(self) -> None:
        """Summary text references the country code."""
        service = _make_service()
        response = await service.review_signals(_review_request(["bull_market"], country="GB"))

        assert "GB" in response.summary

    async def test_signal_counts_are_non_negative(self) -> None:
        """buy/sell/hold counts must all be >= 0."""
        service = _make_service()
        response = await service.review_signals(
            _review_request(["bull_market", "recession_warning", "hold_neutral"])
        )

        assert response.buy_signals >= 0
        assert response.sell_signals >= 0
        assert response.hold_signals >= 0

    async def test_signals_generated_equals_sum_of_types(self) -> None:
        """signals_generated == buy + sell + hold."""
        service = _make_service()
        response = await service.review_signals(
            _review_request(["bull_market", "recession_warning"])
        )

        assert response.signals_generated == (
            response.buy_signals + response.sell_signals + response.hold_signals
        )

    async def test_execution_time_ms_is_non_negative(self) -> None:
        """Execution time is reported as a non-negative float."""
        service = _make_service()
        response = await service.review_signals(_review_request(["bull_market"]))

        assert response.execution_time_ms >= 0.0

    async def test_custom_registry_is_respected(self) -> None:
        """A custom registry with a different signal ID is used correctly."""
        from src.domain.signals.enums import SignalType
        from src.domain.signals.models import SignalDefinition, SignalRule

        custom_def = SignalDefinition(
            signal_id="custom_signal",
            name="Custom",
            signal_type=SignalType.HOLD,
            description="Test-only signal",
            rules=[
                SignalRule(name="always", description="Always", condition="1==1")
            ],
        )
        registry = SignalRegistry({"custom_signal": custom_def})
        service = _make_service(registry=registry)

        response = await service.review_signals(_review_request(["custom_signal"]))

        assert response.success is True


# ---------------------------------------------------------------------------
# AgentService.review_signals — tool failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReviewSignalsToolFailures:
    """Tool failure tests for AgentService.review_signals."""

    async def test_unknown_signal_id_returns_error(self) -> None:
        """An unknown signal ID causes a failed, schema-valid response."""
        service = _make_service()
        response = await service.review_signals(_review_request(["nonexistent_signal"]))

        assert isinstance(response, SignalReviewResponse)
        assert response.success is False
        assert response.error_message is not None
        assert response.engine_run_id == ""
        assert response.summary == ""

    async def test_snapshot_failure_surfaces_cleanly(self) -> None:
        """RuntimeError from the macro service is surfaced as a failed response."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("data unavailable")
        service = AgentService(
            macro_service=mock_macro,
            signal_service=SignalService(),
            registry=default_registry,
        )

        response = await service.review_signals(_review_request(["bull_market"]))

        assert response.success is False
        assert response.error_message is not None
        assert response.engine_run_id == ""

    async def test_engine_failure_surfaces_cleanly(self) -> None:
        """RuntimeError from the signal service is surfaced as a failed response."""
        mock_signal = AsyncMock(spec=SignalService)
        mock_signal.run_engine.side_effect = RuntimeError("engine crash")
        service = AgentService(
            macro_service=MacroService(),
            signal_service=mock_signal,
            registry=default_registry,
        )

        response = await service.review_signals(_review_request(["bull_market"]))

        assert response.success is False
        assert response.error_message is not None

    async def test_error_response_is_schema_valid(self) -> None:
        """Even on failure the response satisfies the SignalReviewResponse schema."""
        service = _make_service()
        response = await service.review_signals(_review_request(["bad_id"]))

        # Re-parsing through the schema must not raise
        reparsed = SignalReviewResponse.model_validate(response.model_dump())
        assert reparsed.success is False

    async def test_request_id_echoed_on_failure(self) -> None:
        """request_id is preserved even when the tool fails."""
        service = _make_service()
        response = await service.review_signals(
            _review_request(["bad_id"], request_id="fail-trace")
        )

        assert response.request_id == "fail-trace"


# ---------------------------------------------------------------------------
# AgentService.summarize_macro_snapshot — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSummarizeMacroSnapshotHappyPath:
    """Happy-path tests for AgentService.summarize_macro_snapshot."""

    async def test_success_returns_valid_response(self) -> None:
        """Valid request returns a successful, schema-valid response."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(_snapshot_request())

        assert isinstance(response, MacroSnapshotSummaryResponse)
        assert response.success is True
        assert response.error_message is None
        assert response.features_count > 0
        assert response.snapshot_timestamp is not None

    async def test_success_echoes_request_id(self) -> None:
        """Response request_id matches request."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(
            _snapshot_request(request_id="snap-trace")
        )

        assert response.request_id == "snap-trace"

    async def test_success_summary_is_non_empty(self) -> None:
        """Successful summary always includes a non-empty summary string."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(_snapshot_request())

        assert len(response.summary) > 0

    async def test_summary_contains_country(self) -> None:
        """Summary text references the country code."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(_snapshot_request(country="JP"))

        assert "JP" in response.summary

    async def test_country_field_is_populated(self) -> None:
        """Response country field matches the request country."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(_snapshot_request(country="DE"))

        assert response.country == "DE"

    async def test_features_count_is_positive(self) -> None:
        """Snapshot summary reports at least one feature."""
        service = _make_service()
        response = await service.summarize_macro_snapshot(_snapshot_request())

        assert response.features_count > 0


# ---------------------------------------------------------------------------
# AgentService.summarize_macro_snapshot — tool failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSummarizeMacroSnapshotToolFailures:
    """Tool failure tests for AgentService.summarize_macro_snapshot."""

    async def test_snapshot_failure_surfaces_cleanly(self) -> None:
        """RuntimeError from macro service is surfaced as a failed response."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("feed offline")
        service = AgentService(
            macro_service=mock_macro,
            signal_service=SignalService(),
        )

        response = await service.summarize_macro_snapshot(_snapshot_request())

        assert isinstance(response, MacroSnapshotSummaryResponse)
        assert response.success is False
        assert response.error_message is not None
        assert response.features_count == 0
        assert response.snapshot_timestamp is None

    async def test_error_response_is_schema_valid(self) -> None:
        """Even on failure the response satisfies the MacroSnapshotSummaryResponse schema."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("feed offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())

        response = await service.summarize_macro_snapshot(_snapshot_request())

        reparsed = MacroSnapshotSummaryResponse.model_validate(response.model_dump())
        assert reparsed.success is False

    async def test_request_id_echoed_on_failure(self) -> None:
        """request_id is preserved even when the tool fails."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())

        response = await service.summarize_macro_snapshot(
            _snapshot_request(request_id="err-trace")
        )

        assert response.request_id == "err-trace"

    async def test_country_field_preserved_on_failure(self) -> None:
        """country is preserved in the failed response for tracing."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())

        response = await service.summarize_macro_snapshot(_snapshot_request(country="AU"))

        assert response.country == "AU"


# ---------------------------------------------------------------------------
# MCPAdapter — unit-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPAdapterErrorNormalisation:
    """Tests that MCPAdapter raises MCPToolError on MCP failures."""

    async def test_snapshot_tool_failure_raises_mcp_tool_error(self) -> None:
        """Adapter raises MCPToolError when snapshot tool returns success=False."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("downstream error")
        adapter = MCPAdapter(macro_service=mock_macro, signal_service=SignalService())

        with pytest.raises(MCPToolError) as exc_info:
            await adapter.get_macro_snapshot(request_id="req-adapt-001", country="US")

        assert exc_info.value.tool_name == "get_macro_snapshot"
        assert exc_info.value.error_message != ""

    async def test_signal_engine_tool_failure_raises_mcp_tool_error(self) -> None:
        """Adapter raises MCPToolError when signal engine tool returns success=False."""
        adapter = MCPAdapter(
            macro_service=MacroService(),
            signal_service=SignalService(),
            registry=default_registry,
        )

        with pytest.raises(MCPToolError) as exc_info:
            await adapter.run_signal_engine(
                request_id="req-adapt-002",
                signal_ids=["unknown_id"],
                country="US",
            )

        assert exc_info.value.tool_name == "run_signal_engine"

    async def test_mcp_tool_error_message_is_informative(self) -> None:
        """The MCPToolError message carries the tool name and a normalized error message."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("downstream failure")
        adapter = MCPAdapter(macro_service=mock_macro, signal_service=SignalService())

        with pytest.raises(MCPToolError) as exc_info:
            await adapter.get_macro_snapshot(request_id="req-adapt-003", country="US")

        error_str = str(exc_info.value)
        assert "get_macro_snapshot" in error_str
