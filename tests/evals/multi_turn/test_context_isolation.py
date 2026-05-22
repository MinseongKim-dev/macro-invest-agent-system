"""Eval: session context isolation — no parameter bleed between sessions.

Verifies that two simultaneous sessions using different ``session_id`` values
never share context; parameters set in session A must not appear in session B.
"""

from __future__ import annotations

import pytest

from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import MacroSnapshotSummaryRequest


@pytest.mark.asyncio
class TestContextIsolation:
    """Two sessions side by side must not share context."""

    async def test_country_does_not_bleed_between_sessions(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Parameters established in session A must not appear in session B."""
        runtime = make_lc_runtime
        sid_a = "isolation-session-a"
        sid_b = "isolation-session-b"

        # Session A: establish country="FR"
        req_a = MacroSnapshotSummaryRequest(
            request_id="iso-req-a",
            country="FR",
            session_id=sid_a,
        )
        await runtime.invoke(req_a)

        # Session B: establish country="CN"
        req_b = MacroSnapshotSummaryRequest(
            request_id="iso-req-b",
            country="CN",
            session_id=sid_b,
        )
        await runtime.invoke(req_b)

        ctx_a = runtime._session_store.get_or_create(sid_a)
        ctx_b = runtime._session_store.get_or_create(sid_b)

        hint_a = ctx_a.active_parameters.as_context_hint()
        hint_b = ctx_b.active_parameters.as_context_hint()

        # A should see FR, not CN
        assert "FR" in hint_a
        assert "CN" not in hint_a

        # B should see CN, not FR
        assert "CN" in hint_b
        assert "FR" not in hint_b

    async def test_turn_counts_are_independent(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Turn counts in each session are fully independent."""
        runtime = make_lc_runtime
        sid_x = "isolation-session-x"
        sid_y = "isolation-session-y"

        # 3 turns for X
        for i in range(3):
            await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"x-{i}", country="US", session_id=sid_x
                )
            )

        # 1 turn for Y
        await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="y-0", country="GB", session_id=sid_y
            )
        )

        ctx_x = runtime._session_store.get_or_create(sid_x)
        ctx_y = runtime._session_store.get_or_create(sid_y)
        assert ctx_x.turn_count == 3
        assert ctx_y.turn_count == 1

    async def test_sessions_produce_independent_results(
        self,
        make_lc_runtime: LangChainAgentRuntime,
    ) -> None:
        """Both sessions return valid results independently."""
        runtime = make_lc_runtime

        for sid, country in [("iso-p", "BR"), ("iso-q", "KR")]:
            result = await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"ind-{sid}",
                    country=country,
                    session_id=sid,
                )
            )
            assert result.success
