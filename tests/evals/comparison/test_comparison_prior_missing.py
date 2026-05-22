"""Eval: snapshot comparison with empty prior_features (prior snapshot missing).

Verifies that when ``prior_features`` is empty the response indicates
``success=False`` and the error message references the prior snapshot label.
"""

from __future__ import annotations

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import SnapshotComparisonRequest
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_runtime() -> LangChainAgentRuntime:
    macro_service = MacroService()
    signal_service = SignalService()
    service = AgentService(macro_service, signal_service)
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(service, adapter, enable_context=False)


@pytest.mark.asyncio
class TestComparisonPriorMissing:
    """Empty prior_features → success=False, error references prior label."""

    async def test_success_false_when_prior_features_empty(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="prior-missing-req-1",
                country="US",
                prior_snapshot_label="missing-label",
                prior_features=[],
            )
        )
        assert result.success is False

    async def test_error_message_references_prior_label(self) -> None:
        runtime = _make_runtime()
        label = "Q4-2025-prior"
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="prior-missing-req-2",
                country="US",
                prior_snapshot_label=label,
                prior_features=[],
            )
        )
        assert result.success is False
        assert result.response.error_message is not None
        assert label in result.response.error_message

    async def test_response_schema_valid_on_failure(self) -> None:
        """model_dump() must not raise even when success=False."""
        runtime = _make_runtime()
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="prior-missing-req-3",
                country="US",
                prior_snapshot_label="missing",
                prior_features=[],
            )
        )
        assert result.success is False
        dump = result.response.model_dump()
        assert dump["success"] is False
        assert dump["error_message"] is not None

    async def test_no_exception_raised_on_missing_prior(self) -> None:
        """The runtime must never raise an exception for missing prior data."""
        runtime = _make_runtime()
        try:
            result = await runtime.invoke(
                SnapshotComparisonRequest(
                    request_id="prior-missing-req-4",
                    country="US",
                    prior_snapshot_label="nothing",
                    prior_features=[],
                )
            )
            assert result.success is False
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Runtime raised unexpected exception: {exc!r}")
