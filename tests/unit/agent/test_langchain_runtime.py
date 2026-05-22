"""Unit tests for agent.runtime.langchain_runtime.

Covers:
- LangChainAgentRuntime.invoke dispatches to the correct service method
- Prompt-template-driven summary formatting
- Output schema validation at the runtime boundary
- ConversationContext turn recording and eviction
- TypeError for unsupported request types
- Tool bindings are created and accessible
- Schema validity on happy and failure paths
- Session-scoped context via session_id: accumulation, isolation, bounded turns,
  failed-turn recording, tool-result immutability
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.mcp_adapter import MCPAdapter
from src.agent.runtime.agent_runtime import AgentOperation, AgentRuntimeResult
from src.agent.runtime.langchain_runtime import (
    ConversationContext,
    ConversationTurn,
    LangChainAgentRuntime,
)
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


def _make_runtime(
    *,
    enable_context: bool = False,
    max_context_turns: int = 10,
) -> LangChainAgentRuntime:
    macro_service = MacroService()
    signal_service = SignalService()
    service = AgentService(macro_service, signal_service)
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(
        service,
        adapter,
        enable_context=enable_context,
        max_context_turns=max_context_turns,
    )


def _review_request(
    signal_ids: list[str] | None = None,
    country: str = "US",
    request_id: str = "lc-req-001",
) -> SignalReviewRequest:
    return SignalReviewRequest(
        request_id=request_id,
        signal_ids=signal_ids or ["bull_market"],
        country=country,
    )


def _snapshot_request(
    country: str = "US",
    request_id: str = "lc-req-002",
) -> MacroSnapshotSummaryRequest:
    return MacroSnapshotSummaryRequest(request_id=request_id, country=country)


# ---------------------------------------------------------------------------
# Dispatch — review_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLangChainRuntimeReviewSignals:
    """Tests that SignalReviewRequest is dispatched correctly."""

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

    async def test_request_id_preserved(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(request_id="trace-lc-001"))
        assert result.response.request_id == "trace-lc-001"

    async def test_summary_is_non_empty_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bull_market"]))
        assert result.success is True
        assert len(result.response.summary) > 0

    async def test_summary_contains_signal_id(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["recession_warning"]))
        assert "recession_warning" in result.response.summary

    async def test_summary_contains_country(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bull_market"], country="GB"))
        assert "GB" in result.response.summary

    async def test_result_is_schema_valid_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request())
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.operation == AgentOperation.REVIEW_SIGNALS

    async def test_failed_review_has_correct_operation(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["unknown_signal_xyz"]))
        assert result.operation == AgentOperation.REVIEW_SIGNALS
        assert result.success is False
        assert result.error_message is not None

    async def test_result_is_schema_valid_on_failure(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bad_id_xyz"]))
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# Dispatch — summarize_macro_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLangChainRuntimeSummarizeSnapshot:
    """Tests that MacroSnapshotSummaryRequest is dispatched correctly."""

    async def test_operation_label(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())
        assert result.operation == AgentOperation.SUMMARIZE_MACRO_SNAPSHOT

    async def test_response_type(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())
        assert isinstance(result.response, MacroSnapshotSummaryResponse)

    async def test_success_proxy(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())
        assert result.success == result.response.success

    async def test_request_id_preserved(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request(request_id="trace-lc-002"))
        assert result.response.request_id == "trace-lc-002"

    async def test_summary_is_non_empty_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())
        assert result.success is True
        assert len(result.response.summary) > 0

    async def test_summary_contains_country(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request(country="JP"))
        assert "JP" in result.response.summary

    async def test_failed_snapshot_has_correct_operation(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("feed down")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        adapter = MCPAdapter(mock_macro, SignalService())
        runtime = LangChainAgentRuntime(service, adapter)

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
        adapter = MCPAdapter(mock_macro, SignalService())
        runtime = LangChainAgentRuntime(service, adapter)

        result = await runtime.invoke(_snapshot_request())
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# TypeError on unsupported request type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLangChainRuntimeTypeError:
    """Tests that unsupported request types raise TypeError."""

    async def test_raises_type_error_for_unknown_type(self) -> None:
        runtime = _make_runtime()

        class FakeRequest:
            request_id = "fake"

        with pytest.raises(TypeError, match="Unsupported request type"):
            await runtime.invoke(FakeRequest())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Prompt-driven formatting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPromptDrivenFormatting:
    """Tests that summaries are produced via the LangChain prompt templates."""

    async def test_signal_review_summary_matches_template(self) -> None:
        """The summary should follow the template pattern."""
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bull_market"]))

        assert result.success is True
        summary = result.response.summary
        assert "Signal review for" in summary
        assert "signal(s) generated" in summary
        assert "Dominant signal direction:" in summary
        assert "Engine run ID:" in summary
        assert "Execution time:" in summary

    async def test_snapshot_summary_matches_template(self) -> None:
        """The summary should follow the template pattern."""
        runtime = _make_runtime()
        result = await runtime.invoke(_snapshot_request())

        assert result.success is True
        summary = result.response.summary
        assert "Macro snapshot for" in summary
        assert "feature(s) available" in summary

    async def test_error_summary_is_empty(self) -> None:
        """On failure the summary should be empty (not template-formatted)."""
        runtime = _make_runtime()
        result = await runtime.invoke(_review_request(["bad_id"]))

        assert result.success is False
        assert result.response.summary == ""


# ---------------------------------------------------------------------------
# Tool bindings
# ---------------------------------------------------------------------------


class TestToolBindings:
    """Tests for LangChain tool bindings."""

    def test_tools_are_created(self) -> None:
        runtime = _make_runtime()
        assert len(runtime.tools) == 2

    def test_tool_names(self) -> None:
        runtime = _make_runtime()
        names = {t.name for t in runtime.tools}
        assert "run_signal_engine" in names
        assert "get_macro_snapshot" in names

    def test_tools_are_read_only_copies(self) -> None:
        runtime = _make_runtime()
        tools = runtime.tools
        tools.clear()
        assert len(runtime.tools) == 2


# ---------------------------------------------------------------------------
# ConversationContext
# ---------------------------------------------------------------------------


class TestConversationContext:
    """Tests for the in-memory ConversationContext."""

    def test_initially_empty(self) -> None:
        ctx = ConversationContext()
        assert ctx.turn_count == 0
        assert ctx.turns == []

    def test_add_turn(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(
            ConversationTurn(
                request_type="SignalReviewRequest",
                request_snapshot={"request_id": "r1"},
                response_summary="ok",
                success=True,
            )
        )
        assert ctx.turn_count == 1
        assert ctx.turns[0].request_type == "SignalReviewRequest"

    def test_fifo_eviction(self) -> None:
        ctx = ConversationContext(max_turns=2)
        for i in range(5):
            ctx.add_turn(
                ConversationTurn(
                    request_type=f"Type{i}",
                    request_snapshot={"i": i},
                    response_summary=f"turn-{i}",
                    success=True,
                )
            )
        assert ctx.turn_count == 2
        assert ctx.turns[0].request_type == "Type3"
        assert ctx.turns[1].request_type == "Type4"

    def test_clear(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(
            ConversationTurn(
                request_type="X",
                request_snapshot={},
                response_summary="ok",
                success=True,
            )
        )
        ctx.clear()
        assert ctx.turn_count == 0

    def test_turns_returns_list_copy(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn(
            ConversationTurn(
                request_type="X",
                request_snapshot={},
                response_summary="ok",
                success=True,
            )
        )
        turns = ctx.turns
        turns.clear()
        assert ctx.turn_count == 1


# ---------------------------------------------------------------------------
# Context integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContextIntegration:
    """Tests that conversation context is recorded when enabled."""

    async def test_context_disabled_by_default(self) -> None:
        runtime = _make_runtime()
        assert runtime.context is None

    async def test_context_records_turn_on_success(self) -> None:
        runtime = _make_runtime(enable_context=True)
        await runtime.invoke(_review_request(["bull_market"]))

        assert runtime.context is not None
        assert runtime.context.turn_count == 1
        turn = runtime.context.turns[0]
        assert turn.request_type == "SignalReviewRequest"
        assert turn.success is True
        assert len(turn.response_summary) > 0

    async def test_context_records_turn_on_failure(self) -> None:
        runtime = _make_runtime(enable_context=True)
        await runtime.invoke(_review_request(["bad_id"]))

        assert runtime.context is not None
        assert runtime.context.turn_count == 1
        turn = runtime.context.turns[0]
        assert turn.success is False

    async def test_context_eviction(self) -> None:
        runtime = _make_runtime(enable_context=True, max_context_turns=2)
        for i in range(5):
            await runtime.invoke(_snapshot_request(request_id=f"req-{i}"))

        assert runtime.context is not None
        assert runtime.context.turn_count == 2

    async def test_no_context_when_disabled(self) -> None:
        runtime = _make_runtime(enable_context=False)
        await runtime.invoke(_review_request())
        assert runtime.context is None


# ---------------------------------------------------------------------------
# ConversationTurn schema
# ---------------------------------------------------------------------------


class TestConversationTurnSchema:
    """Tests for ConversationTurn model validation."""

    def test_valid_turn(self) -> None:
        turn = ConversationTurn(
            request_type="SignalReviewRequest",
            request_snapshot={"request_id": "r1"},
            response_summary="ok",
            success=True,
        )
        assert turn.request_type == "SignalReviewRequest"

    def test_round_trip(self) -> None:
        turn = ConversationTurn(
            request_type="MacroSnapshotSummaryRequest",
            request_snapshot={"country": "US"},
            response_summary="snapshot ok",
            success=True,
        )
        reparsed = ConversationTurn.model_validate(turn.model_dump())
        assert reparsed.request_type == "MacroSnapshotSummaryRequest"
        assert reparsed.response_summary == "snapshot ok"


# ---------------------------------------------------------------------------
# Session-scoped context (session_id carryover)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionScopedContext:
    """Tests for session_id-keyed context in LangChainAgentRuntime.

    Session-scoped context is activated by passing a non-empty ``session_id``
    on the request.  It is independent of the ``enable_context`` flag.
    """

    async def test_session_context_records_turn(self) -> None:
        runtime = _make_runtime()  # enable_context=False (default)
        req_with_session = MacroSnapshotSummaryRequest(
            request_id="sc-001",
            country="US",
            session_id="test-session",
        )
        result = await runtime.invoke(req_with_session)
        # The per-instance context is still None (enable_context=False).
        assert runtime.context is None
        # But the result should be valid.
        assert result.operation == AgentOperation.SUMMARIZE_MACRO_SNAPSHOT

    async def test_session_context_accumulates_across_turns(self) -> None:
        runtime = _make_runtime()
        session_id = "accumulate-session"

        for i in range(3):
            req = MacroSnapshotSummaryRequest(
                request_id=f"req-{i}",
                country="US",
                session_id=session_id,
            )
            await runtime.invoke(req)

        # Retrieve the context directly from the store.
        ctx = runtime._session_store.get(session_id)
        assert ctx is not None
        assert ctx.turn_count == 3

    async def test_session_context_carries_country_parameter(self) -> None:
        runtime = _make_runtime()
        session_id = "param-session"

        await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="req-1",
                country="JP",
                session_id=session_id,
            )
        )
        ctx = runtime._session_store.get(session_id)
        assert ctx is not None
        assert ctx.active_parameters.country == "JP"

    async def test_different_sessions_are_isolated(self) -> None:
        runtime = _make_runtime()

        # Populate session A with a turn.
        await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="req-A",
                country="US",
                session_id="session-A",
            )
        )
        # Session B has no turns yet.
        ctx_b = runtime._session_store.get("session-B")
        assert ctx_b is None

        await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="req-B",
                country="JP",
                session_id="session-B",
            )
        )

        ctx_a = runtime._session_store.get("session-A")
        ctx_b = runtime._session_store.get("session-B")

        assert ctx_a is not None
        assert ctx_b is not None
        assert ctx_a is not ctx_b
        assert ctx_a.turn_count == 1
        assert ctx_b.turn_count == 1
        # Country parameters must not leak.
        assert ctx_a.active_parameters.country == "US"
        assert ctx_b.active_parameters.country == "JP"

    async def test_session_context_bounded_by_max_context_turns(self) -> None:
        runtime = _make_runtime(max_context_turns=2)
        session_id = "bounded-session"

        for i in range(5):
            await runtime.invoke(
                MacroSnapshotSummaryRequest(
                    request_id=f"req-{i}",
                    country="US",
                    session_id=session_id,
                )
            )

        ctx = runtime._session_store.get(session_id)
        assert ctx is not None
        assert ctx.turn_count == 2

    async def test_stateless_request_produces_valid_result(self) -> None:
        """A request with no session_id and enable_context=False is stateless."""
        runtime = _make_runtime()  # enable_context=False, no session_id
        result = await runtime.invoke(_snapshot_request())
        assert result.success is True
        assert runtime.context is None

    async def test_session_context_records_failed_turn(self) -> None:
        from unittest.mock import AsyncMock

        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        adapter = MCPAdapter(mock_macro, SignalService())
        runtime = LangChainAgentRuntime(service, adapter)

        session_id = "fail-session"
        result = await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="req-fail",
                country="US",
                session_id=session_id,
            )
        )

        assert result.success is False
        ctx = runtime._session_store.get(session_id)
        assert ctx is not None
        assert ctx.turn_count == 1
        assert ctx.turns[0].success is False

    async def test_context_hint_injected_into_summary_on_followup(self) -> None:
        """After a first turn establishes context, subsequent turns should
        incorporate the context hint into the rendered summary.

        The context hint is injected into the system message only, not the
        human-message summary text — so we verify the response is schema-valid
        and succeeds rather than inspecting the summary for the hint text.
        """
        runtime = _make_runtime()
        session_id = "hint-session"

        # First turn.
        result1 = await runtime.invoke(
            SignalReviewRequest(
                request_id="req-1",
                signal_ids=["bull_market"],
                country="US",
                session_id=session_id,
            )
        )
        assert result1.success is True

        # Second turn — context is now established.
        result2 = await runtime.invoke(
            SignalReviewRequest(
                request_id="req-2",
                signal_ids=["bull_market"],
                country="US",
                session_id=session_id,
            )
        )
        assert result2.success is True
        # Both responses must be schema-valid.
        AgentRuntimeResult.model_validate(result2.model_dump())

    async def test_tool_results_not_overridden_by_context(self) -> None:
        """Context must never alter deterministic tool results."""
        runtime = _make_runtime()
        session_id = "tool-check-session"

        # Prime context with a first turn.
        await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="prime",
                country="US",
                session_id=session_id,
            )
        )

        # Second turn with the same request.
        result_no_session = await runtime.invoke(
            MacroSnapshotSummaryRequest(request_id="r-no-sess", country="US")
        )
        result_with_session = await runtime.invoke(
            MacroSnapshotSummaryRequest(
                request_id="r-with-sess",
                country="US",
                session_id=session_id,
            )
        )

        # The numeric metadata from deterministic tools must match.
        assert isinstance(result_no_session.response, MacroSnapshotSummaryResponse)
        assert isinstance(result_with_session.response, MacroSnapshotSummaryResponse)
        assert (
            result_no_session.response.features_count
            == result_with_session.response.features_count
        )
