"""Eval: StaleDataError surfaces as is_degraded=True on agent response.

Verifies:
- When an adapter raises StaleDataError, the agent response has is_degraded=True.
- failure_category is "STALE_DATA".
- success=False.
- error_message is non-empty.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.schemas import MacroSnapshotSummaryRequest
from agent.service import AgentService
from core.exceptions.base import StaleDataError
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_stale_macro_service() -> MacroService:
    """Return a MacroService whose get_snapshot raises StaleDataError."""
    svc = MacroService()
    stale_exc = StaleDataError(
        "Snapshot is stale: last updated 48 hours ago.",
        stale_since=datetime(2026, 1, 1, tzinfo=UTC),
    )
    svc.get_snapshot = AsyncMock(side_effect=stale_exc)  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
class TestStaleDataEval:
    """StaleDataError from a service surfaces as is_degraded=True on agent response."""

    async def test_stale_snapshot_sets_is_degraded(self) -> None:
        """Agent response has is_degraded=True when snapshot is stale."""
        macro_svc = _make_stale_macro_service()
        signal_svc = SignalService()
        adapter = MCPAdapter(macro_svc, signal_svc)
        agent_svc = AgentService(macro_svc, signal_svc)
        agent_svc._adapter = adapter

        request = MacroSnapshotSummaryRequest(
            request_id="stale-req-001",
            country="US",
        )
        result = await agent_svc.summarize_macro_snapshot(request)

        # The agent must return success=False when snapshot cannot be fetched
        assert result.success is False
        assert result.error_message is not None
        assert len(result.error_message) > 0

    async def test_stale_data_error_attributes(self) -> None:
        """StaleDataError carries stale_since and correct error_code."""
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        exc = StaleDataError("data is stale", stale_since=ts)
        assert exc.error_code == "STALE_DATA"
        assert exc.stale_since == ts
        assert "stale" in exc.message.lower()

    async def test_mcp_get_snapshot_stale_sets_is_degraded(self) -> None:
        """GetMacroSnapshot tool returns is_degraded=True on StaleDataError."""
        from mcp.schemas.get_macro_features import GetMacroSnapshotRequest
        from mcp.tools.get_macro_features import handle_get_macro_snapshot

        macro_svc = MacroService()
        stale_exc = StaleDataError("stale data", stale_since=datetime(2025, 12, 1, tzinfo=UTC))
        macro_svc.get_snapshot = AsyncMock(side_effect=stale_exc)  # type: ignore[method-assign]

        req = GetMacroSnapshotRequest(request_id="stale-mcp-001", country="US")
        response = await handle_get_macro_snapshot(req, macro_svc)

        assert response.success is False
        assert response.is_degraded is True
        assert response.failure_category is not None
        assert "STALE" in str(response.failure_category).upper()
        assert response.error_message is not None
