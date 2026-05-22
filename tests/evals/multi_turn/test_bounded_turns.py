"""Eval: bounded turn count — context never grows beyond max_context_turns.

Verifies that after exceeding the turn cap, the context length is bounded and
the runtime continues to function correctly.
"""

from __future__ import annotations

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import MacroSnapshotSummaryRequest
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_bounded_runtime(max_turns: int) -> LangChainAgentRuntime:
    macro_service = MacroService()
    signal_service = SignalService()
    service = AgentService(macro_service, signal_service)
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(
        service,
        adapter,
        enable_context=True,
        max_context_turns=max_turns,
    )


@pytest.mark.asyncio
class TestBoundedTurns:
    """Context length never exceeds max_context_turns."""

    async def test_turn_count_capped_at_max(self) -> None:
        """After N + extra turns, turn_count never exceeds N."""
        cap = 3
        runtime = _make_bounded_runtime(max_turns=cap)

        # Fire cap + 2 requests on the legacy (enable_context=True) context.
        for i in range(cap + 2):
            await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"bounded-req-{i}",
                    country="US",
                )
            )

        assert runtime.context is not None
        assert runtime.context.turn_count <= cap

    async def test_session_turn_count_capped_at_max(self) -> None:
        """Session-keyed context also respects the cap."""
        cap = 4
        runtime = _make_bounded_runtime(max_turns=cap)
        sid = "bounded-session-001"

        for i in range(cap + 3):
            await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"s-bounded-{i}",
                    country="US",
                    session_id=sid,
                )
            )

        ctx = runtime._session_store.get_or_create(sid, max_turns=cap)
        assert ctx.turn_count <= cap

    async def test_runtime_functional_after_exceeding_cap(self) -> None:
        """Runtime still returns valid results after the cap is exceeded."""
        cap = 2
        runtime = _make_bounded_runtime(max_turns=cap)

        for i in range(cap + 5):
            result = await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"functional-{i}",
                    country="US",
                )
            )
            assert result.success

    async def test_context_hint_non_empty_after_turns(self) -> None:
        """After at least one turn, the context summary is non-empty."""
        runtime = _make_bounded_runtime(max_turns=5)

        await runtime.invoke(
            MacroSnapshotSummaryRequest(request_id="hint-req-0", country="AU")
        )

        assert runtime.context is not None
        hint = runtime.context.context_summary()
        assert len(hint) > 0
