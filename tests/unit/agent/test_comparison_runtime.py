"""Unit tests for snapshot comparison across agent runtime layers.

Covers:
- AgentRuntime.invoke dispatches SnapshotComparisonRequest → COMPARE_SNAPSHOTS
- LangChainAgentRuntime.invoke dispatches and validates SnapshotComparisonResponse
- validate_snapshot_comparison_response passes/fails correctly
- Prompt template renders comparison summary correctly
- Comparison dispatch in LangChainAgentRuntime with context hint injection
- TypeError for unsupported request type unchanged after new operation added
- Session context accumulates comparison_target from prior_snapshot_label
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.mcp_adapter import MCPAdapter
from src.agent.prompts.templates import (
    SNAPSHOT_COMPARISON_PROMPT,
    render_snapshot_comparison_summary,
)
from src.agent.runtime.agent_runtime import AgentOperation, AgentRuntime, AgentRuntimeResult
from src.agent.runtime.langchain_runtime import LangChainAgentRuntime
from src.agent.runtime.output_validation import (
    OutputValidationError,
    validate_snapshot_comparison_response,
)
from src.agent.schemas import (
    PriorFeatureInput,
    SnapshotComparisonRequest,
    SnapshotComparisonResponse,
)
from src.agent.service import AgentService
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> AgentService:
    return AgentService(MacroService(), SignalService())


def _make_adapter() -> MCPAdapter:
    return MCPAdapter(MacroService(), SignalService())


def _make_runtime() -> AgentRuntime:
    return AgentRuntime(_make_service())


def _make_lc_runtime(
    enable_context: bool = False,
    max_context_turns: int = 10,
) -> LangChainAgentRuntime:
    service = _make_service()
    adapter = _make_adapter()
    return LangChainAgentRuntime(
        service, adapter, enable_context=enable_context, max_context_turns=max_context_turns
    )


def _comparison_request(
    prior_features: list[dict[str, object]] | None = None,
    country: str = "US",
    prior_snapshot_label: str = "Q1-2026",
    request_id: str = "req-comp-1",
    session_id: str | None = None,
) -> SnapshotComparisonRequest:
    features = [PriorFeatureInput(**f) for f in (prior_features or [])]  # type: ignore[arg-type]
    return SnapshotComparisonRequest(
        request_id=request_id,
        country=country,
        prior_snapshot_label=prior_snapshot_label,
        prior_features=features,
        session_id=session_id or "",
    )


# ---------------------------------------------------------------------------
# AgentRuntime — COMPARE_SNAPSHOTS dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentRuntimeCompareSnapshots:
    async def test_returns_compare_snapshots_operation(self) -> None:
        runtime = _make_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert result.operation == AgentOperation.COMPARE_SNAPSHOTS

    async def test_response_is_snapshot_comparison_response(self) -> None:
        runtime = _make_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert isinstance(result.response, SnapshotComparisonResponse)

    async def test_success_on_happy_path(self) -> None:
        runtime = _make_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert result.success is True

    async def test_failure_on_prior_missing(self) -> None:
        runtime = _make_runtime()
        req = _comparison_request(prior_features=[])
        result = await runtime.invoke(req)
        assert result.success is False

    async def test_result_round_trips_schema(self) -> None:
        runtime = _make_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.operation == AgentOperation.COMPARE_SNAPSHOTS

    async def test_type_error_still_raised_for_unknown_type(self) -> None:
        runtime = _make_runtime()
        with pytest.raises(TypeError):
            await runtime.invoke("not-a-request")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LangChainAgentRuntime — COMPARE_SNAPSHOTS dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLangChainRuntimeCompareSnapshots:
    async def test_returns_compare_snapshots_operation(self) -> None:
        runtime = _make_lc_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert result.operation == AgentOperation.COMPARE_SNAPSHOTS

    async def test_success_result_is_schema_valid(self) -> None:
        runtime = _make_lc_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is True

    async def test_failure_result_is_schema_valid(self) -> None:
        runtime = _make_lc_runtime()
        req = _comparison_request(prior_features=[])
        result = await runtime.invoke(req)
        reparsed = AgentRuntimeResult.model_validate(result.model_dump())
        assert reparsed.success is False

    async def test_summary_is_non_empty_on_success(self) -> None:
        runtime = _make_lc_runtime()
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert result.response.summary != ""

    async def test_macro_service_failure_returns_schema_valid_failure(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("offline")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        adapter = MCPAdapter(mock_macro, SignalService())
        runtime = LangChainAgentRuntime(service, adapter)
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result = await runtime.invoke(req)
        assert result.success is False
        AgentRuntimeResult.model_validate(result.model_dump())

    async def test_comparison_with_context_hint_is_schema_valid(self) -> None:
        runtime = _make_lc_runtime(enable_context=True)
        req = _comparison_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        result1 = await runtime.invoke(req)
        result2 = await runtime.invoke(req)
        assert result1.success is True
        assert result2.success is True
        AgentRuntimeResult.model_validate(result2.model_dump())

    async def test_comparison_target_extracted_from_prior_label(self) -> None:
        runtime = _make_lc_runtime()
        session_id = "comp-session"
        req = _comparison_request(
            prior_features=[{"indicator_type": "gdp", "value": 50.0}],
            prior_snapshot_label="Q1-2026",
            session_id=session_id,
        )
        await runtime.invoke(req)
        ctx = runtime._session_store.get(session_id)
        assert ctx is not None
        assert ctx.active_parameters.comparison_target == "Q1-2026"

    async def test_type_error_still_raised_for_unknown_type(self) -> None:
        runtime = _make_lc_runtime()
        with pytest.raises(TypeError):
            await runtime.invoke("not-a-request")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


class TestValidateSnapshotComparisonResponse:
    def _make_success_response(self) -> SnapshotComparisonResponse:
        return SnapshotComparisonResponse(
            request_id="r1",
            success=True,
            summary="Comparison ok.",
            country="US",
            prior_snapshot_label="Q1-2026",
            changed_count=1,
            unchanged_count=2,
            no_prior_count=0,
        )

    def _make_failure_response(self) -> SnapshotComparisonResponse:
        return SnapshotComparisonResponse(
            request_id="r1",
            success=False,
            error_message="prior missing",
            country="US",
            prior_snapshot_label="Q1",
        )

    def test_valid_success_response_passes(self) -> None:
        resp = self._make_success_response()
        result = validate_snapshot_comparison_response(resp)
        assert result is resp

    def test_valid_failure_response_passes(self) -> None:
        resp = self._make_failure_response()
        result = validate_snapshot_comparison_response(resp)
        assert result is resp

    def test_raises_on_invalid_schema(self) -> None:
        resp = SnapshotComparisonResponse(
            request_id="r1",
            success=True,
            summary="ok",
            changed_count=0,
            unchanged_count=0,
            no_prior_count=0,
        )
        # Manually corrupt a field post-construction to simulate schema drift.
        object.__setattr__(resp, "changed_count", -1)
        with pytest.raises(OutputValidationError):
            validate_snapshot_comparison_response(resp)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


class TestSnapshotComparisonPromptTemplate:
    def test_template_has_system_and_human_messages(self) -> None:
        assert len(SNAPSHOT_COMPARISON_PROMPT.messages) == 2

    def test_render_contains_country(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="JP",
            prior_snapshot_label="Q1-2026",
            changed_count=1,
            unchanged_count=2,
            no_prior_count=0,
        )
        assert "JP" in msg

    def test_render_contains_prior_label(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q4-2025",
            changed_count=0,
            unchanged_count=3,
            no_prior_count=0,
        )
        assert "Q4-2025" in msg

    def test_render_contains_changed_count(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q1",
            changed_count=2,
            unchanged_count=1,
            no_prior_count=0,
        )
        assert "2" in msg

    def test_render_no_prior_suffix_present(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q1",
            changed_count=0,
            unchanged_count=0,
            no_prior_count=3,
        )
        assert "3" in msg
        assert "no prior" in msg

    def test_render_no_prior_suffix_absent_when_zero(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q1",
            changed_count=1,
            unchanged_count=0,
            no_prior_count=0,
        )
        assert "no prior" not in msg

    def test_render_context_summary_not_in_human_message(self) -> None:
        msg = render_snapshot_comparison_summary(
            country="US",
            prior_snapshot_label="Q1",
            changed_count=0,
            unchanged_count=1,
            no_prior_count=0,
            context_summary="[Session context hint]",
        )
        # Context hint is injected into system message, not the human message.
        assert "[Session context hint]" not in msg

    def test_render_is_deterministic(self) -> None:
        kwargs = {
            "country": "US",
            "prior_snapshot_label": "Q1-2026",
            "changed_count": 1,
            "unchanged_count": 2,
            "no_prior_count": 0,
        }
        assert render_snapshot_comparison_summary(**kwargs) == render_snapshot_comparison_summary(**kwargs)  # type: ignore[arg-type]
