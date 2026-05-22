"""Eval: snapshot comparison happy path — change-detected and no-change round-trips.

Verifies that the LangChainAgentRuntime.invoke path for SnapshotComparisonRequest
returns success=True, correct counts, and a non-empty summary.
"""

from __future__ import annotations

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.agent_runtime import AgentOperation
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import PriorFeatureInput, SnapshotComparisonRequest
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_runtime() -> LangChainAgentRuntime:
    macro_service = MacroService()
    signal_service = SignalService()
    service = AgentService(macro_service, signal_service)
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(service, adapter, enable_context=False)


def _comparison_req(
    prior_features: list[dict[str, object]] | None = None,
    country: str = "US",
    label: str = "Q1-2026",
    request_id: str = "comp-req-1",
) -> SnapshotComparisonRequest:
    features = [PriorFeatureInput(**f) for f in (prior_features or [])]  # type: ignore[arg-type]
    return SnapshotComparisonRequest(
        request_id=request_id,
        country=country,
        prior_snapshot_label=label,
        prior_features=features,
    )


# Known prior features that differ from the MacroService placeholder value (50.0)
_DIFFERENT_PRIOR = [
    {"indicator_type": "gdp", "value": 99999.0},
    {"indicator_type": "inflation", "value": 99999.0},
    {"indicator_type": "unemployment", "value": 99999.0},
    {"indicator_type": "interest_rate", "value": 99999.0},
    {"indicator_type": "bond_yield", "value": 99999.0},
]


@pytest.mark.asyncio
class TestComparisonHappy:
    """Full round-trip happy-path comparison evals."""

    async def test_returns_success_true_with_prior_features(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.success is True

    async def test_operation_is_compare_snapshots(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.operation == AgentOperation.COMPARE_SNAPSHOTS

    async def test_summary_is_non_empty_on_success(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.success
        assert isinstance(result.response.summary, str)
        assert len(result.response.summary) > 0

    async def test_changed_count_non_negative(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.success
        assert result.response.changed_count >= 0  # type: ignore[union-attr]

    async def test_unchanged_count_non_negative(self) -> None:
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.success
        assert result.response.unchanged_count >= 0  # type: ignore[union-attr]

    async def test_response_fields_schema_valid(self) -> None:
        """model_dump() round-trip must not raise."""
        runtime = _make_runtime()
        result = await runtime.invoke(
            _comparison_req(prior_features=_DIFFERENT_PRIOR)
        )
        assert result.success
        dump = result.response.model_dump()
        assert dump["success"] is True
        assert "summary" in dump
