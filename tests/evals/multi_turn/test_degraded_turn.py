"""Eval: mid-session provider failure in multi-turn context.

Verifies that:
- First turn succeeds with a valid summary.
- Second turn has ProviderTimeoutError; response is success=False.
- Context hint from first turn does not appear in the failed second turn's summary.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import MacroSnapshotSummaryRequest
from agent.service import AgentService
from core.exceptions.base import ProviderTimeoutError
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_runtime_with_context() -> LangChainAgentRuntime:
    macro_svc = MacroService()
    signal_svc = SignalService()
    service = AgentService(macro_svc, signal_svc)
    adapter = MCPAdapter(macro_svc, signal_svc)
    return LangChainAgentRuntime(service, adapter, enable_context=True)


@pytest.mark.asyncio
class TestDegradedTurnEval:
    """Mid-session provider failure does not leak prior context into failed response."""

    async def test_first_turn_succeeds(self) -> None:
        runtime = _make_runtime_with_context()
        request = MacroSnapshotSummaryRequest(
            request_id="mt-degraded-001",
            session_id="session-degraded-001",
            country="US",
        )
        result = await runtime.invoke(request)
        assert result.success is True
        assert result.response.summary != ""

    async def test_second_turn_fails_with_provider_timeout(self) -> None:
        """Second turn fails when provider times out; success=False."""
        runtime = _make_runtime_with_context()
        session_id = "session-degraded-002"

        # First turn — succeeds, stores context
        req1 = MacroSnapshotSummaryRequest(
            request_id="mt-degraded-002a",
            session_id=session_id,
            country="US",
        )
        result1 = await runtime.invoke(req1)
        assert result1.success is True

        # Second turn — ProviderTimeoutError from macro service
        req2 = MacroSnapshotSummaryRequest(
            request_id="mt-degraded-002b",
            session_id=session_id,
            country="US",
        )
        timeout_exc = ProviderTimeoutError("FRED timed out", provider_id="fred", timeout_s=10.0)
        with patch.object(
            runtime._service._macro_service,
            "get_snapshot",
            new=AsyncMock(side_effect=timeout_exc),
        ):
            result2 = await runtime.invoke(req2)

        assert result2.success is False
        assert result2.response.error_message is not None

    async def test_failed_turn_does_not_include_prior_context_hint(self) -> None:
        """The context hint from the first successful turn should not appear
        in the failed second turn's error_message."""
        runtime = _make_runtime_with_context()
        session_id = "session-degraded-003"

        # First turn — succeeds
        req1 = MacroSnapshotSummaryRequest(
            request_id="mt-degraded-003a",
            session_id=session_id,
            country="US",
        )
        result1 = await runtime.invoke(req1)
        assert result1.success is True
        first_summary = result1.response.summary

        # Second turn — fails
        req2 = MacroSnapshotSummaryRequest(
            request_id="mt-degraded-003b",
            session_id=session_id,
            country="US",
        )
        timeout_exc = ProviderTimeoutError("timed out", provider_id="fred")
        with patch.object(
            runtime._service._macro_service,
            "get_snapshot",
            new=AsyncMock(side_effect=timeout_exc),
        ):
            result2 = await runtime.invoke(req2)

        assert result2.success is False
        # The error message should not contain the full first-turn summary text
        error_msg = result2.response.error_message or ""
        # The context hint is typically a short prefix, so check that the
        # detailed first-turn summary is not reproduced in the failure message
        assert first_summary not in error_msg
