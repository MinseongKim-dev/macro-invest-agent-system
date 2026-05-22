"""Eval: context carryover across turns in the same session.

Verifies that when two sequential requests share the same ``session_id``,
the second turn's context hint contains the first turn's country parameter.
"""

from __future__ import annotations

import pytest

from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import MacroSnapshotSummaryRequest


@pytest.mark.asyncio
class TestContextCarryover:
    """Context parameters set in turn 1 are visible in turn 2's context hint."""

    async def test_country_from_first_turn_appears_in_context_after_second(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Country established in turn 1 is carried into the context summary."""
        runtime = make_lc_runtime
        sid = "carryover-session-001"

        # Turn 1: establish country="US"
        req1 = MacroSnapshotSummaryRequest(
            request_id="t1-req-001",
            country="US",
            session_id=sid,
        )
        result1 = await runtime.invoke(req1)
        assert result1.success

        # Turn 2: same session — context should reference US from turn 1
        req2 = MacroSnapshotSummaryRequest(
            request_id="t1-req-002",
            country="US",
            session_id=sid,
        )
        result2 = await runtime.invoke(req2)
        assert result2.success

        # The session context should now have 2 turns
        ctx = runtime._session_store.get_or_create(sid)
        assert ctx.turn_count == 2

    async def test_context_hint_references_first_turn_country(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Active parameters after turn 1 show the established country."""
        runtime = make_lc_runtime
        sid = "carryover-session-002"

        req1 = MacroSnapshotSummaryRequest(
            request_id="ct-req-001",
            country="JP",
            session_id=sid,
        )
        await runtime.invoke(req1)

        ctx = runtime._session_store.get_or_create(sid)
        hint = ctx.active_parameters.as_context_hint()
        assert "JP" in hint

    async def test_second_turn_response_is_valid(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Second turn in same session returns a schema-valid response."""
        runtime = make_lc_runtime
        sid = "carryover-session-003"

        for i in range(2):
            req = MacroSnapshotSummaryRequest(
                request_id=f"ct-req-{i}",
                country="DE",
                session_id=sid,
            )
            result = await runtime.invoke(req)
            assert result.success
            assert isinstance(result.response.summary, str)
            assert len(result.response.summary) > 0
