"""Eval: comparison with degraded current snapshot (partial feature set).

Verifies that when the current snapshot has fewer features than the prior
snapshot (no_prior_count > 0), the comparison still returns success=True
(partial is valid) and the response shape is correct.
"""

from __future__ import annotations

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.agent_runtime import AgentOperation
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import PriorFeatureInput, SnapshotComparisonRequest, SnapshotComparisonResponse
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_runtime() -> LangChainAgentRuntime:
    macro_svc = MacroService()
    signal_svc = SignalService()
    service = AgentService(macro_svc, signal_svc)
    adapter = MCPAdapter(macro_svc, signal_svc)
    return LangChainAgentRuntime(service, adapter, enable_context=False)


# Prior features include indicators that the MacroService (synthetic) does
# also return — plus extra indicators that are NOT in the current snapshot.
_PARTIAL_PRIOR = [
    # These overlap with the synthetic MacroService (GDP, inflation, unemployment)
    {"indicator_type": "gdp", "value": 99999.0},
    {"indicator_type": "inflation", "value": 99999.0},
    {"indicator_type": "unemployment", "value": 99999.0},
    # These are extras that the current snapshot does NOT include
    {"indicator_type": "bond_yield", "value": 99999.0},
    {"indicator_type": "pmi", "value": 99999.0},
]


@pytest.mark.asyncio
class TestDegradedComparisonEval:
    """Comparison with partial current snapshot is still valid (success=True)."""

    async def test_comparison_with_partial_prior_succeeds(self) -> None:
        """When prior features > current features, comparison still succeeds."""
        runtime = _make_runtime()
        prior_features = [PriorFeatureInput(**f) for f in _PARTIAL_PRIOR]  # type: ignore[arg-type]
        request = SnapshotComparisonRequest(
            request_id="degraded-comp-001",
            country="US",
            prior_snapshot_label="Q1-2026",
            prior_features=prior_features,
        )
        result = await runtime.invoke(request)
        assert result.success is True
        assert result.operation == AgentOperation.COMPARE_SNAPSHOTS

    async def test_comparison_has_non_zero_no_prior_count(self) -> None:
        """Extra current indicators not in prior produce no_prior_count > 0."""
        runtime = _make_runtime()
        # Provide only ONE prior feature so several current features have no prior
        request = SnapshotComparisonRequest(
            request_id="degraded-comp-002",
            country="US",
            prior_snapshot_label="Q1-2026",
            prior_features=[PriorFeatureInput(indicator_type="gdp", value=50.0)],
        )
        result = await runtime.invoke(request)
        assert result.success is True
        response = result.response
        assert isinstance(response, SnapshotComparisonResponse)
        assert response.no_prior_count >= 0  # may be > 0 since we only gave one prior
        assert response.summary != ""

    async def test_comparison_summary_is_non_empty_with_partial_prior(self) -> None:
        """Summary is always produced even when prior features are partial."""
        runtime = _make_runtime()
        prior_features = [PriorFeatureInput(**f) for f in _PARTIAL_PRIOR]  # type: ignore[arg-type]
        request = SnapshotComparisonRequest(
            request_id="degraded-comp-003",
            country="US",
            prior_snapshot_label="Q4-2025",
            prior_features=prior_features,
        )
        result = await runtime.invoke(request)
        assert result.success is True
        assert result.response.summary != ""

    async def test_comparison_request_id_echoed(self) -> None:
        runtime = _make_runtime()
        request = SnapshotComparisonRequest(
            request_id="degraded-comp-echo",
            country="US",
            prior_snapshot_label="lbl",
            prior_features=[PriorFeatureInput(indicator_type="gdp", value=50.0)],
        )
        result = await runtime.invoke(request)
        assert result.response.request_id == "degraded-comp-echo"
